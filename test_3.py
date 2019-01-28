import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config
from utility import utility_convert
import ast
#引入代理
from getProxy import getOneProxy
import json

# 处理pdf文档
from io import StringIO
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage

from selenium.webdriver.common.keys import Keys
from selenium import webdriver

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1440,900')
chrome_options.add_argument('--silent')

from time import sleep

import json
import logging
import os

import tesserocr
from PIL import  Image

import binascii

from requests.exceptions import ReadTimeout, ConnectionError

#配置logging
logger = logging.getLogger('国家、省、市、区、县财政部门网站--爬取数据')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

#45.福建省福州市财政局
def FJFuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    url = 'http://www.wnf.gov.cn/system/resource/code/news/newsearch/createimage.jsp'
    key = '国'
    key.encode('ascii')
    browser = webdriver.Firefox()
    browser.get(url)
    browser.save_screenshot('aaa.png')

    browser.maximize_window()
    browser.set_page_load_timeout(5)
    browser.get_screenshot_a
    # 如果弹出图形验证码
    while basesoup.find('img', src='/system/resource/code/news/newsearch/createimage.jsp'):
        if not os.path.exists('./verify_pic'):  # 没有verify_pic目录
            os.mkdir('./verify_pic')
            os.chdir('./verify_pic')
        if os.path.exists('./verify_pic'):  # 有verify_pic目录
            os.chdir('./verify_pic')
        # 保存验证码截图
        browser.save_screenshot('./screenshot.png')
        pic = browser.find_element_by_css_selector(
            "img['/system/resource/code/news/newsearch/createimage.jsp']")
        left = pic.location['x']
        top = pic.location['y']
        right = left + pic.size['width']
        bottom = top + pic.size['height']
        image = Image.open('./screenshot.png')
        image = image.crop((left, top, right, bottom))
        verifycode = tesserocr.image_to_text(image)
        input = browser.find_element_by_name('searchCodea1320a')
        input.send_keys(verifycode)
        button = browser.find_element_by_css_selector(
            'span[onclick="if(document.a1320a.onsubmit()){document.a1320a.submit()} "]')
        button.click()
        sleep(5)
    if not os.path.exists(
            './verify_pic') and 'verify_pic' not in os.getcwd():  # 没有file_data目录且不在其子目录中
        os.mkdir('./verify_pic')
        os.chdir('./verify_pic')
    if os.path.exists(
            './verify_pic') and 'verify_pic' not in os.getcwd():  # 有file_data目录且不在子目录中
        os.chdir('./verify_pic')
    f = requests.get(url, headers=headers)
    with open('./verifypic.png', "wb") as code:
        code.write(f.content)
    image = Image.open('verifypic.png')
    print (tesserocr.image_to_text(image))

if __name__ == '__main__':
    # 45.福建省福州市财政局
    FJFuzhouCZJ()