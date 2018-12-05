import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config
from utility import utility_convert

#引入代理
from getProxy import getOneProxy

from selenium import webdriver

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1440,900')
chrome_options.add_argument('--silent')


from time import sleep

import json
import logging
import datetime

from requests.exceptions import ReadTimeout, ConnectionError

# 连接mongoDB
db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
collection = db.result_data
#crawlerCollection记录上次爬取的最新url
crawler = db.crawler

#配置logging
logger = logging.getLogger('央企及地方重点国企官网--爬取数据')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

#1.国家能源投资集团有限责任公司
def delUrlofGuoNengTou(baseUrl, key):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
               'Refer': 'http://www.dlzb.com/zb/search.php?moduleid=23&kw=%E5%9B%BD%E4%BC%81%E6%94%B9%E9%9D%A9&page=150'}
    siteURL = baseUrl  # 保存网站主页，用于匹配crawlerCollection的url字段
    quitflag = 0  # 到达之前爬过的网址时的退出标记
    last_updated_url = ''  # 记录上次爬过的网站网址
    if crawler.find({'url': siteURL}).count() > 0:
        last = crawler.find_one({'url': siteURL})['last_updated']
        if key in last:
            last_updated_url = last[key]
    pageNum = 1
    requestURL = baseUrl + key + '&page=' + str(pageNum)
    flag = 0
    while flag < 3:
        try:
            r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
            r.encoding = r.apparent_encoding
            if r.status_code == 403:
                flag += 1
                logger.info('ip被封')
                sleep(flag*20)
                if flag == 3:
                    flag = 0
                continue
            basesoup = BeautifulSoup(r.text, 'lxml')
            basesoup.prettify()
            total = basesoup.find('div', class_='list_left').find('cite')
            totalPages = int(re.search('/(\d+)页',total.text)[1])
            if totalPages == 0:
                titleList = []
                break
            if basesoup.find(attrs={'class': 'con_list'}):
                titleNode = basesoup.find(attrs={'class': 'con_list'})
            else: titleNode = basesoup.find(attrs={'class': 'gclist_ul listnew'})
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
            sleep(10+20*flag)
    while titleList:
        for table in titleList:
            a = table.find(name='a', attrs={'class': 'gccon_title'})
            #找到文章链接
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
                return
            while flag < 3:
                try:
                    article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
                    flag = 3
                    article.encoding = article.apparent_encoding
                    articleSoup = BeautifulSoup(article.text, 'lxml')
                    articleSoup.prettify()
                    if r.status_code == 403:
                        flag += 1
                        logger.info('ip被封')
                        sleep(flag * 20)
                        if flag == 3:
                            flag = 0
                        continue
                    if not articleSoup.head.meta:
                        logger.info('没有请求下来完整网页')
                        sleep(5)
                        flag = 0
                        continue

                    # 保存html页面源码
                    htmlSource = article.text

                    # html的URL地址
                    htmlURL = article.url

                    # 保存文章标题信息
                    articleTitle = ''
                    articleTitle = a.text

                    # 保存文章发布时间
                    publishTime = ''
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
                    articleText = ''
                    if articleSoup.find(attrs={'id': 'content'}):
                        articleText = articleSoup.find(attrs={'id': 'content'}).text

                    # 判断标题或正文是否含有关键词
                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
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
                    sleep(10+20*flag)
                    if flag == 3:
                        logger.info('重新请求失败')
                        logger.info('Sleeping...')
                        sleep(60 * 10)
        logger.info('国家能源投资集团有限责任公司-'+key+'-pageNum: ' + str(pageNum))
        pageNum += 1
        if pageNum > totalPages:
            break
        #开始请求下一页关键词搜索结果
        requestURL = baseUrl + key + '&page=' + str(pageNum)
        flag = 0
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                if r.status_code == 403:
                    flag += 1
                    logger.info('ip被封')
                    sleep(flag * 20)
                    if flag == 3:
                        flag = 0
                    continue
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                if basesoup.find(attrs={'class': 'con_list'}):
                    titleNode = basesoup.find(attrs={'class': 'con_list'})
                elif basesoup.find(attrs={'class': 'gclist_ul listnew'}):
                    titleNode = basesoup.find(attrs={'class': 'gclist_ul listnew'})
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
                sleep(10+20*flag)
    logger.info("finished")
    return


#2.中国兵器工业集团有限公司
def dealURLofBingQi(baseUrl, key):
    headers = {
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    siteURL = 'http://www.norincogroup.com.cn/'  # 保存网站主页，用于匹配crawlerCollection的url字段
    quitflag = 0  # 到达之前爬过的网址时的退出标记
    last_updated_url = ''  # 记录上次爬过的网站网址
    if crawler.find({'url': siteURL}).count() > 0:
        last = crawler.find_one({'url': siteURL})['last_updated']
        if key in last:
            last_updated_url = last[key]
    pageNum = 1
    requestURL = baseUrl + key + '&style=1&webid=1&&p=' + str(pageNum)
    flag = 0
    count = 0
    while flag < 3:
        try:
            r = requests.get(requestURL, headers=headers)
            r.encoding = r.apparent_encoding
            basesoup = BeautifulSoup(r.text, 'lxml')
            basesoup.prettify()
            titleNode = basesoup.find(attrs={'class': 'js-result'})
            if '找不到和您的查询' in titleNode.text:
                titleList = []
                break
            else:
                totalResults = int(titleNode.find('td',attrs={'height':'18','align':'right'}).find('b').text)
            titleList = titleNode.find_all(attrs={'class': 'jsearchblue'})
            flag = 3
        except (ReadTimeout, ConnectionError) as e:
            logger.error(e)
            flag += 1
            if flag == 3:
                logger.info('Sleeping...')
                sleep(60 * 10)
                flag = 0
            logger.info('重新请求网页中...')
            sleep(10+20*flag)
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
                return
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
                    if articleSoup.find('h2'):
                        articleTitle = articleSoup.find('h2').text
                    else:
                        articleTitle = a.text

                    # 保存文章发布时间
                    publishTime = ''
                    if articleSoup.find('div', attrs={'class': 'box4'}):
                        if articleSoup.find('div', attrs={'class': 'box4'}).find('td', attrs={'align':"right", 'valign':"middle", 'style':"padding-right:10px;"}):
                            timeNode = articleSoup.find('div', attrs={'class': 'box4'}).find('td', attrs={'align':"right", 'valign':"middle", 'style':"padding-right:10px;"})
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                    # 保存文章位置
                    articleLocation = ''
                    if articleSoup.find(attrs={'class': 'ggl'}):
                        articleLocList = articleSoup.find(attrs={'class': 'ggl'}).find_all('a')
                        for articleLocNode in articleLocList:
                            articleLocation += '>'+articleLocNode.text


                    # 保存文章正文
                    articleText = ''
                    if articleSoup.find('td',attrs={'id': 'zoom'}):
                        if articleSoup.find('td',attrs={'id': 'zoom'}).find('p'):
                            articleTextList = articleSoup.find('td',attrs={'id': 'zoom'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text
                    elif articleSoup.find(attrs={'class': 'box4'}):
                        articleText = articleSoup.find(attrs={'class': 'box4'}).text

                    # 判断标题或正文是否含有关键词
                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
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
                    sleep(10+20*flag)
                    if flag == 3:
                        logger.info('重新请求失败')
                        logger.info('Sleeping...')
                        sleep(60 * 10)
        logger.info('中国兵器工业集团有限公司-'+key+'-pageNum: ' + str(pageNum))
        pageNum += 1
        if count >= totalResults:
            break
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

#3.中国国新控股有限责任公司
def dealURLofGuoXinKongGu():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    requestURL = 'https://www.crhc.cn/sitesearch/search.jsp'
    siteURL = 'https://www.crhc.cn/'  # 保存网站主页，用于匹配crawlerCollection的url字段
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国国新控股有限责任公司'+'关键词：' + key)
        while flag < 3:
            try:
                # 构造POST方法请求数据：
                data = {'SType': '1', 'searchColumn': 'all',
                        'preSWord': 'doctitle/3,docContent/1+=(' + key + ') and (channelid=63 or channelid=64 or channelid=65 or channelid=68 or channelid=69 or channelid=72)',
                        'sword': key, 'page': str(pageNum)}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 记录搜索结果的总页面数量
                totalPage = int(basesoup.find_all('strong')[1].text)
                if totalPage == 0:
                    titleList = []
                    break
                titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
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
                        publishTime = ''
                        if table.find('span'):
                            publishTime = re.search('(\d+.\d+.\d+)', table.find('span').text)[0].replace('.', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'gu_current'}):
                            articleLocList = articleSoup.find(attrs={'class': 'gu_current'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'Custom_UnionStyle'}):
                            articleText = articleSoup.find(attrs={'class': 'Custom_UnionStyle'}).text

                        # 判断标题或正文是否含有关键词
                        matched_keywords_list = []
                        for each_keyword in config.keywords_list:
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
                            sleep(60 * 10)
            logger.info('中国国新控股有限责任公司-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPage or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'SType': '1', 'searchColumn': 'all',
                            'preSWord': 'doctitle/3,docContent/1+=(' + key + ') and (channelid=63 or channelid=64 or channelid=65 or channelid=68 or channelid=69 or channelid=72)',
                            'sword': key, 'page': str(pageNum)}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'gu_results_list'})
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

#4.中国铁路物资集团有限公司
def dealURLofTieLuWuZi():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }

    baseUrlList = ['https://www.crmsc.com.cn/mark.asp?bigID=50&Page=', 'https://www.crmsc.com.cn/mark.asp?bigID=40&Page=',
                   'https://www.crmsc.com.cn/mark.asp?bigID=10&Page=', 'https://www.crmsc.com.cn/mark.asp?bigID=30&Page=',
                   'https://www.crmsc.com.cn/mark.asp?bigID=60&Page=', 'https://www.crmsc.com.cn/mark.asp?bigID=100&Page=']
    siteURL = 'https://www.crmsc.com.cn/'
    for baseUrl in baseUrlList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if baseUrl in last:
                last_updated_url = last[baseUrl]
        logger.info('开始爬取中国铁路物资集团有限公司:' + baseUrl)
        pageNum = 1
        flag = 0
        requestURL = baseUrl + str(pageNum)
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'content_newslist'})
                titleList = titleNode.find_all('li')
                flag = 3
                #记录总页码数
                pagenode = basesoup.find('td', attrs={'align':'right'}).text
                totalPage = int(re.search('(\d+)', pagenode)[0])
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
                    articleURL = 'https://www.crmsc.com.cn/'+a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if baseUrl in last:
                            logger.info('更新last_updated for 关键词： ' + baseUrl)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + baseUrl)
                        last[baseUrl] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {baseUrl: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + baseUrl)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        article = requests.get(articleURL, headers=headers)
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = re.search('(\d+-\d+-\d+)', table.find('span').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'content_right_title'}):
                            articleLocList = articleSoup.find(attrs={'class': 'content_right_title'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'content_info'}):
                            artileTextList = articleSoup.find(attrs={'class': 'content_info'}).find_all('p')
                        for articleTextNode in artileTextList:
                            articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国铁路物资集团有限公司',
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
                            sleep(60 * 10)
            logger.info('中国铁路物资集团有限公司-'+baseUrl+'-pageNum: ' + str(pageNum))
            pageNum += 1
            #如果超出最大页码数则爬取下一网站：
            if pageNum > totalPage or quitflag == 3:
                break
            flag = 0
            requestURL = baseUrl + str(pageNum)
            while flag < 3:
                try:
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'html5lib')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'content_newslist'})
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

