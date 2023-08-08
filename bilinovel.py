#!/usr/bin/python
# -*- coding:utf-8 -*-

from codecs import charmap_encode
from operator import index, itemgetter
from turtle import down
from typing import Container
import requests  # 用来抓取网页的html源码
import random  # 取随机数
from bs4 import BeautifulSoup  # 用于代替正则式 取源码中相应标签中的内容
import time  # 时间相关操作
import os
from rich.progress import track as tqdm
from utils import *
import cv2
import zipfile
import shutil
import numpy as np
import argparse
import re
import pickle

def parse_args():
    """Parse input arguments."""
    parser = argparse.ArgumentParser(description='config')
    parser.add_argument('--book_no', default='2939', type=str)
    parser.add_argument('--volumn_no', default='3', type=int)
    args = parser.parse_args()
    return args


class Editer(object):
    def __init__(self, root_path, book_no='0000', volume_no=1):
        
        # 设置headers是为了模拟浏览器访问 否则的话可能会被拒绝 可通过浏览器获取，这里不用修改
        self.header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.67 Safari/537.36 Edg/87.0.664.47', 'referer': "https://w.linovelib.com/"}

        self.main_page = f'https://w.linovelib.com/novel/{book_no}.html'
        self.cata_page = f'https://w.linovelib.com/novel/{book_no}/catalog'
        self.url_head = 'https://w.linovelib.com'

        main_html = self.get_html(self.main_page)
        bf = BeautifulSoup(main_html, 'html.parser')
        bf = bf.find('div', {'id': 'bookDetailWrapper'})
        self.title = bf.find('h2', {"class": "book-title"}).text
        self.author = bf.find('a').text

        self.img_url_map = dict()
        self.volume_no = volume_no

        self.root_path = root_path
        self.temp_path = os.path.join(self.root_path,  'temp_'+ self.title + '_' + str(self.volume_no))
        os.makedirs(self.temp_path, exist_ok=True)
        self.epub_path = os.path.join(self.root_path,  'epub')
        os.makedirs(self.epub_path, exist_ok=True)

        self.text_path = os.path.join(self.temp_path, 'OEBPS/Text')
        os.makedirs(self.text_path, exist_ok=True)

        self.img_path = os.path.join(self.temp_path,  'OEBPS/Images')
        os.makedirs(self.img_path, exist_ok=True)

    """
    获取html文档内容
    """
    def get_html(self, url, is_gbk=False):
        while True:
            try:
                req = requests.get(url=url, headers=self.header)
                if is_gbk:
                    req.encoding = 'GBK'       #这里是网页的编码转换，根据网页的实际需要进行修改，经测试这个编码没有问题
                break
            except Exception as e:
                print('3', e)
                time.sleep(random.choice(range(5, 10)))
        return req.text
    
    def get_html_img(self, url):
        while True:
            try:
                req=requests.get(url, headers=self.header, timeout=5)
                break
            except Exception as e:
                print('3', e)
                time.sleep(random.choice(range(5, 10)))
        return req.content
    
    def get_index_url(self):
        cata_html = self.get_html(self.cata_page, is_gbk=False)
        cata_html = restore_chars(cata_html)
        bf = BeautifulSoup(cata_html, 'html.parser')
        chap_html_list = bf.find('ol', {'id': 'volumes'}).find_all('li')
        volume = {}
        volume_array = 0
        name = ''
        img_url = ''
        chap_urls = []
        chap_names = []
        for chap_html in chap_html_list:
            if str(chap_html).startswith('<li class="chapter-bar chapter-li">'):
                volume_array += 1
                if volume_array==self.volume_no:
                    name = chap_html.text
            elif volume_array==self.volume_no:
                if str(chap_html).startswith('<li class="chapter-li jsChapter">'):
                    url = self.url_head + chap_html.find('a').get('href')
                    if chap_html.text == '插图':
                        img_url = url
                    else:
                        chap_names.append(chap_html.text)
                        chap_urls.append(url)
        volume = {'name': name, 'chap_names': chap_names, 'chap_urls':chap_urls, 'img_url': img_url}
        return volume

    def get_page_text(self, content_html):
        bf = BeautifulSoup(content_html, 'html.parser')
        text = str(bf.find('div', {'id': 'acontent'}))
        img_urlre_list = re.findall(r"<img.*?/>", text)
        for img_urlre in img_urlre_list:
            img_url = re.search(r'src="(.*?)"', img_urlre).group(1).replace('img1', 'img3')
            text = text.replace('<br/>\n' + img_urlre +'\n<br/>', img_urlre)
            if not img_url in self.img_url_map:
                self.img_url_map[img_url] = str(len(self.img_url_map)).zfill(2)
            ################################图片名占位符, 没有换行情况下加入换行，独自占用一行
            img_symbol = f'[img:{self.img_url_map[img_url]}]'
            if '00' in img_symbol:
                text = text.replace(img_urlre, '')
            else:
                text = text.replace(img_urlre, img_symbol)
                symbol_index = text.index(img_symbol)
                if text[symbol_index-1] != '\n':
                    text = text[:symbol_index] + '\n' + text[symbol_index:]
        bf = BeautifulSoup(text, 'html.parser')
        text = bf.find('div', {'id': 'acontent'}).text[:-1]
        text = restore_chars(text)
        return text
    
    def get_chap_text(self, url):
        chap_no = url.split('/')[-1].strip('.html')
        text_chap = ''
        while chap_no in url:
            print(url)
            content_html = self.get_html(url, is_gbk=False)
            text = self.get_page_text(content_html)
            text_chap += text
            url = self.url_head + re.search(r'nextpage="(.*?)"', content_html).group(1) 
        return text_chap
    
    def get_text(self, volume):
        img_url = volume['img_url']
        img_chap_name = '彩插'
        if img_url != '':
            text = self.get_chap_text(img_url)
            text_html = text2htmls(img_chap_name, text)
            textfile = self.text_path + '/color.xhtml'
            with open(textfile, 'w+', encoding='utf-8') as f:
                f.writelines(text_html)

        chap_names, chap_urls = volume['chap_names'], volume['chap_urls']
        for chap_no, (chap_name, chap_url) in enumerate(zip(chap_names, chap_urls)):
            print(chap_name)
            text = self.get_chap_text(chap_url)
            text_html = text2htmls(chap_name, text) 
            textfile = self.text_path + f'/{str(chap_no).zfill(2)}.xhtml'
            with open(textfile, 'w+', encoding='utf-8') as f:
                f.writelines(text_html)

    def buffer(self, volume):
        filename = 'buffer.pkl'
        filepath = os.path.join(self.temp_path, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'rb') as f:
                volume, self.img_url_map = pickle.load(f)
        else:
            with open(filepath, 'wb') as f:
                pickle.dump((volume ,self.img_url_map), f)
        return volume
    
    def is_buffer(self):
        filename = 'buffer.pkl'
        filepath = os.path.join(self.temp_path, filename)
        return os.path.isfile(filepath)

    def get_image(self):
        img_path = self.img_path
        for img_url, img_name in tqdm(self.img_url_map.items()):
            # print(img_url)
            content = self.get_html_img(img_url)
            with open(img_path+f'/{img_name}.jpg', 'wb') as f:
                f.write(content) #写入二进制内容

    def get_cover(self):
        textfile = os.path.join(self.text_path, 'cover.xhtml')
        img_w, img_h = 300, 300
        try:
            imgfile = os.path.join(self.img_path, '00.jpg')
            img = cv2.imread(imgfile)
            img_w, img_h = img.shape[1], img.shape[0]
        except:
            pass
        img_htmls = get_cover_html(img_w, img_h)
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(img_htmls)

    def get_toc(self, volume):
        toc_htmls = get_toc_html(self.title, volume["chap_names"])
        textfile = self.temp_path + '/OEBPS/toc.ncx'
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(toc_htmls)

    def get_content(self, volume):
        num_chap = len(volume["chap_names"])
        num_img = len(os.listdir(self.img_path))
        content_htmls = get_content_html(self.title + '-' + volume['name'], self.author, num_chap, num_img, volume)
        textfile = self.temp_path + '/OEBPS/content.opf'
        with open(textfile, 'w+', encoding='utf-8') as f:
            f.writelines(content_htmls)

    def get_epub_head(self):
        mimetype = 'application/epub+zip'
        mimetypefile = self.temp_path + '/mimetype'
        with open(mimetypefile, 'w+', encoding='utf-8') as f:
            f.write(mimetype)
        metainf_folder = os.path.join(self.temp_path, 'META-INF')
        os.makedirs(metainf_folder, exist_ok=True)
        container = metainf_folder + '/container.xml'
        container_htmls = get_container_html()
        with open(container, 'w+', encoding='utf-8') as f:
            f.writelines(container_htmls)

    def get_epub(self):
        os.remove(os.path.join(self.temp_path, 'buffer.pkl'))
        epub_file = self.epub_path + '/' + self.title + '-' + volume['name'] + '.epub'
        with zipfile.ZipFile(epub_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(self.temp_path):
                fpath = dirpath.replace(self.temp_path,'') #这一句很重要，不replace的话，就从根目录开始复制
                fpath = fpath and fpath + os.sep or ''#这句话理解我也点郁闷，实现当前文件夹以及包含的所有文件的压缩
                for filename in filenames:
                    zf.write(os.path.join(dirpath, filename), fpath+filename)
        shutil.rmtree(self.temp_path)
        return epub_file
    
    def check_volume(self, volume):
        error_nos = []
        if 'javascript' in volume['img_url'] or 'cid' in volume['img_url']:
            volume['img_url'] = input(f'章节\"插图\"连接有误，请手动输入该章节链接:')
        for url_no, url in enumerate(volume['chap_urls']):
            if 'javascript' in url or 'cid' in url:
                error_nos.append(url_no)
        chap_names = volume['chap_names']
        for url_no in error_nos:
            volume['chap_urls'][url_no] = input(f'章节\"{chap_names[url_no]}\"连接有误，请手动输入该章节链接:')
        return volume

if __name__=='__main__':
    args = parse_args()
    # color_page_num = args.color_page
    editer = Editer(root_path='out', book_no=args.book_no, volume_no=args.volumn_no)

    print('正在获取书籍信息....')
    volume = editer.get_index_url()
    print(editer.title + '-' + volume['name'], editer.author)

    if not editer.is_buffer():
        print('正在下载文本....')
        volume = editer.check_volume(volume)
        editer.get_text(volume)
        editer.buffer(volume)
    else:
        print('检测到文本文件，直接下载插图')
        volume = editer.buffer(volume)

    print('正在下载插图....')
    editer.get_image()
    
    print('正在编辑元数据....')
    editer.get_cover()
    editer.get_toc(volume)
    editer.get_content(volume)
    editer.get_epub_head()

    print('正在生成电子书....')
    epub_file = editer.get_epub()
    print('生成成功！', '电子书路径【', epub_file, '】')
    
