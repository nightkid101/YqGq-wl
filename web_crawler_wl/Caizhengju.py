import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config
from utility import utility_convert
from urllib.parse import quote

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

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1440,900')
chrome_options.add_argument('--silent')
chrome_options.add_argument('lang=zh_CN.UTF-8')
chrome_options.add_argument('user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36')

from time import sleep
import json
import logging
import tesserocr
from PIL import Image


from requests.exceptions import ReadTimeout, ConnectionError

# 连接mongoDB
db = MongoClient(host=config.mongodb_host, port=config.mongodb_port,
                 username=config.mongodb_username,
                 password=config.mongodb_password)[config.mongodb_db_name]
collection = db.result_data
#crawlerCollection记录上次爬取的最新url
crawler = db.crawler

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


#1.河北省石家庄市财政局
def HBShijiazhuangCaizhengju():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://121.28.35.99:10080/search.html?keyword='
    siteURL = 'http://www.sjzcz.gov.cn/'#保存网站主页，用于匹配crawlerCollection的url字段
    for key in config.keywords_list:
        ##################################################
        quitflag = 0#到达之前爬过的网址时的退出标记
        last_updated_url = ''#记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count()>0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        #####################################################
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                #####################################
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
            logger.info('河北省石家庄市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag==3:
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
    return

#2.河北省张家口市财政局
def HBZhangjiakouCaizhengju():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.zjkcz.gov.cn/Search.asp?ModuleName=article&ChannelID=0&Field=Title&Keyword='
    siteURL = 'http://www.zjkcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取河北省张家口市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                key = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%')
                requestURL = baseURL + key + '&ClassID=0&SpecialID=0&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('td', attrs={'valign':'top','width':'790','class':'bian'})
                if '没有或没有找到任何信息' in titleNode.text:
                    titleList = []
                    break
                titleList = titleNode.find_all('td', attrs={'width':"96%", 'height':"30", 'align':"left", 'valign':"top"})
                total = basesoup.find('div', attrs={'class': 'show_page'})
                totalResults = int(total.find('b').text)
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
                if 'http:' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.zjkcz.gov.cn'+a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL,headers=headers)
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
                        publishTime = (re.search('(\d+-\d+-\d+)', table.text)[0]).replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'width':"628", 'align':"right"}):
                            articleLocation = articleSoup.find('td', attrs={'width':"628", 'align':"right"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td', attrs={'class': "td_article_m",'id':'ArticleContent'}):
                            articleText = articleSoup.find('td', attrs={'class': "td_article_m",'id':'ArticleContent'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-河北省张家口市财政局',
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
            logger.info('河北省张家口市财政局-'+key+ '-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag==3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&ClassID=0&SpecialID=0&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('td', attrs={'valign': 'top', 'width': '790', 'class': 'bian'})
                    titleList = titleNode.find_all('td', attrs={'width': "96%", 'height': "30", 'align': "left",
                                                                'valign': "top"})
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

#3.山西省太原市财政局
def SXTaiyuanCZJ():
    headers1 = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
        'Content-Type': 'application/json;charset=UTF-8',
        'Host': 'czxx.taiyuan.gov.cn'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    requestURL = 'http://czxx.taiyuan.gov.cn//r_search'
    siteURL = 'http://czxx.taiyuan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省太原市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                data = {"fl": "ID,__HTML,TITLE,CONTENT,CHANNEL_ROOT,CHANNEL_PATH,MOD_TIME,URL,#internal_id#",
                        "hl": "true",
                        "hl.fl": "TITLE,CONTENT", "hl.id": "ID",
                        "hl.simple.pre": "<span style='color:red; font-size:16px;'>",
                        "hl.simple.post": "</span>", "facet": "true", "facet.mincount": "1",
                        "facet.field": "CHANNEL_ROOT",
                        "debugQuery": "false", "q": "TITLE:" + key + " OR CONTENT:" + key + " OR ATTA_CONTENT:" + key,
                        "fq": "SITE_ID:19 AND STATUS:4", "start": str(count), "rows": "10", "sort": "score desc",
                        "defType": "edismax",
                        "pf": "CONTENT TITLE ATTA_CONTENT", "qf": "ATTA_CONTENT^0.7 CONTENT^0.9 TITLE^1.1",
                        "bf": "recip(ms(NOW,MOD_TIME),3.16e-11,1,1)^3", "extKey": key, "token": "123"}
                datadump = json.dumps(data)
                r = requests.post(requestURL, headers=headers1, data=datadump)
                r.encoding = r.apparent_encoding
                basesoup = json.loads(r.text)
                flag = 3
                totalResults = int(basesoup['data']['response']['data']['response']['numFound'])
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup['data']['response']['data']['response']['data']
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
                if 'http:' in table['URL']:
                    articleURL = table['URL']
                else:
                    articleURL = 'http://czxx.taiyuan.gov.cn'+ table['URL']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        articleTitle = BeautifulSoup(table['TITLE']).text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('p',attrs={'class':'explain'}):
                            if articleSoup.find('p',attrs={'class':'explain'}).find('em'):
                                publishTime = articleSoup.find('p',attrs={'class':'explain'}).find('em').text.replace('-', '')

                        # 保存文章位置
                        articleLocation = table['CHANNEL_PATH']

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'Zoom'}).text

                        try:
                            # 检查是否存在附件
                            if articleSoup.find('div', attrs={'id': 'Zoom'}).find('a'):
                                hrefList = articleSoup.find('div', attrs={'id': 'Zoom'}).find_all('a')
                                for href in hrefList:
                                    docText = ''
                                    if '.doc' in href['href']:
                                        docID = href.text
                                        if not os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                            os.mkdir('./file_data')
                                            os.chdir('./file_data')
                                        if os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                            os.chdir('./file_data')
                                        if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                            f = requests.get('http://czxx.taiyuan.gov.cn'+href['href'])
                                            with open('./' + docID, "wb") as code:
                                                code.write(f.content)
                                            logger.info('.doc download over')
                                        # 解析doc文件
                                        utility_convert.convert_doc_to_txt('./' + docID)
                                        if os.path.exists('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt'):
                                            f = open('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt', encoding='utf-8')
                                            docText = f.read()
                                            articleText += '\n\n\n\附件内容：\n' + docText
                                            f.close()
                                        else:
                                            logger.info('无法解析doc文档')

                                    elif '.docx' in href['href']:
                                        docID = href.text
                                        if not os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                            os.mkdir('./file_data')
                                            os.chdir('./file_data')
                                        if os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                            os.chdir('./file_data')
                                        if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                            f = requests.get('http://czxx.taiyuan.gov.cn'+href['href'])
                                            with open('./' + docID, "wb") as code:
                                                code.write(f.content)
                                            logger.info('.docx download over')
                                        # 解析docx文件
                                        utility_convert.convert_doc_to_txt('./' + docID)
                                        if os.path.exists('./' + docID.rstrip('.docx') + '/' + docID.rstrip('.docx') + '.txt'):
                                            f = open('./' + docID.rstrip('.docx') + '/' + docID.rstrip('.docx') + '.txt', encoding='utf-8')
                                            docText = f.read()
                                            articleText += '\n\n\n\附件内容：\n' + docText
                                            f.close()
                                        else:
                                            logger.info('无法解析docx文档')

                                    elif '.pdf' in href['href']:
                                        docID = href.text
                                        if not os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                            os.mkdir('./file_data')
                                            os.chdir('./file_data')
                                        if os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                            os.chdir('./file_data')
                                        if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                            f = requests.get('http://czxx.taiyuan.gov.cn' + href['href'])
                                            with open('./' + docID, "wb") as code:
                                                code.write(f.content)
                                            logger.info('.pdf download over')
                                        # 解析pdf文件
                                        docText=utility_convert.convert_pdf_to_txt('./' + docID)
                                        if docText:
                                            articleText += '\n\n\n\附件内容：\n'
                                            for docNode in docText:
                                                articleText += docNode
                                    elif '.rar' in href['href']:
                                        docID = href.text
                                        if not os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                            os.mkdir('./file_data')
                                            os.chdir('./file_data')
                                        if os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                            os.chdir('./file_data')
                                        if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                            f = requests.get('http://czxx.taiyuan.gov.cn' + href['href'])
                                            with open('./' + docID, "wb") as code:
                                                code.write(f.content)
                                            logger.info('.rar download over')
                                        # 解析.rar文件
                                        utility_convert.convert_rar_to_txt('./' + docID)
                                        if os.path.exists(
                                                './' + docID.rstrip('.rar') + '/' + docID.rstrip('.rar') + '.txt'):
                                            f = open(
                                                './' + docID.rstrip('.rar') + '/' + docID.rstrip('.rar') + '.txt',
                                                encoding='utf-8')
                                            docText = f.read()
                                            articleText += '\n\n\n\附件内容：\n' + docText
                                            f.close()
                                        else:
                                            logger.info('无法解析rar文档')

                        except Exception as e:
                            logger.error(e)
                            logger.info('处理附件内容失败')
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
                                    'site': '国家、省、市、区、县财政部门网站-山西省太原市财政局',
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
            logger.info('山西省太原市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    data = {"fl": "ID,__HTML,TITLE,CONTENT,CHANNEL_ROOT,CHANNEL_PATH,MOD_TIME,URL,#internal_id#",
                            "hl": "true",
                            "hl.fl": "TITLE,CONTENT", "hl.id": "ID",
                            "hl.simple.pre": "<span style='color:red; font-size:16px;'>",
                            "hl.simple.post": "</span>", "facet": "true", "facet.mincount": "1",
                            "facet.field": "CHANNEL_ROOT",
                            "debugQuery": "false",
                            "q": "TITLE:" + key + " OR CONTENT:" + key + " OR ATTA_CONTENT:" + key,
                            "fq": "SITE_ID:19 AND STATUS:4", "start": str(count), "rows": "10", "sort": "score desc",
                            "defType": "edismax",
                            "pf": "CONTENT TITLE ATTA_CONTENT", "qf": "ATTA_CONTENT^0.7 CONTENT^0.9 TITLE^1.1",
                            "bf": "recip(ms(NOW,MOD_TIME),3.16e-11,1,1)^3", "extKey": key, "token": "123"}
                    datadump = json.dumps(data)
                    r = requests.post(requestURL, headers=headers1, data=datadump)
                    r.encoding = r.apparent_encoding
                    basesoup = json.loads(r.text)
                    flag = 3
                    titleList = basesoup['data']['response']['data']['response']['data']
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

#4.山西省朔州市财政局
def SXShuozhouCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
                #'Host': 'search.shuozhou.gov.cn',
                'Referer': 'http://czj.shuozhou.gov.cn/'
    }
    headers1 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'czj.shuozhou.gov.cn',
        'Referer': 'http://czj.shuozhou.gov.cn/czdt/201811/t20181109_221894.html'
    }
    baseURL = 'http://search.shuozhou.gov.cn/was5/web/search?page='
    siteURL = 'http://czj.shuozhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省朔州市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&channelid=217807&searchword=' + key + '&keyword=' + key + '&token=16.1427427910002.50&perpage=10&outlinepage=10&andsen=&total=&orsen=&exclude=&searchscope=&timescope=&timescopecolumn=&orderby=-DOCRELTIME'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('td',attrs={'class':'searchresult'})
                if '很抱歉，没有找到和您的查询相匹配的结果。' in titleNode.text:
                    titleList = []
                    break
                total = basesoup.find('div', attrs={'class': 'outline'})
                totalResults = int(re.search('约(\d+)条',total.text)[1])
                titleList = titleNode.find_all('td', attrs={'style':"color:blue;"})
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers1)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
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
                        if articleSoup.find('table', attrs={'class':"fbxx", 'id':"tb_general"}):
                            publishTime = (re.search('(\d+-\d+-\d+)', articleSoup.find('table', attrs={'class':"fbxx", 'id':"tb_general"}).text)[0]).replace('-', '')
                        elif articleSoup.find('td', attrs={'class':"f14"}):
                            publishTime = articleSoup.find('td', attrs={'class':"f14"}).text.replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'b_hh'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'b_hh'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山西省朔州市财政局',
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
            logger.info('山西省朔州市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=217807&searchword=' + key + '&keyword=' + key + '&token=16.1427427910002.50&perpage=10&outlinepage=10&andsen=&total=&orsen=&exclude=&searchscope=&timescope=&timescopecolumn=&orderby=-DOCRELTIME'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('td', attrs={'class': 'searchresult'})
                    titleList = titleNode.find_all('td', attrs={'style': "color:blue;"})
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

#5.山西省沂州市财政局
def SXYizhouCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://czj.sxxz.gov.cn/was5/web/search?searchscope=&timescope=&timescopecolumn=&orderby=-docreltime&channelid=267445&andsen=&total=&orsen=&exclude=&lanmu=&page='
    siteURL = 'http://czj.sxxz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省沂州市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&searchword=' + key + '&perpage=&token=0.1450753920719.14&templet='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                totalResults = int(basesoup.find('li', attrs={'class':'resul-tt-font'}).find('span').text)
                if totalResults<=0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': 'search-result-inner-box'})
                titleList = titleNode.find_all('dl', attrs={'class': "search-result-item"})
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        articleSoup.prettify()
                        flag = 3

                        if not articleSoup.head.meta:
                            logger.info('网页未完整请求，5秒后重试')
                            sleep(5)
                            flag = 0
                            continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('span'):
                            publishTime = (re.search('(\d+.\d+.\d+)', table.find('span').text)[0]).replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('p', attrs={'class': 'location'}):
                            articleLocation = articleSoup.find('p', attrs={'class': 'location'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            if articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': "TRS_Editor"}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山西省沂州市财政局',
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
            logger.info('山西省沂州市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&searchword=' + key + '&perpage=&token=0.1450753920719.14&templet='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'search-result-inner-box'})
                    titleList = titleNode.find_all('dl', attrs={'class': "search-result-item"})
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

#6.山西省晋中市财政局
def SXJinzhongCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://czj.sxjz.gov.cn/s?sid=53&wd='
    siteURL = 'http://czj.sxjz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省晋中市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', attrs={'class': 's-result'})
                totalResults = int(re.search('(\d+)',titleNode.find('div', attrs={'class': 'result-info'}).text)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleList = titleNode.find_all('li')
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    sleep(60 * 10)
                    flag = 0
                print('重新请求网页中...')
                sleep(10 + 20 * flag)
        while titleList:
            for table in titleList:
                a = table.find('a')
                articleURL = a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        articleTitle = ''
                        if articleSoup.find(class_='title'):
                            articleTitle = articleSoup.find(class_='title').text.replace('\t','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find(class_='attribution')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')
                        elif articleSoup.find(class_='property'):
                            if re.search('(\d+-\d+-\d+)', articleSoup.find(class_='property').text):
                                publishTime = re.search('(\d+-\d+-\d+)', articleSoup.find(class_='property').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'path'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'path'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "conTxt"}):
                            articleText = articleSoup.find('div', attrs={'class': "conTxt"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山西省晋中市财政局',
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
                    except (ReadTimeout, ConnectionError,Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山西省晋中市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 's-result'})
                    titleList = titleNode.find_all('li')
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.infot('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return;

#7.山西省长治市财政局
def SXChangzhiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.czj.changzhi.gov.cn/was5/web/search?searchscope=&timescope=&timescopecolumn=&orderby=-docreltime&channelid=285736&andsen=&total=&orsen=&exclude=&lanmu=&page='
    siteURL = 'http://www.czj.changzhi.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省长治市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&searchword=' + key + '&perpage=&token=26.1504774285950.94&templet='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('span', class_='page-sum')
                if total:
                    if total.find('strong'):
                        totalResults = int(total.find('strong').text)
                titleNode = basesoup.find('div', attrs={'class': 'search-result-inner-box'})
                titleList = titleNode.find_all(class_='search-result-item')
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+.\d+.\d+)', timeNode.text):
                                publishTime = re.search('(\d+.\d+.\d+)', timeNode.text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'currenturl content-currenturl'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'currenturl content-currenturl'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            if articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text
                        elif articleSoup.find('div',class_='content-body'):
                            if articleSoup.find('div',class_='content-body').find('p'):
                                articleTextList = articleSoup.find('div',class_='content-body').find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div',class_='content-body').text

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
                                    'site': '国家、省、市、区、县财政部门网站-山西省长治市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山西省长治市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&searchword=' + key + '&perpage=&token=26.1504774285950.94&templet='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'search-result-inner-box'})
                    titleList = titleNode.find_all(class_='search-result-item')
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

#8.山西省运城市财政局
def SXYunchengCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'https://www.yuncheng.gov.cn/search/?s=1&page='
    siteURL = 'https://www.yuncheng.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取山西省运城市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&isadv=0&q=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', class_='cen_list')
                if titleNode:
                    if titleNode.find('span', class_='keyword'):
                        totalResults = int(titleNode.find('span', class_='keyword').text)
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'https://www.yuncheng.gov.cn'+ a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('div',attrs={'id':'info_title'}):
                            articleTitle = articleSoup.find('div',attrs={'id':'info_title'}).text
                        else:
                            articleTitle = a.text.replace('\t','').replace('\r','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('span',attrs={'id':'info_released_dtime'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('span', attrs={'id': 'info_source'}):
                            articleLocation = articleSoup.find('span', attrs={'id': 'info_source'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id':'info_content','class': 'info_content_mid'}):
                            articleText = articleSoup.find('div', attrs={'id':'info_content','class': 'info_content_mid'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山西省运城市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山西省运城市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&isadv=0&q=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='cen_list')
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

#9.内蒙古包头市财政局
def NMBaotouCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://czj.baotou.gov.cn/search_'
    siteURL = 'http://czj.baotou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取内蒙古包头市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '.jspx?q=' + key + '&token=ff68ffe8-af14-444a-ad71-e15db6bf5ad7'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('div',class_='searchNav')
                if total:
                    if total.find('span'):
                        totalResults = int(total.find_all('span')[1].text)
                        if totalResults <= 0:
                            titleList = []
                            break
                titleNode = basesoup.find('div', class_='searchList')
                titleList = titleNode.find_all('div',class_='item')
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        timeNode = table.find('div', attrs={'class': 'search-date'})
                        if timeNode:
                            if timeNode.find('em'):
                                if re.search('(\d+-\d+-\d+)', timeNode.find('em').text):
                                    publishTime = re.search('(\d+-\d+-\d+)', timeNode.find('em').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'new_czj_nav'}):
                            if articleSoup.find('div', attrs={'class': 'new_czj_nav'}).find('h2'):
                                articleLocation = articleSoup.find('div', attrs={'class': 'new_czj_nav'}).find('h2').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'xxgk_rr02'}):
                            articleText = articleSoup.find('div', attrs={'class': 'xxgk_rr02'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-内蒙古包头市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('内蒙古包头市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '.jspx?q=' + key + '&token=ff68ffe8-af14-444a-ad71-e15db6bf5ad7'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='searchList')
                    titleList = titleNode.find_all('div', class_='item')
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

#10.辽宁省沈阳市财政局
def LNShenyangCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    requestURL = 'http://czj.shenyang.gov.cn/search/searchAction.ct'
    siteURL = 'http://czj.shenyang.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取辽宁省沈阳市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                data = {'searchKey':key, 'siteCode':'SYCZJ', 'offset':count, 'template':'syczj'}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', class_='lbk')
                titleList = titleNode.find_all('div', class_='lb')
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        timeNode = table.find('div', attrs={'class': 'time'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                    publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-','')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'nr'}):
                            articleText = articleSoup.find('div', attrs={'class': 'nr'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-辽宁省沈阳市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('辽宁省沈阳市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    data = {'searchKey': key, 'siteCode': 'SYCZJ', 'offset': count, 'template': 'syczj'}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='lbk')
                    titleList = titleNode.find_all('div', class_='lb', attrs={'id': 'result0'})
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

#11.辽宁省大连市财政局
def LNDaLianCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.czj.dl.gov.cn/qwresult.jsp?wbtreeid=1001&currentnum='
    keyDict = {'国企改革':'5Zu95LyB5pS56Z2p','国企改制':'5Zu95LyB5pS55Yi2','国企混改':'5Zu95LyB5re35pS5','国有企业改革':'5Zu95pyJ5LyB5Lia5pS56Z2p','国有企业改制':'5Zu95pyJ5LyB5Lia5pS55Yi2'}
    siteURL = 'http://www.czj.dl.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取辽宁省大连市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&newskeycode2=' + keyDict[key]
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                if '找不到和您的查询' in basesoup.text:
                    totalResults = 0
                    titleList = []
                    break
                total = basesoup.find_all('table', attrs={'border':"0", 'cellpadding':"0", 'cellspacing':"1", 'class':"listFrame", 'width':"100%"})
                total2 = total[len(total)-1]
                if re.search('(\d+)',total2.text):
                    totalResults = int(re.search('(\d+)',total2.text)[0])
                else:
                    totalResults = 0
                    titleList = []
                    break
                titleNode = total[len(total)-2]
                titleList = titleNode.find_all('a')
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
                a = table
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.czj.dl.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        timeNode = articleSoup.find('span', attrs={'class': 'timestyle1404'})
                        if timeNode:
                            if re.search('(\d+年\d+月\d+日)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+日)', timeNode.text)[0].replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('table',attrs={'class':'winstyle1191'}):
                            articleLocation = articleSoup.find('table',attrs={'class':'winstyle1191'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'vsb_content'}):
                            articleText = articleSoup.find('div', attrs={'id': 'vsb_content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-辽宁省大连市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('辽宁省大连市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&newskeycode2=' + keyDict[key]
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    total = basesoup.find_all('table', attrs={'border': "0", 'cellpadding': "0", 'cellspacing': "1",
                                                              'class': "listFrame", 'width': "100%"})
                    titleNode = total[len(total) - 2]
                    titleList = titleNode.find_all('a')
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

#12.辽宁省营口市财政局
def LNYingkouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.ykcz.gov.cn/channel/search/l/cn?Keywords='
    siteURL = 'http://www.ykcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取辽宁省营口市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&id=0&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('span', attrs={'class':'pageinfo'})
                if total:
                    if re.search('\d+/(\d+)',total.text):
                        totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                else:
                    totalPages = 1
                titleNode = basesoup.find('ul', class_= 'textlist4')
                if '找不到和您的查询' in titleNode.text:
                    titleList = []
                    break
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
                a = table.find_all('a')
                if 'http://' in a[1]['href']:
                    articleURL = a[1]['href']
                else:
                    articleURL = 'http://www.ykcz.gov.cn' + a[1]['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a[1].text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = a[0].text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':'InfoContent', 'id': 'InfoContent'}):
                            articleText = articleSoup.find('div', attrs={'class':'InfoContent', 'id': 'InfoContent'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-辽宁省营口市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('辽宁省营口市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&id=0&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('ul', class_='textlist4')
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

#13.黑龙江省哈尔滨市财政局
def HLJHaerbinCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.hrbczj.gov.cn/app/search/search.jsp?currentPage='
    siteURL = 'http://www.hrbczj.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取黑龙江省哈尔滨市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                key = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%')
                requestURL = baseURL + str(pageNum) + '&leixing=&keywords=' + key + '&type=top'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleList = basesoup.find_all('li', class_='sosuo_tit')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.hrbczj.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', attrs={'id':'sosuo_date'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'width':'722'}):
                            articleLocation = articleSoup.find('td', attrs={'width':'722'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'news_finish_main'}):
                            if articleSoup.find('div', attrs={'class': 'news_finish_main'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'news_finish_main'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': 'news_finish_main'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-黑龙江省哈尔滨市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('黑龙江省哈尔滨市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    key = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\', '').replace('x', '%')
                    requestURL = baseURL + str(pageNum) + '&leixing=&keywords=' + key + '&type=top'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleList = basesoup.find_all('li', class_='sosuo_tit')
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

#14.黑龙江省伊春市财政局
def HLJYichuanCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    requestURL = 'http://czj.yc.gov.cn/search/searchChaxun.action'
    siteURL = 'http://czj.yc.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取黑龙江省伊春市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                data = {'tiaojian.moHuGJZ': key,'tiaojian.ziCiWeiZhi': 3,'zhanDianPath': 'czj','px': 'jifen','page.currentPage': pageNum}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('div', class_='page')
                if total:
                    if re.search('当前1/(\d+)页',total.text):
                        totalPages = int(re.search('当前1/(\d+)页',total.text)[1])
                titleNode = basesoup.find('div',class_='boxRight').find('ul')
                titleList = titleNode.find_all('h5')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.yc.gov.cn' + a['href'].replace('\\','/')
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        #保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('div',class_='end_tit'):
                            if articleSoup.find('div',class_='end_tit').find('h2'):
                                timeNode = articleSoup.find('div',class_='end_tit').find('h2')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'end_tit01'}):
                            articleText = articleSoup.find('div', attrs={'class': 'end_tit01'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-黑龙江省伊春市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('黑龙江省伊春市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'tiaojian.moHuGJZ': key, 'tiaojian.ziCiWeiZhi': 3, 'zhanDianPath': 'czj', 'px': 'jifen',
                            'page.currentPage': pageNum}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='boxRight').find('ul')
                    titleList = titleNode.find_all('h5')
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

#15.吉林省长春市财政局
def JLChangchunCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Host': 'www.cccz.gov.cn',
        'Referer': 'http://www.cccz.gov.cn/webroot/AttachManage/fullsearch/smain.aspx?siteid=1&searchtext=%E5%9B%BD',
        'Upgrade-Insecure-Requests': '1'
        }
    baseURL = 'http://www.cccz.gov.cn/webroot/AttachManage/fullsearch/smain.aspx?siteid=1&searchtext='
    siteURL = 'http://www.cccz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取吉林省长春市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                key = '%E5%9B%BD'
                #key = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\', '').replace('x', '%')
                requestURL = baseURL + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                if not basesoup.head.meta:
                    logger.info('again')
                    sleep(5)
                    continue
                flag = 3
                viewstate = basesoup.find('input',attrs={'name':"__VIEWSTATE"})['value']
                viewstategenerator = basesoup.find('input',attrs={'name':"__VIEWSTATEGENERATOR"})['value']
                eventvalidation = basesoup.find('input',attrs={'name':"__EVENTVALIDATION"})['value']
                data = {'__EVENTTARGET': 'GridView1$ctl15$lbNext',
                        '__VIEWSTATE': viewstate,
                        '__VIEWSTATEGENERATOR': '841553D6',
                        '__EVENTVALIDATION': eventvalidation,
                        'GridView1$ctl15$ddlPagerList': pageNum}
                total = basesoup.find('span', attrs={'id':"GridView1_ctl15_labCountInfo"})
                if total:
                    if re.search('\d+/(\d+)', total.text):
                        totalPages = int(re.search('\d+/(\d+)', total.text)[1])
                titleList = basesoup.find_all('tr', class_='RowStyle')
                titleList += basesoup.find_all('tr', class_='AlternatingRowStyle')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.yc.gov.cn' + a['href'].replace('\\', '/')
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        if articleSoup.find('div', class_='end_tit'):
                            if articleSoup.find('div', class_='end_tit').find('h2'):
                                timeNode = articleSoup.find('div', class_='end_tit').find('h2')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'end_tit01'}):
                            articleText = articleSoup.find('div', attrs={'class': 'end_tit01'}).text
                            # if articleSoup.find('div', attrs={'class': 'end_tit01'}).find('p'):
                            #     articleTextList = articleSoup.find('div', attrs={'class': 'end_tit01'}).find_all('p')
                            #     for articleTextNode in articleTextList:
                            #         articleText += articleTextNode.text
                            # else:

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
                                    'site': '国家、省、市、区、县财政部门网站-吉林省长春市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('吉林省长春市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'tiaojian.moHuGJZ': key, 'tiaojian.ziCiWeiZhi': 3, 'zhanDianPath': 'czj', 'px': 'jifen',
                            'page.currentPage': pageNum}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='boxRight').find('ul')
                    titleList = titleNode.find_all('h5')
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

#16.吉林省吉林市财政局
def JLJilinCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://122.137.242.29:8083/was5/web/search?page='
    siteURL = 'http://czj.jlcity.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取吉林省吉林市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&channelid=230337&searchword=' + key +'&perpage=10&outlinepage=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('div', class_='cont-list-title')
                if total:
                    if total.find('font',attrs={'size':'3','color':'red'}):
                        if re.search('(\d+)', total.find('font',attrs={'size':'3','color':'red'}).text):
                            totalResults = int(re.search('(\d+)', total.find('font',attrs={'size':'3','color':'red'}).text)[0])
                        else:
                            totalResults = 0
                            titleList = []
                            break
                titleNode = basesoup.find('ul', class_='list-item')
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('span'):
                            if re.search('(\d+/\d+/\d+)',table.find('span').text):
                                publishTime = re.search('(\d+/\d+/\d+)',table.find('span').text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-吉林省吉林市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('吉林省吉林市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=230337&searchword=' + key + '&perpage=10&outlinepage=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('ul', class_='list-item')
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

#17.吉林省四平市财政局
def JLSipingCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://58.244.255.84:8080/was5/web/search?page='
    siteURL = 'http://cz.siping.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取吉林省四平市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(
                    pageNum) + '&channelid=278718&searchword=' + key + '&keyword=' + key +'&perpage=7&outlinepage=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', class_='main_left')
                if not titleNode:
                    titleList = []
                    break
                titleList = titleNode.find_all('h3')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue
                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章发布时间
                        publishTime = ''
                        if a.find('span'):
                            publishTime = a.find('span').text.replace('-', '')

                        # 保存文章标题信息
                        articleTitle = ''
                        if a.find('span'):
                            a.span.decompose()
                            articleTitle = a.text.replace('\t','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('span', attrs={'class': 'dqwz'}):
                            articleLocation = articleSoup.find('span', attrs={'class': 'dqwz'}).text
                        elif articleSoup.find(attrs={'class': 'currentstation'}):
                            articleLocation = articleSoup.find(attrs={'class': 'currentstation'}).text
                        elif articleSoup.find(attrs={'class': 'locating_txt'}):
                            articleLocation = articleSoup.find(attrs={'class': 'locating_txt'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            if articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-吉林省四平市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('吉林省四平市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=278718&searchword=' + key + '&keyword=' + key + '&perpage=7&outlinepage=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='main_left')
                    if not titleNode:
                        titleList = []
                        break
                    titleList = titleNode.find_all('h3')
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

#18.吉林省白山市财政局
def JLBaishanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://122.143.195.10:8080/was5/web/search?page='
    siteURL = 'http://czj.cbs.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取吉林省白山市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(
                    pageNum) + '&channelid=293162&searchword=' + key + '&keyword=' + key + '&perpage=20&outlinepage=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', class_='mainmlist')
                if '很抱歉，没有找到和您的查询相匹配的结果，您可以尝试更换检索词，重新检索' in titleNode.text:
                    titleList = []
                    break
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('span'):
                            publishTime = table.find('span').text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'path'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'path'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            if articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-吉林省白山市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('吉林省白山市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=293162&searchword=' + key + '&keyword=' + key + '&perpage=20&outlinepage=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', class_='mainmlist')
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

#19.上海市普陀区财政局
def SHPutuoquCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://iservice.shpt.gov.cn/search2/search?page='
    siteURL = 'http://iservice.shpt.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取上海市普陀区财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&view=&dsId=&daterange=1&dateorder=1&contentScope=1&dateRangePicker=&searchTarget=all&q=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                total = basesoup.find('div', class_='result-count')
                if total:
                    if re.search('(\d+)',total.text):
                        totalResults = int(re.search('(\d+)',total.text)[0])
                else:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'id':'results'})
                titleList = titleNode.find_all('div', class_='result')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://iservice.shpt.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('font' ,attrs={'color':"#6a6a6a"}):
                            publishTime = table.find('font' ,attrs={'color':"#6a6a6a"}).text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('ol', class_="breadcrumb no-margin txt-16"):
                            articleLocation = articleSoup.find('ol', class_="breadcrumb no-margin txt-16").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id':"ivs_content", 'class':"Article_content"}):
                            if articleSoup.find('div', attrs={'id':"ivs_content", 'class':"Article_content"}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'id':"ivs_content", 'class':"Article_content"}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'id':"ivs_content", 'class':"Article_content"}).text
                        elif articleSoup.find('div', attrs={'class':"panel gaojian"}):
                            articleText = articleSoup.find('div', attrs={'class':"panel gaojian"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-上海市普陀区财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('上海市普陀区财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&view=&dsId=&daterange=1&dateorder=1&contentScope=1&dateRangePicker=&searchTarget=all&q=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'id': 'results'})
                    titleList = titleNode.find_all('div', class_='result')
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

#20.上海市静安区财政局
def SHJinganCZJ():
    headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'zh-CN,zh;q=0.9,eo;q=0.8,ht;q=0.7,en;q=0.6',
                'Connection': 'keep-alive',
                'Host': 'www.jingan.gov.cn',
                'Referer': 'http://www.jingan.gov.cn/EpointFulltextSearch/fulltextsearch/fulltextsearch/search/search.seam?keyword=_PERCENT_E5_PERCENT_9B_PERCENT_BD_PERCENT_E4_PERCENT_BC_PERCENT_81_PERCENT_E6_PERCENT_94_PERCENT_B9_PERCENT_E9_PERCENT_9D_PERCENT_A9&selectedSearchCategory=0&selectedIndexCategory=&startDateTime=19900101&endDateTime=',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36'}
    headers1 = {'Accept': 'application/xml, text/xml, */*',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'zh-CN,zh;q=0.9,eo;q=0.8,ht;q=0.7,en;q=0.6',
                'Connection': 'keep-alive',
                'Content-Length': '571',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Host': 'www.jingan.gov.cn',
                'Origin': 'http://www.jingan.gov.cn',
                'Referer': 'http://www.jingan.gov.cn/EpointFulltextSearch/fulltextsearch/fulltextsearch/search/search.seam?keyword=_PERCENT_E5_PERCENT_9B_PERCENT_BD_PERCENT_E4_PERCENT_BC_PERCENT_81_PERCENT_E6_PERCENT_94_PERCENT_B9_PERCENT_E9_PERCENT_9D_PERCENT_A9&selectedSearchCategory=0&selectedIndexCategory=&startDateTime=19900101&endDateTime=',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest'
    }
    baseURL = 'http://www.jingan.gov.cn/EpointFulltextSearch/fulltextsearch/fulltextsearch/search/search.seam?keyword='
    siteURL = 'http://www.jingan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取上海市静安区财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL +  key + '&selectedSearchCategory=0&selectedIndexCategory=&startDateTime=19900101&endDateTime='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                # total = basesoup.find('div', class_='container indexbg').find('label', attrs={'id':"templateform:lable"})
                # if re.search('(\d+)', total.text):
                #         totalResults = int(re.search('(\d+)', total.text)[0])
                # if totalResults <= 0:
                #     titleList = []
                #     break
                titleNode = basesoup.find('table', attrs={'id':"templateform:refreshData_table", 'class':"ui-datagrid-data"})
                titleList = titleNode.find_all('td', class_='ui-datagrid-column')
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
            # for table in titleList:
            #     a = table.find('a')
            #     articleURL = a['href']
            #     flag = 0
            #     count += 1
            # 如果是最新的网页，则更新crawlerCollection
            # index = titleList.index(table)
            # if pageNum == 1 and index == 0:  # 第一页的第一个网址
            #     if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
            #         last = crawler.find_one({'url': siteURL})['last_updated']
            #         if key in last:
            #             logger.info('更新last_updated for 关键词： ' + key)
            #         else:
            #             logger.info('首次插入last_updated for 关键词： ' + key)
            #         last[key] = articleURL
            #         crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
            #     else:  # 否则向crawlerCollection插入新的数据
            #         last = {key: articleURL}
            #         crawler.insert_one({'url': siteURL, 'last_updated': last})
            #         logger.info('首次插入last_updated for 关键词： ' + key)
            # # 如果到达上次爬取的网址
            # if articleURL == last_updated_url:
            #     quitflag = 3
            #     logger.info('到达上次爬取的进度')
            #     break
            #     while flag < 3:
            #         try:
            #             article = requests.get(articleURL, headers=headers)
            #             article.encoding = article.apparent_encoding
            #             articleSoup = BeautifulSoup(article.text, 'lxml')
            #             articleSoup.prettify()
            #             flag = 3
            #
            #
            #             if articleSoup.head:
            #                 if not articleSoup.head.meta:
            #                     print('网页未完整请求，5秒后重试')
            #                     sleep(5)
            #                     flag = 0
            #                     continue
            #
            #             # 保存网页源码
            #             htmlSource = article.text
            #
            #             # html的URL地址
            #             htmlURL = articleURL
            #
            #             # 保存文章标题信息
            #             articleTitle = a.text
            #
            #             # 保存文章发布时间
            #             publishTime = ''
            #             timeNode = table.find('div', attrs={'style':"width: 90%;"})
            #             if timeNode:
            #                 if re.search('(\d+-\d+-\d+)', timeNode.text):
            #                     publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')
            #
            #             # 保存文章位置
            #             articleLocation = ''
            #             if articleSoup.find('div', class_="nowfzfont"):
            #                 articleLocation = articleSoup.find('div', class_="nowfzfont").text.replace(' ','')
            #             elif articleSoup.find('p', class_="margin-bottom-10"):
            #                 articleLocation = articleSoup.find('p', class_="margin-bottom-10").text
            #
            #                 # 保存文章正文
            #             articleText = ''
            #             if articleSoup.find('div', attrs={'class': "infoContent_info"}):
            #                 if articleSoup.find('div', attrs={'class': "infoContent_info"}).find('p'):
            #                     articleTextList = articleSoup.find('div', attrs={'class': "infoContent_info"}).find_all('p')
            #                     for articleTextNode in articleTextList:
            #                         articleText += articleTextNode.text
            #                 else:
            #                     articleText = articleSoup.find('div', attrs={'class': "infoContent_info"}).text
            #             elif articleSoup.find('div', attrs={'id': "content"}):
            #                 if articleSoup.find('div', attrs={'id': "content"}).find('p'):
            #                     articleTextList = articleSoup.find('div', attrs={'id': "content"}).find_all('p')
            #                     for articleTextNode in articleTextList:
            #                         articleText += articleTextNode.text
            #                 else:
            #                     articleText = articleSoup.find('div', attrs={'id': "content"}).text
            #
            #
            #
            #             # 判断标题或正文是否含有关键词
            #             matched_keywords_list = []
            #             for each_keyword in config_sample.keywords_list:
            #                 if each_keyword in articleTitle or each_keyword in articleText:
            #                     matched_keywords_list.append(each_keyword)
            #             if matched_keywords_list.__len__() > 0:
            #                 if collection.find({'url': htmlURL}).count() == 0:
            #                     item = {
            #                         'url': htmlURL,
            #                         'title': articleTitle,
            #                         'date': publishTime,
            #                         'site': '国家、省、市、区、县财政部门网站-上海市静安区财政局',
            #                         'keyword': matched_keywords_list,
            #                         'tag_text': articleLocation,
            #                         'content': articleText,
            #                         'html': htmlSource
            #                     }
            #                     print('#insert_new_article: ' + articleTitle)
            #                     result = collection.insert_one(item)
            #                     print(result.inserted_id)
            #                 else:
            #                     print('#article already exists:' + articleTitle)
            #             else:
            #                 print('#no keyword matched: ' + articleTitle)
            #         except (ReadTimeout, ConnectionError, Exception) as e:
            #             logger.error(e)
            #             flag += 1
            #             print('重新请求网页中...')
            #             sleep(10 + 20 * flag)
            #             if flag == 3:
            #                 print('重新请求失败')
            # #                 logger.info('Sleeping...')
            logger.info('上海市静安区财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # if count >= totalResults or quitflag == 3:
            #     break
            javax = basesoup.find('input', attrs={'type':"hidden", 'name':"javax.faces.ViewState", 'id':"javax.faces.ViewState"})['value']
            flag = 0
            while flag < 3:
                try:
                    data1 = {'templateform': 'templateform',
                            'templateform:search_input': key,
                            'templateform:fields': '0',
                             'javax.faces.ViewState': javax,
                             'primefacesPartialRequest': 'true',
                             'templateform:myrefresh_ajax': 'templateform: myrefresh_ajax',
                             'primefacesPartialUpdate': 'templateform:lable, templateform: leftLabel, templateform: categorylist'
                    }
                    r = requests.post(requestURL, headers=headers, data=data1)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    javax = basesoup.find('input', attrs={'type': "hidden", 'name': "javax.faces.ViewState",
                                                          'id': "javax.faces.ViewState"})['value']
                    data = {'templateform': 'templateform',
                            'templateform:search_input': key,
                            'templateform:fields': '0',
                            'javax.faces.ViewState': javax,
                            'primefacesPartialSource': 'templateform:refreshData',
                            'primefacesPartialRequest': 'true',
                            'primefacesPartialProcess': 'templateform:refreshData',
                            'templateform:refreshData_ajaxPaging': 'true',
                            'templateform:refreshData_first': str(count),
                            'templateform:refreshData_rows': '10',
                            'templateform:refreshData_page': pageNum}
                    requestURL = 'http://www.jingan.gov.cn/EpointFulltextSearch/fulltextsearch/fulltextsearch/search/search.seam'
                    r = requests.post(requestURL, headers=headers1, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'id': 'results'})
                    titleList = titleNode.find_all('div', class_='result')
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

#21.江苏省南京市财政局
def JSNanjingCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.nanjing.gov.cn/was5/web/search?page='
    siteURL = 'http://www.nanjing.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省南京市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&channelid=210454&searchword=' + key + '+and+siteid%3D119&keyword=' + key + '+and+siteid%3D119&perpage=10&outlinepage=10&siteid=null&docchannel='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('td', class_='searchresult')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace('\t','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', attrs={'class': "pubtime"})
                        if timeNode:
                            if re.search('(\d+.\d+.\d+)', timeNode.text):
                                publishTime = re.search('(\d+.\d+.\d+)', timeNode.text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        content = articleSoup.find('div', class_="content")
                        if content:
                            if content.find('div', class_= 'o_lf_top'):
                                articleLocation = content.find('div', class_= 'o_lf_top').text.replace(' ','')

                            # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            if articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': "TRS_Editor"}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省南京市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省南京市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=210454&searchword=' + key + '+and+siteid%3D119&keyword=' + key + '+and+siteid%3D119&perpage=10&outlinepage=10&siteid=null&docchannel='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('td', class_='searchresult')
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

#22.江苏省无锡市财政局
def JSYixingCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://bot.wuxi.gov.cn/ss/search?v=1&q='
    siteURL = 'http://bot.wuxi.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省无锡市财政局')
        logger.info('关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&searchTarget=self&dsId=cz.wuxi.gov.cn&view=&contentScope=1&dateScope=0&page=' + str(pageNum-1) + '&order=1'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div', class_='resultinfo')
                if total:
                    totalResults = int(total['total'])
                    if totalResults <= 0:
                        titleList = []
                        break
                titleNode = basesoup.find('div', class_='main-result')
                titleList = titleNode.find_all('div', class_="result customdata ")
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        if articleSoup.head:
                            if not articleSoup.head.meta:
                                logger.info('网页未完整请求，5秒后重试')
                                sleep(5)
                                flag = 0
                                continue

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', attrs={'class': "f"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('span', class_="tit fl"):
                            articleLocation = articleSoup.find('span', class_="tit fl").text
                        elif articleSoup.find('p', class_="font12 fl fn location"):
                            articleLocation = articleSoup.find('p', class_="font12 fl fn location")

                            # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': "Zoom"}):
                            articleText = articleSoup.find('div', attrs={'id': "Zoom"}).text
                        elif articleSoup.find('div', attrs={'class': "Zoom"}):
                            articleText = articleSoup.find('div', attrs={'class': "Zoom"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省无锡市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省无锡市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&searchTarget=self&dsId=cz.wuxi.gov.cn&view=&contentScope=1&dateScope=0&page=' + str(
                        pageNum - 1) + '&order=1'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('div', class_="result customdata ")
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

#23.江苏省苏州市财政局
def JSSuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.szcz.gov.cn/szczj//ShowInfo/SearchResult.aspx?keyword='
    siteURL = 'http://www.szcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省苏州市财政局'+'关键词：' + key)
        requestURL = baseURL + key + '&searchtype=title'
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                flag = 3
                total = basesoup.find('td', attrs={'valign':"bottom", 'align':"left", 'nowrap':"true", 'style':"width:40%;"})
                if total:
                    if re.search('\d+/(\d+)',total.text):
                        totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                    if totalPages <= 0:
                        titleList = []
                        break
                titleNode = basesoup.find('table', attrs={'align':"Center", 'rules':"all", 'id':"SearchResult1_DataGrid1"})
                titleList = titleNode.find_all('tr', attrs={'valign':"top", 'style':"height:25px;"})
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
            # for table in titleList:
            #     a = table.find('a')
            #     if 'http://' in a['href']:
            #         articleURL = a['href']
            #     else:
            #         articleURL = 'http://www.szcz.gov.cn' + a['href']
            #     flag = 0
            # 如果是最新的网页，则更新crawlerCollection
            # index = titleList.index(table)
            # if pageNum == 1 and index == 0:  # 第一页的第一个网址
            #     if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
            #         last = crawler.find_one({'url': siteURL})['last_updated']
            #         if key in last:
            #             logger.info('更新last_updated for 关键词： ' + key)
            #         else:
            #             logger.info('首次插入last_updated for 关键词： ' + key)
            #         last[key] = articleURL
            #         crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
            #     else:  # 否则向crawlerCollection插入新的数据
            #         last = {key: articleURL}
            #         crawler.insert_one({'url': siteURL, 'last_updated': last})
            #         logger.info('首次插入last_updated for 关键词： ' + key)
            # # 如果到达上次爬取的网址
            # if articleURL == last_updated_url:
            #     quitflag = 3
            #     logger.info('到达上次爬取的进度')
            #     break
            #     while flag < 3:
            #         try:
            #             article = requests.get(articleURL, headers=headers)
            #             article.encoding = article.apparent_encoding
            #             articleSoup = BeautifulSoup(article.text, 'lxml')
            #             articleSoup.prettify()
            #             flag = 3
            #
            #             if articleSoup.head:
            #                 if not articleSoup.head.meta:
            #                     logger.info('网页未完整请求，5秒后重试')
            #                     sleep(5)
            #                     flag = 0
            #                     continue
            #
            #             # 保存网页源码
            #             htmlSource = article.text
            #
            #             # html的URL地址
            #             htmlURL = articleURL
            #
            #             # 保存文章标题信息
            #             articleTitle = a.text.replace(' ','')
            #
            #             # 保存文章发布时间
            #             publishTime = ''
            #             timeNode = table.find('td', attrs={'align': "right"})
            #             if timeNode:
            #                 if re.search('(\d+-\d+-\d+)', timeNode.text):
            #                     publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')
            #
            #             # 保存文章位置
            #             articleLocation = ''
            #             if articleSoup.find('font', attrs={'color':"#888888", 'class':"webfont"}):
            #                 if articleSoup.find('font', attrs={'color':"#888888", 'class':"webfont"}).find('font', attrs={'color':"red"}):
            #                     articleLocation = articleSoup.find('font', attrs={'color':"#888888", 'class':"webfont"}).find('font', attrs={'color':"red"}).text
            #
            #                 # 保存文章正文
            #             articleText = ''
            #             if articleSoup.find('td', attrs={'valign':"top", 'class':"infodetail", 'id':"TDContent"}):
            #                 articleText = articleSoup.find('td', attrs={'valign':"top", 'class':"infodetail", 'id':"TDContent"}).text
            #
            #             # 判断标题或正文是否含有关键词
            #             matched_keywords_list = []
            #             for each_keyword in config_sample.keywords_list:
            #                 if each_keyword in articleTitle or each_keyword in articleText:
            #                     matched_keywords_list.append(each_keyword)
            #             if matched_keywords_list.__len__() > 0:
            #                 if collection.find({'url': htmlURL}).count() == 0:
            #                     item = {
            #                         'url': htmlURL,
            #                         'title': articleTitle,
            #                         'date': publishTime,
            #                         'site': '国家、省、市、区、县财政部门网站-江苏省苏州市财政局',
            #                         'keyword': matched_keywords_list,
            #                         'tag_text': articleLocation,
            #                         'content': articleText,
            #                         'html': htmlSource
            #                     }
            #                     print('#insert_new_article: ' + articleTitle)
            #                     result = collection.insert_one(item)
            #                     print(result.inserted_id)
            #                 else:
            #                     print('#article already exists:' + articleTitle)
            #             else:
            #                 print('#no keyword matched: ' + articleTitle)
            #         except (ReadTimeout, ConnectionError, Exception) as e:
            #             logger.error(e)
            #             flag += 1
            #             print('重新请求网页中...')
            #             sleep(10 + 20 * flag)
            #             if flag == 3:
            #                 print('重新请求失败')
            #                 logger.info('Sleeping...')
            logger.info('江苏省苏州市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            #获取viewstate
            viewstate = basesoup.find('input', attrs={'type':"hidden", 'name':"__VIEWSTATE", 'id':"__VIEWSTATE"})['value']

            headers1 = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Encoding': 'gzip, deflate',
                        'Accept-Language': 'zh-CN,zh;q=0.9,eo;q=0.8,ht;q=0.7,en;q=0.6',
                        'Cache-Control': 'max-age=0',
                        'Connection': 'keep-alive',
                        #'Content-Length': '7616',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Host': 'www.szcz.gov.cn',
                        #'Origin': 'http://www.szcz.gov.cn',
                        'Referer': 'http://www.szcz.gov.cn/szczj//ShowInfo/SearchResult.aspx?keyword=%u56fd&searchtype=title',
                        'Upgrade-Insecure-Requests': '1',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36'
            }
            flag = 0
            while flag < 3:
                try:
                    requestURL = 'http://www.szcz.gov.cn/szczj//ShowInfo/SearchResult.aspx?keyword=国&searchtype=title'
                    data = {'__VIEWSTATE': viewstate, '__EVENTTARGET': 'SearchResult1$Pager', '__EVENTARGUMENT': str(pageNum)}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'html5lib')
                    flag = 3
                    titleNode = basesoup.find('table', attrs={'align': "Center", 'rules': "all",
                                                              'id': "SearchResult1_DataGrid1"})
                    titleList = titleNode.find_all('tr', attrs={'valign': "top", 'style': "height:25px;"})
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

#24.江苏省连云港财政局
def JSLianyungangCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://czj.lyg.gov.cn/TrueCMS/searchController/getResult.do?flag=1&site=lygsczj&siteId=&siteName=&excludeSites=&siteCode=&rootCode=&canChooseSite=&sysId=&sysName=&pageSize=10&timeScope=&searchScope=&order=&obj=&fileType=&searchIndexModel=&word_correct=y&columns=&searchStarttime=&searchEndtime=&query='
    baseURL2 = 'http://czj.lyg.gov.cn/TrueCMS/searchController/getResult.do?word_correct=y&query='
    siteURL = 'http://czj.lyg.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省连云港财政局')
        logger.info('关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pageSize=10&page='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('span', class_='fr')
                if total:
                    if total.find('span', class_='blue-color'):
                        totalResults = int(total.find('span', class_='blue-color').text)
                        if totalResults <= 0:
                            titleList = []
                            break
                titleNode = basesoup.find('ul', class_='search-list mt15')
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
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_="fr gray-color")
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="gb-title"):
                            articleLocation = articleSoup.find('div', class_="gb-title").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':"art-main", 'id':"menu"}):
                            articleText =articleSoup.find('div', attrs={'class':"art-main", 'id':"menu"}).text
                        elif articleSoup.find('div', attrs={'id':"wznr"}):
                            articleText = articleSoup.find('div', attrs={'id':"wznr"}).text
                        elif articleSoup.find('div', attrs={'id':"printer"}):
                            articleText = articleSoup.find('div', attrs={'id':"printer"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省连云港财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省连云港财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL2 + key + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('ul', class_='search-list mt15')
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

#25.江苏省淮安市财政局
def JSHuaianCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    requestURL = 'http://q8.huaian.gov.cn:9980/api/query.do'
    siteURL = 'http://czj.huaian.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省淮安市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                data = {'q': 'title:'+key,'ename': 'core','pageNo': pageNum,'hl.fl': 'title,TEXT_CONTENT','fq': '["","layer:0146*"]','rows': 20}
                r = requests.post(requestURL, headers=headers,data=data)
                r.encoding = r.apparent_encoding
                basesoup = json.loads(r.text)
                totalResults = basesoup['numfound']
                flag = 3
                titleList = basesoup['list']
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
                articleURL = table['domain']+table['path']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = BeautifulSoup(table['title'],'lxml').text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table['input_time']
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = table['name_layer']

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "nr-zw"}):
                            articleText = articleSoup.find('div', attrs={'class': "nr-zw"}).text

                        try:
                            # 判断页面是否含有链接
                            if articleSoup.find('div', attrs={'class': "nr-zw"}):
                                if articleSoup.find('div', attrs={'class': "nr-zw"}).find('a'):
                                    fujian = articleSoup.find('div', attrs={'class': "nr-zw"}).find('a')
                                    fujianURL = 'http://czj.huaian.gov.cn'+fujian['href']
                                    if '.doc' in fujianURL:
                                        docID = fujian.text
                                        if not os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                            os.mkdir('./file_data')
                                            os.chdir('./file_data')
                                        if os.path.exists(
                                                './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                            os.chdir('./file_data')
                                        if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                            f = requests.get(fujianURL)
                                            with open('./' + docID, "wb") as code:
                                                code.write(f.content)
                                            logger.info('.doc download over')
                                        # 解析doc文件
                                        utility_convert.convert_doc_to_txt('./' + docID)
                                        if os.path.exists('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt'):
                                            f = open('./' + docID.rstrip('.doc') + '/' + docID.rstrip('.doc') + '.txt', encoding='utf-8')
                                            docText = f.read()
                                            articleText += '\n\n\n\附件内容：\n' + docText
                                            f.close()
                                        else:
                                            logger.info('无法解析doc文档')
                        except Exception as e:
                            logger.error(e)
                            logger.info('处理附件内容失败')

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省淮安市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省淮安市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count>=totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    data = {'q': 'title:' + key, 'ename': 'core', 'pageNo': pageNum, 'hl.fl': 'title,TEXT_CONTENT',
                            'fq': '["","layer:0146*"]', 'rows': 20}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = json.loads(r.text)
                    flag = 3
                    titleList = basesoup['list']
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

#26.江苏省盐城市财政局
def JSYanchengCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.yccz.gov.cn/ycczj/index/search?num='
    siteURL = 'http://www.yccz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省盐城市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum-1) + '&title=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div', class_='zys')
                if total:
                    if re.search('\d+/(\d+)',total.text):
                        totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                titleNode = basesoup.find('table', class_='tableall')
                titleList = titleNode.find_all('tr',attrs={'height':'35'})
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.yccz.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('td', attrs={'width':"100", 'align':"left", 'class':"line"})
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="ma_content_show_top1"):
                            articleLocation = articleSoup.find('div', class_="ma_content_show_top1").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':"ma_content_show_ce"}):
                            articleText = articleSoup.find('div', attrs={'class':"ma_content_show_ce"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省盐城市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省盐城市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum-1) + '&title=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('table', class_='tableall')
                    titleList = titleNode.find_all('tr', attrs={'height': '35'})
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

#27.江苏省宿迁市财政局
def JSSuqianCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://sqcz.suqian.gov.cn/sofpro/znss/mtgsss.jsp?keyword='
    baseURL2 = 'http://sqcz.suqian.gov.cn/sofpro/znss/mtgsss.jsp?website_Id=97a03f1c74aa452fbfb1ba19d8db62f4'
    siteURL = 'http://sqcz.suqian.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取江苏省宿迁市财政局')
        logger.info('关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&website_Id=97a03f1c74aa452fbfb1ba19d8db62f4'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('span', attrs={'id':'page2'})
                if total:
                    if re.search('共(\d+)页', total.text):
                        totalPages = int(re.search('共(\d+)页', total.text)[1])
                titleNode = basesoup.find('div', attrs={'id':'bodymain'})
                titleList = titleNode.find_all('td', attrs={'width':"72%", 'class':"xxx"})
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://sqcz.suqian.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3
                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('publishtime'):
                            publishTime =  articleSoup.find('publishtime').text.replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='dqwz'):
                            if articleSoup.find('div', class_='dqwz').find('td',attrs={'width':'651'}):
                                articleLocation = articleSoup.find('div', class_='dqwz').find('td',attrs={'width':'651'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('ucapcontent'):
                            articleText = articleSoup.find('ucapcontent').text

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
                                    'site': '国家、省、市、区、县财政部门网站-江苏省宿迁市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('江苏省宿迁市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data={'website_Id': '97a03f1c74aa452fbfb1ba19d8db62f4','keyword': key,'desc': 2,'currentPage': pageNum}
                    r = requests.post(baseURL2, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'id': 'bodymain'})
                    titleList = titleNode.find_all('td', attrs={'width': "72%", 'class': "xxx"})
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

#28.浙江省杭州市财政局
def ZJHangzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.hzft.gov.cn/jsearch/search.do?appid=1&ck=x&imageField=&pagemode=result&pos=title%2Ccontent&q='
    siteURL = 'http://www.hzft.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取浙江省杭州市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&style=1&webid=1&&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('td', attrs={'class': 'js-result'})
                titleList = titleNode.find_all('table', attrs={'width':"1000", 'border':"0", 'align':"center", 'cellspacing':"0", 'cellpadding':"0"})
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('td', attrs={'class':"jsearchhuise STYLE4"}):
                            if re.search('(\d+-\d+-\d+)',table.find('td', attrs={'class':"jsearchhuise STYLE4"}).text):
                                publishTime = re.search('(\d+-\d+-\d+)',table.find('td', attrs={'class':"jsearchhuise STYLE4"}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='lm_dqwz'):
                           articleLocation = articleSoup.find('div', class_='lm_dqwz').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td',class_='bt_content'):
                            articleText = articleSoup.find('td',class_='bt_content').text

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
                                    'site': '国家、省、市、区、县财政部门网站-浙江省杭州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('浙江省杭州市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&style=1&webid=1&&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('td', attrs={'class': 'js-result'})
                    titleList = titleNode.find_all('table', attrs={'width': "1000", 'border': "0", 'align': "center",
                                                                   'cellspacing': "0", 'cellpadding': "0"})
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

# 29.浙江省宁波市财政局
def ZJNingboCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.nbcs.gov.cn/jsearch/search.do?appid=1&category=&ck=x&pagemode=result&pg=12&q='
    siteURL = 'http://www.nbcs.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取浙江省宁波市财政局')
        logger.info('关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&style=1&tpl=&webid=5&&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                if '找不到和您的查询' in basesoup.text:
                    titleList = []
                    break
                titleNode = basesoup.find('td', attrs={'class': 'js-result'})
                titleList = titleNode.find_all('td', class_='jsearchblue')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('h4', attrs={'class': "fxx"}):
                            if re.search('(\d+-\d+-\d+)',
                                         articleSoup.find('h4', attrs={'class': "fxx"}).text):
                                publishTime = re.search('(\d+-\d+-\d+)',
                                                        articleSoup.find('h4', attrs={'class': "fxx"}).text)[
                                    0].replace('-', '')
                        elif articleSoup.find('td', attrs={'align':"center", 'class':"bt_link_w"}):
                            if re.search('(\d+-\d+-\d+)',articleSoup.find('td', attrs={'align': "center", 'class': "bt_link_w"}).text):
                                publishTime = re.search('(\d+-\d+-\d+)',
                                                        articleSoup.find('td', attrs={'align': "center",
                                                                                      'class': "bt_link_w"}).text)[
                                    0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('ul', class_='cadress'):
                            articleLocation = articleSoup.find('ul', class_='cadress').text
                        elif articleSoup.find('div', attrs={'class':"bd_box", 'style':"height:10px;"}):
                            tmp = articleSoup.find('div', attrs={'class':"bd_box", 'style':"height:10px;"})
                            tmp.decompose()
                            if articleSoup.find('div', attrs={'class':"bd_box"}):
                                articleLocation = articleSoup.find('div', attrs={'class':"bd_box"}).text
                        elif articleSoup.find('table', class_='tableadress'):
                            articleLocation = articleSoup.find('table', class_='tableadress').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id':'ivs_content'}):
                            articleText = articleSoup.find('div', attrs={'id':'ivs_content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-浙江省宁波市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('浙江省宁波市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&style=1&tpl=&webid=5&&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    if '找不到和您的查询' in basesoup.text:
                        titleList = []
                        break
                    titleNode = basesoup.find('td', attrs={'class': 'js-result'})
                    titleList = titleNode.find_all('td', class_='jsearchblue')
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

#30.浙江省温州市财政局
def ZJWenzhouCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.wenzhou.gov.cn/jrobot/search.do?webid=2651&pg=12&p='
    siteURL = 'http://www.wenzhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取浙江省温州市财政局'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key + '&pos=&od=&date=&date='
                r = requests.get(requestURL, headers=headers)
                if r.status_code == 403:
                    flag += 1
                    if flag == 3:
                        logger.info('重新请求失败')
                        logger.info('403')
                        titleList = []
                        break
                        logger.info('403,即将重新请求')
                    sleep(20*flag)
                    continue
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div',attrs={'id':'jsearch-info-box'})
                if total:
                    totalResults = int(total['data-total'])
                else:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'id':"jsearch-result-items",'class':"ui-search-result-items"})
                titleList = titleNode.find_all('div', class_='jsearch-result-box')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.wenzhou.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('td', attrs={'height':"45", 'width':"100%", 'align':"center", 'valign':"middle"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')
                        elif re.search('(\d+-\d+-\d+)',articleSoup.text):
                                publishTime = re.search('(\d+-\d+-\d+)',articleSoup.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='location'):
                            articleLocation = articleSoup.find('div', class_='location').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td', attrs={'class': 'bt_content'}):
                            articleText = articleSoup.find('td', attrs={'class': 'bt_content'}).text
                        elif articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-浙江省温州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('浙江省温州市财政局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key + '&pos=&od=&date=&date='
                    r = requests.get(requestURL, headers=headers)
                    if r.status_code == 403:
                        flag += 1
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('403')
                            titleList = []
                            break
                        logger.info('403,即将重新请求')
                        sleep(20 * flag)
                        continue
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('div',
                                              attrs={'id': "jsearch-result-items", 'class': "ui-search-result-items"})
                    titleList = titleNode.find_all('div', class_='jsearch-result-box')
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

#31.浙江省湖州市财政局
def ZJHuzhouCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://app.huzhou.gov.cn/hzgov/front/aisearch/loaddata.do?tplid=0&indexids=&siteid=7&searchscope=0&timescope=0&sorttype=0&lastwd=&secondsearch=&curpageno='
    siteURL = 'http://czj.huzhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取浙江省湖州市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + ' &pagesize=10&categorycode=&wd=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('table',
                                          attrs={'width':"100%", 'border':"0", 'cellspacing':"0", 'cellpadding':"0", 'class':"shadow", 'style':"margin-bottom:10px;"})
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('td', attrs={'width':"80", 'align':"right", 'valign':"middle", 'class':"jsrq"})
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('a', attrs={'style':"font-size:12px"}):
                            articleLocList = articleSoup.find_all('a', attrs={'style':"font-size:12px"})
                            for articleLocNode in articleLocList:
                                articleLocation += articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-浙江省湖州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('浙江省湖州市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + ' &pagesize=10&categorycode=&wd=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('table',
                                                  attrs={'width': "100%", 'border': "0", 'cellspacing': "0",
                                                         'cellpadding': "0", 'class': "shadow",
                                                         'style': "margin-bottom:10px;"})
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

#32.浙江省台州市财政局
def ZJTaizhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.tzcs.gov.cn/dynamic/search/result/index.php?page='
    siteURL = 'http://www.tzcs.gov.cn/'
    dict = {'国企改革':'4366','国企改制':'0','国企混改':'4368','国有企业改革':'4369','国有企业改制':'0'}
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取浙江省台州市财政局'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum-1) + '&searchid=' + dict[key]
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('ul', class_='news_list')
                if titleNode:
                    titleList = titleNode.find_all('li')
                else:
                    titleList = []
                    break
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.tzcs.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "navsub4 dn"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "navsub4 dn"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'news_content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'news_content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-浙江省台州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('浙江省台州市财政局-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum - 1) + '&searchid=' + dict[key]
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('ul', class_='news_list')
                    if titleNode:
                        titleList = titleNode.find_all('li')
                    else:
                        titleList = []
                        break
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

#33.安徽省合肥市财政厅
def AHHefeiCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
               # 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
               # 'Accept-Encoding': 'gzip, deflate',
               # 'Accept-Language': 'zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7',
               # 'Connection': 'keep-alive',
               # 'Content-Type': 'application/x-www-form-urlencoded',
               # 'Upgrade-Insecure-Requests': '1',
               # 'Host': 'hfcz.hefei.gov.cn',
               # 'Referer': 'http://www.hfcz.gov.cn/gnlm/jsjg/?word=%E5%9B%BD%E4%BC%81%E6%94%B9%E9%9D%A9'
               }
    baseURL = 'http://hfcz.hefei.gov.cn/was5/web/search?page='
    siteURL = 'http://hfcz.hefei.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取安徽省合肥市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + 'channelid=298451&searchword=' + key +'+and+siteid%3D7&keyword='+key+'+and+siteid%3D7&perpage=10&outlinepage=10'
                #requestURL = 'http://hfcz.hefei.gov.cn/was5/web/search?channelid=298451&searchword=%E5%9B%BD%E4%BC%81%E6%94%B9%E9%9D%A9%20and%20siteid=7'
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                print(r.text)
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('td', class_='searchresult')
                if titleNode:
                    titleList = titleNode.find_all('li')
                else:
                    titleList = []
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', class_='pubtime')
                        if timeNode:
                            if re.search('(\d+.\d+.\d+)',timeNode.text):
                                publishTime = re.search('(\d+.\d+.\d+)',timeNode.text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "navsub4 dn"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "navsub4 dn"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'news_content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'news_content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省合肥市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省合肥市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum - 1) + '&searchid=' + dict[key]
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('ul', class_='news_list')
                    if titleNode:
                        titleList = titleNode.find_all('li')
                    else:
                        titleList = []
                        break
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

#34.安徽省淮北市财政厅
def AHHuaibeiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.huaibei.gov.cn/site/search/4697569?columnId=&columnIds=&typeCode=&beginDate=&endDate=&fromCode=&keywords='
    siteURL = 'http://czj.huaibei.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省淮北市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(pageNum) + '&pageSize=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('ul',class_='search-list')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_='date')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "wz_top"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "wz_top"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省淮北市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省淮北市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(
                        pageNum) + '&pageSize=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('ul', class_='search-list')
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

#35.安徽省毫州市财政厅
def AHBozhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.bozhou.gov.cn/index.php?keywords='
    siteURL = 'http://cz.bozhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省毫州市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&c=search&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('div',class_='is-search-list')
                titleList = basesoup.find_all('li')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://cz.bozhou.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_='time')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'm-location'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'm-location'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省毫州市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省毫州市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&c=search&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('div', class_='is-search-list')
                    titleList = basesoup.find_all('li')
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

#36.安徽省宿州市财政厅
def AHSuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.ahsz.gov.cn/site/search/14320822?columnId=&columnIds=&typeCode=&beginDate=&endDate=&fromCode=&keywords='
    siteURL = 'http://cz.ahsz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省宿州市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(pageNum) + '&pageSize=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('ul', class_='search-list')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_='date')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'wz_top'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'wz_top'}).text

                        # 保存文章正文
                        articleText = ''
                        articleTextNode = articleSoup.find('div', attrs={'id': 'zoom'})
                        if articleTextNode:
                            articleText = articleTextNode.text

                        #判断是否有pdf文档
                        if articleTextNode.find('a'):
                            if '.pdf' in articleTextNode.find('a').text:
                                try:
                                    docID = articleTextNode.find('a').text
                                    href = articleTextNode.find('a')['href']
                                    if"http://"not in href:
                                        href = 'http://cz.ahsz.gov.cn'+href
                                    if not os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                        os.mkdir('./file_data')
                                        os.chdir('./file_data')
                                    if os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                        os.chdir('./file_data')
                                    if not os.path.exists('./' + docID):  # 如果文件尚未存在
                                        f = requests.get(href)
                                        with open('./' + docID, "wb") as code:
                                            code.write(f.content)
                                        logger.info('pdf文件 download over')
                                    # 解析pdf文件
                                    docText = utility_convert.convert_pdf_to_txt('./' + docID)
                                    if docText:
                                        articleText += '\n\n\n\附件内容：\n'
                                        for docNode in docText:
                                            articleText += docNode
                                except Exception as e:
                                    logger.error(e)
                                    logger.info('pdf文件解析失败')

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省宿州市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省宿州市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(
                        pageNum) + '&pageSize=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('ul', class_='search-list')
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

#37.安徽省蚌埠市财政厅
def AHBengbuCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.bengbu.gov.cn/searchResult.jsp?keyword='
    siteURL = 'http://czj.bengbu.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('安徽省蚌埠市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&searchType=1&pages=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div',class_='page')
                if total:
                    if re.search('共(\d+)条',total.text):
                        totalResults = int(re.search('共(\d+)条',total.text)[1])
                        if totalResults==0:
                            titleList=[]
                            break
                titleNode = basesoup.find('ul',class_='list_search')
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
                if "http://" in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.bengbu.gov.cn/'+a['href']
                flag = 0
                count+=1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', class_='date')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'position'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'position'}).text.replace(' ','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content_news'}):
                            if articleSoup.find('div', attrs={'class': 'content_news'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'content_news'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'class': 'content_news'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省蚌埠市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省蚌埠市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&searchType=1&pages=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('ul', class_='list_search')
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

#38.安徽省阜阳市财政厅
def AHFuyangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.czj.fy.gov.cn/wgp/cms/search.do?pubType=S&startDate=19000101&endDate=20990101&newkeywords=&cxfld=topic%5e&keywords='
    siteURL = 'http://www.czj.fy.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省阜阳市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '%5E&channelCode=A0001&templetId=1355487603590046&pageNo=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('table', attrs={'align':"center", 'bgcolor':"#DDDDDD", 'border':"0", 'cellpadding':"5", 'cellspacing':"1", 'width':"800"})
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
                if "http://" in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.czj.fy.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('td', attrs={'class':"bottom", 'height':"25", 'width':"272"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'class':"blue14", 'width':"928"}):
                            articleLocation = articleSoup.find('td', attrs={'class':"blue14", 'width':"928"}).text
                        elif articleSoup.find('td', attrs={'class':"weizhis"}):
                            articleLocation = articleSoup.find('td', attrs={'class':"weizhis"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'BodyLabel'}):
                            articleText = articleSoup.find('div', attrs={'id': 'BodyLabel'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省阜阳市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省阜阳市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '%5E&channelCode=A0001&templetId=1355487603590046&pageNo=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('table',
                                                  attrs={'align': "center", 'bgcolor': "#DDDDDD", 'border': "0",
                                                         'cellpadding': "5", 'cellspacing': "1", 'width': "800"})
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

#39.安徽省淮南市财政厅
def AHHuainanCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.huainan.gov.cn/site/search/15476659?columnId=&columnIds=&typeCode=&beginDate=&endDate=&fromCode=&keywords='
    siteURL = 'http://cz.huainan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省淮南市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(pageNum) + '&pageSize=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('ul', class_='search-list')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "date"})
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "wzy_position"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "wzy_position"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'wzcon', 'id':'J_content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'wzcon', 'id':'J_content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省淮南市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省淮南市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(
                        pageNum) + '&pageSize=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('ul', class_='search-list')
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

#40.安徽省马鞍山市财政厅
def AHMaanshanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.mas.gov.cn/site/search/4697368?all=1&spSiteId=&columnId=&columnIds=&typeCode=&catIds=&beginDate=&endDate=&fromCode=&keywords='
    siteURL = 'http://www.mas.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省马鞍山市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(
                    pageNum) + '&pageSize='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('ul', class_='search-list')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "date"})
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "wzy_position"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "wzy_position"}).text
                        elif articleSoup.find('div', attrs={'class': "lmpos"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "lmpos"}).text
                        elif articleSoup.find('div', attrs={'class': "position"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "position"}).text

                            # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'wzcon j-fontContent'}):
                            articleText = articleSoup.find('div', attrs={'class': 'wzcon j-fontContent'}).text
                        elif articleSoup.find('div', attrs={'class': 'contentboxwz'}):
                            articleText = articleSoup.find('div', attrs={'class': 'contentboxwz'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省马鞍山市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省马鞍山市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&searchType=&searchTplId=&pageIndex=' + str(
                        pageNum) + '&pageSize=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('ul', class_='search-list')
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

#41.安徽省芜湖市财政厅
def AHWuhuCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czgz.wuhu.gov.cn/item/index.asp?page='
    siteURL = 'http://czgz.wuhu.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('安徽省芜湖市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                query = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%').upper()
                requestURL = baseURL + str(pageNum) + '&key=' + query + '&ChannelID=1&t=1&tid=0'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div', class_='sear_result').find_all('span')
                totalResults = int(total[1].text)
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', class_='artlisting')
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div', attrs={'class': "info"})
                        if timeNode:
                            if re.search('(\d+年\d+月\d+日)',timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+日)',timeNode.text)[0].replace('年','').replace('月','').replace('日','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "tit"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "tit"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'newscontent'}):
                            articleText = articleSoup.find('div', attrs={'class': 'newscontent'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省芜湖市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省芜湖市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    query = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\', '').replace('x',
                                                                                                           '%').upper()
                    requestURL = baseURL + str(pageNum) + '&key=' + query + '&ChannelID=1&t=1&tid=0'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('div', class_='artlisting')
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

#42.安徽省池州市财政厅
def AHChizhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.chizhou.gov.cn/index.php?keywords='
    siteURL = 'http://czj.chizhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省池州市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&c=search&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleNode = basesoup.find('div', class_='is-search-list')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.chizhou.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('td', attrs={'class': "is-leftinfo"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "is-posbg"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "is-posbg"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'text'}):
                            articleText = articleSoup.find('div', attrs={'class': 'text'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省池州市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省池州市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&c=search&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleNode = basesoup.find('div', class_='is-search-list')
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

#43.安徽省安庆市财政厅
def AHAnqingCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.anqing.gov.cn/site/search/18855598?columnId=&columnIds=&typeCode=&beginDate=&endDate=&fromCode=&keywords='
    siteURL = 'http://czj.anqing.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('安徽省安庆市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&pageIndex=' + str(pageNum) + '&pageSize=10'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('ul', class_='search-list')
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "date"})
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "wzy_position"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "wzy_position"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'wzcon j-fontContent'}):
                            articleText = articleSoup.find('div', attrs={'class': 'wzcon j-fontContent'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省安庆市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省安庆市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&excColumns=&datecode=&sort=&type=&tableColumnId=&indexNum=&fileNum=&flag=false&pageIndex=' + str(
                        pageNum) + '&pageSize=10'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('ul', class_='search-list')
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

#44.安徽省黄山市财政局
def AHHuangshanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.huangshan.gov.cn/Search/JA011/?keyword='
    siteURL = 'http://czj.huangshan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('安徽省黄山市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('span', class_='title')
                if re.search('(\d+)',total.text):
                    totalResults = int(re.search('(\d+)', total.text)[0])
                    if totalResults==0:
                        titleList = []
                        break
                tilteNode = basesoup.find('div', attrs={'class':'rightnr'})
                titleList = tilteNode.find_all('li')
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
                count += 1
                a = table.find('a')
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.huangshan.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "url"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "m-location"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "m-location"}).text.replace(' ','')
                        elif articleSoup.find('div', attrs={'class': "m-address"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "m-address"}).text.replace(' ','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text
                        elif articleSoup.find('div', attrs={'class': 'm-content'}):
                            articleText =articleSoup.find('div', attrs={'class': 'm-content'}).text
                        elif articleSoup.find('div', attrs={'class': 'm-par'}):
                            articleText = articleSoup.find('div', attrs={'class': 'm-par'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-安徽省黄山市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('安徽省黄山市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count>=totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    tilteNode = basesoup.find('div', attrs={'class':'rightnr'})
                    titleList = tilteNode.find_all('li')
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

#45.福建省福州市财政局
def FJFuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czt.fujian.gov.cn/was5/web/search?channelid=229105&templet=docs.jsp&sortfield=-docreltime&classsql=(doctitle%3D%27%25'
    siteURL = 'http://czt.fujian.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('福建省福州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '%25%27)*(siteid%3D47)&prepage=15&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                regex = r"http:\/\/.*?\.htm"
                matches = re.finditer(regex, r.text)
                titleList = []
                for matchNum,match in enumerate(matches):
                    if match.group() not in titleList:
                        titleList.append(match.group())
                flag = 3
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
                articleURL = table
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('div',class_='czxw-tit'):
                            articleTitle = articleSoup.find('div',class_='czxw-tit').text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('p', attrs={'class': "fbsk"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "nye_bg"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "nye_bg"}).text.replace('\t','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'czxw-w'}):
                            articleText = articleSoup.find('div', attrs={'class': 'czxw-w'}).text
                        elif articleSoup.find('div', attrs={'class': 'Section1'}):
                            articleText = articleSoup.find('div', attrs={'class': 'Section1'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省福州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省福州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '%25%27)*(siteid%3D47)&prepage=15&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    regex = r"http:\/\/.*?\.htm"
                    matches = re.finditer(regex, r.text)
                    titleList = []
                    for matchNum, match in enumerate(matches):
                        if match.group() not in titleList:
                            titleList.append(match.group())
                    flag = 3
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

#46.福建省厦门市财政局
def FJXiamenCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.xm.gov.cn/was5/web/search?channelid=203160&searchword='
    siteURL = 'http://cz.xm.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('福建省厦门市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&x=28&y=12&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                titleList = basesoup.find_all('td', class_="pad_b10 pad_t10")
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace('\t','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_="tb pad_r10")
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "p_path"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "p_path"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':"p_newsview_c", 'id':"newsview"}):
                            articleText = articleSoup.find('div', attrs={'class':"p_newsview_c", 'id':"newsview"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省厦门市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省厦门市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&x=28&y=12&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('td', class_="pad_b10 pad_t10")
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

#47.山东省财政厅
def SDCZT():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.sdcz.gov.cn/sdczww.s?method=dosearch'
    siteURL = 'http://www.sdcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('山东省财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                data = {'sn':key}
                r = requests.post(baseURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                tilteList = basesoup.find('td', class_="pad_b10 pad_t10")
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_="tb pad_r10")
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "m-location"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "m-location"}).text.replace(' ',
                                                                                                                  '')
                        elif articleSoup.find('div', attrs={'class': "m-address"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "m-address"}).text.replace(' ',
                                                                                                                 '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text
                        elif articleSoup.find('div', attrs={'class': 'm-content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'm-content'}).text
                        elif articleSoup.find('div', attrs={'class': 'm-par'}):
                            articleText = articleSoup.find('div', attrs={'class': 'm-par'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山东省财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山东省财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    tilteNode = basesoup.find('div', attrs={'class': 'rightnr'})
                    titleList = tilteNode.find_all('li')
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

#48.山东省青岛市财政局
def SDQingdaoCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://27.223.1.61:8080/searchqdf/WebSite/cms/SearchInfoList.aspx?lkocok_pageNo='
    siteURL = 'http://qdcz.qingdao.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('山东省青岛市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&searchContent=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('table',attrs={'align':'right','id':'pagerTable'})
                totalResults = int(re.search('(\d+)',total.text)[0])
                titleList = basesoup.find_all('td', attrs={'align':"left", 'style':"padding-left:5px;"})
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
                temp = a['onclick'].lstrip('OnFileLinkUrl(').rstrip(')').split(',')
                str0 = re.search('(\d+)',temp[0])[0]
                str2 = re.search('(\d+)',temp[2])[0]
                str3 = re.search('(\d+)',temp[3])[0]
                articleURL = 'http://www.qdf.gov.cn/n' + str3 + '/n' + str2 + '/' + str0 + '.html'
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div', class_="content_date")
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "content_path"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "content_path"}).text.replace(' ','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content_wz'}):
                            articleText = articleSoup.find('div', attrs={'class': 'content_wz'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山东省青岛市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山东省青岛市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count>=totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&searchContent=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('td', attrs={'align': "left", 'style': "padding-left:5px;"})
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

#49.山东省淄博市财政局
def SDZiboCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://sczj.zibo.gov.cn/jrobot/search.do?webid=28&pg=12&p='
    siteURL = 'http://sczj.zibo.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('山东省淄博市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key +'&pos=title%2Ccontent&od=&date=&date='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('div', attrs={'id': 'jsearch-info-box'})
                totalResults = total['data-total']
                if totalResults == '':
                    titleList = []
                    break
                else:
                    totalResults = int(totalResults)
                titleList = basesoup.find_all('div', attrs={'class': "jsearch-result-box"})
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://sczj.zibo.gov.cn'+a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_="jsearch-result-date")
                        if timeNode:
                            publishTime = timeNode.text.replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "dqwz_box"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "dqwz_box"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山东省淄博市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山东省淄博市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Ccontent&od=&date=&date='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('div', attrs={'class': "jsearch-result-box"})
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

#50.福建省莆田市财政局
def FJPutianCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.putian.gov.cn/was5/web/search?channelid=210831&templet=docs.jsp&sortfield=-docreltime&classsql=%25'
    siteURL = 'http://czj.putian.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('福建省莆田市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '%25*siteid%3D46&prepage=5&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                titleList = []
                totalResults = int(re.search('(\d+)',r.text)[0])
                if totalResults==0:
                    break
                regex = r"http:\/\/.*?\.htm"
                matches = re.finditer(regex, r.text)
                for matchNum, match in enumerate(matches):
                    if match.group() not in titleList:
                        titleList.append(match.group())
                flag = 3
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
                articleURL = table
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('h3'):
                            articleTitle = articleSoup.find('h3').text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('span', attrs={'class': "fbt"})
                        if timeNode:
                            if re.search('(\d+年\d+月\d+日)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+日)', timeNode.text)[0].replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "location"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "location"}).text.replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'subject'}):
                            articleText = articleSoup.find('div', attrs={'class': 'subject'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省莆田市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省莆田市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count>=totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '%25*siteid%3D46&prepage=5&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    titleList = []
                    regex = r"http:\/\/.*?\.htm"
                    matches = re.finditer(regex, r.text)
                    for matchNum, match in enumerate(matches):
                        if match.group() not in titleList:
                            titleList.append(match.group())
                    flag = 3
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

#52.福建省三明市财政局
def FJSanmingCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.sm.gov.cn/was5/web/search?channelid=212807&templet=advsch.jsp&sortfield=-docreltime&classsql=doctitle%2Cdoccontent%2Cfileno%2B%3D%27%25'
    siteURL = 'http://cz.sm.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('福建省三明市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '%25%27*siteid%3D7&page=' + str(pageNum) + '&prepage=5'
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                titleList = []
                totalResults = int(re.search('(\d+)', r.text)[0])
                if totalResults == 0:
                    break
                regex = r"http:\/\/.*?\.htm"
                matches = re.finditer(regex, r.text)
                for matchNum, match in enumerate(matches):
                    if match.group() not in titleList:
                        titleList.append(match.group())
                flag = 3
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
                articleURL = table
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('h3'):
                            articleTitle = articleSoup.find('h3').text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('h5')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "dqwz"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "dqwz"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text
                        elif articleSoup.find('div', attrs={'class': 'xl_main'}):
                            articleText = articleSoup.find('div', attrs={'class': 'xl_main'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省三明市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省三明市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '%25%27*siteid%3D7&page=' + str(pageNum) + '&prepage=5'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    titleList = []
                    totalResults = int(re.search('(\d+)', r.text)[0])
                    if totalResults == 0:
                        break
                    regex = r"http:\/\/.*?\.htm"
                    matches = re.finditer(regex, r.text)
                    for matchNum, match in enumerate(matches):
                        if match.group() not in titleList:
                            titleList.append(match.group())
                    flag = 3
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

#53.福建省南平市财政局
def FJNanpingCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.np.gov.cn/cms/siteresource/search.shtml?key='
    siteURL = 'http://czj.np.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('福建省南平市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&searchSiteId=330329092345780000&siteId=330329092345780000&currentFormApplicationName=cms%2Fsitemanage&currentFormName=quickSiteSearch&pageName=quickSiteSearch&queryString=siteId%3D330329092345780000&requestCode=115edfd7ad710908b5baa9ada102603c5f88a3f6556646591a8c7d99be9a2d0aea9e4b757124a3f8ef5004dcba747e76a292bca24b7649bd9565c458741a6af58bb175b4a84cad38&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup=BeautifulSoup(r.text,'lxml')
                flag = 3
                total=basesoup.find('div',class_='tz').find('input')['value']
                index=total.index('/')
                totalPages = int(total[index+1:])
                titleNode = basesoup.find('ul',class_='ri-list')
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.np.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "dqwz"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "dqwz"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'Zoom'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省南平市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省南平市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&searchSiteId=330329092345780000&siteId=330329092345780000&currentFormApplicationName=cms%2Fsitemanage&currentFormName=quickSiteSearch&pageName=quickSiteSearch&queryString=siteId%3D330329092345780000&requestCode=115edfd7ad710908b5baa9ada102603c5f88a3f6556646591a8c7d99be9a2d0aea9e4b757124a3f8ef5004dcba747e76a292bca24b7649bd9565c458741a6af58bb175b4a84cad38&page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    total = basesoup.find('div', class_='tz').find('input')['value']
                    index = total.index('/')
                    totalPages = int(total[index + 1:])
                    titleNode = basesoup.find('ul', class_='ri-list')
                    titleList = timeNode.find_all('li')
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

#54.福建省龙岩市财政局
def FJLongyanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://218.6.120.12:8081/was5/web/search?pertemplet=&token=&channelid=260439&searchword='
    siteURL = 'http://218.6.120.12:8081/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('福建省龙岩市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&searchscope=&orderby=RELEVANCE&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                total = basesoup.find('td', class_='t14')
                if re.search('(\d+)',total.text):
                    totalResults = int(re.search('(\d+)',total.text)[0])
                else:
                    titleList = []
                    break
                titleList = basesoup.find_all('td',class_='pad_l10')
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
                count += 1
                a = table.find('a')
                articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('td', attrs={'height':"40", 'style':"color:#7e7e7e;border-bottom:1px solid #dedbde"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'width':"953"}):
                            articleLocation = articleSoup.find('td', attrs={'width':"953"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省龙岩市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省龙岩市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&searchscope=&orderby=RELEVANCE&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag = 3
                    titleList = basesoup.find_all('td', class_='pad_l10')
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

#55.福建省宁德市财政局
def FJNingdeCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.ningde.gov.cn/was5/web/search?channelid=262447&templet=docs.jsp&sortfield=-docreltime&classsql=%25'
    siteURL = 'http://czj.ningde.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('福建省宁德市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '%25*siteid%3D24*siteid%3D24&prepage=5&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                titleList = []
                totalResults = int(re.search('(\d+)', r.text)[0])
                if totalResults == 0:
                    break
                regex = r"http:\/\/.*?\.htm"
                matches = re.finditer(regex, r.text)
                for matchNum, match in enumerate(matches):
                    if match.group() not in titleList:
                        titleList.append(match.group())
                flag = 3
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
                articleURL = table
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('h4'):
                            articleTitle = articleSoup.find('h4').text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div',class_='xl_tit')
                        if timeNode:
                            if timeNode.find('span'):
                                publishTime = timeNode.find('span').text.replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "nav_link"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "nav_link"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text
                        elif articleSoup.find('div', attrs={'class': 'xl_news_box'}):
                            articleText = articleSoup.find('div', attrs={'class': 'xl_news_box'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-福建省宁德市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('福建省宁德市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '%25*siteid%3D24*siteid%3D24&prepage=5&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    titleList = []
                    totalResults = int(re.search('(\d+)', r.text)[0])
                    if totalResults == 0:
                        break
                    regex = r"http:\/\/.*?\.htm"
                    matches = re.finditer(regex, r.text)
                    for matchNum, match in enumerate(matches):
                        if match.group() not in titleList:
                            titleList.append(match.group())
                    flag = 3
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

#56.山东省潍坊市财政局
def SDWeifangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.wfcz.gov.cn/search_'
    siteURL = 'http://www.wfcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('山东省潍坊市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '.jspx?q=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text,'lxml')
                titleNode = baseSoup.find('div', class_="main_left clearfix")
                titleList = titleNode.find_all('li')
                flag = 3
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.wfcz.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode =table.find('span')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '').replace('[','').replace(']','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "location"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "location"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content_c'}):
                            articleText = articleSoup.find('div', attrs={'class': 'content_c'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-山东省潍坊市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山东省潍坊市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '.jspx?q=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = baseSoup.find('div', class_="main_left clearfix")
                    titleList = titleNode.find_all('li')
                    flag = 3
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

#57.山东省威海市财政局
def SDWeihaiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.weihai.gov.cn/jrobot/search.do?webid=37&pg=12&p='
    siteURL = 'http://www.weihai.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('山东省威海市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Ccontent&od=&date=&date='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text,'lxml')
                titleList = baseSoup.find_all('div',class_='jsearch-result-box')
                total = baseSoup.find('div',attrs={'id':'jsearch-info-box'})
                try:
                    totalResults = int(total['data-total'])
                except Exception:
                    titleList = []
                    break
                flag = 3
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
                a = table.find('div',class_='jsearch-result-url').find('a')
                articleURL = a.text
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span',class_='jsearch-result-date')
                        if timeNode:
                            publishTime = timeNode.text.replace('-', '').replace('年', '').replace('月', '').replace('日', '').replace(' ', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'align':"right", 'style':"font-size:14px; color:#333;"}):
                            articleLocation = articleSoup.find('td', attrs={'align':"right", 'style':"font-size:14px; color:#333;"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleText = articleSoup.find('div', attrs={'id': 'zoom'}).text.replace(' ','')

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
                                    'site': '国家、省、市、区、县财政部门网站-山东省威海市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('山东省威海市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count>=totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Ccontent&od=&date=&date='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    titleList = baseSoup.find_all('div', class_='jsearch-result-box')
                    flag = 3
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

#58.河南省兰考县财政局
def HNLankaoCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.kfcz.gov.cn/searchEngine.do'
    siteURL = 'http://www.kfcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('河南省兰考县财政局' + '关键词：' + key)
        while flag < 3:
            #获取JSESSIONID
            try:
                r = requests.get(baseURL,headers=headers)
                set_cookie = dict(r.cookies._cookies)
                cookie = set_cookie['www.kfcz.gov.cn']['/']['JSESSIONID'].value
            except Exception as e:
                logger.error(e)

            try:
                headers1 = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                    'Cookie': cookie + '; undefined=undefined'
                }
                data = {'cicontentIndex':key}
                requestURL = baseURL
                r = requests.post(requestURL, data=data, headers=headers1)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text, 'lxml')
                if r.status_code == 404:
                    titleList = []
                    break
                total = baseSoup.find('td', attrs={'height':"28", 'colspan':"3", 'valign':"top", 'background':"./images/11.gif", 'bgcolor':"#FFFFFF"})
                totalResults = int(total.find_all('strong')[1].text)
                titleList = baseSoup.find_all('td', attrs={'height':"30", 'valign':"top"})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                articleURL = a['href'].rstrip('\n')
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('a', class_='green')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'style':"width:952px; float:left;  height:27px;"}):
                            articleLocation = articleSoup.find('div', attrs={'style':"width:952px; float:left;  height:27px;"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('table', attrs={'class': 'context'}):
                            articleText = articleSoup.find('table', attrs={'class': 'context'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-河南省兰考县财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('河南省兰考县财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    headers2 = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                        'Cookie': 'Hm_lvt_16534621cf4bf3aece06f70a56750d3e=1546002870; JSESSIONID='+cookie+'; undefined=undefined;'
                    }
                    data = {'siteidIndex': 0, 'cicontentIndex': key,'cititleIndex': key,'cikeyIndex': key,'cicontentIndex': key}
                    requestURL = baseURL+'?offset='+str(pageNum-1)
                    r = requests.post(requestURL, data=data, headers=headers2)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleList = baseSoup.find_all('td', attrs={'height': "30", 'valign': "top"})
                    flag = 3
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

#59.河南省汝州市财政局
def HNRuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.ruzhou.gov.cn/71.search.list.dhtml'
    siteURL = 'http://czj.ruzhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('河南省汝州市财政局' + '关键词：' + key)
        while flag < 3:
            # 获取JSESSIONID
            try:
                r = requests.get(baseURL, headers=headers)
                set_cookie = dict(r.cookies._cookies)
                cookie = set_cookie['czj.ruzhou.gov.cn']['/']['JSESSIONID'].value
            except Exception as e:
                logger.error(e)

            try:
                headers1 = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                    'Cookie': 'Hm_lvt_58b349fa2bbd6891b1a32ca7a3cf2f54=545959675,1546004252,1546343509; name=value; JSESSIONID='+cookie+'; Hm_lpvt_58b349fa2bbd6891b1a32ca7a3cf2f54=15461546343590'
                }
                data = {'keyword': key}
                requestURL = baseURL
                r = requests.post(requestURL, data=data, headers=headers1)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text, 'lxml')
                total = baseSoup.find('ul', attrs={'class':'pagination'})
                totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                if totalPages==0:
                    titlelist = []
                    break
                titleList = baseSoup.find_all('li', class_="list-group-item")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                articleURL = 'http://czj.ruzhou.gov.cn/'+a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+-\d+-\d+)', table.text):
                                publishTime = re.search('(\d+-\d+-\d+)', table.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('ol', class_="breadcrumb"):
                            articleLocation = articleSoup.find('ol', class_="breadcrumb").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'news'}):
                            articleText = articleSoup.find('div', attrs={'class': 'news'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-河南省汝州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('河南省汝州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    headers2 = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                        'Cookie': 'Hm_lvt_58b349fa2bbd6891b1a32ca7a3cf2f54=1545959675,1546004252,1546343509; name=value; JSESSIONID='+cookie+'; Hm_lpvt_58b349fa2bbd6891b1a32ca7a3cf2f54=1546343606'
                    }
                    data = {'page': pageNum, 'keyword': key}
                    requestURL = baseURL
                    r = requests.post(requestURL, data=data, headers=headers2)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleList = baseSoup.find_all('li', class_="list-group-item")
                    flag = 3
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

#60.河南省滑县财政局
def HNHuaxianCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://caizhengju.hnhx.gov.cn/ss.jsp?wbtreeid=1129&searchScope=0&currentnum='
    siteURL = 'http://caizhengju.hnhx.gov.cn/'
    dic = {'国企改革':'5Zu95LyB5pS56Z2p','国企改制':'5Zu95LyB5pS55Yi2','国企混改':'5Zu95LyB5re35pS5','国有企业改革':'5Zu95pyJ5LyB5Lia5pS56Z2p','国有企业改制':'5Zu95pyJ5LyB5Lia5pS55Yi2'}
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('河南省滑县财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&newskeycode2=' + dic[key]
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text, 'lxml')
                titleNode = baseSoup.find_all('table', attrs={'border':"0", 'cellpadding':"0", 'cellspacing':"1", 'class':"listFrame", 'width':"100%"})
                total = titleNode[len(titleNode)-1]
                if re.search('(\d+)', total.text):
                    totalResults = int(re.search('(\d+)', total.text)[0])
                else:
                    titlelist = []
                    break
                titleList = titleNode[1].find_all('a')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in table['href']:
                    articleURL = table['href']
                else:
                    articleURL = 'http://caizhengju.hnhx.gov.cn' + table['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('span', attrs={'class':"c112487_date"})
                        if timeNode:
                            if re.search('(\d+年\d+月\d+)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+)', timeNode.text)[0].replace('年', '').replace('月', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('table', attrs={'class':"winstyle112486"}):
                            articleLocation = articleSoup.find('table', attrs={'class':"winstyle112486"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'Section1'}):
                            articleText = articleSoup.find('div', attrs={'class': 'Section1'}).text
                        elif articleSoup.find('div', attrs={'class': 'WordSection1'}):
                            articleText = articleSoup.find('div', attrs={'class': 'WordSection1'}).text
                        elif articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                            articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-河南省滑县财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('河南省滑县财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&newskeycode2=' + dic[key]
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = baseSoup.find_all('table', attrs={'border': "0", 'cellpadding': "0", 'cellspacing': "1",
                                                                  'class': "listFrame", 'width': "100%"})
                    titleList = titleNode[1].find_all('a')
                    flag = 3
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

#61.河南省固始县财政局
def HNGushiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.gsxzf.gov.cn/cms/cmsadmin/infopub/search.jsp?templetid=1416682860341242&pubtype=S&pubpath=gsxrmzf&page='
    siteURL = 'http://www.gsxzf.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('河南省固始县财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum)+'&keywordencode='+key+'&keyword='+key+'&relation=0&webappcode=A01'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text, 'lxml')
                titleNode = baseSoup.find('div', attrs={'class': "l_zw04"})
                titleList = titleNode.find_all('li',class_='res-list')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.gsxzf.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "sp"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "l_zw02"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "l_zw02"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'l_zwnr_bodyzw'}):
                            articleText = articleSoup.find('div', attrs={'class': 'l_zwnr_bodyzw'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-河南省固始县财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('河南省固始县财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&keywordencode=' + key + '&keyword=' + key + '&relation=0&webappcode=A01'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = baseSoup.find('div', attrs={'class': "l_zw04"})
                    titleList = titleNode.find_all('li', class_='res-list')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#62.湖北省荆州市财政局
def HBJingzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.jzcz.gov.cn/search.jspx?q='
    siteURL = 'http://www.jzcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖北省荆州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                baseSoup = BeautifulSoup(r.text, 'lxml')
                titleNode = baseSoup.find('div', attrs={'class': "ss_con_b"})
                titleList = titleNode.find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.jzcz.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+-\d+-\d+)', table.text):
                            publishTime = re.search('(\d+-\d+-\d+)', table.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "yn_a"}):
                            articleLocation = articleSoup.find('div', attrs={'class': "yn_a"}).text

                        # 保存文章正文
                        articleText = ''
                        articleTextNode = articleSoup.find('div', attrs={'class': 'yn_b'})
                        if articleTextNode:
                            temp = articleTextNode.find('div',class_='yconent')
                            temp.decompose()
                            articleText = articleTextNode.text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖北省荆州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖北省荆州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    baseSoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = baseSoup.find('div', attrs={'class': "ss_con_b"})
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#63.湖北省荆门市财政局
def HBJingmenCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.jingmen.gov.cn/e/search/result/index.php?page='
    siteURL = 'http://czj.jingmen.gov.cn/'
    browser = webdriver.Chrome()
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖北省荆门市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                input = browser.find_element_by_name("keyboard")
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                r = browser.page_source
                basesoup = BeautifulSoup(r,'lxml')
                if '没有搜索到相关的内容' in basesoup.text:
                    titleList = []
                    break
                url = browser.current_url
                searchid = re.search('searchid=(\d+)',url)[1]#获得网站服务器缓存的结果id
                requestURL = baseURL + str(pageNum-1) + '&searchid=' + searchid
                r = requests.get(requestURL,headers=headers)
                r.encoding=r.apparent_encoding
                basesoup = BeautifulSoup(r.text,'lxml')
                titleList = basesoup.find_all('h2',class_='ssbt')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.jingmen.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div',class_='ys')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = '荆门市财政局'

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'content'}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖北省荆门市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖北省荆门市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum - 1) + '&searchid=' + searchid
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('h2', class_='ssbt')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
        logger.info('搜索间隔等待30秒')
        sleep(30)#网站两次搜索间隔30秒
    logger.info("finish")
    browser.close()
    return;

#64.湖北省恩施州财政局
def HBEnshiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://app.enshi.cn/?app=search&controller=index&action=search&type=all&mode=full&catid=362&wd='
    siteURL = 'http://app.enshi.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖北省荆门市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&order=time&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleList = basesoup.find_all('li', class_="article-picture-item")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_='time')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'id':'bread'}):
                            articleLocation = articleSoup.find('div', attrs={'id':'bread'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "article-detail-inner article-relevance clear"}):
                            articleText = articleSoup.find('div', attrs={'class': "article-detail-inner article-relevance clear"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖北省恩施州财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖北省恩施州财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&order=time&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('li', class_="article-picture-item")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#65.湖南省长沙市财政局
def HNChangshaCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://media.changsha.gov.cn:8088/search/search?jsoncallback=objs&siteid=129&q='
    siteURL = 'http://csczj.changsha.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖南省长沙市财政局' + '关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&&start=' + str(pageNum-1) + '&rows=5&_=1546505829412'
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                regex = r"http:\/\/.*?\.html"
                matches = re.finditer(regex, r.text)
                titleList = []
                for matchNum, match in enumerate(matches):
                    if match.group() not in titleList:
                        titleList.append(match.group())
                if re.search('"counts" :(\d+)',r.text):
                    totalResults = int(re.search('"counts" :(\d+)',r.text)[1])
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                articleURL = table
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        if articleSoup.find('div', class_='title'):
                            articleTitle = articleSoup.find('div', class_='title').text
                        elif articleSoup.h4:
                            articleTitle = articleSoup.h4.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('div', class_='gl-top'):
                            if articleSoup.find('div', class_='gl-top').find('span'):
                                timeNode = articleSoup.find('div', class_='gl-top').find('span')
                                if re.search('(\d+-\d+-\d+)', timeNode.text):
                                    publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')
                        elif articleSoup.find('div', class_='date'):
                            timeNode = articleSoup.find('div', class_='date')
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'main-box'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'main-box'}).text
                        elif articleSoup.find('div', attrs={'class': 'loc'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'loc'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "gl-box"}):
                            articleText = articleSoup.find('div', attrs={'class': "gl-box"}).text
                        elif articleSoup.find('div', attrs={'class': "con"}):
                            articleText = articleSoup.find('div', attrs={'class': "con"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖南省长沙市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖南省长沙市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&&start=' + str(pageNum - 1) + '&rows=5&_=1546505829412'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    regex = r"http:\/\/.*?\.html"
                    matches = re.finditer(regex, r.text)
                    titleList = []
                    for matchNum, match in enumerate(matches):
                        if match.group() not in titleList:
                            titleList.append(match.group())
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#66.湖南省湘潭市财政局
def HNXiangtanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://cz.xiangtan.gov.cn/fulltextsearch/rest/getfulltextdata?format=json&wd='
    siteURL = 'http://cz.xiangtan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖南省湘潭市财政局' + '关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pn=' + str(pageNum - 1) + '&rn=5&cl=150&idx_cgy=xtczj%7Cxtzzbsfw'
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                basesoup = json.loads(r.text)
                totalResults = int(basesoup['result']['totalcount'])
                titleList = basesoup['result']['records']
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                a = table['link']
                if 'http://' in a:
                    articleURL = a
                elif '=' in a:
                    ind = a.index('/')
                    articleURL = 'http://cz.xiangtan.gov.cn' + a[ind:]
                else:
                    articleURL = 'http://cz.xiangtan.gov.cn' + a
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+-\d+-\d+)', table['date']):
                            publishTime = re.search('(\d+-\d+-\d+)', table['date'])[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'ewb-location'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'ewb-location'}).text.replace('\t','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':"ewb-info-copy"}):
                            articleText = articleSoup.find('div', attrs={'class':"ewb-info-copy"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖南省湘潭市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖南省湘潭市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pn=' + str(pageNum - 1) + '&rn=5&cl=150&idx_cgy=xtczj%7Cxtzzbsfw'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    basesoup = json.loads(r.text)
                    titleList = basesoup['result']['records']
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#67.湖南省岳阳市财政局
def HNYueyangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    headers1 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                'Cookie':'HttpOnly; insert_cookie=98184645; RUMS_SESSIONID=05BFB92B73C1CE6F93D381056A7C59D4; HttpOnly; BA6EC46FBE8E3AB22FF53BB4F218C4BE=%E5%9B%BD%E4%BC%81%E6%94%B9%E9%9D%A9%23%E5%9B%BD%E4%BC%81%E6%94%B9%E5%88%B6'}
    baseURL = 'http://www.yueyang.gov.cn/creatorCMS/searchManage/searchProcess.page'
    baseURL1 = 'http://www.yueyang.gov.cn/cms/searchManage/search_results.jsp?siteId=1&indexId=77&suffix=&sort=relevance&sortType=true&field=all&dayTime=&categories=-1&advanceTag=0&dayEnd=&dayBegin=&isInResult=&pager.offset=10&pager.desc=false'
    siteURL = 'http://czj.yueyang.gov.cn/'
    browser = webdriver.Chrome()
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖南省岳阳市财政局' + '关键词：' + key)
        count = 0
        while flag < 3:
            try:
                browser.get(siteURL)
                input = browser.find_element_by_class("sch_input")
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                r = browser.page_source
                tmpkey = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\', '').replace('x', '%')
                data = {'querryString':tmpkey,
                        'siteid':1,
                        'advanceTag':0,
                        'andor':'OR',
                        'indexid':77,
                        'categories':-1}
                r = requests.post(baseURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding

                print(r.text)
                basesoup = json.loads(r.text)
                totalResults = int(basesoup['result']['totalcount'])
                titleList = basesoup['result']['records']
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                a = table['link']
                if 'http://' in a:
                    articleURL = a
                elif '=' in a:
                    ind = a.index('/')
                    articleURL = 'http://cz.xiangtan.gov.cn' + a[ind:]
                else:
                    articleURL = 'http://cz.xiangtan.gov.cn' + a
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+-\d+-\d+)', table['date']):
                            publishTime = re.search('(\d+-\d+-\d+)', table['date'])[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'ewb-location'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'ewb-location'}).text.replace(
                                '\t', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "ewb-info-copy"}):
                            articleText = articleSoup.find('div', attrs={'class': "ewb-info-copy"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖南省岳阳市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖南省岳阳市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pn=' + str(pageNum - 1) + '&rn=5&cl=150&idx_cgy=xtczj%7Cxtzzbsfw'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = 'utf-8'
                    basesoup = json.loads(r.text)
                    titleList = basesoup['result']['records']
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#68.湖南省常德市财政局
def HNChangdeCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.changde.gov.cn/jrobot/search.do?webid=1&pg=12&p='
    siteURL = 'http://czj.changde.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖南省常德市财政局' + '关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Ccontent&od=2&date=&date='
                r = requests.get(requestURL, headers = headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div',attrs={'id':'jsearch-info-box'})
                try:
                    totalResults = int(total['data-total'])
                except Exception:
                    titleList = []
                    break
                titleList = basesoup.find_all('div',class_='jsearch-result-box')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://gzw.changde.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span',class_='jsearch-result-date')
                        if timeNode:
                            if re.search('(\d+年\d+月\d+)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+)', timeNode.text)[0].replace('年', '').replace('月', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'ty_lm2'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'ty_lm2'}).text
                        elif articleSoup.find('div', attrs={'class': 'wz_dqwz'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'wz_dqwz'}).text
                        elif articleSoup.find('div', attrs={'class': 'BreadcrumbNav'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'BreadcrumbNav'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': "zoom"}):
                            articleText = articleSoup.find('div', attrs={'id': "zoom"}).text
                        elif articleSoup.find('div', attrs={'class': "pages_content"}):
                            articleText = articleSoup.find('div', attrs={'class': "pages_content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖南省常德市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖南省常德市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Ccontent&od=2&date=&date='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', class_='jsearch-result-box')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#69.湖南省娄底市财政局
def HNLoudiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://search.hnloudi.gov.cn/search.aspx?q='
    siteURL = 'http://search.hnloudi.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('湖南省娄底市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&s=czj&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleList = basesoup.find_all('div', class_='item')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find_all('div', class_='i-info')[1]
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.h3:
                            articleLocation = articleSoup.h3.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-湖南省娄底市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('湖南省娄底市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&s=czj&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', class_='item')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#70.广西壮族自治区南宁市财政局
def GXNanningCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://search.nanning.gov.cn/igs/front/search.jhtml?code=f24ebd4f8cb34d008a2cc9286e0641de&pageNumber='
    siteURL = 'http://search.nanning.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广西壮族自治区南宁市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&pageSize=10&searchWord=' + key + '&siteId=41'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = json.loads(r.text)
                totalResults = int(basesoup['page']['total'])
                titleList = basesoup['page']['content']
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                articleURL = table['url']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table['trs_time']
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div',class_='breakcrumb ma'):
                            articleLocation = articleSoup.find('div',class_='breakcrumb ma').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text
                        elif articleSoup.find('div', attrs={'class': "pages_content"}):
                            articleText = articleSoup.find('div', attrs={'class': "pages_content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区南宁市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区南宁市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&pageSize=10&searchWord=' + key + '&siteId=41'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = json.loads(r.text)
                    titleList = basesoup['page']['content']
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#71.广西壮族自治区柳州市财政局
def GXLiuzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://so.liuzhou.gov.cn/was5/web/search?page='
    siteURL = 'http://www.lzscz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广西壮族自治区柳州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&channelid=10000000&searchword='+key+'&keyword='+key+'&orderby=-DocRelTime&was_custom_expr=%28'+key+'%29+and+%28siteid%3D227%29&perpage=10&outlinepage=10&siteid=227&searchscope=&timescope=&timescopecolumn=&orderby=-DocRelTime&andsen=&total=&orsen=&exclude='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text,'lxml')
                totalResults = int(basesoup.find('td',class_='search_result').find('span',attrs={'style':'color:red'}).text)
                titleList = basesoup.find_all('span',class_='js_zi2')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('span',class_='releaseTime')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='czj-position'):
                            articleLocation = articleSoup.find('div', class_='czj-position').text.replace('\t','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            if articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style'):
                                tmp = articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区柳州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区柳州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=10000000&searchword=' + key + '&keyword=' + key + '&orderby=-DocRelTime&was_custom_expr=%28' + key + '%29+and+%28siteid%3D227%29&perpage=10&outlinepage=10&siteid=227&searchscope=&timescope=&timescopecolumn=&orderby=-DocRelTime&andsen=&total=&orsen=&exclude='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('td', class_='js_zi')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#72.广西壮族自治区桂林市财政局
def GXGuilinCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.guilin.gov.cn/search'
    siteURL = 'http://czj.guilin.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广西壮族自治区桂林市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL
                data = {'page1': pageNum, 'doctitle': key, 'docchannel': 0}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                try:
                    total = basesoup.find('div',class_='main')
                    totalResults = int(total.find('font',attrs={'color':'#FF0000'}).text)
                except Exception:
                    titleList = []
                    break
                total.decompose()
                titleList = basesoup.find_all('div', class_='main')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.h6:
                            timeNode = articleSoup.h6.find('label')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.h2:
                            articleLocation = articleSoup.h2.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区桂林市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区桂林市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL
                    data = {'page1': pageNum, 'doctitle': key, 'docchannel': 0}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    total = basesoup.find('div', class_='main')
                    total.decompose()
                    titleList = basesoup.find_all('div', class_='main')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#73.广西壮族自治区防城港市财政局
def GXFangchenggangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.fcgs.gov.cn/search?q='
    siteURL = 'http://www.fcgs.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广西壮族自治区防城港市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&sid=23&st=pubtime&pg=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='info_right')
                totalResults = int(total.find('span', attrs={'style': 'color:red'}).text)
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div',class_='content_right')
                titleList = titleNode.find_all('table', class_='result')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('font',class_='dateShow')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区防城港市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区防城港市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&sid=23&st=pubtime&pg=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('div', class_='content_right')
                    titleList = titleNode.find_all('table', class_='result')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#74.广西壮族自治区钦州市财政局
def GXQinzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.qzcz.gov.cn/s/index.php?kw='
    siteURL = 'http://www.qzcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广西壮族自治区钦州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleNode = basesoup.find('div', class_='Page_search_result').find('ul')
                if '没有找到您要搜索的内容' in titleNode.text:
                    titleList = []
                    break
                titleList = titleNode.find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('p', class_='pld')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('ul',class_='Path'):
                            articleLocation = articleSoup.find('ul',class_='Path').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('ul', attrs={'class': "txt"}):
                            articleText = articleSoup.find('ul', attrs={'class': "txt"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区钦州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区钦州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            try:
                tmp = basesoup.find('p',class_='pagelist').find_all('a')
                nextp = tmp[len(tmp)-1]
                if 'disabled' in nextp['class']:
                    break
            except Exception:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('div', class_='Page_search_result').find('ul')
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#75.广西财政厅
def GXCaizhengting():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.gxcz.gov.cn:8080/index.php?sids=0&c=so&q='
    siteURL = 'http://www.gxcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广西财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pn=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleList = basesoup.find_all('h3')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                a.decompose()
                a = table.find('a')
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.gxcz.gov.cn:8080/index.php'+a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='crumb'):
                            articleLocation = articleSoup.find('div', class_='crumb').text.replace('\t','').replace(' ','').replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            if articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style'):
                                tmp = articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pn=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('h3')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#76.广西壮族自治区贺州市财政局
def GXHezhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.gxczkj.gov.cn/search_'
    siteURL = 'http://www.gxczkj.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广西壮族自治区贺州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '.jspx?q=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div',class_='search_msg').find_all('span',class_='red')[1]
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('dl', class_='list3')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                tmp = table.find('span')
                tmp.decompose()
                a = table.find('a')
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.gxczkj.gov.cn' + a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div', class_='msgbar')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='position cb5'):
                            articleLocation = articleSoup.find('div', class_='position cb5').text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "content"}):
                            articleText = articleSoup.find('div', attrs={'class': "content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区贺州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区贺州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '.jspx?q=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('dl', class_='list3')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#77.广西壮族自治区来宾市财政局
def GXLaibinCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.laibin.gov.cn/LBFront/lbzy/ShowInfo/SearchResult.aspx?searchtext='
    siteURL = 'http://www.laibin.gov.cn/LBFront/'
    browser = webdriver.Chrome()
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广西壮族自治区来宾市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                browser.set_page_load_timeout(5)
                input = browser.find_element_by_class_name("txt1")
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                browser.implicitly_wait(5)
                browser.switch_to_window(browser.window_handles[1])
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'html5lib')
                titleNode = basesoup.find('table', attrs={'id':'SearchResult1_DataGrid1'})
                if not titleNode:
                    titleList = []
                    break
                total = basesoup.find('div',class_='pagemargin').find('td',class_='huifont').text
                totalPages = int(re.search('\d+/(\d+)',total)[1])
                titleList = titleNode.find_all('tr', attrs={'valign':'top'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.laibin.gov.cn/LBFront/' + a['href'].lstrip('../..//')
                flag = 0
                #如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        #网页跳转
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        tmpstr = str(article.text)
                        try:
                            articleURL = re.search('(http://.*\.htm)',tmpstr)[0]
                        except Exception:
                            flag = 3
                            break
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace(' ','').replace('\n','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('td', attrs={'align':'right'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='BreadcrumbNav'):
                            articleLocation = articleSoup.find('div', class_='BreadcrumbNav').text.replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "pages_content"}):
                            articleText = articleSoup.find('div', attrs={'class': "pages_content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-广西壮族自治区来宾市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广西壮族自治区来宾市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    tmpkey = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%')
                    requestURL = baseURL + tmpkey + '&searchtype=title&Paging=' + str(pageNum)
                    browser.get(requestURL)
                    browser.implicitly_wait(5)
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'html5lib')
                    titleNode = basesoup.find('table', attrs={'id': 'SearchResult1_DataGrid1'})
                    if not titleNode:
                        titleList = []
                        break
                    titleList = titleNode.find_all('tr', attrs={'valign': 'top'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
        #关闭当前窗口句柄，并切换回第一个窗口，搜索下一个关键词
        browser.close()
        browser.switch_to.window(browser.window_handles[0])
    browser.close()
    logger.info("finish")
    return;

#78.海南省三亚市财政厅
def HNSanyaCZT():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://118.178.151.173/s?q=1&qt='
    siteURL = 'http://mof.sanya.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('海南省三亚市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL+key+'&pageSize=10&database=all&siteCode=4602000030&docQt=&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div',class_='bottom posa').find('div',attrs={'style':'float: right;color: #666;'}).text
                if re.search('(\d+)',total):
                    totalResults = int(re.search('(\d+)',total)[0])
                    if totalResults == 0:
                        titleList = []
                        break
                titleList = basesoup.find_all('div', attrs={'class': 'titleP'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://118.178.151.173/' + a['href'].replace('\n','')
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        # 网页跳转
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        tmpsoup = BeautifulSoup(article.text,'lxml')
                        articleURL = tmpsoup.find('script', attrs={'type':"text/javascript"}).text.replace('\r','').replace('\n','').replace('"','').replace('location.href = ','').replace(';','')
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.head:
                            if articleSoup.head.find('meta', attrs={'name':'PubDate'}):
                                timeNode = articleSoup.head.find('meta', attrs={'name':'PubDate'})['content']
                        elif articleSoup.find('publishtime'):
                            timeNode = articleSoup.find('publishtime').text
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='crumbs'):
                            articleLocation = articleSoup.find('div', class_='crumbs').text.replace('\r', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "pages_content"}):
                            if articleSoup.find('div', attrs={'class': "pages_content"}).find('style'):
                                tmp = articleSoup.find('div', attrs={'class': "pages_content"}).find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', attrs={'class': "pages_content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-海南省三亚市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('海南省三亚市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pageSize=10&database=all&siteCode=4602000030&docQt=&page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', attrs={'class': 'titleP'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#79.海南省海口市财政厅
def HNHaikouCZT():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.haikou.gov.cn/HaiKou/f/search?title='
    siteURL = 'http://www.haikou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('海南省海口市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&type=search&order_time_asc=&order_time_desc=&startTime=2000-1-1&endTime=2019-1-10&content=&pageNum=' + str(pageNum) + '&organization=&radio_pace=1'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='resultCount').find_all('em')
                totalPages = int(total[1].text)
                if totalPages == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('div', attrs={'class': 'resultOne'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        tmp = a.find_all('em')
                        for tmpem in tmp:
                            tmpem.decompose()#去掉多余的数字编号
                        articleTitle = a.text.replace('.','').replace(' ','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+年\d+月\d+)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+)', timeNode.text)[0].replace('年', '').replace('月', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_='navpath'):
                            articleLocation = articleSoup.find('div', class_='navpath').text
                        elif articleSoup.find('div', attrs={'id':'navbar'}):
                            articleLocation = articleSoup.find('div', attrs={'id':'navbar'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "TRS_Editor"}):
                            if articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style'):
                                tmp = articleSoup.find('div', attrs={'class': "TRS_Editor"}).find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', attrs={'class': "TRS_Editor"}).text
                        elif articleSoup.find('div', attrs={'class': "maincon-c"}):
                            articleText = articleSoup.find('div', attrs={'class': "maincon-c"}).text
                        elif articleSoup.find('div', attrs={'class': "content"}):
                            articleText = articleSoup.find('div', attrs={'class': "content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-海南省海口市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('海南省海口市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&type=search&order_time_asc=&order_time_desc=&startTime=2000-1-1&endTime=2019-1-10&content=&pageNum=' + str(
                        pageNum) + '&organization=&radio_pace=1'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', attrs={'class': 'resultOne'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#80.重庆市渝中区财政局
def CQYuzhongquCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://jcz.cq.gov.cn/Search.asp?Key='
    siteURL = 'http://jcz.cq.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('重庆市渝中区财政局' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%')
                requestURL = baseURL + tmpkey + '&Sort=0&sMod=title&startdate=&enddate=&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='page').find_all('span')
                if not total:
                    titleList = []
                    break
                totalPages = int(re.search('(\d+)',total[len(total)-1].text)[0])
                titleList = basesoup.find_all('div', attrs={'class': 'item'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://jcz.cq.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div',class_='item-time')
                        if timeNode:
                            if re.search('(\d+年\d+月\d+)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+)', timeNode.text)[0].replace('年', '').replace('月',
                                                                                                                    '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'id':'position1'}):
                            articleLocation = articleSoup.find('div', attrs={'id':'position1'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': "showcontent"}):
                            articleText = articleSoup.find('div', attrs={'id': "showcontent"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-重庆市渝中区财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('重庆市渝中区财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    tmpkey = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\', '').replace('x', '%')
                    requestURL = baseURL + tmpkey + '&Sort=0&sMod=title&startdate=&enddate=&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    totalPages = int(re.search('(\d+)', total[len(total) - 1].text)[0])
                    titleList = basesoup.find_all('div', attrs={'class': 'item'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#81.四川省成都市财政局
def SCChengduCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.chenghua.gov.cn/search/s?q=1&qt='
    siteURL = 'http://www.chenghua.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('四川省成都市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pageSize=10&database=all&siteCode=5101000030&docQt=&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='bottom posa').find('div',attrs={'style':'float: right;color: #666;'})
                if total:
                    if re.search('(\d+)',total.text):
                        totalResults = int(re.search('(\d+)',total.text)[0])
                        if totalResults == 0:
                            titleList = []
                            break
                titleList = basesoup.find_all('div', attrs={'class': 'msg discuss'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.chenghua.gov.cn/search/' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        # 网页跳转
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        tmpsoup = BeautifulSoup(article.text, 'lxml')
                        articleURL = tmpsoup.find('script', attrs={'type': "text/javascript"}).text.replace('\r',
                                                                                                            '').replace(
                            '\n', '').replace('"', '').replace('location.href = ', '').replace(';', '')
                        if 'http://' not in articleURL:
                            articleURL = 'http://cdcz.chengdu.gov.cn' + articleURL

                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace('\n','').replace('\r','').replace(' ','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_='colo-666')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'dqwz'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'dqwz'}).text.replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('table', attrs={'id': "myTable"}):
                            articleText = articleSoup.find('table', attrs={'id': "myTable"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-四川省成都市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('四川省成都市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pageSize=10&database=all&siteCode=5101000030&docQt=&page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', attrs={'class': 'msg discuss'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#82.四川省阿坝州财政局
def SCAbazhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://xxgk.abazhou.gov.cn:8080/Search.aspx?title='
    siteURL = 'http://www.abcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('四川省阿坝州财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&askCode=&page=' + str(pageNum-1)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                titleList = basesoup.find_all('tr', attrs={'style': 'height:15px;','align':'center'})
                del titleList[0]
                if len(titleList) >= 1:
                    del titleList[len(titleList)-1]
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://xxgk.abazhou.gov.cn:8080/' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find_all('td', attrs={'style':'background-color:#ffffff;color:#d30000'})
                        if len(timeNode)>=3:
                            if re.search('(\d+-\d+-\d+)', timeNode[2].text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode[2].text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'height':"28", 'align':"left", 'background':"images/20100730wj_xxgk_17.jpg", 'bgcolor':"#FFFFFF"}):
                            articleLocation = articleSoup.find('td', attrs={'height':"28", 'align':"left", 'background':"images/20100730wj_xxgk_17.jpg", 'bgcolor':"#FFFFFF"}).text.replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': "Content"}):
                            articleText = articleSoup.find('div', attrs={'id': "Content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-四川省阿坝州财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('四川省阿坝州财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&askCode=&page=' + str(pageNum - 1)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'html5lib')
                    titleList = basesoup.find_all('tr', attrs={'style': 'height:15px;', 'align': 'center'})
                    del titleList[0]
                    if len(titleList) >= 1:
                        del titleList[len(titleList) - 1]
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#83.四川省泸州市财政局
def SCGuangyuanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.luzhou.gov.cn/s?sid=1&wd='
    siteURL = 'http://czj.luzhou.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('四川省泸州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div',class_='result-info')
                if re.search('(\d+)',total.text):
                    totalResults = int(re.search('(\d+)',total.text)[0])
                    if totalResults == 0:
                        titleList = []
                        break
                titleNode = basesoup.find('div',class_='result-list article result-list information clearfix')
                titleList = titleNode.find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace(' ','').replace('\r','').replace('\n','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', attrs={'class': 'attribution'})
                        if re.search('(\d+/\d+/\d+)', timeNode.text):
                            timeNode = re.search('(\d+/\d+/\d+)', timeNode.text)[0]
                            eles = timeNode.split('/')
                            for each in eles:
                                if int(each) < 10:
                                    publishTime += '0'+each
                                else:
                                    publishTime += each

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class':'path'}):
                            articleLocation = articleSoup.find('div', attrs={'class':'path'}).text.replace('\r','').replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "conTxt"}):
                            articleText = articleSoup.find('div', attrs={'class': "conTxt"}).text
                        elif articleSoup.find('div', attrs={'id': "content"}):
                            articleText = articleSoup.find('div', attrs={'id': "content"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-四川省泸州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('四川省泸州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('div', class_='result-list article result-list information clearfix')
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#84.四川省南充市财政局
def SCNanchongCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.nccz.gov.cn/view/searchlist?title='
    siteURL = 'http://www.nccz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('四川省南充市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='fenye').find('span')
                if re.search('(\d+)', total.text):
                    totalPages = int(re.search('(\d+)', total.text)[0])
                    if totalPages == 0:
                        titleList = []
                        break
                titleNode = basesoup.find('ul', class_='listpage')
                titleList = titleNode.find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table
                        if re.search('(\d+-\d+-\d+)', timeNode.text):
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'left'}).find('div',attrs={'style':'float:left; height:40px;line-height:50px'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'left'}).find('div',attrs={'style':'float:left; height:40px;line-height:50px'}).text.replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'style': "align:center; text-align:left; float:left;width:90%;margin-left: 2px;font-size: 12px;line-height: 28px;margin-top:20px"}):
                            articleText = articleSoup.find('div', attrs={'style': "align:center; text-align:left; float:left;width:90%;margin-left: 2px;font-size: 12px;line-height: 28px;margin-top:20px"}).text

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
                                    'site': '国家、省、市、区、县财政部门网站-四川省南充市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('四川省南充市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('ul', class_='listpage')
                    titleList = titleNode.find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#85.云南省昆明市财政局
def YNKunmingCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.km.gov.cn/zcms/search/result?Query='
    siteURL = 'http://czj.km.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('云南省昆明市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&SiteID=239&AllSite=&TitleOnly=N&usingSynonym=N&PageIndex=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                totalResults = int(basesoup.find('div', class_='crumb').find('b').text)
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('div', class_='searchResults')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('font', color='#1a7b2e')
                        if re.search('(\d+-\d+-\d+)', timeNode.text):
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'info ui-float-right'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'info ui-float-right'}).text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='content-box'):
                            articleText = articleSoup.find('div', class_='content-box').text
                        elif articleSoup.find('div', class_='wrap'):
                            articleText = articleSoup.find('div', class_='wrap').text

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
                                    'site': '国家、省、市、区、县财政部门网站-云南省昆明市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('云南省昆明市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&SiteID=239&AllSite=&TitleOnly=N&usingSynonym=N&PageIndex=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', class_='searchResults')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#86.陕西省咸阳市财政局
def SXXianyangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.xys.gov.cn/search/searchResultGJ.jsp?q='
    siteURL = 'http://czj.xys.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('陕西省咸阳市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&t_id=1494&image=搜索&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleList = basesoup.find('div',id='NewsList').find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if re.search('(\d+-\d+-\d+)', timeNode.text):
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'zy_left_tr'}):
                            articleLocation = articleSoup.find('div',attrs={'class': 'zy_left_tr'}).text.replace('\n', '').replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='zy_left_con1'):
                            if articleSoup.find('div', id='zy_left_con1').find('td',style='padding:5px 0px;'):
                                articleText = articleSoup.find('div', id='zy_left_con1').find('td',style='padding:5px 0px;').text

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
                                    'site': '国家、省、市、区、县财政部门网站-陕西省咸阳市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('陕西省咸阳市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&t_id=1494&image=搜索&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find('div', id='NewsList').find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#87.陕西省铜川市财政局
def SXTongchuanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.tccz.gov.cn/home_front_searchList.do'
    siteURL = 'http://www.tccz.gov.cn/'
    Dict={'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('陕西省铜川市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                data = {'keyStr':key,'typeStr':'18','pageNo':pageNum}
                r = requests.post(baseURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div',class_='finan_listd1').find('h2')
                if total:
                    tmp = total.text.split('，')
                    if re.search('(\d+)',tmp[1]):
                        totalPages = int(re.search('(\d+)',tmp[1])[0])
                titleList = basesoup.find('div', class_='finan_listc3').find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.tccz.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('div', class_='finan_listc5').find('h2')
                        eles = timeNode.text.split(' ')
                        publishTime = eles[5]+eles[2]+Dict[eles[1]]

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'finan_lista1'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'finan_lista1'}).text.replace('\n','').replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='zoom'):
                            articleText = articleSoup.find('div', id='zoom').text

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
                                    'site': '国家、省、市、区、县财政部门网站-陕西省铜川市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('陕西省铜川市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    data = {'keyStr': key, 'typeStr': '18', 'pageNo': pageNum}
                    r = requests.post(baseURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find('div', class_='finan_listc3').find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
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

#88.陕西省渭南市财政局
def SXWeinanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    siteURL = 'http://www.wnf.gov.cn/'
    browser = webdriver.Chrome()
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('陕西省渭南市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                browser.set_page_load_timeout(5)
                input = browser.find_element_by_name("INTEXT")
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                sleep(5)
                r = browser.page_source
                basesoup = BeautifulSoup(r,'lxml')
                if basesoup.find('img', src='/system/resource/code/news/newsearch/createimage.jsp'):
                    print('图形验证码，等待30秒')
                    sleep(30)
                    continue
                browser.switch_to.window(browser.window_handles[1])
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'html5lib')
                total = basesoup.find('td',nowrap='',align='left',width='1%')
                if re.search('\d+/(\d+)',total.text):
                    totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                    if totalPages == 0:
                        titleList = []
                        break
                titleList = basesoup.find('form',attrs={'method':'post','name':'a1401','action':'/sousuo.jsp?wbtreeid=1001'}).find('ul').find_all('li')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.wnf.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('table', class_='winstyle1304'):
                            articleLocation = articleSoup.find('table', class_='winstyle1304').text.replace('\n', '').replace('\r', '').replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='vsb_newscontent'):
                            articleText = articleSoup.find('div', id='vsb_newscontent').text

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
                                    'site': '国家、省、市、区、县财政部门网站-陕西省渭南市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('陕西省渭南市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    button = browser.find_element_by_class_name('Next')
                    button.click()
                    sleep(5)
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'html5lib')
                    titleList = basesoup.find('form', attrs={'method': 'post', 'name': 'a1401',
                                                             'action': '/sousuo.jsp?wbtreeid=1001'}).find(
                        'ul').find_all('li')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
        browser.close()
        browser.switch_to.window(browser.window_handles[0])
    browser.close()
    logger.info("finish")
    return;

#89.甘肃省兰州市财政局
def GSLanzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    siteURL = 'http://www.lzcz.gov.cn/'
    browser = webdriver.Chrome()
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('甘肃省兰州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                browser.set_page_load_timeout(5)
                input = browser.find_element_by_name("INTEXT")
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                sleep(5)
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'lxml')
                if basesoup.find('img', src='/system/resource/code/news/newsearch/createimage.jsp'):
                    print('图形验证码，等待30秒')
                    sleep(30)
                    continue
                browser.switch_to.window(browser.window_handles[1])
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'html5lib')
                total = basesoup.find('td', nowrap='', align='left', width='1%')
                if re.search('\d+/(\d+)', total.text):
                    totalPages = int(re.search('\d+/(\d+)', total.text)[1])
                    if totalPages == 0:
                        titleList = []
                        break
                titleList = basesoup.find_all('tr', attrs={'class': 'listContentBright'})
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.lzcz.gov.cn/' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace('\n','').replace(' ', '')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span',class_='timestyle1583')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('table', class_='winstyle1577'):
                            articleLocation = articleSoup.find('table', class_='winstyle1577').text.replace('\n','').replace('\r', '').replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='vsb_content_501'):
                            articleText = articleSoup.find('div', id='vsb_content_501').text

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
                                    'site': '国家、省、市、区、县财政部门网站-甘肃省兰州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('甘肃省兰州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    button = browser.find_element_by_class_name('Next')
                    button.click()
                    sleep(5)
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'html5lib')
                    titleList = basesoup.find_all('tr', attrs={'class': 'listContentBright'})
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
        browser.close()
        browser.switch_to.window(browser.window_handles[0])
    browser.close()
    logger.info("finish")
    return;

#90.甘肃省嘉峪关市财政局
def GSJiayuguanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.jyg.gov.cn/search/search.jsp'
    siteURL = 'http://czj.jyg.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('甘肃省嘉峪关市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = quote(key, 'utf-8')
                data = {'searchword': tmpkey, 'pagestr': pageNum, 'pagenum': 10, 'siteid': 13}
                r = requests.post(baseURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                totalPages = int(basesoup.find('allpages').text)
                titleList = basesoup.find_all('row')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                a = table.find('url')
                if 'http://' in a.text:
                    articleURL = a.text
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = articleSoup.h1.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('time')
                        if timeNode:
                            publishTime = timeNode.text.replace('.','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'gl-nav'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'gl-nav'}).text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='TRS_Editor'):
                            if articleSoup.find('div', class_='TRS_Editor').find('style'):
                                tmp = articleSoup.find('div', class_='TRS_Editor').find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', class_='TRS_Editor').text

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
                                    'site': '国家、省、市、区、县财政部门网站-甘肃省嘉峪关市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('甘肃省嘉峪关市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    data = {'searchword': tmpkey, 'pagestr': pageNum, 'pagenum': 10, 'siteid': 13}
                    r = requests.post(baseURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'html5lib')
                    titleList = basesoup.find_all('row')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#91.甘肃省金昌市财政局
def GSJinchangCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.jc.gansu.gov.cn/module/sitesearch/index.jsp?keyword=vc_title&columnid=0&keyvalue='
    siteURL = 'http://czj.jc.gansu.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('甘肃省金昌市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&webid=17&modalunitid=78842&currpage=' +str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('td', align="right", style="padding-right:15px;color:#0064CC")
                if re.search('(\d+)',total.text):
                    totalResults = int(re.search('(\d+)',total.text)[0])
                titleList = basesoup.find_all('td', height="23", align="left")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace('\n', '').replace(' ', '').replace('\r', '')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div', class_='article').find('span')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)',timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)',timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'currentpath'}):
                            articleLocation = articleSoup.find('div', attrs={'class': 'currentpath'}).text.replace('\n', '').replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='zoom'):
                            articleText = articleSoup.find('div', id='zoom').text

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
                                    'site': '国家、省、市、区、县财政部门网站-甘肃省金昌市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('甘肃省金昌市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&webid=17&modalunitid=78842&currpage=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('td', height="23", align="left")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#92.甘肃省天水市财政局
def GSTianshuiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.tssczj.gov.cn/search.asp?page='
    siteURL = 'http://www.tssczj.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('甘肃省天水市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = str(key.encode('gb2312')).lstrip('b\'').rstrip('\'').replace('\\','').replace('x','%')
                requestURL = baseURL + str(pageNum) + '&condition=title&keyword=' + tmpkey + '&Types=News'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleNode = basesoup.find('td', width="78%", colspan="2", bgcolor="#FFFFFF")
                tmp = titleNode.find('table', width="100%", border="0", cellspacing="0", cellpadding="6")
                tmp.decompose()
                titleList = titleNode.find_all('table', width="100%", border="0", cellspacing="0", cellpadding="0")
                del titleList[len(titleList)-1]
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                a.decompose()
                a = table.find('a')
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.tssczj.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace(' ', '')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('font', color='#999999')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', height="32", align="left", bgcolor="#FFFFD9"):
                            articleLocation = articleSoup.find('td', height="32", align="left", bgcolor="#FFFFD9").text.replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td', class_='nr'):
                            articleText = articleSoup.find('td', class_='nr').text

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
                                    'site': '国家、省、市、区、县财政部门网站-甘肃省天水市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('甘肃省天水市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&condition=title&keyword=' + tmpkey + '&Types=News'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('td', width="78%", colspan="2", bgcolor="#FFFFFF")
                    tmp = titleNode.find('table', width="100%", border="0", cellspacing="0", cellpadding="6")
                    tmp.decompose()
                    titleList = titleNode.find_all('table', width="100%", border="0", cellspacing="0", cellpadding="0")
                    del titleList[len(titleList) - 1]
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#93.甘肃省酒泉市财政局
def GSJiuquanCZJ():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.jiuquan.gov.cn/search.aspx'
    siteURL = 'http://czj.jiuquan.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('甘肃省酒泉市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = quote(key, 'utf-8')
                data={'keyword':tmpkey,'btn_send.x':13,'btn_send.y':7}
                requestURL = baseURL
                r = requests.post(requestURL, headers=headers, data=data)
                cookies = requests.utils.dict_from_cookiejar(r.cookies)#获取cookies
                headers1 = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
                    'Cookie': 'eZNews_X-Token=' + cookies['eZNews_X-Token'] + '; ASP.NET_SessionId=' + cookies[
                        'ASP.NET_SessionId']}
                r = requests.post(requestURL, headers=headers1, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                # 获取viewstate：
                viewstate = basesoup.find('input', type='hidden', id='__VIEWSTATE')['value']
                total = basesoup.find('span', id="labMsg")
                if re.search('(\d+)',total.text):
                    totalResults = int(re.search('(\d+)',total.text)[0])
                    if totalResults == 0:
                        titleList = []
                        break
                titleList = basesoup.find_all('div', class_="searchNewsTitle")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.jiuquan.gov.cn' + a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text.replace(' ', '').replace('\r', '').replace('\n', '')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('div', class_='textinfo')
                        if timeNode:
                            if re.search('(\d+年\d+月\d+)', timeNode.text):
                                publishTime = re.search('(\d+年\d+月\d+)', timeNode.text)[0].replace('年', '').replace('月', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="position_content"):
                            articleLocation = articleSoup.find('div', class_="position_content").text.replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='contents'):
                            articleText = articleSoup.find('div', class_='contents').text

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
                                    'site': '国家、省、市、区、县财政部门网站-甘肃省酒泉市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('甘肃省酒泉市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count>=totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    data = {'__VIEWSTATE': viewstate, '__VIEWSTATEGENERATOR': 'BBBC20B8', '__EVENTTARGET': 'pager', '__EVENTARGUMENT':str(pageNum), '__VIEWSTATEENCRYPTED':'','isWap':0, 'txtKeyword':tmpkey, 'categoryID':0}
                    r = requests.post(requestURL, headers=headers1, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('div', class_="searchNewsTitle")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#94.宁夏银川市财政局
def NXYinchuanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.yinchuan.gov.cn/was5/web/search?channelid=207312&searchword='
    siteURL = 'http://czj.yinchuan.gov.cn/'
    browser = webdriver.Chrome()
    browser.set_page_load_timeout(5)
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('宁夏银川市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key
                browser.get(requestURL)
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'lxml')
                totalResults = int(basesoup.find('span', class_="num").text)
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('div', class_="js-con")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.yinchuan.gov.cn' + a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+.\d+.\d+)', timeNode.text):
                                publishTime = re.search('(\d+.\d+.\d+)', timeNode.text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="persite"):
                            articleLocation = articleSoup.find('div', class_="persite").text
                        elif articleSoup.find('div', class_="la2nav"):
                            articleLocation = articleSoup.find('div', class_="la2nav").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='con'):
                            articleText = articleSoup.find('div', class_='con').text
                        elif articleSoup.find('table', class_='conTable'):
                            articleText = articleSoup.find('table', class_='conTable').text

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
                                    'site': '国家、省、市、区、县财政部门网站-宁夏银川市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('宁夏银川市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    button = browser.find_element_by_class_name('next-page')
                    button.click()
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'lxml')
                    titleList = basesoup.find_all('div', class_="js-con")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    browser.close()
    logger.info("finish")
    return

#95.宁夏中卫市财政局
def NXZhongweiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.nxzw.gov.cn/was5/web/search?channelid=293540&searchword='
    siteURL = 'http://www.nxzw.gov.cn/'
    browser = webdriver.Chrome()
    browser.set_page_load_timeout(5)
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('宁夏中卫市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key
                browser.get(requestURL)
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'lxml')
                totalResults = int(basesoup.find('span', class_="num").text)
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('div', class_="js-con")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.yinchuan.gov.cn' + a['href']
                count += 1
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+.\d+.\d+)', timeNode.text):
                                publishTime = re.search('(\d+.\d+.\d+)', timeNode.text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="location"):
                            articleLocation = articleSoup.find('div', class_="location").text.replace(' ','').replace('\n','')
                        elif articleSoup.find('div', class_="la2nav"):
                            articleLocation = articleSoup.find('div', class_="la2nav").text.replace(' ','').replace('\n','')
                        elif articleSoup.find('div', class_="zw-loc"):
                            articleLocation = articleSoup.find('div', class_="zw-loc").text.replace(' ','').replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='zz-xl-sec'):
                            if articleSoup.find('div', class_='TRS_Editor').find('style'):
                                tmplist = articleSoup.find('div', class_='TRS_Editor').find_all('style')
                                for tmp in tmplist:
                                    tmp.decompose()
                            articleText = articleSoup.find('div', class_='zz-xl-sec').text
                        elif articleSoup.find('div', class_='TRS_Editor'):
                            if articleSoup.find('div', class_='TRS_Editor').find('style'):
                                tmplist = articleSoup.find('div', class_='TRS_Editor').find_all('style')
                                for tmp in tmplist:
                                    tmp.decompose()
                            articleText = articleSoup.find('div', class_='TRS_Editor').text
                        elif articleSoup.find('div', class_='view TRS_UEDITOR trs_paper_default trs_web trs_key4format'):
                            articleText = articleSoup.find('div', class_='view TRS_UEDITOR trs_paper_default trs_web trs_key4format').text

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
                                    'site': '国家、省、市、区、县财政部门网站-宁夏中卫市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('宁夏中卫市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    button = browser.find_element_by_class_name('next-page')
                    button.click()
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'lxml')
                    titleList = basesoup.find_all('div', class_="js-con")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    browser.close()
    logger.info("finish")
    return

#96.青海省西宁市财政局
def QHXiningCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.xining.gov.cn/search/Default.aspx?q='
    siteURL = 'http://www.xining.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('青海省西宁市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&ie=utf-8&portalid=1&image.x=0&image.y=0'
                r = requests.get(requestURL,headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('span',id='Label2')
                totalPages = int(total.text)
                if totalPages == 0:
                    titleList = []
                    break
                evalidation = basesoup.find('input',id='__EVENTVALIDATION')['value']
                viewstate = basesoup.find('input',id='__VIEWSTATE')['value']
                titleNode = basesoup.find('table',id='GridView1')
                titleList = titleNode.find_all('td', align="left")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        tmp = table.find('td',class_='hei12')
                        tmp.decompose()
                        timeNode = table.find('td',class_='hei12')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('font', class_='nr'):
                            articleText = articleSoup.find('font', class_='nr').text

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
                                    'site': '国家、省、市、区、县财政部门网站-青海省西宁市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('青海省西宁市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = 'http://www.xining.gov.cn/search/Default.aspx?q=' +key+ '&ie=utf-8&portalid=1&image.x=0&image.y=0'
                    data={'__EVENTTARGET':'GridView1','__EVENTARGUMENT':'Page$'+str(pageNum),'__VIEWSTATE':viewstate,'__EVENTVALIDATION':evalidation,'TextBox1':key
                    }
                    r = requests.post(requestURL,headers=headers,data=data)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    evalidation = basesoup.find('input', id='__EVENTVALIDATION')['value']
                    viewstate = basesoup.find('input', id='__VIEWSTATE')['value']
                    titleNode = basesoup.find('table', id='GridView1')
                    titleList = titleNode.find_all('td', align="left")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#97.青海省海东市财政局
def QHHaidongCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.qhhdcz.gov.cn/search/Default.aspx?q='
    siteURL = 'http://www.qhhdcz.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('青海省海东市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&ie=utf-8&portalid=12&Submit32=站内搜索'
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('span', id='Label2')
                totalPages = int(total.text)
                if totalPages == 0:
                    titleList = []
                    break
                evalidation = basesoup.find('input', id='__EVENTVALIDATION')['value']
                viewstate = basesoup.find('input', id='__VIEWSTATE')['value']
                titleNode = basesoup.find('table', id='GridView1')
                titleList = titleNode.find_all('td', align="left")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        tmp = table.find('td', class_='hei12')
                        tmp.decompose()
                        timeNode = table.find('td', class_='hei12')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td',class_='lan12'):
                            articleLocation = articleSoup.find('td',class_='lan12').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('span', class_='nr13'):
                            articleText = articleSoup.find('span', class_='nr13').text

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
                                    'site': '国家、省、市、区、县财政部门网站-青海省海东市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('青海省海东市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = 'http://www.qhhdcz.gov.cn/search/Default.aspx?q=' + key + '&ie=utf-8&portalid=12&Submit32=%u7ad9%u5185%u641c%u7d22'
                    data = {'__EVENTTARGET': 'GridView1', '__EVENTARGUMENT': 'Page$' + str(pageNum),
                            '__VIEWSTATE': viewstate,'__VIEWSTATEGENERATOR':'CCE6BD4A' ,'__EVENTVALIDATION': evalidation, 'TextBox1': key
                            }
                    r = requests.post(requestURL, headers=headers, data=data)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    evalidation = basesoup.find('input', id='__EVENTVALIDATION')['value']
                    viewstate = basesoup.find('input', id='__VIEWSTATE')['value']
                    titleNode = basesoup.find('table', id='GridView1')
                    titleList = titleNode.find_all('td', align="left")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#98.青海省玉树市财政局
def QHYushuCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.qhys.gov.cn/search/Default.aspx?q='
    siteURL = 'http://www.qhys.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('青海省玉树市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&ie=utf-8&portalid=1&Submit32=站内搜索'
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('span', id='Label2')
                totalPages = int(total.text)
                if totalPages == 0:
                    titleList = []
                    break
                evalidation = basesoup.find('input', id='__EVENTVALIDATION')['value']
                viewstate = basesoup.find('input', id='__VIEWSTATE')['value']
                titleNode = basesoup.find('table', id='GridView1')
                titleList = titleNode.find_all('td', align="left")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        tmp = table.find('td', class_='hei12')
                        tmp.decompose()
                        timeNode = table.find('td', class_='hei12')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td',  align="left", class_="hei12"):
                            articleLocation = articleSoup.find('td',  align="left", class_="hei12").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('font',  class_="nr14"):
                            articleText = articleSoup.find('font',  class_="nr14").text

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
                                    'site': '国家、省、市、区、县财政部门网站-青海省玉树市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('青海省玉树市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = 'http://www.qhys.gov.cn/search/Default.aspx?q=' + key + '&ie=utf-8&portalid=1&Submit32=%u7ad9%u5185%u641c%u7d22'
                    data = {'__EVENTTARGET': 'GridView1', '__EVENTARGUMENT': 'Page$' + str(pageNum),
                            '__VIEWSTATE': viewstate, '__VIEWSTATEGENERATOR': 'CCE6BD4A',
                            '__EVENTVALIDATION': evalidation, 'TextBox1': key
                            }
                    r = requests.post(requestURL, headers=headers, data=data)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    evalidation = basesoup.find('input', id='__EVENTVALIDATION')['value']
                    viewstate = basesoup.find('input', id='__VIEWSTATE')['value']
                    titleNode = basesoup.find('table', id='GridView1')
                    titleList = titleNode.find_all('td', align="left")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#99.青海省德令哈市财政局
def QHDelherCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.delingha.gov.cn/secondaryList.action?pageNum='
    siteURL = 'http://www.delingha.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('青海省德令哈市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&numPerPage=20&xwlbid=&xwbt=' + key
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('td', height='50', align='center')
                if re.search('\d+/(\d+)',total.text):
                    totalPages = int(re.search('\d+/(\d+)',total.text)[1])
                if totalPages == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('td', height="1", bgcolor="#E0EEEE")
                titleList = titleNode.find_all('tr')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.delingha.gov.cn/' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+-\d+-\d+)', table.text):
                                publishTime = re.search('(\d+-\d+-\d+)', table.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="BreadcrumbNav"):
                            articleLocation = articleSoup.find('div', class_="BreadcrumbNav").text.replace('\n','')
                        elif articleSoup.find('td', height="50", align='left'):
                            articleLocation = articleSoup.find('td', height="50", align='left').text.replace('\n','')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td', class_="b12c", id='UCAP-CONTENT'):
                            articleText = articleSoup.find('td', class_="b12c", id='UCAP-CONTENT').text
                        elif articleSoup.find('div', class_="pages_content", id='UCAP-CONTENT'):
                            articleText = articleSoup.find('div', class_="pages_content", id='UCAP-CONTENT').text
                        elif articleSoup.find('table', width="1000", border="0", cellspacing="0", cellpadding="0", align="center"):
                            articleText = articleSoup.find('table', width="1000", border="0", cellspacing="0", cellpadding="0", align="center").text
                        elif articleSoup.find('table', border="1", cellpadding="0", cellspacing="0", class_="MsoNormalTable"):
                            articleText = articleSoup.find('table', border="1", cellpadding="0", cellspacing="0", class_="MsoNormalTable").text

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
                                    'site': '国家、省、市、区、县财政部门网站-青海省德令哈市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('青海省德令哈市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&numPerPage=20&xwlbid=&xwbt=' + key
                    r = requests.get(requestURL, headers=headers)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('td', height="1", bgcolor="#E0EEEE")
                    titleList = titleNode.find_all('tr')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#100.贵州省贵阳市财政厅
def GZGuiyangCZT():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://czj.gygov.gov.cn/index.php?m=search&c=index&a=init&typeid=&siteid=1&q='
    siteURL = 'http://czj.gygov.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('贵州省贵阳市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = quote(key.encode('gb2312'))
                requestURL = baseURL + tmpkey + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='jg')
                if re.search('(\d+)', total.text):
                    totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('li', class_='wrap')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.gygov.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = basesoup.find('div', class_='adds')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="crumbs", style="width:980px;background:#fff;margin-bottom:0px;height:25px"):
                            articleLocation = articleSoup.find('div', class_="crumbs", style="width:980px;background:#fff;margin-bottom:0px;height:25px").text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_="content"):
                            articleText = articleSoup.find('div', class_="content").text

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
                                    'site': '国家、省、市、区、县财政部门网站-贵州省贵阳市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('贵州省贵阳市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + tmpkey + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('li', class_='wrap')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#101.贵州省铜仁市财政厅
def GZTongrenCZT():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.trczj.gov.cn/index.php?info%5Bcatid%5D=0&info%5Btypeid%5D=0&info%5Btitle%5D='
    siteURL = 'http://www.trczj.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('贵州省铜仁市财政厅' + '关键词：' + key)
        while flag < 3:
            try:
                tmpkey = quote(key.encode('gb2312'))
                requestURL = baseURL + tmpkey + '&info%5Bkeywords%5D=&orderby=a.id+DESC&m=content&c=search&a=init&catid=106&dosubmit=1&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', class_='search-point')
                if re.search('(\d+)', total.text):
                    totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('li', style="margin:0")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.trczj.gov.cn' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="crumbs"):
                            articleLocation = articleSoup.find('div', class_="crumbs").text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_="content"):
                            articleText = articleSoup.find('div', class_="content").text

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
                                    'site': '国家、省、市、区、县财政部门网站-贵州省铜仁市财政厅',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('贵州省铜仁市财政厅-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + tmpkey + '&info%5Bkeywords%5D=&orderby=a.id+DESC&m=content&c=search&a=init&catid=106&dosubmit=1&page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleList = basesoup.find_all('li', style="margin:0")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#102.广东省广州市财政局
def GDGuangzhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://118.178.151.173/s?q=1&qt='
    siteURL = 'http://www.gzfinance.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广东省广州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pageSize=10&database=all&siteCode=4401000001&docQt=&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('div', style="float: right;color: #666;")
                if re.search('(\d+)', total.text):
                    totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', class_='classify project')
                titleList = titleNode.find_all('div', class_='title')
                titleList2 = titleNode.find_all('div', class_='titleP')
                titleList += titleList2
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://118.178.151.173/' + a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        #爬取公告，操作说明性的文件跳过
                        if table.find('i'):
                            flag = 3
                            break
                        #网页跳转
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        try:
                            tmpstr = articleSoup.find('script', type="text/javascript").text.replace('\r','').replace('\n','')
                            articleURL = re.search('(http://.*\.shtml)', tmpstr)[0]
                        except Exception:
                            flag = 3
                            break
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        if articleSoup.find('div', class_='title'):
                            articleTitle = articleSoup.find('div', class_='title').text
                        else:
                            articleTitle = a.text.replace('\n', '').replace('\r', '').replace(' ', '')

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('div',class_="info"):
                            timeNode = articleSoup.find('div',class_="info").find('span')
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="location"):
                            articleLocation = articleSoup.find('div', class_="location").text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_="cont"):
                            articleText = articleSoup.find('div', class_="cont").text

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
                                    'site': '国家、省、市、区、县财政部门网站-广东省广州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广东省广州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pageSize=10&database=all&siteCode=4401000001&docQt=&page=' + str(
                        pageNum)
                    r = requests.get(requestURL, headers=headers)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('div', class_='classify project')
                    titleList = titleNode.find_all('div', class_='title')
                    titleList2 = titleNode.find_all('div', class_='titleP')
                    titleList += titleList2
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#103.广东省珠海市财政局
def GDZhuhaiCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    siteURL = 'http://www.zhcz.gov.cn/'
    browser = webdriver.Chrome()
    browser.set_page_load_timeout(50)
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广东省珠海市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                browser.maximize_window()
                input = browser.find_element_by_id('Word')
                input.send_keys(key)
                button = browser.find_element_by_class_name('search-btn')
                button.click()
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'lxml')
                total = basesoup.find('div',class_="outlineBar", style="margin-top: 20px;")
                if re.search('共(\d+)页',total.text):
                    totalPages = int(re.search('共(\d+)页',total.text)[1])
                if totalPages == 0:
                    titleList = []
                    break
                titleList = basesoup.find_all('div', class_="msg")
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', class_="colo-666", style="font-size:12px;")
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="dz"):
                            articleLocation = articleSoup.find('div', class_="dz").text.replace('\n', '')
                        elif articleSoup.find('span', class_="dis_in_b float_left l-box"):
                            articleLocation = articleSoup.find('span', class_="dis_in_b float_left l-box").text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_='content-box'):
                            if articleSoup.find('div', class_='content-box').find('style'):
                                tmp = articleSoup.find('div', class_='content-box').find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', class_='content-box').text
                        elif articleSoup.find('div', class_='nr'):
                            if articleSoup.find('div', class_='nr').find('style'):
                                tmp = articleSoup.find('div', class_='nr').find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', class_='nr').text

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
                                    'site': '国家、省、市、区、县财政部门网站-广东省珠海市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广东省珠海市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum>totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    button = browser.find_element_by_class_name('next-page')
                    button.click()
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'lxml')
                    titleList = basesoup.find_all('div', class_="msg")
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    browser.close()
    logger.info("finish")
    return

#104.广东省韶关市财政局
def GDShaoguanCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://plugin.www.sg.gov.cn/was5/web/search?page='
    siteURL = 'http://www.sgczj.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        count = 0
        logger.info('广东省韶关市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum)+'&channelid=276402&searchword='+key+'&keyword='+key+'&perpage=10&outlinepage=10&andsen=&total=&orsen=&exclude=&searchscope=&timescope=&timescopecolumn=&orderby=-DOCRELTIME'
                r = requests.get(requestURL, headers=headers)
                basesoup = BeautifulSoup(r.text, 'lxml')
                total = basesoup.find('p', class_="search_msg")
                if total:
                    if total.find('span'):
                        totalResults = int(total.find('span').text)
                else:
                    titleList = []
                    break
                titleNode = basesoup.find('ol')
                titleList = titleNode.find_all('dl')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                if 'http://' in a['href']:
                    articleURL = a['href']
                flag = 0
                count += 1
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('dd')
                        if timeNode:
                            if re.search('(\d+/\d+/\d+)', timeNode.text):
                                publishTime = re.search('(\d+/\d+/\d+)', timeNode.text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="curmb"):
                            articleLocation = articleSoup.find('div', class_="curmb").text.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_="nr"):
                            if articleSoup.find('div', class_='nr').find('style'):
                                tmp = articleSoup.find('div', class_='nr').find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', class_="nr").text

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
                                    'site': '国家、省、市、区、县财政部门网站-广东省韶关市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广东省韶关市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or count >= totalResults:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&channelid=276402&searchword=' + key + '&keyword=' + key + '&perpage=10&outlinepage=10&andsen=&total=&orsen=&exclude=&searchscope=&timescope=&timescopecolumn=&orderby=-DOCRELTIME'
                    r = requests.get(requestURL, headers=headers)
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    titleNode = basesoup.find('ol')
                    titleList = titleNode.find_all('dl')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

#105.广东省惠州市财政局
def GDHuizhouCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    siteURL = 'http://czj.huizhou.gov.cn/pages/cms/hzczj/html/index.html'
    browser = webdriver.Chrome()
    browser.set_page_load_timeout(50)
    for key in config.keywords_list:
        key = '财政'
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广东省惠州市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                browser.get(siteURL)
                browser.maximize_window()
                input = browser.find_element_by_id('searchKey')
                input.clear()
                input.send_keys(key)
                input.send_keys(Keys.ENTER)
                sleep(5)
                browser.switch_to_window(browser.window_handles[1])
                r = browser.page_source
                basesoup = BeautifulSoup(r, 'lxml')
                total = basesoup.find('td', height="25", id="div_page").find('td', width="100", align="center")
                if re.search('\d+/(\d+)', total.text):
                    totalPages = int(re.search('\d+/(\d+)', total.text)[1])
                    if totalPages == 0:
                        browser.close()
                        browser.switch_to_window(browser.window_handles[0])
                        titleList = []
                        break
                titleNode = basesoup.find('td', id='div_list')
                titleList = titleNode.find_all('tr')
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    sleep(60 * 10)
                    flag = 0
                logger.info('重新请求网页中...')
                sleep(10 + 20 * flag)
                browser.close()
                browser.switch_to_window(browser.window_handles[0])
        while titleList:
            for table in titleList:
                a = table.find('a')
                a.decompose()
                a = table.find('a')
                if 'http://' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://czj.huizhou.gov.cn' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('td', width="80", align="center")
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', id="navigation"):
                            articleLocation = articleSoup.find('td', id="navigation").text#.replace('\n', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', id='divZoom'):
                            articleText = articleSoup.find('div', id='divZoom').text

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
                                    'site': '国家、省、市、区、县财政部门网站-广东省惠州市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广东省惠州市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum > totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    browser.execute_script('javascript:artSearch.writeList('+str(pageNum)+')')
                    r = browser.page_source
                    basesoup = BeautifulSoup(r, 'lxml')
                    titleNode = basesoup.find('td', id='div_list')
                    titleList = titleNode.find_all('tr')
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
                    browser.close()
                    browser.switch_to_window(browser.window_handles[0])
    browser.close()
    logger.info("finish")
    return

#106.广东省江门市财政局
def GDJiangmenCZJ():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'}
    baseURL = 'http://www.jiangmen.gov.cn/igs/front/search.jhtml?code=eb0e00c4792c4e27baa85823948c2a1a&pageNumber='
    siteURL = 'http://www.jiangmen.gov.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('广东省江门市财政局' + '关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&pageSize=10&searchWord=' + key + '&siteId=29'
                r = requests.get(requestURL, headers=headers)
                r.encoding=r.apparent_encoding
                tmp = json.loads(r.text)
                totalPages = int(tmp['page']['totalPages'])
                if totalPages == 0:
                    titleList = []
                    break
                titleList = tmp['page']['content']
                flag = 3
            except (ReadTimeout, ConnectionError, Exception) as e:
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
                articleURL = table['url']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if key in last:
                            logger.info('更新last_updated for 关键词： ' + key)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + key)
                        last[key] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {key: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + key)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        flag = 3

                        # 保存网页源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table['title'].replace('<em>','').replace('</em>','')

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table['trs_time']
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', class_="location"):
                            articleLocation = articleSoup.find('div', class_="location").text.replace(' ', '')

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', class_="con"):
                            if articleSoup.find('div', class_='con').find('style'):
                                tmp = articleSoup.find('div', class_='con').find('style')
                                tmp.decompose()
                            articleText = articleSoup.find('div', class_="con").text

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
                                    'site': '国家、省、市、区、县财政部门网站-广东省江门市财政局',
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
                    except (ReadTimeout, ConnectionError, Exception) as e:
                        logger.error(e)
                        flag += 1
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('广东省江门市财政局-' + key + '-pageNum: ' + str(pageNum))
            if quitflag == 3 or pageNum >= totalPages:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&pageSize=10&searchWord=' + key + '&siteId=29'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    tmp = json.loads(r.text)
                    titleList = tmp['page']['content']
                    flag = 3
                except (ReadTimeout, ConnectionError, Exception) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        sleep(60 * 10)
                        flag = 0
                    logger.info('重新请求网页中...')
                    sleep(10 + 20 * flag)
    logger.info("finish")
    return

if __name__ == '__main__':
    # #1.河北省石家庄市财政局
    # HBShijiazhuangCaizhengju()
    #
    # #2.河北省张家口市财政局
    # HBZhangjiakouCaizhengju()
    #
    # #3.山西省太原市财政局
    # SXTaiyuanCZJ()
    #
    # #4.山西省朔州市财政局
    # SXShuozhouCZJ()
    #
    # #5.山西省沂州市财政局
    # SXYizhouCZJ()
    #
    # #6.山西省晋中市财政局
    # SXJinzhongCZJ()
    #
    # #7.山西省长治市财政局
    # SXChangzhiCZJ()
    #
    # #8.山西省运城市财政局
    # SXYunchengCZJ()
    #
    # #9.内蒙古包头市财政局
    # NMBaotouCZJ()
    #
    # #10.辽宁省沈阳市财政局
    # LNShenyangCZJ()
    #
    # #11.辽宁省大连市财政局
    # LNDaLianCZJ()
    #
    # #12.辽宁省营口市财政局
    # LNYingkouCZJ()
    #
    # #13.黑龙江省哈尔滨市财政局
    # HLJHaerbinCZJ()
    #
    # #14.黑龙江省伊春市财政局
    # HLJYichuanCZJ()
    #
    # #15.吉林省长春市财政局
    # JLChangchunCZJ()
    #
    # #16.吉林省吉林市财政局
    # JLJilinCZJ()
    #
    # #17.吉林省四平市财政局
    # JLSipingCZJ()
    #
    # #18.吉林省白山市财政局
    # JLBaishanCZJ()
    #
    # #19.上海市普陀区财政局
    # SHPutuoquCZJ()
    #
    # #20.上海市静安区财政局
    # SHJinganCZJ()
    #
    # #21.江苏省南京市财政局
    # JSNanjingCZJ()
    #
    # #22.江苏省无锡市财政局
    # JSYixingCZJ()
    #
    # #23.江苏省苏州市财政局
    # JSSuzhouCZJ()
    #
    # #24.江苏省连云港财政局
    # JSLianyungangCZJ()
    #
    # #25.江苏省淮安市财政局
    # JSHuaianCZJ()
    #
    # #26.江苏省盐城市财政局
    # JSYanchengCZJ()
    #
    # #27.江苏省宿迁市财政局
    # JSSuqianCZJ()
    #
    # #28.浙江省杭州市财政局
    # ZJHangzhouCZJ()
    #
    # # 29.浙江省宁波市财政局
    # ZJNingboCZJ()
    #
    # #30.浙江省温州市财政局
    # ZJWenzhouCZJ()
    #
    # #31.浙江省湖州市财政局
    # ZJHuzhouCZJ()
    #
    # #32.浙江省台州市财政局
    # ZJTaizhouCZJ()
    #
    # #33.安徽省合肥市财政厅
    # AHHefeiCZJ()
    #
    # #34.安徽省淮北市财政厅
    # AHHuaibeiCZJ()
    #
    # #35.安徽省毫州市财政厅
    # AHBozhouCZJ()
    #
    # #36.安徽省宿州市财政厅
    # AHSuzhouCZJ()
    #
    # #37.安徽省蚌埠市财政厅
    # AHBengbuCZJ()
    #
    # #38.安徽省阜阳市财政厅
    # AHFuyangCZJ()
    #
    # #39.安徽省淮南市财政厅
    # AHHuainanCZJ()
    #
    # #40.安徽省马鞍山市财政厅
    # AHMaanshanCZJ()
    #
    # #41.安徽省芜湖市财政厅
    # AHWuhuCZJ()
    #
    # #42.安徽省池州市财政厅
    # AHChizhouCZJ()
    #
    # #43.安徽省安庆市财政厅
    # AHAnqingCZJ()
    #
    # #44.安徽省黄山市财政局
    # AHHuangshanCZJ()
    #
    # #45.福建省福州市财政局
    # FJFuzhouCZJ()
    #
    # #46.福建省厦门市财政局
    # FJXiamenCZJ()
    #
    # #47.山东省财政厅
    # SDCZT()
    #
    # #48.山东省青岛市财政局
    # SDQingdaoCZJ()
    #
    # #49.山东省淄博市财政局
    # SDZiboCZJ()
    #
    # #50.福建省莆田市财政局
    # FJPutianCZJ()
    #
    # #52.福建省三明市财政局
    # FJSanmingCZJ()
    #
    # #53.福建省南平市财政局
    # FJNanpingCZJ()
    #
    # #54.福建省龙岩市财政局
    # FJLongyanCZJ()
    #
    # #55.福建省宁德市财政局
    # FJNingdeCZJ()
    #
    # #56.山东省潍坊市财政局
    # SDWeifangCZJ()
    #
    # #57.山东省威海市财政局
    # SDWeihaiCZJ()
    #
    # #58.河南省兰考县财政局
    # HNLankaoCZJ()
    #
    # #59.河南省汝州市财政局
    # HNRuzhouCZJ()
    #
    # #60.河南省滑县财政局
    # HNHuaxianCZJ()
    #
    # #61.河南省固始县财政局
    # HNGushiCZJ()
    #
    # #62.湖北省荆州市财政局
    # HBJingzhouCZJ()

    # #63.湖北省荆门市财政局
    # HBJingmenCZJ()
    #
    # #64.湖北省恩施州财政局
    # HBEnshiCZJ()
    #
    # #65.湖南省长沙市财政局
    # HNChangshaCZJ()
    #
    # #66.湖南省湘潭市财政局
    # HNXiangtanCZJ()
    #
    # #67.湖南省岳阳市财政局
    # HNYueyangCZJ()
    #
    # #68.湖南省常德市财政局
    # HNChangdeCZJ()
    #
    # #69.湖南省娄底市财政局
    # HNLoudiCZJ()
    #
    # #70.广西壮族自治区南宁市财政局
    # GXNanningCZJ()

    # #71.广西壮族自治区柳州市财政局
    # GXLiuzhouCZJ()

    # #72.广西壮族自治区桂林市财政局
    # GXGuilinCZJ()
    #
    # #73.广西壮族自治区防城港市财政局
    # GXFangchenggangCZJ()
    #
    # #74.广西壮族自治区钦州市财政局
    # GXQinzhouCZJ()
    #
    # #75.广西财政厅
    # GXCaizhengting()
    #
    # #76.广西壮族自治区贺州市财政局
    # GXHezhouCZJ()
    #
    # #77.广西壮族自治区来宾市财政局
    # GXLaibinCZJ()
    #
    # #78.海南省三亚市财政厅
    # HNSanyaCZT()
    #
    # #79.海南省海口市财政厅
    # HNHaikouCZT()
    #
    # #80.重庆市渝中区财政局
    # CQYuzhongquCZJ()
    #
    # #81.四川省成都市财政局
    # SCChengduCZJ()
    #
    # #82.四川省阿坝州财政局
    # SCAbazhouCZJ()
    #
    # #83.四川省泸州市财政局
    # SCGuangyuanCZJ()

    # #84.四川省南充市财政局
    # SCNanchongCZJ()
    #
    # #85.云南省昆明市财政局
    # YNKunmingCZJ()
    #
    # #86.陕西省咸阳市财政局
    # SXXianyangCZJ()

    # #87.陕西省铜川市财政局
    # SXTongchuanCZJ()
    #
    # #88.陕西省渭南市财政局
    # SXWeinanCZJ()
    #
    # #89.甘肃省兰州市财政局
    # GSLanzhouCZJ()
    #
    # #90.甘肃省嘉峪关市财政局
    # GSJiayuguanCZJ()
    #
    # #91.甘肃省金昌市财政局
    # GSJinchangCZJ()
    #
    # #92.甘肃省天水市财政局
    # GSTianshuiCZJ()
    # #93.甘肃省酒泉市财政局
    # GSJiuquanCZJ()
    # #94.宁夏银川市财政局
    # NXYinchuanCZJ()
    # #95.宁夏中卫市财政局
    # NXZhongweiCZJ()
    # #96.青海省西宁市财政局
    # QHXiningCZJ()
    # #97.青海省海东市财政局
    # QHHaidongCZJ()
    # #98.青海省玉树市财政局
    # QHYushuCZJ()
    # #99.青海省德令哈市财政局
    # QHDelherCZJ()
    # #100.贵州省贵阳市财政厅
    # GZGuiyangCZT()
    # #101.贵州省铜仁市财政厅
    # GZTongrenCZT()
    # #102.广东省广州市财政局
    # GDGuangzhouCZJ()
    # #103.广东省珠海市财政局
    # GDZhuhaiCZJ()
    # #104.广东省韶关市财政局
    # GDShaoguanCZJ()
    # #105.广东省惠州市财政局
    # GDHuizhouCZJ()
    #106.广东省江门市财政局
    GDJiangmenCZJ()











