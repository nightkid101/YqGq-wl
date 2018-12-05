import urllib3
import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config
from utility import utility_convert

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

def test():
    os.chdir('./file_data')
    utility_convert.convert_doc_to_txt('./太原市发展和改革委员会2016年决算公开.doc')
    # if os.path.exists('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt'):
    #     f = open('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt', encoding='utf-8')
    #     docText = f.read()
    #     articleText += '\n\n\n\附件内容：\n' + docText
    #     f.close()
    # else:
    #     print('无法解析doc文档')




def getFirstTimeFlag(siteid, searchkey):
    if last_time_collection.find({'site': siteid, 'searchkey': searchkey}).count() == 0:
        return 1
    else:
        return 0
def getLastTime(siteid, searchkey, flag):
    if flag==1:
        return None
    else:
        return last_time_collection.find_one({'site': siteid, 'searchkey': searchkey})['last_time']

def getNewLastTime(siteid, searchkey,flag):
    if flag==1:
        return '19000101'
    else:
        return last_time_collection.find_one({'site': siteid, 'searchkey': searchkey})['last_time']

def updateLastTime(siteid,searchkey,Time):
    last_time_collection.update_one({'site': siteid, 'searchkey': searchkey}, {"$set": {"last_time": Time}},True)

#1.河北省石家庄市财政局
def HBShijiazhuangCaizhengju():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://121.28.35.99:10080/search.html?keyword='
    for key in config.keywords_list:

        # #判断是否是第一次爬取本网站本关键词的公告
        quitflag = 0#爬到之前爬过的文档的退出标记
        siteid = '河北省石家庄市财政局'
        first_time_flag = getFirstTimeFlag(siteid,key)#记录是否是第一次爬取这个网站这个关键词的公告
        last_time = getLastTime(siteid,key,first_time_flag)#记录上次爬到的公告时间
        new_last_time = getNewLastTime(siteid,key,first_time_flag)#用于更新本次爬取到的最新公告时间
        #####################################

        pageNum = 1
        flag = 0
        logger.info('开始爬取河北省石家庄市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&keyword2=&time=all&webid=25&fanwei=all&new=0&this_page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('div', attrs={'class':'search-bottom'}).find_all('b')
                totalResults = int(total[1].text)
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class':'result-box'})
                titleList = titleNode.find_all('li')
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    sleep(60 * 10)
                    flag = 0
                logger.info('重新请求网页中...')
                sleep(10 + 20 * flag)
        while titleList:
            for table in titleList:
                a = table.find('a')
                articleURL = a['href']
                count += 1
                flag = 0
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('span', attrs={'style':"color:#999;"}):
                            publishTime = (re.search('(\d+/\d+/\d+)', table.find('span', attrs={'style':"color:#999;"}).text)[0]).replace('/', '')

                        #更新last_time_collection中的last_time字段
                        if publishTime != '':
                            if publishTime > new_last_time:#如果本次爬取的公告时间更新，则更新时间
                                new_last_time = publishTime
                                logger.info('#update last_time for ' + siteid + ': ' + key)
                                updateLastTime(siteid, key, publishTime)
                            if first_time_flag == 0:  # 如果原来爬过这个网站关于这个关键词的公告，且已经爬到上次爬过的数据了，则退出
                                if publishTime < last_time:
                                    quitflag = 1
                                    break
                        ########################################

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'dqwz'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'dqwz'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "dqwz-nr"}):
                            articleText = articleSoup.find('div', attrs={'class': "dqwz-nr"}).text

                        # 判断标题或正文是否含有关键词
                        matched_keywords_list = []
                        for each_keyword in config.keywords_list:
                            if each_keyword in articleTitle or each_keyword in articleText:
                                matched_keywords_list.append(each_keyword)
                        if matched_keywords_list.__len__() > 0:
                            if collection.find({'url': htmlURL}).count() == 0:
                                item = {
                                    'url': htmlURL,
                                    'title': articleTitle,
                                    'date': publishTime,
                                    'site': '国家、省、市、区、县财政部门网站-河北省石家庄市财政局',
                                    'keyword': matched_keywords_list,
                                    'tag_text': articleLocation,
                                    'content': articleText,
                                    'html': htmlSource
                                }
                                logger.info('#insert_new_article: ' + articleTitle)
                                result = collection.insert_one(item)
                                logger.info(result.inserted_id)
                            else:
                                logger.info('#article already exists:' + articleTitle)
                        else:
                            logger.info('#no keyword matched: ' + articleTitle)

                    except (ReadTimeout, ConnectionError) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
                #跳出for循环########
                if quitflag==1:
                    break
                ###################
            logger.info('pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag==1:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&keyword2=&time=all&webid=25&fanwei=all&new=0&this_page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'result-box'})
                    titleList = titleNode.find_all('li')
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return;


if __name__=="__main__":
    test()


