import urllib
import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config_sample
from utility import utility_convert

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

# 等待页面元素加载
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep

import json
import math
import logging
import datetime

import xml.etree.ElementTree as ET

from requests.exceptions import ReadTimeout, ConnectionError

import patoolib # 解压压缩文件
import shutil   # 删除目录下所有文件，包括该目录

loggerBingQi = logging.getLogger('中国兵器工业集团有限公司--爬取数据')
loggerBingQi.setLevel(logging.DEBUG)
#定义函数处理 中国兵器工业集团有限公司 网站
def dealURLofBingQi(baseUrl, key, keyList):
    # 连接mongoDB
    db = MongoClient(host=config_sample.mongodb_host, port=config_sample.mongodb_port, username=config_sample.mongodb_username,
                     password=config_sample.mongodb_password)[config_sample.mongodb_db_name]
    collection = db.result_data
    headers = {
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    pageNum = 1
    requestURL = baseUrl + key + '&style=1&webid=1&&p=' + str(pageNum)
    flag = 0
    while flag < 3:
        try:
            r = requests.get(requestURL, headers=headers)
            r.encoding = r.apparent_encoding
            basesoup = BeautifulSoup(r.text, 'lxml')
            basesoup.prettify()
            titleNode = basesoup.find(attrs={'class': 'js-result'})
            titleList = titleNode.find_all(attrs={'class': 'jsearchblue'})
            flag = 3
        except (ReadTimeout, ConnectionError) as e:
            loggerBingQi.error(e)
            flag += 1
            if flag == 3:
                loggerBingQi.info('Sleeping...')
                sleep(60 * 10)
                flag = 0
            print('重新请求网页中...')
            sleep(10+20*flag)
    while titleList:
        for table in titleList:
            a = table.find('a')
            articleURL = a['href']
            flag = 0
            while flag < 3:
                try:
                    article = requests.get(articleURL, headers=headers)
                    flag = 3
                    article.encoding = article.apparent_encoding
                    articleSoup = BeautifulSoup(article.text, 'lxml')
                    articleSoup.prettify()
                    # 保存html页面源码
                    htmlSource = article.text

                    # html的URL地址
                    htmlURL = article.url

                    # 保存文章标题信息
                    articleTitle = a.text

                    # 保存文章发布时间
                    if articleSoup.find(attrs={'class': 'box4'}):
                        if articleSoup.find(attrs={'class': 'box4'}).find(name='td', align='right', valign='middle'):
                            timeNode = articleSoup.find(attrs={'class': 'box4'}).find(name='td', align='right', valign='middle')
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')
                    else:
                        publishTime = ''

                    # 保存文章位置
                    articleLocation = ''
                    if articleSoup.find(attrs={'class': 'gg'}):
                        articleLocList = articleSoup.find(attrs={'class': 'gg'}).find_all('a')
                        for articleLocNode in articleLocList:
                            articleLocation += '>'+articleLocNode.text


                    # 保存文章正文
                    if articleSoup.find(attrs={'class': 'box4'}):
                        articleText = articleSoup.find(attrs={'class': 'box4'}).text


                    # 判断标题或正文是否含有关键词
                    matched_keywords_list = []
                    for each_keyword in keyList:
                        if each_keyword in articleTitle or each_keyword in articleText:
                            matched_keywords_list.append(each_keyword)
                    if matched_keywords_list.__len__() > 0:
                        if collection.find({'url': articleURL}).count() == 0:
                            item = {
                                'url': htmlURL,
                                'title': articleTitle,
                                'date': publishTime,
                                'site': '央企及地方重点国企官网-央企-中国兵器工业集团有限公司',
                                'keyword': matched_keywords_list,
                                'tag_text': articleLocation,
                                'content': articleText,
                                'html': htmlSource
                            }
                            print('#insert_new_article: ' + articleTitle)
                            result = collection.insert_one(item)
                            print(result.inserted_id)
                        else:
                            print('#article already exits:' + articleTitle)
                    else:
                        print('#no keyword matched: ' + articleTitle)

                except (ReadTimeout, ConnectionError) as e:
                    loggerBingQi.error(e)
                    flag += 1
                    if flag == 3:
                        print('重新请求失败')
                        loggerBingQi.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    print('重新请求网页中...')
                    sleep(10+20*flag)

        print('pageNum: ' + str(pageNum))
        pageNum += 1
        requestURL = baseUrl + key + '&style=1&webid=1&&p=' + str(pageNum)
        flag = 0
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'js-result'})
                titleList = titleNode.find_all(attrs={'class': 'jsearchblue'})
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                loggerBingQi.error(e)
                flag += 1
                if flag == 3:
                    loggerBingQi.info('Sleeping...')
                    sleep(60 * 10)
                    flag = 0
                print('重新请求网页中...')
                sleep(10 + 20 * flag)

    print("finish")
    return;

if __name__=="__main__":
    keyWordList = ['国企改革','国企改制','国企混改','国有企业改革','国有企业改制']
    print('开始爬取中国兵器工业集团有限公司')
    for keyWord in keyWordList:
        print('关键词：'+keyWord)
        dealURLofBingQi('http://www.norincogroup.com.cn/jsearch/search.do?appid=1&ck=x&imageField=&od=0&pagemode=result&pos=title%2Ccontent&q=', keyWord, keyWordList)
