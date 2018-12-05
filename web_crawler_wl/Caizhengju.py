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

from time import sleep

import json
import logging

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
    return;

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

    #40.安徽省马鞍山市财政厅
    AHMaanshanCZJ()




