import urllib
import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config_sample
from utility import utility_convert

#引入代理
from getProxy import getOneProxy

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


#定义函数处理 国家能源投资集团有限责任公司
def delUrlofGuoNengTou(baseUrl, key):
    loggerGuoNengTou = logging.getLogger('国家能源投资集团有限责任公司--爬取数据')
    loggerGuoNengTou.setLevel(logging.DEBUG)
    # 连接mongoDB
    db = MongoClient(host=config_sample.mongodb_host, port=config_sample.mongodb_port, username=config_sample.mongodb_username,
                     password=config_sample.mongodb_password)[config_sample.mongodb_db_name]
    collection = db.result_data
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    pageNum = 1
    requestURL = baseUrl + key + '&page=' + str(pageNum)
    flag = 0
    while flag < 3:
        try:
            r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
            r.encoding = r.apparent_encoding
            basesoup = BeautifulSoup(r.text, 'lxml')
            basesoup.prettify()
            if basesoup.find(attrs={'class': 'con_list'}):
                titleNode = basesoup.find(attrs={'class': 'con_list'})
            elif basesoup.find(attrs={'class': 'gclist_ul listnew'}):
                titleNode = basesoup.find(attrs={'class': 'gclist_ul listnew'})
            titleList = titleNode.find_all('li')
            flag = 3
        except (ReadTimeout, ConnectionError) as e:
            loggerGuoNengTou.error(e)
            flag += 1
            if flag == 3:
                loggerGuoNengTou.info('Sleeping...')
                sleep(60 * 10)
                flag = 0
            print('重新请求网页中...')
            sleep(10+20*flag)

    while titleList:
        for table in titleList:
            a = table.find(name='a', attrs={'class': 'gccon_title'})
            #找到文章链接
            articleURL = a['href']

            flag = 0
            while flag < 3:
                try:
                    article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
                    flag = 3
                    article.encoding = article.apparent_encoding
                    articleSoup = BeautifulSoup(article.text, 'lxml')
                    articleSoup.prettify()
                    # 保存html页面源码
                    htmlSource = article.text

                    # html的URL地址
                    htmlURL = article.url

                    # 保存文章标题信息
                    if articleSoup.head.find('title') is None:
                        articleTitle = ''
                    else: articleTitle = articleSoup.head.find('title').text

                    # 保存文章发布时间
                    if basesoup.find(attrs={'class':'gc_date'}):
                        timeNode = basesoup.find(attrs={'class':'gc_date'})
                        publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                    # 保存文章位置
                    articleLocation = ''
                    if articleSoup.find(attrs={'class': 'position'}):
                        articleLocationList = articleSoup.find(attrs={'class': 'position'}).find_all('a')
                        for articleLocationNode in articleLocationList:
                            articleLocation += '>'+articleLocationNode.text
                    elif articleSoup.find(attrs={'class': 'm h_30'}):
                        articleLocationList = articleSoup.find(attrs={'class': 'm h_30'}).find_all('a')
                        for articleLocationNode in articleLocationList:
                            articleLocation += '>'+articleLocationNode.text

                    # 保存文章正文
                    if articleSoup.find(attrs={'id': 'content'}):
                        articleText = articleSoup.find(attrs={'id': 'content'}).text

                    # 判断标题或正文是否含有关键词
                    matched_keywords_list = []
                    for each_keyword in config_sample.keywords_list:
                        if each_keyword in articleTitle or each_keyword in articleText:
                            matched_keywords_list.append(each_keyword)
                    if matched_keywords_list.__len__() > 0:
                        if collection.find({'url': articleURL}).count() == 0:
                            item = {
                                'url': htmlURL,
                                'title': articleTitle,
                                'date': publishTime,
                                'site': '央企及地方重点国企官网-央企-国家能源投资集团有限责任公司',
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
                    loggerGuoNengTou.error(e)
                    flag += 1
                    if flag == 3:
                        print('重新请求失败')
                        loggerGuoNengTou.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    print('重新请求网页中...')
                    sleep(10+20*flag)

        print('pageNum: ' + str(pageNum))
        pageNum += 1

        #开始请求下一页关键词搜索结果
        requestURL = baseUrl + key + '&page=' + str(pageNum)
        flag = 0
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                if basesoup.find(attrs={'class': 'con_list'}):
                    titleNode = basesoup.find(attrs={'class': 'con_list'})
                elif basesoup.find(attrs={'class': 'gclist_ul listnew'}):
                    titleNode = basesoup.find(attrs={'class': 'gclist_ul listnew'})
                titleList = titleNode.find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                loggerGuoNengTou.error(e)
                flag += 1
                if flag == 3:
                    loggerGuoNengTou.info('Sleeping...')
                    sleep(60 * 10)
                    flag = 0
                print('重新请求网页中...')
                sleep(10+20*flag)

    print("finished")
    return

#中国国新控股有限责任公司
def dealURLofGuoXinKongGu():
    loggerGuoXin = logging.getLogger('中国国新控股有限责任公司--爬取数据')
    loggerGuoXin.setLevel(logging.DEBUG)
    # 连接mongoDB
    db = MongoClient(host=config_sample.mongodb_host, port=config_sample.mongodb_port, username=config_sample.mongodb_username,
                     password=config_sample.mongodb_password)[config_sample.mongodb_db_name]
    collection = db.result_data
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }

    requestURL = 'https://www.crhc.cn/sitesearch/search.jsp'


    for key in config_sample.keywords_list:
        pageNum = 1
        flag = 0
        print('开始爬取中国国新控股有限责任公司')
        print('关键词：' + key)
        #构造POST方法请求数据：
        data = {'SType': '1', 'searchColumn': 'all',
                'preSWord': 'doctitle/3,docContent/1+=('+key+') and (channelid=63 or channelid=64 or channelid=65 or channelid=68 or channelid=69 or channelid=72)',
                'sword': key, 'page': str(pageNum)}
        while flag < 3:
            try:
                r = requests.post(requestURL, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
                titleList = titleNode.find_all('li')
                flag = 3
                #记录搜索结果的总页面数量
                totalPage = int(basesoup.find_all('strong')[1].text)
            except (ReadTimeout, ConnectionError) as e:
                loggerGuoXin.error(e)
                flag += 1
                if flag == 3:
                    loggerGuoXin.info('Sleeping...')
                    sleep(60 * 10)
                flag = 0
                print('重新请求网页中...')
                sleep(10 + 20 * flag)
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
                        publishTime = re.search('(\d+.\d+.\d+)', table.find('span').text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'gu_current'}):
                            articleLocList = articleSoup.find(attrs={'class': 'gu_current'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        if articleSoup.find(attrs={'class': 'Custom_UnionStyle'}):
                            articleText = articleSoup.find(attrs={'class': 'Custom_UnionStyle'}).text

                        # 判断标题或正文是否含有关键词
                        matched_keywords_list = []
                        for each_keyword in config_sample.keywords_list:
                            if each_keyword in articleTitle or each_keyword in articleText:
                                matched_keywords_list.append(each_keyword)
                        if matched_keywords_list.__len__() > 0:
                            if collection.find({'title': articleTitle}).count() == 0:
                                item = {
                                    'url': htmlURL,
                                    'title': articleTitle,
                                    'date': publishTime,
                                    'site': '央企及地方重点国企官网-央企-中国国新控股有限责任公司',
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
                        loggerGuoXin.error(e)
                        flag += 1
                        if flag == 3:
                            print('重新请求失败')
                            loggerGuoXin.info('Sleeping...')
                            sleep(60 * 10)
                            flag = 0
                        print('重新请求网页中...')
                        sleep(10 + 20 * flag)

            print('pageNum: ' + str(pageNum))
            pageNum += 1

            if pageNum > totalPage:
                break

            flag = 0
            requestURL = 'https://www.crhc.cn/sitesearch/search.jsp'
            data = {'SType': '1', 'searchColumn': 'all',
                    'preSWord': 'doctitle/3,docContent/1+=(' + key + ') and (channelid=63 or channelid=64 or channelid=65 or channelid=68 or channelid=69 or channelid=72)',
                    'sword': key, 'page': str(pageNum)}
            while flag < 3:
                try:
                    r = requests.post(requestURL, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    loggerGuoXin.error(e)
                    flag += 1
                    if flag == 3:
                        loggerGuoXin.info('Sleeping...')
                        sleep(60 * 10)
                    flag = 0
                    print('重新请求网页中...')
                    sleep(10 + 20 * flag)
    print("finish")
    return;

#中国铁路物资集团有限公司
def dealURLofTieLuWuZi():

    #构造POST请求关键词的编码字典
    dataDict={'国企改革': '%B9%FA%C6%F3%B8%C4%B8%EF', '国企改制': '%B9%FA%C6%F3%B8%C4%D6%C6',
              '国企混改': '%B9%FA%C6%F3%BB%EC%B8%C4', '国有企业改革': '%B9%FA%D3%D0%C6%F3%D2%B5%B8%C4%B8%EF',
              '国有企业改制': '%B9%FA%D3%D0%C6%F3%D2%B5%B8%C4%D6%C6'}

    loggerTieLu = logging.getLogger('中国铁路物资集团有限公司--爬取数据')
    loggerTieLu.setLevel(logging.DEBUG)
    # 连接mongoDB
    db = MongoClient(host=config_sample.mongodb_host, port=config_sample.mongodb_port, username=config_sample.mongodb_username,
                     password=config_sample.mongodb_password)[config_sample.mongodb_db_name]
    collection = db.result_data
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }

    baseUrl = 'https://www.crmsc.com.cn/mark_search.asp？Page='

    for key in config_sample.keywords_list:
        pageNum = 1
        flag = 0
        requestURL = baseUrl + str(pageNum)
        print('开始爬取中国铁路物资集团有限公司')
        print('关键词：' + key)
        # 构造POST方法请求数据：
        data = {'key': dataDict[key]}

        while flag < 3:
            try:
                r = requests.post(requestURL, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
                titleList = titleNode.find_all('li')
                flag = 3
                # 记录搜索结果的总页面数量
                totalPage = int(basesoup.find_all('strong')[1].text)
            except (ReadTimeout, ConnectionError) as e:
                loggerGuoXin.error(e)
                flag += 1
                if flag == 3:
                    loggerGuoXin.info('Sleeping...')
                    sleep(60 * 10)
                flag = 0
                print('重新请求网页中...')
                sleep(10 + 20 * flag)
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
                        publishTime = re.search('(\d+.\d+.\d+)', table.find('span').text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'gu_current'}):
                            articleLocList = articleSoup.find(attrs={'class': 'gu_current'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        if articleSoup.find(attrs={'class': 'Custom_UnionStyle'}):
                            articleText = articleSoup.find(attrs={'class': 'Custom_UnionStyle'}).text

                        # 判断标题或正文是否含有关键词
                        matched_keywords_list = []
                        for each_keyword in config_sample.keywords_list:
                            if each_keyword in articleTitle or each_keyword in articleText:
                                matched_keywords_list.append(each_keyword)
                        if matched_keywords_list.__len__() > 0:
                            if collection.find({'title': articleTitle}).count() == 0:
                                item = {
                                    'url': htmlURL,
                                    'title': articleTitle,
                                    'date': publishTime,
                                    'site': '央企及地方重点国企官网-央企-中国国新控股有限责任公司',
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
                        loggerGuoXin.error(e)
                        flag += 1
                        if flag == 3:
                            print('重新请求失败')
                            loggerGuoXin.info('Sleeping...')
                            sleep(60 * 10)
                            flag = 0
                        print('重新请求网页中...')
                        sleep(10 + 20 * flag)

            print('pageNum: ' + str(pageNum))
            pageNum += 1

            #如果查询页码超出最大可查询页码，退出循环，检索下一关键词
            if pageNum > totalPage:
                break

            flag = 0
            requestURL = 'https://www.crhc.cn/sitesearch/search.jsp'
            data = {'SType': '1', 'searchColumn': 'all',
                    'preSWord': 'doctitle/3,docContent/1+=(' + key + ') and (channelid=63 or channelid=64 or channelid=65 or channelid=68 or channelid=69 or channelid=72)',
                    'sword': key, 'page': str(pageNum)}
            while flag < 3:
                try:
                    r = requests.post(requestURL, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    loggerGuoXin.error(e)
                    flag += 1
                    if flag == 3:
                        loggerGuoXin.info('Sleeping...')
                        sleep(60 * 10)
                    flag = 0
                    print('重新请求网页中...')
                    sleep(10 + 20 * flag)
    print("finish")
    return;

if __name__ == "__main__":

    #国家能源投资集团有限责任公司
    print('开始爬取国家能源投资集团有限责任公司')
    for keyWord in config_sample.keywords_list:
        print('开始爬取招标采购信息')
        print('关键词：' + keyWord)
        delUrlofGuoNengTou('http://www.dlzb.com/zb/search.php?kw=', keyWord)
    for keyWord in config_sample.keywords_list:
        print('开始爬取中标公示')
        print('关键词：' + keyWord)
        delUrlofGuoNengTou('http://www.dlzb.com/zhongbiao/search.php?kw=', keyWord)

    #中国国新控股有限责任公司
    # #dealURLofGuoXinKongGu()

    dealURLofTieLuWuZi()