#5.中国西电集团有限公司
def delURLofXiDian():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    baseUrl = 'http://www.xd.com.cn/structure/ssjg?currentPageNum='
    siteURL = 'http://www.xd.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国西电集团有限公司'+'关键词：' + key)
        requestURL = baseUrl+str(pageNum)+'&keyword='+key+'&range=site&pagesize=15&siteid=xd&channelid=root'
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleList = basesoup.find_all('result')
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
                articleURL = table.find('url').text
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = table.find('title').text

                        # 保存文章发布时间
                        publishTime = re.search('(\d+-\d+-\d+)', table.find('time').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = '资讯园地'
                        if articleSoup.find(attrs={'valign': 'middle', 'class': 'CicroJK23PR_2437_5453_xd_25_Local_page'}):
                            articleLocation += '>' + articleSoup.find_all(attrs={'valign': 'middle', 'class': 'CicroJK23PR_2437_5453_xd_25_Local_page'})[1].text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'id': 'content'}):
                            articleText = articleSoup.find(attrs={'id': 'content'}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国西电集团有限公司',
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
                            sleep(60 * 10)
            logger.info('中国西电集团有限公司-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            requestURL = baseUrl + str(pageNum) + '&keyword=' + key + '&range=site&pagesize=15&siteid=xd&channelid=root'
            while flag < 3:
                try:
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleList = basesoup.find_all('result')
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

#6.南光（集团）有限公司[中国南光集团有限公司]
def delURLofNanGuang():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
        'Referer': 'http://www.namkwong.com.mo/e/search/result/?searchid=1362'
    }
    #编写搜索关键词字典
    keyDict = {'国企改革': '1362', '国企改制': '2190', '国企混改': '2189', '国有企业改革': '2191', '国有企业改制': '2242'}
    #这个网站构造请求时，页码是从0开始计算的（后面pageNum在请求网页时可减1）
    baseUrl = 'http://www.namkwong.com.mo/e/search/result/index.php?page='
    siteURL = 'http://www.namkwong.com.mo/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国南光集团有限公司'+'关键词：' + key)
        requestURL = baseUrl+str(pageNum-1)+'&start=0&searchid='+keyDict[key]
        #记录当前关键词已经爬取的结果数
        numResults = 0
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'html5lib')
                basesoup.prettify()
                # 记录当前关键词总的结果数
                totalResults = int(basesoup.find('strong').text)
                titleList = basesoup.find_all('h2', attrs={'class': 'r'})
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
                numResults += 1
                a = table.find('a')
                if 'http:' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.namkwong.com.mo'+a['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('h1'):
                            articleTitle = articleSoup.find('h1').text
                        elif articleSoup.find('title'):
                            articleTitle = articleSoup.find('title').text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find(attrs={'class': 'date_source'}):
                            publishTime = re.search('(\d+-\d+-\d+)', articleSoup.find(attrs={'class': 'date_source'}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'news_nav'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'news_nav'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        if articleSoup.find('div', attrs={'class': 'news-text'}):
                            articleText = articleSoup.find('div', attrs={'class': 'news-text'}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国南光集团有限公司',
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
                            sleep(60 * 10)
            logger.info('南光（集团）-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            requestURL = baseUrl + str(pageNum - 1) + '&start=0&searchid=' + keyDict[key]
            #如果这个关键词搜索的结果已经达到最大，跳出循环检索下一个关键词
            if numResults >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'html5lib')
                    basesoup.prettify()
                    titleList = basesoup.find_all('h2', attrs={'class': 'r'})
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


#7.华侨城集团有限公司
def delURLofHuaQiaoCheng():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3497.100 Safari/537.36'
    }
    baseUrl = 'http://www.chinaoct.com/search/pcRender?sr=dateTime+desc&pageId=8a159d051d784d44b99eec0aead3ed47&pNo='
    siteURL = 'http://www.chinaoct.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取华侨城集团有限公司'+'关键词：' + key)
        requestURL = baseUrl + str(pageNum) + '&q=' + key
        count = 0
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find('div', attrs={'id':"resultSet"})
                totalResults = int(re.search('(\d+)',titleNode.find('span').text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleList = titleNode.find_all(attrs={'class':"news-style1"})
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
                        publishTime = ''
                        if table.find('span', attrs={'class':'new_date'}):
                            publishTime = re.search('(\d+年\d+月\d+日)', table.find('span', attrs={'class':'new_date'}).text)[
                                0].replace('年', '').replace('月', '').replace('日', '')
                        elif articleSoup.find(attrs={'class': 'detail_body'}):
                            publishTime = \
                            re.search('(\d+年\d+月\d+日)', articleSoup.find(attrs={'class': 'detail_body'}).text)[
                                0].replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'mbx'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'mbx'}).find('span').find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'detail_center'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'detail_center'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-华侨城集团有限公司',
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
                            sleep(60 * 10)
            logger.info('华侨城集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            requestURL = baseUrl + str(pageNum) + '&q=' + key
            while flag < 3:
                try:
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('div', attrs={'id': "resultSet"})
                    titleList = titleNode.find_all(attrs={'class': "news-style1"})
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

#8.武汉邮电科学研究院有限公司
def delURLofWuHanYouDian():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }
    requestURL = 'http://www.wri.com.cn/cn/tools/submit_self_ajax.ashx?action=search_list'
    siteURL = 'http://www.wri.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取武汉邮电科学研究院有限公司'+'关键词：' + key)
        # 构造POST方法请求数据：
        data = {'key': key, 'pageindex': str(pageNum)}
        #记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                r = requests.post(requestURL, headers=headers, data=data, proxies=getOneProxy())
                r.encoding = 'utf-8'
                titleNode = json.loads(r.text)
                titleList = titleNode['List']
                #统计最大结果数
                totalResults = int(titleNode['Count'])
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
                if 'http:' in table['link_url']:
                    articleURL = table['link_url']
                else:
                    articleURL = 'http://www.wri.com.cn'+table['link_url']
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
                        articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find(attrs={'class': 'detailSetTime'}):
                            publishTime = re.search('(\d+/\d+/\d+)', articleSoup.find(attrs={'class': 'detailSetTime'}).text)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'subnav'}):
                            articleLocList = articleSoup.find(attrs={'class': 'subnav'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'detailParagraphBox'}):
                            articleTextList =  articleSoup.find(attrs={'class': 'detailParagraphBox'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-武汉邮电科学研究院有限公司',
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
                            sleep(60 * 10)
            logger.info('武汉邮电科学研究院-'+key+'-pageNum: ' + str(pageNum))
            #如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            pageNum += 1
            flag = 0
            data = {'key': key, 'pageindex': str(pageNum)}
            while flag < 3:
                try:
                    r = requests.post(requestURL, headers=headers, data=data, proxies=getOneProxy())
                    r.encoding = 'utf-8'
                    titleNode = json.loads(r.text)
                    titleList = titleNode['List']
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

#9.上海诺基亚贝尔股份有限公司
def delURLofNokiasbell():
    baseURL = ['http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN', 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN', 'http://www.nokia-sbell.com/Default.aspx?tabid=543&language=zh-CN']
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Upgrade-Insecure-Requests': '1',
        'Host': 'www.nokia-sbell.com',
        'Referer': 'http://www.nokia-sbell.com/'
    }
    siteURL = 'http://www.nokia-sbell.com/'
    for requestURL in baseURL:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if requestURL in last:
                last_updated_url = last[requestURL]
        pageNum = 1
        flag = 0
        logger.info('开始爬取上海诺基亚贝尔股份有限公司')
        if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN':
            logger.info('新闻稿')
        elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
            logger.info('新闻动态')
        else: logger.info('国资要闻')
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                flag = 3
                if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN':
                    total = basesoup.find(attrs={'class': 'TableNewsTD3'})
                    totalPages = int(re.search('/(\d+)页', total.text)[1])
                    titleList = basesoup.find(attrs={'id': 'dnn_ctr1900_ArticleList_PanelA'}).find('table').find_all('tr')
                elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
                    titleList = basesoup.find(attrs={'id': 'dnn_ctr1814_ArticleList_PanelA'}).find('table').find_all('tr')
                else:
                    total = basesoup.find(attrs={'class': 'TableNewsTD3'})
                    totalPages = int(re.search('/(\d+)页', total.text)[1])
                    titleList = basesoup.find(attrs={'id': 'dnn_ctr1901_ArticleList_PanelA'}).find('table').find_all('tr')
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
                        if requestURL in last:
                            logger.info('更新last_updated for 关键词： ' + requestURL)
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + requestURL)
                        last[requestURL] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {requestURL: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + requestURL)
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
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
                        articleTitle = a['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find(attrs={'class': 'TableNewsTD1'}):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find(attrs={'class': 'TableNewsTD1'}).text)[0].replace('-', '')
                        elif table.find('div'):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find('div').text)[0].replace('-', '')

                        # 保存文章位置
                        if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN':
                            articleLocation = '新闻稿'
                        elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
                            articleLocation = '新闻动态'
                        elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=543&language=zh-CN':
                            articleLocation = '国资要闻'

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'NewsPageContent'}):
                            if articleSoup.find('div', attrs={'class': 'NewsPageContent'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'class': 'NewsPageContent'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-上海诺基亚贝尔股份有限公司',
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
                            sleep(60 * 10)
            logger.info('诺基亚贝尔-'+requestURL+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
                next = basesoup.find('div', attrs={'class': 'Page001'})
                if next.find('a', attrs={'disabled': 'disabled'}) and next.find('a', attrs={'disabled': 'disabled'}).text == '下一页':
                    break
            elif pageNum >= totalPages:
                    break
            pageNum += 1
            flag = 0
            viewstate = basesoup.find(attrs={'id': '__VIEWSTATE'})['value']
            while flag < 3:
                try:
                    if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN':
                        data = {
                            '__VIEWSTATE': viewstate,
                            '__EVENTTARGET': 'dnn$ctr1900$ArticleList$cmdNext',
                            '__EVENTARGUMENT': '',
                            '__VIEWSTATEGENERATOR': 'CA0B0334',
                            'dnn$ctr1900$ArticleList$cboPages': pageNum - 2,
                            'dnn$ctr852$Search$cboSearchType': 1,
                            'ScrollTop': 334,
                            '__dnnVariable': '{"__scdoff":"1"}'
                        }
                    elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
                        data = {
                            '__VIEWSTATE': viewstate,
                            '__EVENTTARGET': 'dnn$ctr1814$ArticleList$cmdNext',
                            '__EVENTARGUMENT': '',
                            '__VIEWSTATEGENERATOR': 'CA0B0334',
                            '__dnnVariable': '{"__scdoff":"1"}'
                        }
                    else:
                        data = {
                            '__VIEWSTATE': viewstate,
                            '__EVENTTARGET': 'dnn$ctr1901$ArticleList$cmdNext',
                            '__EVENTARGUMENT': '',
                            '__VIEWSTATEGENERATOR': 'CA0B0334',
                            'dnn$ctr1901$ArticleList$cboPages': pageNum-2,
                            'ScrollTop': '500',
                            '__dnnVariable': '{"__scdoff":"1"}'
                        }
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    flag =3
                    if requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=181&language=zh-CN':
                        titleList = basesoup.find(attrs={'id': 'dnn_ctr1900_ArticleList_PanelA'}).find(
                            'table').find_all('tr')
                    elif requestURL == 'http://www.nokia-sbell.com/Default.aspx?tabid=536&language=zh-CN':
                        titleList = basesoup.find(attrs={'id': 'dnn_ctr1814_ArticleList_PanelA'}).find(
                            'table').find_all('tr')
                    else:
                        titleList = basesoup.find(attrs={'id': 'dnn_ctr1901_ArticleList_PanelA'}).find(
                            'table').find_all('tr')
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

#10.中国华录集团有限公司
def delURLofHuaLu():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'
    }

    requestURL = 'http://www.hualu.com.cn/index.php?component=search&view=search&xid=72'
    siteURL = 'http://www.hualu.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国华录集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                # 构造POST方法请求数据：
                data = {'hform[condition_type]': 'news',
                        'hform[key_words]': key,
                        'searchsearchlimitstart': str(count),
                        'searchsearchlimit': '10',
                        'task': 'search'}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'newslists newslists_search'})
                titleList = titleNode.find_all('li')
                # 统计最大页数
                if basesoup.find(attrs={'class': 'page_blue'}):
                    totalNode = basesoup.find_all(attrs={'class': 'page_blue'})
                    totalPages = int(totalNode[4].text)
                else: totalPages = 1
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
                if 'http:' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.hualu.com.cn/' + a['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = a['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find(attrs={'class': 'date'}):
                            publishTime = \
                            re.search('(\d+-\d+-\d+)', table.find(attrs={'class': 'date'}).text)[
                                0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'breadcrumb'}):
                            articleLocList = articleSoup.find(attrs={'class': 'breadcrumb'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'id': 'page_break'}):
                            articleTextList = articleSoup.find(attrs={'id': 'page_break'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国华录集团有限公司',
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
                            sleep(60 * 10)
            logger.info('中国华录-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    # 构造POST方法请求数据：
                    data = {'hform[condition_type]': 'news',
                            'hform[key_words]': key,
                            'searchsearchlimitstart': str(count),
                            'searchsearchlimit': '10',
                            'task': 'search'}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'newslists newslists_search'})
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

#11.中国广核集团有限公司
def delURLofCGN():
    headers = {
        'Referer': 'http://www.cgnpc.com.cn/usoso/search.do',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    requestURL = 'http://www.cgnpc.com.cn/usoso/search.do'
    siteURL = 'http://www.cgnpc.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国广核集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        # 构造POST方法请求数据：
        data = {'keyword': key,
                'startlocation': count,
                'old_keyword': key,
                's_keyword': key,
                'flag': 1,
                'indexpath': 'cgn',
                'webPath': 'webPath'}
        while flag < 3:
            try:
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'record'})
                titleList = titleNode.find_all('h2')
                # 统计最大结果数
                totalResults = int(basesoup.find(attrs={'class': 'timeout'}).find('span').text)
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
                articleURL = ('http://www.cgnpc.com.cn' + a['href']).replace('\n','')
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('ucaptitle'):
                            articleTitle = articleSoup.find('ucaptitle').text
                        if articleTitle == '':
                            articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('publishtime'):
                            publishTime = re.search('(\d+年\d+月\d+日)', articleSoup.find('publishtime').text)[0].replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'wrap crumbs c'}):
                            articleLocList = articleSoup.find(attrs={'class': 'wrap crumbs c'}).find(attrs={'class': 'pull-right'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('ucapcontent'):
                            articleTextList = articleSoup.find('ucapcontent').find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国广核集团有限公司',
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
                            sleep(60 * 10)
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            logger.info('中国广核-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    # 构造POST方法请求数据：
                    data = {'keyword': key,
                            'startlocation': count,
                            'old_keyword': key,
                            's_keyword': key,
                            'flag': 1,
                            'indexpath': 'cgn',
                            'webPath': 'webPath'}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'record'})
                    titleList = titleNode.find_all('h2')
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

#12.中国黄金集团有限公司
def delURLofChinaGold():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = ['http://www.chinagoldgroup.com/n4/n62/index.html',
               'http://www.chinagoldgroup.com/n4/n755/index.html',
               'http://www.chinagoldgroup.com/n4/n64/index.html',
               'http://www.chinagoldgroup.com/n4/n65/index.html',
               'http://www.chinagoldgroup.com/n4/n66/index.html',
               'http://www.chinagoldgroup.com/n4/n67/index.html',
               'http://www.chinagoldgroup.com/n4/n69/index.html',
               'http://www.chinagoldgroup.com/n6/n119/index.html',
               'http://www.chinagoldgroup.com/n6/n118/index.html']
    LocDict={'http://www.chinagoldgroup.com/n4/n62/index.html':'集团要闻',
               'http://www.chinagoldgroup.com/n4/n755/index.html':'国资动态',
               'http://www.chinagoldgroup.com/n4/n64/index.html':'行业资讯',
               'http://www.chinagoldgroup.com/n4/n65/index.html':'金市行情',
               'http://www.chinagoldgroup.com/n4/n66/index.html':'子公司动态',
               'http://www.chinagoldgroup.com/n4/n67/index.html':'媒体报道',
               'http://www.chinagoldgroup.com/n4/n69/index.html':'企业公告',
               'http://www.chinagoldgroup.com/n6/n119/index.html':'科研动态',
               'http://www.chinagoldgroup.com/n6/n118/index.html':'科研成果'}
    NextpageDict={'http://www.chinagoldgroup.com/n4/n62/index.html':'http://www.chinagoldgroup.com/n4/n62/index_1281_',
               'http://www.chinagoldgroup.com/n4/n755/index.html':'http://www.chinagoldgroup.com/n4/n755/index_6720_',
               'http://www.chinagoldgroup.com/n4/n64/index.html':'http://www.chinagoldgroup.com/n4/n64/index_1393_',
               'http://www.chinagoldgroup.com/n4/n65/index.html':'http://www.chinagoldgroup.com/n4/n65/index_1400_',
               'http://www.chinagoldgroup.com/n4/n66/index.html':'http://www.chinagoldgroup.com/n4/n66/index_1407_',
               'http://www.chinagoldgroup.com/n4/n67/index.html':'http://www.chinagoldgroup.com/n4/n67/index_1414_',
               'http://www.chinagoldgroup.com/n4/n69/index.html':'http://www.chinagoldgroup.com/n4/n69/index_1862_',
               'http://www.chinagoldgroup.com/n6/n119/index.html':'http://www.chinagoldgroup.com/n6/n119/index_833_',
               'http://www.chinagoldgroup.com/n6/n118/index.html':'http://www.chinagoldgroup.com/n6/n118/index_826_'}
    siteURL = 'http://www.chinagoldgroup.com/'
    for requestURL in baseURL:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[requestURL] in last:
                last_updated_url = last[LocDict[requestURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国黄金集团有限公司'+'子栏目：' + LocDict[requestURL])
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 如果没有请求下来完整的html页面，则再次请求
                if not basesoup.head.meta:
                    logger.info('html页面未完整请求，10秒后再次请求')
                    sleep(10)
                    flag = 0
                    continue
                titleNode = basesoup.find('td', attrs={'style':"padding:10px;"})
                titleList = titleNode.find_all('tr')
                #统计总页数
                if basesoup.find('td', attrs={'id':"pag_833", 'class':"th_x_12", 'align':"center"}):
                    total = basesoup.find('td', attrs={'id':"pag_833", 'class':"th_x_12", 'align':"center"})
                    totalPages = int(re.search('maxPageNum = (\d+)', total.text)[1])
                elif basesoup.find('td', attrs={'id':"pag_826", 'class':"th_x_12", 'align':"center"}):
                    total = basesoup.find('td', attrs={'id':"pag_826", 'class':"th_x_12", 'align':"center"})
                    totalPages = int(re.search('maxPageNum = (\d+)', total.text)[1])
                else:
                    total = basesoup.find('table', attrs={'id':"fanye", 'width':"100%"})
                    totalPages = int(re.search('maxPageNum = \d+', total.text)[0].replace('maxPageNum = ',''))
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
                articleURL = 'http://www.chinagoldgroup.com/'+a['href'].lstrip('../../')
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[requestURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[requestURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[requestURL])
                        last[LocDict[requestURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[requestURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[requestURL])
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
                        if table.find('td', attrs={'class': 'h_x_12'}):
                            publishTime = re.search('(\d+-\d+-\d+)',table.find('td', attrs={'class': 'h_x_12'}).text)[0].replace('-','')

                        # 保存文章位置
                        articleLocation = LocDict[requestURL]

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('table', attrs={'id': 'asop_content'}):
                            if articleSoup.find('table', attrs={'id': 'asop_content'}).find('p'):
                                articleTextList = articleSoup.find('table', attrs={'id': 'asop_content'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('table', attrs={'id': 'asop_content'}).text



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
                                    'site': '央企及地方重点国企官网-央企-中国黄金集团有限公司',
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
            logger.info('中国黄金-'+LocDict[requestURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if pageNum > totalPages or quitflag == 3:
                break
            while flag < 3:
                try:
                    nexturl = NextpageDict[requestURL] + str(totalPages-pageNum+1) + '.html'
                    r = requests.get(nexturl, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    # 如果没有请求下来完整的html页面，则再次请求
                    if not basesoup.find('td', attrs={'style': "padding:10px;"}):
                        logger.info('html页面未完整请求，10秒后再次请求')
                        sleep(10)
                        flag = 0
                        continue
                    titleNode = basesoup.find('td', attrs={'style': "padding:10px;"})
                    titleList = titleNode.find_all('tr')
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

# 13.中国能源建设集团有限公司
def delURLofceec():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    baseURL = 'http://www.ceec.net.cn/jsearch/search.do?appid=1&ck=x&pagemode=result&pos=title%2Ccontent&q='
    siteURL = 'http://www.ceec.net.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国能源建设集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&style=1&webid=40&&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'js-result'}).find_all('table')
                #如果找不到查询结果：
                if not titleNode:
                    flag = 3
                    titleList = []
                    break
                titleList = []
                for i in range(1,len(titleNode)-1):
                    titleList.append(titleNode[i])
                # 统计最大结果数
                totalResults = int(titleNode[0].find('b').text)
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
                        publishTime = ''
                        timeNode = articleSoup.head.find(attrs={'name': 'pubDate'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode['content']):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode['content'])[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'nowrap': 'nowrap'}):
                            articleLoc = articleSoup.find_all(attrs={'nowrap': 'nowrap'})
                            articleLocList = articleLoc[1].find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'id': 'zoom'}):
                            articleText = articleSoup.find(attrs={'id': 'zoom'}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国能源建设集团有限公司',
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
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            logger.info('中国能源建设-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&style=1&webid=40&&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'js-result'}).find_all('table')
                    titleList = []
                    for i in range(1, len(titleNode) - 1):
                        titleList.append(titleNode[i])
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

#14.中国电力建设集团有限公司
def delURLofPowerChina():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    baseURL = 'http://www.powerchina.cn/jsearch/search.do?appid=1&ck=x&imageField.x=0&imageField.y=0&pagemode=result&pos=title%2Ccontent&q='
    siteURL = 'http://www.powerchina.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国电力建设集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&style=1&webid=1&&p=' + str(pageNum)
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                titleNode = basesoup.find(attrs={'class': 'js-result'}).find_all('table')
                titleList = []
                if not titleNode:
                    flag = 3
                    break
                for i in range(1, len(titleNode)-1):
                    titleList.append(titleNode[i])
                # 统计最大结果数
                totalResults = int(titleNode[0].find('b').text)
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
                        article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'html5lib')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.head.find(attrs={'name': 'pubDate'})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode['content']):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode['content'])[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'wei fr'}):
                            if articleSoup.find(attrs={'class': 'wei fr'}).find('table'):
                                articleLoc = articleSoup.find(attrs={'class': 'wei fr'}).find('table')
                                articleLocList = articleLoc.find_all('a')
                                for articleLocNode in articleLocList:
                                    articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'bt_content'}):
                            articleTextList = articleSoup.find(attrs={'class': 'bt_content'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国电力建设集团有限公司',
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
            logger.info('中国电力建设-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&style=1&webid=1&&p=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'js-result'}).find_all('table')
                    titleList = []
                    for i in range(1, len(titleNode) - 1):
                        titleList.append(titleNode[i])
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

#15.中国航空器材集团有限公司
def delURLofHangkongQicai():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURLList = ['http://www.casc.com.cn/cas/?cat=10&paged=',
               'http://www.casc.com.cn/cas/?cat=9&paged=',
               'http://www.casc.com.cn/cas/?cat=14&paged=',
               'http://www.casc.com.cn/cas/?cat=12&paged=',
               'http://www.casc.com.cn/cas/?cat=13&paged=',
               'http://www.casc.com.cn/cas/?cat=18&paged=',
               'http://www.casc.com.cn/cas/?cat=4&paged=',
               'http://www.casc.com.cn/cas/?cat=36&paged=']
    LocDict = {'http://www.casc.com.cn/cas/?cat=10&paged=':'集团要闻',
               'http://www.casc.com.cn/cas/?cat=9&paged=':'业务板块新闻',
               'http://www.casc.com.cn/cas/?cat=14&paged=':'国资动态',
               'http://www.casc.com.cn/cas/?cat=12&paged=':'媒体聚焦',
               'http://www.casc.com.cn/cas/?cat=13&paged=':'企业公告',
               'http://www.casc.com.cn/cas/?cat=18&paged=':'安全管理',
               'http://www.casc.com.cn/cas/?cat=4&paged=':'社会责任',
               'http://www.casc.com.cn/cas/?cat=36&paged=':'科技创新'}
    siteURL = 'http://www.casc.com.cn/'
    for baseURL in baseURLList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[baseURL] in last:
                last_updated_url = last[LocDict[baseURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国航空器材集团有限公司'+'子栏目：' + LocDict[baseURL])
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                #获取最大页码
                total = basesoup.find('div', attrs={'class': 'wp-pagenavi'})
                if not total:
                    totalPages = 1
                else:
                    totalPages = int(re.search('(/ \d+ 页)', total.text)[0].replace('/ ','').replace(' 页',''))
                titleNode = basesoup.find('div', attrs={'id': "bg2"})
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
                if 'http://http://' in articleURL:
                    articleURL = articleURL[7:]
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[baseURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[baseURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                        last[LocDict[baseURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[baseURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
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
                        publishTime = re.search('(\d+-\d+-\d+)', table.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = LocDict[baseURL]

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'content'}).text
                        elif articleSoup.find('div', attrs={'class': 'zsy_content'}):
                            articleText = articleSoup.find('div', attrs={'class': 'zsy_content'}).text

                        # 判断标题或正文是否含有关键词
                        matched_keywords_list = []
                        for each_keyword in config.keywords_list:
                            if each_keyword in articleTitle or each_keyword in articleText or each_keyword in htmlSource:
                                matched_keywords_list.append(each_keyword)
                        if matched_keywords_list.__len__() > 0:
                            if collection.find({'url': htmlURL}).count() == 0:
                                item = {
                                    'url': htmlURL,
                                    'title': articleTitle,
                                    'date': publishTime,
                                    'site': '央企及地方重点国企官网-央企-中国航空器材集团有限公司',
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
            logger.info('中国航空器材集团-'+LocDict[baseURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'id': "bg2"})
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

#16.中国航空油料集团有限公司
def delURLofHKYouliao():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    requestURL = 'https://www.cnaf.com/PORTAL_LNG_RLS_XWGJ.getSearchList.do'
    siteURL = 'https://www.cnaf.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国航空油料集团有限公司'+'关键词：' + key)
        while flag < 3:
            try:
                data={'XW_TITLE': key, 'pageNo': str(pageNum)}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = 'utf-8'
                r = json.loads(r.text)
                titleNode = r['searchHTML']
                basesoup = BeautifulSoup(titleNode,'lxml')
                titleList = basesoup.find_all('li')
                #统计总页数
                totalPages = int(r['totalPage'])
                flag = 3
                if r['endPage']=='0':
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
                urltail = a['href'].lstrip('../../..')
                articleURL = 'https://www.cnaf.com/'+urltail
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        artNodeList = articleSoup.find_all('script', attrs={'type': 'text/javascript'})
                        if len(artNodeList)-2 < 0:
                            break
                        artNode = artNodeList[len(artNodeList)-2]
                        lmCode = re.search('var lmCode = "(\w+)"', artNode.text)[1]
                        xwCode = re.search('var xwCode = "(\w+)"', artNode.text)[1]
                        artdata = {'XW_CODE': xwCode, 'LM_CODE': lmCode}
                        artJson = requests.post('https://www.cnaf.com/PORTAL_LNG_RLS_XWGJ.getContent.do',headers=headers,data=artdata)
                        artJson.encoding = 'utf-8'
                        article = json.loads(artJson.text)
                        articleSoup = BeautifulSoup(article['contentHTML'], 'lxml')
                        articleSoup.prettify()
                        # 保存html页面源码
                        htmlSource = article['contentHTML']

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('h5'):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find('h5').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'selectTag xuanzhong'}):
                            articleLocation = articleSoup.find(attrs={'class': 'selectTag xuanzhong'}).find('a').text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'yewu_title'}):
                            articleTextList = articleSoup.find(attrs={'class': 'yewu_title'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国航空油料集团有限公司',
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
            logger.info('中国航空油料集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数已经超过最大页码数，则退出循环
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'XW_TITLE': key, 'pageNo': str(pageNum)}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = 'utf-8'
                    r = json.loads(r.text)
                    titleNode = r['searchHTML']
                    basesoup = BeautifulSoup(titleNode, 'lxml')
                    titleList = basesoup.find_all('li')
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

#17.中国民航信息集团有限公司
def delURLofMinHangXinXi():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    baseURL = 'http://www.travelsky.net/dig/search.action?ty=&w=false&f=&dr=true&p='
    siteURL = 'http://www.travelsky.net/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国民航信息集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&advtime=&advrange=&fq=siteid%3Amain&q=' + key + '&startTime=&endTime=&sr=score+desc'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                total = basesoup.find(attrs={'class': 'left_tit'}).text
                totalResults = int(re.search('(\d+)', total)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find(attrs={'class': 'cen_list'})
                titleList = titleNode.find_all('ul')
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
                a = table.h3.a
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
                        publishTime = ''
                        timeNode = table.li
                        if timeNode:
                            publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class': 'next_menu_body'}):
                            if articleSoup.find(attrs={'class': 'next_menu_body'}).find(attrs={'class':'Selected'}):
                                articleLocation = articleSoup.find(attrs={'class': 'next_menu_body'}).find(attrs={'class': 'Selected'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td',attrs={'class': 'neirong'}):
                            articleTextList = articleSoup.find('td',attrs={'class': 'neirong'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国民航信息集团有限公司',
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
            logger.info('中国民航信息集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&advtime=&advrange=&fq=siteid%3Amain&q=' + key + '&startTime=&endTime=&sr=score+desc'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find(attrs={'class': 'cen_list'})
                    titleList = titleNode.find_all('ul')
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

#18.新兴际华集团有限公司
def delURLofXinxingJihua():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    baseURL = 'http://www.xxcig.com/cms/search/searchResults.jsp?query='
    siteURL = 'http://www.xxcig.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取新兴际华集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&siteID=45&offset=' + str(count) + '&rows=10&flg=1'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                total = basesoup.find('td', attrs={'class': 'tboder'})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find('td', attrs={'align': 'center'})
                titleList = titleNode.find_all('blockquote')
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
                if 'http:' in a['href']:
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.xxcig.com/cms/search/'+a['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if a.find('font'): articleTitle = a.find('font').text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('font', attrs={'color':"#008000"}):
                            publishTime = re.search('(\d+年\d+月\d+日)', table.find('font', attrs={'color':"#008000"}).text)[0].replace('年', '').replace('月', '').replace('日', '')
                        elif articleSoup.find('h3'):
                            publishTime = re.search('(\d+-\d+-\d+)', articleSoup.find('h3').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'add'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'add'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'art_con'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'art_con'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-新兴际华集团有限公司',
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
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            logger.info('新兴际华集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&siteID=45&offset=' + str(count) + '&rows=10&flg=1'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('td', attrs={'align': 'center'})
                    titleList = titleNode.find_all('blockquote')
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

# 19.中国煤炭地质总局
def delURLofMeitanZongju():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    baseURL = 'http://www.ccgc.cn/module/sitesearch/index.jsp?keyword=vc_title&columnid=0&keyvalue='
    siteURL = 'http://www.ccgc.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国煤炭地质总局'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&webid=1&modalunitid=23765&currpage=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                total = basesoup.find('td',attrs={'align': 'right', 'style':'padding-right:15px;color:#0064CC'})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode1 = basesoup.find('div').find_all('table',attrs={'width':'961','cellspacing':'0','cellpadding':'0','border':'0','align':'center'})
                titleNode2 = titleNode1[len(titleNode1)-1]
                titleList = titleNode2.find('table',attrs={'width':'100%','cellspacing':'0','cellpadding':'0','border':'0'}).find_all('a')
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
                articleURL = table['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if table['title']: articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if re.search('(\d+/\d+/\d+)', articleURL):
                            publishTime = re.search('(\d+/\d+/\d+)', articleURL)[0].replace('/', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find(attrs={'class':'bt_link'}):
                            articleLocList = articleSoup.find_all(attrs={'class':'bt_link'})
                            for articleLocNode in articleLocList:
                                articleLocation += '>'+articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleTextList = articleSoup.find('div', attrs={'id': 'zoom'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国煤炭地质总局',
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
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            logger.info('中国煤炭地质总局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&webid=1&modalunitid=23765&currpage=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode1 = basesoup.find('div').find_all('table', attrs={'width': '961', 'cellspacing': '0',
                                                                               'cellpadding': '0', 'border': '0',
                                                                               'align': 'center'})
                    titleNode2 = titleNode1[len(titleNode1) - 1]
                    titleList = titleNode2.find('table', attrs={'width': '100%', 'cellspacing': '0', 'cellpadding': '0',
                                                                'border': '0'}).find_all('a')
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

#20.中国冶金地质总局
def delURLofYejinZongju():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
        'Refer': 'http://www.cmgb.com.cn/searchcontent/search.jsp'
    }
    requestURL = 'http://www.cmgb.com.cn/searchcontent/search.jsp'
    siteURL = 'http://www.cmgb.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国冶金地质总局')
        logger.info('关键词：' + key)
        while flag < 3:
            try:
                data = {'topic': key, 'Page': str(pageNum), 'sid': '1'}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                titleNode = basesoup.find('table', attrs={'align':"center", 'border':"0", 'cellpadding':"0", 'cellspacing':"0", 'class':"m_t10 f12_grey", 'width':"100%"})
                titleList = titleNode.find_all('tr')
                flag = 3
                # 统计总页数
                total = basesoup.find('table', attrs={'align':"center", 'border':"0", 'cellpadding':"0", 'cellspacing':"0", 'style':" margin-top:15px;", 'width':"80%"})
                total2 = total.find_all('b')
                totalPages = int(total2[2].text)
                if totalPages == 0:
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
                else: articleURL = 'http://www.cmgb.com.cn' + a['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find(attrs={'class':'news_time'}):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find(attrs={'class':'news_time'}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'class':"zjxw_tit", 'width':"100"}):
                            articleLocation = articleSoup.find('td', attrs={'class':"zjxw_tit", 'width':"100"}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'class': 'news_content p'}):
                            if articleSoup.find(attrs={'class': 'news_content p'}).find('p'):
                                articleTextList = articleSoup.find(attrs={'class': 'news_content p'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else: articleText = articleSoup.find(attrs={'class': 'news_content p'}).text


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
                                    'site': '央企及地方重点国企官网-央企-中国冶金地质总局',
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
            logger.info('中国冶金地质总局-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数已经超过最大页码数，则退出循环
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'topic': key, 'Page': str(pageNum), 'sid': '1'}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('table', attrs={'align': "center", 'border': "0", 'cellpadding': "0",
                                                              'cellspacing': "0", 'class': "m_t10 f12_grey",
                                                              'width': "100%"})
                    titleList = titleNode.find_all('tr')
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

#21.中国建设科技有限公司
def delURLofJiansheKeji():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip,deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,eo;q=0.8,ht;q=0.7,en;q=0.6',
        'Host': 'www.cadreg.com.cn'}
    baseURL = 'http://www.cadreg.com.cn/tabid/39/searchmid/418/searchtid/38/549pageidx/'
    siteURL = 'http://www.cadreg.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国建设科技有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '/Default.aspx?keywords=' + key
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                totalResults = 10000
                totalPages = 1000
                total = basesoup.find('td', attrs={'class':"Normal", 'valign':"bottom", 'align':"left", 'nowrap':"true", 'style':"width:40%;"})
                if total:
                    totalResults = int(re.search('(\d+)', total.text)[0])
                else:
                    totalPages = 1
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find('table', attrs={'id':"ess_ctr549_ListC_Info_LstC_Info", 'cellspacing':"0", 'cellpadding':"0", 'border':"0", 'style':"width:100%;border-collapse:collapse;"})
                if not titleNode:
                    titleList = []
                    break
                titleList = titleNode.find_all('a')
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
                if 'http:' in table['href']:
                    articleURL = table['href']
                else:
                    articleURL = 'http://www.cadreg.com.cn' + table['href']
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
                        articleTitle = table.text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = articleSoup.find('td', attrs={'valign':"middle", 'align':"left", 'style':"font-size: 12px; color: #000000; height: 30px;"})
                        if timeNode:
                            if re.search('(\d+-\d+-\d+)', timeNode.text):
                                publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('td', attrs={'align':"left", 'colspan':"2", 'style':"font-size: 12px; color: #000000; line-height: 30px; height: 30px;"}):
                            articleLocList = articleSoup.find('td', attrs={'align':"left", 'colspan':"2", 'style':"font-size: 12px; color: #000000; line-height: 30px; height: 30px;"}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('td', attrs={'id': 'zoom'}):
                            articleTextList = articleSoup.find('td', attrs={'id': 'zoom'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国建设科技有限公司',
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
            logger.info('中国建设科技有限公司-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if (count >= totalResults) or (int(pageNum) > totalPages) or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '/Default.aspx?keywords=' + key
                    r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('table',
                                              attrs={'id': "ess_ctr549_ListC_Info_LstC_Info", 'cellspacing': "0",
                                                     'cellpadding': "0", 'border': "0",
                                                     'style': "width:100%;border-collapse:collapse;"})
                    if not titleNode:
                        titleList = []
                        break
                    titleList = titleNode.find_all('a')
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

#22.中国保利集团有限公司
def defURLofBaoli():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.poly.com.cn/1435.html?word='
    siteURL = 'http://www.poly.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国保利集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&author=&sd=&ed=&mode=1&sort=1&pindex=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                totalResults = 10000
                totalPages = 1000
                total = basesoup.find('span', attrs={'id': "dnn_ctr4867_Searcher_lblCount", 'class': "lbl-col"})
                if total:
                    totalResults = int(re.search('(\d+)', total.text)[0])
                else:
                    totalPages = 1
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                if titleNode:
                    titleList = titleNode.find_all('div', attrs={'class':'s-result-item-title'})
                else: titleList = []
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
                articleURL = table.find('a')['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find(attrs={'id':'Title'}):
                            articleTitle = articleSoup.find(attrs={'id':'Title'}).text
                        elif articleSoup.find('span', attrs={'id':"dnn_ctr5986_zhdTITLE_titleLabel", 'class':"Head"}):
                            articleTitle = articleSoup.find('span', attrs={'id':"dnn_ctr5986_zhdTITLE_titleLabel", 'class':"Head"}).text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'class': "result-date"})
                        if timeNode:
                            publishTime = table.find('span', attrs={'class': "result-date"}).text

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "content-path"}):
                            articleLocList = articleSoup.find('div', attrs={'class': "content-path"}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Content'}):
                            if articleSoup.find('div', attrs={'id': 'Content'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleText = articleSoup.find('div', attrs={'id': 'Content'}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国保利集团有限公司',
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
            logger.info('中国保利集团有限公司-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if (count >= totalResults) or (int(pageNum) > totalPages) or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&author=&sd=&ed=&mode=1&sort=1&pindex=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                    if titleNode:
                        titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                    else:
                        titleList = []
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

#23. 中国医药集团有限公司
def delURLofYiyaoJituan():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.sinopharm.com/1229.html?word='
    siteURL = 'http://www.sinopharm.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国医药集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&author=&sd=&ed=&mode=1&sort=1&pindex=' + str(pageNum)
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                total = basesoup.find('span', attrs={'id': "dnn_ctr4118_Searcher_lblCount", 'class': "lbl-col"})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                if titleNode:
                    titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                else:
                    titleList = []
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
                articleURL = table.find('a')['href']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find(attrs={'id': 'Title'}):
                            articleTitle = articleSoup.find(attrs={'id': 'Title'}).text
                            if articleSoup.find(attrs={'id': 'SubTitle'}):
                                articleTitle += articleSoup.find(attrs={'id': 'SubTitle'}).text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'clas': "result-date"})
                        if timeNode:
                            publishTime = table.find('span', attrs={'clas': "result-date"}).text

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "Gst-breadrumb"}):
                            articleLocList = articleSoup.find('div', attrs={'class': "Gst-breadrumb"}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Content'}):
                            if articleSoup.find('div', attrs={'id': 'Content'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('p')
                            else: articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('div')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国医药集团有限公司',
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
            logger.info('中国医药集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&author=&sd=&ed=&mode=1&sort=1&pindex=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                    if titleNode:
                        titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                    else:
                        titleList = []
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

#24.中国林业集团有限公司
def delURLofLinyeJituan():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.cfgc.cn/g2758.aspx?word='
    siteURL = 'http://www.cfgc.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国林业集团有限公司'+'关键词：' + key)
        # 记录已爬取的结果数
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                # 统计最大结果数
                total = basesoup.find('span', attrs={'id': "dnn_ctr6329_List_lblCount", 'class': "lbl-col"})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults <= 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                if titleNode:
                    titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                else:
                    titleList = []
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
                articleURL = table.find('a')['href']
                flag = 0
                count += 1
                if articleURL == 'http://www.cfgc.cn/Portals/0/Uploads/Files/2017/12-25/636498113033803152.jpg':
                    continue
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = article.url

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find(attrs={'id': 'Title'}):
                            articleTitle = articleSoup.find(attrs={'id': 'Title'}).text
                            if articleSoup.find(attrs={'id': 'SubTitle'}):
                                articleTitle += articleSoup.find(attrs={'id': 'SubTitle'}).text

                        # 保存文章发布时间
                        publishTime = ''
                        timeNode = table.find('span', attrs={'clas': "result-date"})
                        if timeNode:
                            publishTime = table.find('span', attrs={'clas': "result-date"}).text

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': "cfgc-content-path"}):
                            articleLocList = articleSoup.find('div', attrs={'class': "cfgc-content-path"}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Content'}):
                            if articleSoup.find('div', attrs={'id': 'Content'}).find('p'):
                                articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国林业集团有限公司',
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
            logger.info('中国林业集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的文章已经超过最大结果数，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    titleNode = basesoup.find('div', attrs={'class': "G-sResult"})
                    if titleNode:
                        titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                    else:
                        titleList = []
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

#25.中国中丝集团有限公司
def delURLofChinasilk():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
        'Refer': 'http://www.chinasilk.com/NewsInfoSearch?searchKey=%E4%B8%9D%E7%BB%B8'
    }
    requestURL = 'http://www.chinasilk.com/Designer/Common/GetData'
    siteURL = 'http://www.chinasilk.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国中丝集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                data = {'dataType': 'news', 'key': key, 'pageIndex': str(pageNum-1), 'pageSize': '4', 'selectCategory': '0', 'dateFormater': 'yyyy-MM-dd', 'orderByField': 'createtime', 'orderByType': 'desc', 'templateId': '0', 'es': 'true', 'setTop': 'true', '__RequestVerificationToken': '$__RequestVerificationToken$'}
                r = requests.post(requestURL, headers=headers, data=data)
                r.encoding = 'utf-8'
                r = json.loads(r.text)
                if r['IsSuccess'] == 'False':
                    continue
                titleList = r['Data']
                # 统计总结果数和总页数
                totalPages = int(r['TotalPages'])
                totalResults = int(r['TotalCount'])
                flag = 3
                if totalResults == 0:
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
                if 'http:' in table['LinkUrl']:
                    articleURL = table['LinkUrl']
                else:
                    articleURL = 'http://www.chinasilk.com' + table['LinkUrl']
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
                        flag = 3
                        article.encoding = article.apparent_encoding
                        articleSoup = BeautifulSoup(article.text, 'lxml')
                        articleSoup.prettify()

                        #如果没有请求下来完整的html页面，则再次请求
                        if not articleSoup.head.meta:
                            logger.info('html页面未完整请求，5秒后再次请求')
                            sleep(5)
                            flag = 0
                            continue
                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = table['Name']

                        # 保存文章发布时间
                        publishTime = ''
                        if table['QTime']:
                            publishTime = table['QTime'].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'w-crumbs'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'w-crumbs'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>'+articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'w-detail'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'w-detail'}).find_all('span')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国中丝集团有限公司',
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
            logger.info('中国中丝集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if pageNum > totalPages or count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    data = {'dataType': 'news', 'key': key, 'pageIndex': str(pageNum - 1), 'pageSize': '4',
                            'selectCategory': '0', 'dateFormater': 'yyyy-MM-dd', 'orderByField': 'createtime',
                            'orderByType': 'desc', 'templateId': '0', 'es': 'true', 'setTop': 'true',
                            '__RequestVerificationToken': '$__RequestVerificationToken$'}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = 'utf-8'
                    r = json.loads(r.text)
                    if r['IsSuccess'] == 'False':
                        continue
                    titleList = r['Data']
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

#26.中国农业发展集团有限公司
def delURLofNongyeFazhan():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.cnadc.com.cn/index.php?m=search&c=index&a=init&typeid=1&siteid=1&q='
    siteURL = 'http://www.cnadc.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国农业发展集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&page=' + str(pageNum)
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数和总页数
                total = basesoup.find('div', attrs={'class':"jg"})
                totalResults = int(re.search('(\d+)',total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('ul',attrs={'class':'wrap'})
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
                        article = requests.get(articleURL, headers=headers, proxies=getOneProxy())
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
                        if articleSoup.find('div', attrs={'id':'title'}):
                            articleTitle = articleSoup.find('div', attrs={'id':'title'}).text
                        elif articleSoup.find('td', attrs={'class':"title_h14 pad_top"}):
                            articleTitle = articleSoup.find('td', attrs={'class':"title_h14 pad_top"}).text
                        elif articleSoup.find('td', attrs={'style':"FONT-SIZE: 16px", 'class':"title_h14 pad_top", 'colspan':"2", 'align':"center"}):
                            articleTitle = articleSoup.find('td', attrs={'style':"FONT-SIZE: 16px", 'class':"title_h14 pad_top", 'colspan':"2", 'align':"center"}).text

                            # 保存文章发布时间
                        publishTime = ''
                        if table.find('div', attrs={'class':'adds'}):
                            publishTime = re.search('(\d+-\d+-\d+)',table.find('div', attrs={'class':'adds'}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'nav-p'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'nav-p'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text
                        elif articleSoup.find('td', attrs={'style':"PADDING-LEFT: 15px", 'bgcolor':"#dfdfdf", 'align':"left"}):
                            articleLocList = articleSoup.find('td', attrs={'style':"PADDING-LEFT: 15px", 'bgcolor':"#dfdfdf", 'align':"left"}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find(attrs={'id': 'zoom'}):
                            articleText = articleSoup.find(attrs={'id': 'zoom'}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国农业发展集团有限公司',
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
            logger.info('中国农业发展集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&page=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('ul', attrs={'class': 'wrap'})
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

#27.电信科学技术研究院有限公司
def delURLofDTDianxin():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.datanggroup.cn/templates/T_Second/index.aspx?nodeid=60&keyword='
    siteURL = 'http://www.datanggroup.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取电信科学技术研究院有限公司'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&pagesize=' + str(pageNum) +'&pagenum=20'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总页数
                totalPages = 1
                total = basesoup.find('span', attrs={'class': "page"})
                if total:
                    if re.search('(\d+)', total.text):
                        totalPages = int(re.search('(\d+)', total.text)[0])
                titleNode = basesoup.find('ul', attrs={'class': 'acc_newsList', 'id': 'acc_SearchList'})
                if titleNode: titleList = titleNode.find_all('li')
                else: titleList = []
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
                    articleURL = 'http://www.datanggroup.cn' + a['href']
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
                        articleTitle = a['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if articleSoup.find('div', attrs={'class': 'm2nw_info'}):
                            if articleSoup.find('div', attrs={'class': 'm2nw_info'}).find('div', attrs={'class': 'right'}):
                                publishTime = re.search('(\d+-\d+-\d+)', articleSoup.find('div', attrs={'class': 'm2nw_info'}).find('div', attrs={'class': 'right'}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'm2Con_posAdr'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'm2Con_posAdr'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'm2nw_edit'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'm2nw_edit'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-电信科学技术研究院有限公司',
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
            logger.info('电信科学技术研究院-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if int(pageNum) > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&pagesize=' + str(pageNum) + '&pagenum=20'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('ul', attrs={'class': 'acc_newsList', 'id': 'acc_SearchList'})
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
    logger.info("finish")
    return;

#28.中国普天信息产业集团有限公司
def delURLofPutian():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURLList = ['http://www.potevio.com/g333/m1033/mp',
                   'http://www.potevio.com/g334/m1034/mp',
                   'http://www.potevio.com/g335/m1035/mp',
                   'http://www.potevio.com/g325/m1676/mp',
                   'http://www.potevio.com/g764/m2127/mp',
                   'http://www.potevio.com/g765/m2128/mp',
                   'http://www.potevio.com/g327/m1675/mp',
                   'http://www.potevio.com/g328/m1675/mp',
                   'http://www.potevio.com/g350/m1675/mp',
                   'http://www.potevio.com/g790/m1675/mp',
                   'http://www.potevio.com/g356/m1260/mp',
                   'http://www.potevio.com/g391/m1688/mp']
    LocDict = {'http://www.potevio.com/g333/m1033/mp':'公司新闻',
                   'http://www.potevio.com/g334/m1034/mp':'出资企业动态',
                   'http://www.potevio.com/g335/m1035/mp':'上市公司信息披露',
                   'http://www.potevio.com/g325/m1676/mp':'媒体关注',
                   'http://www.potevio.com/g764/m2127/mp':'国有经济',
                   'http://www.potevio.com/g765/m2128/mp':'国资监管',
                   'http://www.potevio.com/g327/m1675/mp':'行业资讯',
                   'http://www.potevio.com/g328/m1675/mp':'公司公告',
                   'http://www.potevio.com/g350/m1675/mp':'上市公告',
                   'http://www.potevio.com/g790/m1675/mp':'文化故事',
                   'http://www.potevio.com/g356/m1260/mp':'文化活动',
                   'http://www.potevio.com/g391/m1688/mp':'相关新闻'}
    siteURL = 'http://www.potevio.com/'
    for baseURL in baseURLList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[baseURL] in last:
                last_updated_url = last[LocDict[baseURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国普天信息产业集团有限公司'+'子栏目：' + LocDict[baseURL])
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '.aspx'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 获取最大页码
                total = basesoup.find('span', attrs={'class': 'i-pager-info-p'})
                totalPages = int(re.search('(\d+)', total.text)[0])
                if totalPages == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'id': "dnn_ContentPane"})
                titleList = titleNode.find_all('div', attrs={'class': 'right-news-item'})
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
                    articleURL = 'http://www.potevio.com' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[baseURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[baseURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                        last[LocDict[baseURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[baseURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
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
                        articleTitle = a['title']

                        # 保存文章发布时间
                        publishTime = re.search('(\d+-\d+-\d+)', table.find('div', attrs={'class': 'right-news-item-date'}).text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = LocDict[baseURL]

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'article_content'}):
                            if articleSoup.find('div', attrs={'id': 'article_content'}).find('span'):
                                articleTextList = articleSoup.find('div', attrs={'id': 'article_content'}).find_all('span')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
                            else:
                                articleTextList = articleSoup.find('div', attrs={'id': 'article_content'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text
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
                                    'site': '央企及地方重点国企官网-央企-中国普天信息产业集团有限公司',
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
            logger.info('中国普天信息产业集团-'+LocDict[baseURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            if pageNum > totalPages or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '.aspx'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'id': "dnn_ContentPane"})
                    titleList = titleNode.find_all('div', attrs={'class': 'right-news-item'})
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

#29.中国交通建设集团有限公司
def delURLofJiaotongJianshe():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.cccnews.cn/search/search?page='
    siteURL = 'http://www.cccnews.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国交通建设集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&channelid=112248&searchword=' + key + '&prepage=20'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.h2
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': 'scy_zbyw'})
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

                        # 保存html页面源码
                        htmlSource = article.text

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = ''
                        if articleSoup.find('h2'):
                            if articleSoup.find('h2').find('font'):
                                articleTitle = articleSoup.find('h2').find('font').text
                            else: articleTitle = articleSoup.find('h2').text
                        if articleSoup.find('h3'):
                            if articleSoup.find('h3').find('font'):
                                articleTitle = articleSoup.find('h3').find('font').text
                            else: articleTitle = articleSoup.find('h3').text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('span'):
                            publishTime = re.search('(\d+.\d+.\d+)', table.find('span').text)[0].replace('.', '')

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
                                    'site': '央企及地方重点国企官网-央企-中国交通建设集团有限公司',
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
            logger.info('中国交通建设集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag == 3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&channelid=112248&searchword=' + key + '&prepage=20'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'scy_zbyw'})
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

#30.中国铁道建筑有限公司
def delURLofZhongguoTiejian():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.crcc.cn/jrobotwww/search.do?webid=1&analyzeType=1&pg=12&p='
    siteURL = 'http://www.crcc.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国铁道建筑有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Csectitle%2Cthdtitle%2Ccontent%2Cauthor%2Cmemo%2C_default_search&od=&date=&date='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.find('div', attrs={'id': 'jsearch-info-box'})
                if not total['data-total']:
                    totalResults = 0
                    titleList = []
                    break
                totalResults = int(total['data-total'])
                titleNode = basesoup.find('div', attrs={'id': 'jsearch-result-items', 'class': 'ui-search-result-items'})
                titleList = titleNode.find_all('div', attrs={'class': 'jsearch-result-box'})
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
                    articleURL = 'http://www.crcc.cn' + a['href']
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
                        if table.find('span', attrs={'class': 'jsearch-result-date'}):
                            publishTime = re.search('(\d+年\d+月\d+日)', table.find('span', attrs={'class': 'jsearch-result-date'}).text)[0].replace('年', '').replace('月', '').replace('日', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'position1'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'position1'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'zoom'}):
                            articleTextList = articleSoup.find('div', attrs={'id': 'zoom'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国铁道建筑有限公司',
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
            logger.info('中国铁道建筑有限公司-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag==3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(
                        pageNum) + '&tpl=&category=&q=' + key + '&pos=title%2Csectitle%2Cthdtitle%2Ccontent%2Cauthor%2Cmemo%2C_default_search&od=&date=&date='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    totalResults = int(total['data-total'])
                    titleNode = basesoup.find('div',
                                              attrs={'id': 'jsearch-result-items', 'class': 'ui-search-result-items'})
                    titleList = titleNode.find_all('div', attrs={'class': 'jsearch-result-box'})
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

#31.中国铁路工程集团有限公司
def delURLofTieluGongcheng():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.crecg.com/dig/ui/search.action?ty=&w=false&f=&dr=true&p='
    siteURL = 'http://www.crecg.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国铁路工程集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + str(pageNum) + '&sr=score+desc&rp=&advtime=&advrange=&fq=&q=' + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.find('div', attrs={'class': 'cen_top'}).find('h3')
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': 'cen_list'})
                #把搜索结果中的相似文档去除
                if titleNode.find('div', attrs={'class':"con_relArticleList"}):
                    titleNode.find('div', attrs={'class':"con_relArticleList"}).decompose()
                titleList = titleNode.find_all('ul')
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
                    articleURL = 'http://www.crecg.com' + a['href']
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
                        if table.find('li'):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find('li').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'xxcur'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'xxcur'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'xxcontent', 'id': 'zoom'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'xxcontent', 'id': 'zoom'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国铁路工程集团有限公司',
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
            logger.info('中国铁路工程集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag==3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + str(pageNum) + '&sr=score+desc&rp=&advtime=&advrange=&fq=&q=' + key
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'cen_list'})
                    # 把搜索结果中的相似文档去除
                    if titleNode.find('div', attrs={'class': "con_relArticleList"}):
                        titleNode.find('div', attrs={'class': "con_relArticleList"}).decompose()
                    titleList = titleNode.find_all('ul')
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

#32.中国铁路通信信号集团有限公司
def delURLofTieluXinhao():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.crsc.cn/1151.html?word='
    siteURL = 'http://www.crsc.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国铁路通信信号集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.find('span', attrs={'id':"dnn_ctr3876_List_lblCount", 'class':"lbl-col"})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': 'G-sResult'})
                titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
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
                    articleURL = 'http://www.crsc.cn' + a['href']
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
                        if table.find('span', attrs={'clas': 'result-date'}):
                            publishTime = table.find('span', attrs={'clas': 'result-date'}).text

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'Gst-breadrumb'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'Gst-breadrumb'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': 'Content'}):
                            articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国铁路通信信号集团有限公司',
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
            logger.info('中国铁路通信信号集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag==3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'G-sResult'})
                    titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
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

#33.中国中车集团有限公司
def delURLofZhongche():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.crrcgc.cc/g4925.aspx?word='
    siteURL = 'http://www.crrcgc.cc/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 18
        flag = 0
        print('开始爬取中国中车集团有限公司')
        print('关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.find('span', attrs={'id': "dnn_ctr10332_List_lblCount", 'class': "lbl-col"})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('div', attrs={'class': 'G-sResult'})
                titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                if totalResults > 0 and titleList == []:
                    flag = 0
                    sleep(15)
                    continue
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
                        if '.pdf' in articleURL:
                            flag = 3
                            # 保存html页面源码
                            htmlSource = ''

                            # html的URL地址
                            htmlURL = articleURL

                            # 保存文章标题信息
                            articleTitle = a.text

                            # 保存文章发布时间
                            publishTime = ''
                            if table.find('span', attrs={'clas': 'result-date'}):
                                publishTime = table.find('span', attrs={'clas': 'result-date'}).text

                            # 保存文章位置
                            articleLocation = ''

                            # 保存文章正文
                            articleText = ''
                            if not os.path.exists(
                                    './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                os.mkdir('./file_data')
                                os.chdir('./file_data')
                            if os.path.exists('./file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                os.chdir('./file_data')
                            if not os.path.exists('./' + articleTitle + '.pdf'):  # 如果文件尚未存在
                                f = requests.get(articleURL)
                                with open('./' + articleTitle + '.pdf', "wb") as code:
                                    code.write(f.content)
                                logger.info('pdf download over')
                            # 解析pdf文件并判断关键字
                            articleText = ''
                            docText = utility_convert.convert_pdf_to_txt('./' + articleTitle + '.pdf')
                            if docText:
                                for docNode in docText:
                                    articleText += docNode

                        else:
                            article = requests.get(articleURL, headers=headers)
                            article.encoding = article.apparent_encoding
                            articleSoup = BeautifulSoup(article.text, 'lxml')
                            flag = 3
                            # 保存html页面源码
                            htmlSource = article.text

                            # html的URL地址
                            htmlURL = articleURL

                            # 保存文章标题信息
                            articleTitle = a.text

                            # 保存文章发布时间
                            publishTime = ''
                            if table.find('span', attrs={'clas': 'result-date'}):
                                publishTime = table.find('span', attrs={'clas': 'result-date'}).text

                            # 保存文章位置
                            articleLocation = ''
                            if articleSoup.find('div', attrs={'class': 'Gst-breadrumb'}):
                                articleLocList = articleSoup.find('div', attrs={'class': 'Gst-breadrumb'}).find_all('a')
                                for articleLocNode in articleLocList:
                                    articleLocation += '>' + articleLocNode.text

                            # 保存文章正文
                            articleText = ''
                            if articleSoup.find('div', attrs={'id': 'Content'}):
                                articleTextList = articleSoup.find('div', attrs={'id': 'Content'}).find_all('p')
                                for articleTextNode in articleTextList:
                                    articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国中车集团有限公司',
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
            logger.info('中国中车集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            # 如果爬取的页数或结果数已经超过上限，则退出循环
            if count >= totalResults or quitflag==3:
                break
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&author=&sd=&ed=&mode=&sort=d&pindex=' + str(pageNum) + '&amid='
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'G-sResult'})
                    titleList = titleNode.find_all('div', attrs={'class': 's-result-item-title'})
                    if titleList == []:
                        flag = 0
                        sleep(15)
                        continue
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

#34.中国建筑科学研究院有限公司
def delURLofJianzhuKexueyuan():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = ['http://www.cabr.com.cn/sub2_5_xinwenzhongxin.aspx',
               'http://www.cabr.com.cn/sub2_7_xinwenzhongxin.aspx',
               'http://www.cabr.com.cn/sub2_10_xinwenzhongxin.aspx',
               'http://www.cabr.com.cn/sub2_1_xinwenzhongxin.aspx',
               'http://www.cabr.com.cn/sub2_2_xinwenzhongxin.aspx']
    LocDict = {'http://www.cabr.com.cn/sub2_5_xinwenzhongxin.aspx':'信息公开',
               'http://www.cabr.com.cn/sub2_7_xinwenzhongxin.aspx':'国资要闻',
               'http://www.cabr.com.cn/sub2_10_xinwenzhongxin.aspx':'关注与视野',
               'http://www.cabr.com.cn/sub2_1_xinwenzhongxin.aspx':'通知公告',
               'http://www.cabr.com.cn/sub2_2_xinwenzhongxin.aspx':'新闻动态'}
    posturlDict = {
        'http://www.cabr.com.cn/sub2_5_xinwenzhongxin.aspx':'http://www.cabr.com.cn/sub2_5_xinwenzhongxin.aspx?EoneAjax_CallBack=true',
               'http://www.cabr.com.cn/sub2_7_xinwenzhongxin.aspx':'http://www.cabr.com.cn/sub2_7_xinwenzhongxin.aspx?EoneAjax_CallBack=true',
               'http://www.cabr.com.cn/sub2_10_xinwenzhongxin.aspx':'http://www.cabr.com.cn/sub2_10_xinwenzhongxin.aspx?EoneAjax_CallBack=true',
               'http://www.cabr.com.cn/sub2_1_xinwenzhongxin.aspx':'http://www.cabr.com.cn/sub2_1_xinwenzhongxin.aspx?EoneAjax_CallBack=true',
               'http://www.cabr.com.cn/sub2_2_xinwenzhongxin.aspx':'http://www.cabr.com.cn/sub2_2_xinwenzhongxin.aspx?EoneAjax_CallBack=true'}
    siteURL = 'http://www.cabr.com.cn/'
    for requestURL in baseURL:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[requestURL] in last:
                last_updated_url = last[LocDict[requestURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国建筑科学研究院有限公司'+'子栏目：' + LocDict[requestURL])
        while flag < 3:
            try:
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                # 获取VIEWSTATE
                viewstate = basesoup.find(attrs={'id': '____VIEWSTATE'})['value']
                data = {'EoneAjax_PageMethod': 'Ajax_NavLoadDataPage',
                        'EoneAjax_UpdatePage': 'true',
                        'EoneAjax_CallBackArgument0': pageNum,
                        'EoneAjax_CallBackArgument1': 15,
                        '____VIEWSTATE': viewstate,
                        '__VIEWSTATE': '',
                        '__EVENTTARGET': ''}
                r = requests.post(posturlDict[requestURL], headers=headers, data=data)
                r.encoding = r.apparent_encoding
                r = json.loads(r.text)
                basesoup = BeautifulSoup(r['value']['DataPageHTML'], 'lxml')
                titleList = basesoup.find_all('li')
                #如果有热点新闻,在后面加一个字典
                if r['value']['HotHrefURL']:
                    commend = {'href':'http://www.cabr.com.cn/' + r['value']['HotHrefURL'],
                               'date':r['value']['HotDate'],
                               'title':r['value']['HotTitle']}
                    titleList.append(commend)
                # 统计总页数
                totalPages = int(r['value']['PageTotal'])
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
                if isinstance(table,dict):
                    articleURL = table['href']
                else:
                    a = table.find('a')
                    if 'http:' in a['href']:
                        articleURL = a['href']
                    else:
                        articleURL = 'http://www.cabr.com.cn/' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[requestURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[requestURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[requestURL])
                        last[LocDict[requestURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[requestURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[requestURL])
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
                        articleTitle = table['title']

                        # 保存文章发布时间
                        publishTime = ''
                        if isinstance(table, dict):
                            publishTime = table['date'].replace('-', '')
                        elif table.find('span'):
                            publishTime = re.search('(\d+-\d+-\d+)', table.find('span').text)[0].replace('-', '')

                        # 保存文章位置
                        articleLocation = LocDict[requestURL]

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'content'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'content'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国建筑科学研究院有限公司',
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
            logger.info('中国建筑科学研究院-'+LocDict[requestURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if pageNum > totalPages or quitflag==3:
                break
            #获取VIEWSTATE
            viewstate = re.search('domViewState.value="(.+)";', r['script'][0])[1]
            while flag < 3:
                try:
                    data = {'EoneAjax_PageMethod': 'Ajax_NavLoadDataPage',
                            'EoneAjax_UpdatePage': 'true',
                            'EoneAjax_CallBackArgument0': pageNum,
                            'EoneAjax_CallBackArgument1': 15,
                            '____VIEWSTATE': viewstate,
                            '__VIEWSTATE':'',
                            '__EVENTTARGET':'' }
                    r = requests.post(posturlDict[requestURL],headers=headers,data=data)
                    r.encoding = r.apparent_encoding
                    r = json.loads(r.text)
                    basesoup = BeautifulSoup(r['value']['DataPageHTML'], 'lxml')
                    titleList = basesoup.find_all('li')
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

#35.中国国际技术智力合作有限公司
def delURLofJishuZhili():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.ciic.com.cn/SearchResult.aspx?searchKey='
    siteURL = 'http://www.ciic.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国国际技术智力合作有限公司'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key + '&PageIndex=' + str(pageNum)
                r = requests.get(requestURL, headers=headers, proxies=getOneProxy())
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', attrs={'class': 'body'})
                titleList = titleNode.find_all('dt')
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
                    articleURL = 'http://www.ciic.com.cn' + a['href']
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
                        article = requests.get(articleURL, headers=headers,proxies=getOneProxy())
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
                        if table.find('span'):
                            publishTime = table.find('span').text

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('h1', attrs={'class': 'h1'}):
                            articleLocation =  articleSoup.find('h1', attrs={'class': 'h1'}).text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': 'info'}):
                            articleTextList = articleSoup.find('div', attrs={'class': 'info'}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-中国国际技术智力合作有限公司',
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
            logger.info('中国国际技术智力合作-'+key+'-pageNum: ' + str(pageNum))
            if quitflag == 3:
                break
            pageNum += 1
            flag = 0
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&PageIndex=' + str(pageNum)
                    r = requests.get(requestURL, headers=headers,proxies=getOneProxy())
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': 'body'})
                    titleList = titleNode.find_all('dt')
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

#36.北京矿冶科技集团有限公司
def delURLofBJKuangyeKeji():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.bgrimm.com/cms/search/searchResults.jsp?query='
    siteURL = 'http://www.bgrimm.com/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取北京矿冶科技集团有限公司'+'关键词：' + key)
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL + key + '&siteID=6&offset=' + str(count) + '&rows=10&flg=1'
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                #统计总结果数
                total = basesoup.find('td', attrs={'class': 'tboder'})
                totalResults = int(re.search('(\d+)', total.text)[0])
                if totalResults == 0:
                    titleList = []
                    break
                titleNode = basesoup.find('table', attrs={'width': '778', 'border': '0', 'cellspacing': '0', 'cellpadding': '0', 'align': 'center'})
                titleList = titleNode.find_all('td', attrs={'class': 'border2'})
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
                        if '403 Forbidden' in article.text:
                            continue

                        # html的URL地址
                        htmlURL = articleURL

                        # 保存文章标题信息
                        articleTitle = a.text

                        # 保存文章发布时间
                        publishTime = ''
                        if table.find('font', attrs={'color': '#008000'}):
                            publishTime = (re.search('(\d+年\d+月\d+日)', table.find('font', attrs={'color': '#008000'}).text)[0]).replace('年','').replace('月','').replace('日','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class':'sjw-mnav main'}):
                            articleLocList = articleSoup.find('div', attrs={'class':'sjw-mnav main'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text
                        elif articleSoup.find('div', attrs={'class':'location'}):
                            articleLocList = articleSoup.find('div', attrs={'class':'location'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text
                        elif articleSoup.find('div', attrs={'class':'BreadcrumbNav'}):
                            articleLocList = articleSoup.find('div', attrs={'class':'BreadcrumbNav'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class':"zsy_comain"}):
                            articleTextList = articleSoup.find('div', attrs={'class':"zsy_comain"}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text
                        elif articleSoup.find('div', attrs={'class':"zhengwen"}):
                            articleTextList = articleSoup.find('div', attrs={'class':"zhengwen"}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text
                        elif articleSoup.find('div', attrs={'class':"pages_content"}):
                            articleTextList = articleSoup.find('div', attrs={'class':"pages_content"}).find_all('p')
                            for articleTextNode in articleTextList:
                                articleText += articleTextNode.text

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
                                    'site': '央企及地方重点国企官网-央企-北京矿冶科技集团有限公司',
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
            logger.info('北京矿冶科技-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if count >= totalResults or quitflag == 3:
                break
            while flag < 3:
                try:
                    requestURL = baseURL + key + '&siteID=6&offset=' + str(count) + '&rows=10&flg=1'
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    # 统计总结果数
                    total = basesoup.find('td', attrs={'class': 'tboder'})
                    totalResults = int(re.search('(\d+)', total.text)[0])
                    titleNode = basesoup.find('table', attrs={'width': '778', 'border': '0', 'cellspacing': '0',
                                                              'cellpadding': '0', 'align': 'center'})
                    titleList = titleNode.find_all('td', attrs={'class': 'border2'})
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

#37.有研科技集团有限公司
def delURLofYouyanKeji():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURLList = ['http://www.grinm.com/p380.aspx',
               'http://www.grinm.com/p382.aspx',
               'http://www.grinm.com/p415.aspx',
               'http://www.grinm.com/p1031.aspx',
               'http://www.grinm.com/p1140.aspx']
    LocDict = {'http://www.grinm.com/p380.aspx':'集团动态',
               'http://www.grinm.com/p382.aspx':'子公司动态',
               'http://www.grinm.com/p415.aspx':'企业公告',
               'http://www.grinm.com/p1031.aspx':'国资动态',
               'http://www.grinm.com/p1140.aspx':'信息公开'}
    siteURL = 'http://www.grinm.com/'
    for baseURL in baseURLList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[baseURL] in last:
                last_updated_url = last[LocDict[baseURL]]
        pageNum = 1
        flag = 0
        logger.infot('开始爬取有研科技集团有限公司'+'子栏目：' + LocDict[baseURL])
        while flag < 3:
            try:
                r = requests.get(baseURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('div', attrs={'class': "center_contain"})
                titleList = titleNode.find_all(attrs={'class':'newsWord_2-1'})
                # 统计总页数
                total = basesoup.find('span', attrs={'class': "i-pager-info"}).find(attrs={'class':'i-pager-info-p'})
                totalPages = int(total.text)
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
                if re.match('http://',a['href']):
                    articleURL = a['href']
                else: articleURL = 'http://www.grinm.com' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[baseURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[baseURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                        last[LocDict[baseURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[baseURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        if '.pdf' not in articleURL:
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
                            articleTitle = a['title']

                            # 保存文章发布时间
                            publishTime = ''
                            if table.find('div', attrs={'class': 'datetime'}):
                                publishTime = re.search('(\d+-\d+-\d+)', table.find('div', attrs={'class': 'datetime'}).text)[0].replace('-', '')

                            # 保存文章位置
                            articleLocation = LocDict[baseURL]

                            # 保存文章正文
                            articleText = ''
                            if articleSoup.find('div', attrs={'class': 'article_info'}):
                                articleText = articleSoup.find('div', attrs={'class': 'article_info'}).text



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
                                        'site': '央企及地方重点国企官网-央企-有研科技集团有限公司',
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

                        elif '.pdf' in articleURL:
                            # 保存html页面源码
                            htmlSource = ''

                            # html的URL地址
                            htmlURL = articleURL

                            # 保存文章标题信息
                            articleTitle = a['title']

                            # 保存文章发布时间
                            publishTime = ''
                            if table.find('div', attrs={'class': 'datetime'}):
                                publishTime = \
                                re.search('(\d+-\d+-\d+)', table.find('div', attrs={'class': 'datetime'}).text)[
                                    0].replace('-', '')

                            # 保存文章位置
                            articleLocation = LocDict[baseURL]

                            # 保存文章正文
                            articleText = ''
                            if not os.path.exists('./file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                os.mkdir('./file_data')
                                os.chdir('./file_data')
                            if os.path.exists('./file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                os.chdir('./file_data')
                            if not os.path.exists('./' + articleTitle + '.pdf'):  # 如果文件尚未存在
                                f = requests.get(articleURL)
                                with open('./'+ articleTitle + '.pdf', "wb") as code:
                                    code.write(f.content)
                                logger.info('pdf download over')
                            #解析pdf文件并判断关键字
                            docText = utility_convert.convert_pdf_to_txt('./'+ articleTitle +'.pdf')
                            if docText:
                                articleText += '\n\n\n\附件内容：\n'
                                for docNode in docText:
                                    articleText += docNode
                            flag = 3
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
                                        'site': '央企及地方重点国企官网-央企-有研科技集团有限公司',
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
            logger.info('有研科技集团-'+LocDict[baseURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if pageNum > totalPages or quitflag==3:
                break
            while flag < 3:
                try:
                    next = basesoup.find('a', attrs={'class':'i-pager-next'})
                    nexturl = 'http://www.grinm.com' + next['href']
                    r = requests.get(nexturl, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('div', attrs={'class': "center_contain"})
                    titleList = titleNode.find_all(attrs={'class': 'newsWord_2-1'})
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

#38.中国有色矿业集团有限公司
def delURLofYouseKuangye():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURLList = ['&column_no=0302',
                   '&column_no=0301',
                   '&column_no=0316',
                   '&column_no=0317',
                   '&column_no=0304',
                   '&column_no=0305',
                   '&column_no=0306']
    LocDict = {'&column_no=0302':'集团动态',
                   '&column_no=0301':'国资要闻',
                   '&column_no=0316':'国内业务动态',
                   '&column_no=0317':'境外业务动态',
                   '&column_no=0304':'行业新闻',
                   '&column_no=0305':'媒体报道',
                   '&column_no=0306':'信息公开'}
    siteURL = 'http://www.cnmc.com.cn/'
    for baseURL in baseURLList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[baseURL] in last:
                last_updated_url = last[LocDict[baseURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国有色矿业集团有限公司'+'子栏目：' + LocDict[baseURL])
        while flag < 3:
            try:
                requestURL = 'http://www.cnmc.com.cn/outline.jsp?topage=' + str(pageNum) + baseURL
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                titleNode = basesoup.find('ul', attrs={'class': "secList"})
                titleList = titleNode.find_all('td', attrs={'align': 'left', 'width':'580'})
                # 统计总页数
                total = basesoup.find('td', attrs={'colspan': "2", 'class':'page'})
                totalPages = int(re.search('共(\d+)页', total.text)[1])
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
                if re.match('http://', a['href']):
                    articleURL = a['href']
                else:
                    articleURL = 'http://www.cnmc.com.cn/' + a['href']
                flag = 0
                # 如果是最新的网页，则更新crawlerCollection
                index = titleList.index(table)
                if pageNum == 1 and index == 0:  # 第一页的第一个网址
                    if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                        last = crawler.find_one({'url': siteURL})['last_updated']
                        if LocDict[baseURL] in last:
                            logger.info('更新last_updated for 关键词： ' + LocDict[baseURL])
                        else:
                            logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                        last[LocDict[baseURL]] = articleURL
                        crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                    else:  # 否则向crawlerCollection插入新的数据
                        last = {LocDict[baseURL]: articleURL}
                        crawler.insert_one({'url': siteURL, 'last_updated': last})
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                # 如果到达上次爬取的网址
                if articleURL == last_updated_url:
                    quitflag = 3
                    logger.info('到达上次爬取的进度')
                    break
                while flag < 3:
                    try:
                        if '.pdf' not in articleURL:
                            article = requests.get(articleURL, headers=headers)
                            article.encoding = article.apparent_encoding
                            articleSoup = BeautifulSoup(article.text, 'lxml')
                            flag = 3
                            # 保存html页面源码
                            htmlSource = article.text

                            # html的URL地址
                            htmlURL = articleURL

                            # 保存文章标题信息
                            if articleSoup.find('h2'):
                                articleTitle = articleSoup.find('h2').text
                            else: articleTitle = a.text

                            # 保存文章发布时间
                            publishTime = ''
                            timeList = articleSoup.find_all('td')
                            for timeNode in timeList:
                                if '发布时间' in timeNode.text:
                                    publishTime = re.search('(\d+-\d+-\d+)', timeNode.text)[0].replace('-', '')
                                    break

                            # 保存文章位置
                            articleLocation = LocDict[baseURL]

                            # 保存文章正文
                            articleText = ''
                            if articleSoup.find('td', attrs={'class': 'indent'}):
                                articleText = articleSoup.find('td', attrs={'class': 'indent'}).text

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
                                        'site': '央企及地方重点国企官网-央企-中国有色矿业集团有限公司',
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
                        elif '.pdf' in articleURL:
                            # 保存html页面源码
                            htmlSource = ''

                            # html的URL地址
                            htmlURL = articleURL

                            # 保存文章标题信息
                            articleTitle = a.text

                            # 保存文章发布时间
                            publishTime = ''

                            # 保存文章位置
                            articleLocation = LocDict[baseURL]

                            # 保存文章正文
                            articleText = ''
                            if not os.path.exists('./file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                os.mkdir('./file_data')
                                os.chdir('./file_data')
                            if os.path.exists('./file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                os.chdir('./file_data')
                            if not os.path.exists('./' + articleTitle + '.pdf'):  # 如果文件尚未存在
                                f = requests.get(articleURL)
                                with open('./'+ articleTitle + '.pdf', "wb") as code:
                                    code.write(f.content)
                                logger.info('pdf download over')
                            #解析pdf文件并判断关键字
                            docText = utility_convert.convert_pdf_to_txt('./'+ articleTitle +'.pdf')
                            if docText:
                                articleText += '\n\n\n\附件内容：\n'
                                for docNode in docText:
                                    articleText += docNode
                            flag = 3
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
                                        'site': '央企及地方重点国企官网-央企-中国有色矿业集团有限公司',
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
                        if 'Name or service not known' in str(e):
                            break
                        logger.info('重新请求网页中...')
                        sleep(10 + 20 * flag)
                        if flag == 3:
                            logger.info('重新请求失败')
                            logger.info('Sleeping...')
            logger.info('有色矿业集团-'+LocDict[baseURL]+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if pageNum > totalPages or quitflag==3:
                break
            while flag < 3:
                try:
                    requestURL = 'http://www.cnmc.com.cn/outline.jsp?topage=' + str(pageNum) + baseURL
                    r = requests.get(requestURL, headers=headers)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find('ul', attrs={'class': "secList"})
                    titleList = titleNode.find_all('td', attrs={'align': 'left', 'width': '580'})
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

#39.中国建材集团有限公司
def delURLofJiancaiJituan():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURL = 'http://www.cnbm.com.cn/CNBM/Search.aspx?cn='
    siteURL = 'http://www.cnbm.com.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国建材集团有限公司'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                # 统计总结果数
                total = basesoup.find('div', attrs={'class': 'pages'})
                totalPages = int(re.search('\d+/(\d+)', total.text)[1])
                titleNode = basesoup.find(attrs={'class':"centerBoxMainRightNewsSpan centerBoxMainRightList1 centerBoxMainRightList"})
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
                else: articleURL = 'http://www.cnbm.com.cn' + a['href']
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
                        if table.find('span'):
                            publishTime = '20'+(re.search('(\d+-\d+-\d+)', table.find('span').text)[0]).replace('-', '')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'luJing'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'luJing'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'class': "newsNei"}):
                            articleText = articleSoup.find('div', attrs={'class': "newsNei"}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国建材集团有限公司',
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
            logger.info('中国建材集团-'+key+'-pageNum: ' + str(pageNum))
            pageNum += 1
            flag = 0
            if pageNum > totalPages or quitflag==3:
                break
            #获取viewstate,viewstategenerator,eventvalidation
            viewstate = basesoup.find(attrs={'id':'__VIEWSTATE'})['value']
            viewstategenerator = basesoup.find(attrs={'id':'__VIEWSTATEGENERATOR'})['value']
            eventvalidation = basesoup.find(attrs={'id':'__EVENTVALIDATION'})['value']
            while flag < 3:
                try:
                    data = {'__EVENTTARGET': 'Next',
                            '__EVENTARGUMENT': '',
                            '__VIEWSTATE': viewstate,
                            '__VIEWSTATEGENERATOR': viewstategenerator,
                            '__EVENTVALIDATION': eventvalidation}
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleNode = basesoup.find(
                        attrs={'class': "centerBoxMainRightNewsSpan centerBoxMainRightList1 centerBoxMainRightList"})
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

#40.中国盐业有限公司
def delURLofZhongguoYanye():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'}
    baseURLList = ['http://www.chinasalt.com.cn/xwzx/zyyw/',
                   'http://www.chinasalt.com.cn/xwzx/zytz/',
                   'http://www.chinasalt.com.cn/xwzx/zydt/',
                   'http://www.chinasalt.com.cn/xwzx/hyxw/',
                   'http://www.chinasalt.com.cn/xwzx/mtjj/',
                   'http://www.chinasalt.com.cn/xwzx/gzdt/',
                   'http://www.chinasalt.com.cn/xwzx/gzysy/']
    LocDict = {'http://www.chinasalt.com.cn/xwzx/zyyw/':'中盐要闻',
                   'http://www.chinasalt.com.cn/xwzx/zytz/':'重要通知',
                   'http://www.chinasalt.com.cn/xwzx/zydt/':'中盐动态',
                   'http://www.chinasalt.com.cn/xwzx/hyxw/':'行业新闻',
                   'http://www.chinasalt.com.cn/xwzx/mtjj/':'媒体聚焦',
                   'http://www.chinasalt.com.cn/xwzx/gzdt/':'国资动态',
                   'http://www.chinasalt.com.cn/xwzx/gzysy/':'关注与视野'}
    siteURL = 'http://www.chinasalt.com.cn/'
    for baseURL in baseURLList:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if LocDict[baseURL] in last:
                last_updated_url = last[LocDict[baseURL]]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国盐业有限公司'+'子栏目：' + LocDict[baseURL])
        count = 0
        while flag < 3:
            try:
                requestURL = baseURL+'json.xml?t=0.4333708042084443'
                r = requests.get(requestURL, headers=headers)
                r.encoding = 'utf-8'
                titleList = json.loads(r.text)
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
        for table in titleList:
            if 'http' in table['source_www']:
                articleURL = table['source_www']
            else:
                articleURL = baseURL + table['id'] +'.html'
            flag = 0
            count += 1
            # 如果是最新的网页，则更新crawlerCollection
            index = titleList.index(table)
            if pageNum == 1 and index == 0:  # 第一页的第一个网址
                if crawler.find({'url': siteURL}).count() > 0:  # 如果原来爬过这个siteURL，则更新last_updated字段
                    last = crawler.find_one({'url': siteURL})['last_updated']
                    if LocDict[baseURL] in last:
                        logger.info('更新last_updated for 关键词： ' + LocDict[baseURL])
                    else:
                        logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
                    last[LocDict[baseURL]] = articleURL
                    crawler.update_one({'url': siteURL}, {'$set': {'last_updated': last}})
                else:  # 否则向crawlerCollection插入新的数据
                    last = {LocDict[baseURL]: articleURL}
                    crawler.insert_one({'url': siteURL, 'last_updated': last})
                    logger.info('首次插入last_updated for 关键词： ' + LocDict[baseURL])
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
                    if article.status_code == 403:
                        continue
                    # 如果没有请求下来完整的html页面，则再次请求
                    if not articleSoup.head.meta:
                        logger.info('html页面未完整请求，5秒后再次请求')
                        sleep(5)
                        flag = 0
                        continue
                    # 保存html页面源码
                    htmlSource = article.text

                    # html的URL地址
                    htmlURL = articleURL

                    # 保存文章标题信息
                    articleTitle = table['title']

                    # 保存文章发布时间
                    publishTime = table['createTime'].replace('-','')

                    # 保存文章位置
                    articleLocation = LocDict[baseURL]

                    # 保存文章正文
                    articleText = ''
                    if articleSoup.find('div', attrs={'class': 'nrtxt'}):
                        neirong = articleSoup.find('div', attrs={'class': 'nrtxt'})
                        articleText = neirong.text
                    elif articleSoup.find('div', attrs={'class': 'TRS_Editor'}):
                        articleText = articleSoup.find('div', attrs={'class': 'TRS_Editor'}).text

                    try:
                        # 判断页面是否含有链接
                        if neirong.find('a'):
                            hrefList = neirong.find_all('a')
                            for href in hrefList:
                                docText = ''
                                if '.doc' in href['href']:
                                    docID = href.text.replace('/', '')
                                    if not os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                        os.mkdir('./file_data')
                                        os.chdir('./file_data')
                                    if os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                        os.chdir('./file_data')
                                    if not os.path.exists('./' + docID + '.doc'):  # 如果文件尚未存在
                                        f = requests.get(href['href'])
                                        with open('./' + docID + '.doc', "wb") as code:
                                            code.write(f.content)
                                        logger.info('.doc download over')
                                    # 解析doc文件
                                    utility_convert.convert_doc_to_txt('./' + docID + '.doc')
                                    if os.path.exists('./' + docID + '/' + docID + '.txt'):
                                        f = open('./' + docID + '/' + docID + '.txt', encoding='utf-8')
                                        docText = f.read()
                                        articleText += '\n\n\n\附件内容：\n' + docText
                                        f.close()
                                    else:
                                        logger.info('无法解析doc文档')

                                elif '.docx' in href['href']:
                                    docID = href.text.replace('/', '')
                                    if not os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                        os.mkdir('./file_data')
                                        os.chdir('./file_data')
                                    if os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                        os.chdir('./file_data')
                                    if not os.path.exists('./' + docID + '.docx'):  # 如果文件尚未存在
                                        f = requests.get(href['href'])
                                        with open('./' + docID + '.docx', "wb") as code:
                                            code.write(f.content)
                                        logger.info('.docx download over')
                                    # 解析docx文件
                                    utility_convert.convert_doc_to_txt('./' + docID + '.docx')
                                    if os.path.exists('./' + docID + '/' + docID + '.txt'):
                                        f = open('./' + docID + '/' + docID + '.txt', encoding='utf-8')
                                        docText = f.read()
                                        articleText += '\n\n\n\附件内容：\n' + docText
                                        f.close()
                                    else:
                                        logger.info('无法解析docx文档')

                                elif '.pdf' in href['href']:
                                    docID = href.text.replace('/', '')
                                    if not os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
                                        os.mkdir('./file_data')
                                        os.chdir('./file_data')
                                    if os.path.exists(
                                            './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
                                        os.chdir('./file_data')
                                    if not os.path.exists('./' + docID + '.pdf'):  # 如果文件尚未存在
                                        f = requests.get(href['href'])
                                        with open('./' + docID + '.pdf', "wb") as code:
                                            code.write(f.content)
                                        logger.info('.pdf download over')
                                    # 解析pdf文件
                                    docText = utility_convert.convert_pdf_to_txt('./' + docID + '.pdf')
                                    if docText:
                                        articleText += '\n\n\n\附件内容：\n'
                                        for docNode in docText:
                                            articleText += docNode
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
                                'site': '央企及地方重点国企官网-央企-中国盐业有限公司',
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
            if count %20 == 0:
                logger.info('中国盐业有限公司-'+LocDict[baseURL]+'-pageNum: ' + str(pageNum))
                pageNum += 1
    logger.info("finish")
    return;

#41.中国化学工程集团有限公司
def delURLofHuaxueGongcheng():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
              'Refer':'http://www.cncec.cn/'}
    baseURL = 'http://www.cncec.cn/selectNews.aspx?tags='
    siteURL = 'http://www.cncec.cn/'
    for key in config.keywords_list:
        quitflag = 0  # 到达之前爬过的网址时的退出标记
        last_updated_url = ''  # 记录上次爬过的网站网址
        if crawler.find({'url': siteURL}).count() > 0:
            last = crawler.find_one({'url': siteURL})['last_updated']
            if key in last:
                last_updated_url = last[key]
        pageNum = 1
        flag = 0
        logger.info('开始爬取中国化学工程集团有限公司'+'关键词：' + key)
        while flag < 3:
            try:
                requestURL = baseURL + key
                r = requests.get(requestURL, headers=headers)
                r.encoding = r.apparent_encoding
                basesoup = BeautifulSoup(r.text, 'lxml')
                basesoup.prettify()
                flag = 3
                if '抱歉，没有找到您要搜索的内容！' in basesoup.find('span', id='Label3'):
                    titleList = []
                    break
                titleList = basesoup.find_all('div', attrs={'class':'m_lx'})
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
                    articleURL = 'http://www.cncec.cn' + a['href']
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
                        # 如果没有请求下来完整的html页面，则再次请求
                        if not articleSoup.head.meta:
                            logger.info('html页面未完整请求，5秒后再次请求')
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
                            publishTime = (re.search('(\d+-\d+-\d+)', table.find('span').text)[0]).replace('-','')

                        # 保存文章位置
                        articleLocation = ''
                        if articleSoup.find('div', attrs={'class': 'weizhi'}):
                            articleLocList = articleSoup.find('div', attrs={'class': 'weizhi'}).find_all('a')
                            for articleLocNode in articleLocList:
                                articleLocation += '>' + articleLocNode.text

                        # 保存文章正文
                        articleText = ''
                        if articleSoup.find('div', attrs={'id': "p_content"}):
                            articleText = articleSoup.find('div', attrs={'id': "p_content"}).text
                        elif articleSoup.find('div', attrs={'class': "m_x_cont"}):
                            articleText = articleSoup.find('div', attrs={'class': "m_x_cont"}).text

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
                                    'site': '央企及地方重点国企官网-央企-中国化学工程集团有限公司',
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
            logger.info('中国化学工程集团'+key+'-pageNum: ' + str(pageNum))
            if quitflag==3:
                break
            pageNum += 1
            flag = 0
            if basesoup.find('div',attrs={'id':'AspNetPager1','class':'anpager'}):
                total = basesoup.find('div',attrs={'id':'AspNetPager1','class':'anpager'}).find_all('a')
                next = total[len(total)-2]
                if ('disabled' in str(next)) and next.text=='下一页':
                    break
            else: break
            # 获取viewstate,viewstategenerator,eventvalidation
            viewstate = basesoup.find(attrs={'id': '__VIEWSTATE'})['value']
            viewstategenerator = basesoup.find(attrs={'id': '__VIEWSTATEGENERATOR'})['value']
            while flag < 3:
                try:
                    data = {'__VIEWSTATE':viewstate,
                            '__VIEWSTATEGENERATOR': viewstategenerator,
                            '__EVENTTARGET': 'AspNetPager1',
                            '__EVENTARGUMENT': pageNum
                            }
                    r = requests.post(requestURL, headers=headers, data=data)
                    r.encoding = r.apparent_encoding
                    basesoup = BeautifulSoup(r.text, 'lxml')
                    basesoup.prettify()
                    flag = 3
                    titleList = basesoup.find_all('div', attrs={'class': 'm_lx'})
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

if __name__ == "__main__":

    #1.国家能源投资集团有限责任公司
    logger.info('开始爬取国家能源投资集团有限责任公司')
    for keyWord in config.keywords_list:
        logger.info('开始爬取招标采购信息'+'关键词：' + keyWord)
        delUrlofGuoNengTou('http://www.dlzb.com/zb/search.php?kw=', keyWord)
    for keyWord in config.keywords_list:
        logger.info('开始爬取中标公示'+'关键词：' + keyWord)
        delUrlofGuoNengTou('http://www.dlzb.com/zhongbiao/search.php?kw=', keyWord)

    #2.中国兵器工业集团有限公司
    for keyWord in config.keywords_list:
        logger.info('开始爬取中国兵器工业集团有限公司'+'关键词：' + keyWord)
        dealURLofBingQi(
           'http://www.norincogroup.com.cn/jsearch/search.do?appid=1&ck=x&imageField=&od=0&pagemode=result&pos=title%2Ccontent&q=',
            keyWord)

    #3.中国国新控股有限责任公司
    dealURLofGuoXinKongGu()

    #4.中国铁路物资集团有限公司
    dealURLofTieLuWuZi()

    #5.中国西电集团有限公司
    delURLofXiDian()

    #6.南光（集团）有限公司[中国南光集团有限公司]
    delURLofNanGuang()

    #7.华侨城集团有限公司
    delURLofHuaQiaoCheng()

    #8.武汉邮电科学研究院有限公司
    delURLofWuHanYouDian()

    #9.上海诺基亚贝尔股份有限公司
    delURLofNokiasbell()

    #10.中国华录集团有限公司
    delURLofHuaLu()

    #11.中国广核集团有限公司
    delURLofCGN()

    #12.中国黄金集团有限公司
    delURLofChinaGold()

    #13.中国能源建设集团有限公司
    delURLofceec()

    #14.中国电力建设集团有限公司
    delURLofPowerChina()

    #15.中国航空器材集团有限公司
    delURLofHangkongQicai()

    #16.中国航空油料集团有限公司
    delURLofHKYouliao()

    #17.中国民航信息集团有限公司
    delURLofMinHangXinXi()

    #18.新兴际华集团有限公司
    delURLofXinxingJihua()

    #19.中国煤炭地质总局
    delURLofMeitanZongju()

    #20.中国冶金地质总局
    delURLofYejinZongju()

    #21.中国建设科技有限公司
    delURLofJiansheKeji()

    #22.中国保利集团有限公司
    defURLofBaoli()

    #23.中国医药集团有限公司
    delURLofYiyaoJituan()

    #24.中国林业集团有限公司
    delURLofLinyeJituan()

    #25.中国中丝集团有限公司
    delURLofChinasilk()

    #26.中国农业发展集团有限公司
    delURLofNongyeFazhan()

    #27.电信科学技术研究院有限公司
    delURLofDTDianxin()

    #28.中国普天信息产业集团有限公司
    delURLofPutian()

    #29.中国交通建设集团有限公司
    delURLofJiaotongJianshe()

    #30.中国铁道建筑有限公司
    delURLofZhongguoTiejian()

    #31.中国铁路工程集团有限公司
    delURLofTieluGongcheng()

    #32.中国铁路通信信号集团有限公司
    delURLofTieluXinhao()

    #33.中国中车集团有限公司
    delURLofZhongche()

    #34.中国建筑科学研究院有限公司
    delURLofJianzhuKexueyuan()

    #35.中国国际技术智力合作有限公司
    delURLofJishuZhili()

    #36.北京矿冶科技集团有限公司
    delURLofBJKuangyeKeji()

    #37.有研科技集团有限公司
    delURLofYouyanKeji()

    #38.中国有色矿业集团有限公司
    delURLofYouseKuangye()

    #39.中国建材集团有限公司
    delURLofJiancaiJituan()

    #40.中国盐业有限公司
    delURLofZhongguoYanye()

    #41.中国化学工程集团有限公司
    delURLofHuaxueGongcheng()
