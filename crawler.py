from requests_html import HTMLSession, HTML
from pymongo import MongoClient
from pymongo import UpdateOne
import config
import json
import time
import math
import re
from requests.exceptions import ReadTimeout, ConnectionError
from urllib import parse
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
import xml.etree.ElementTree as ET

import logging

logger = logging.getLogger('国有资产监督管理--爬取数据')
logger.setLevel(logging.DEBUG)
# create console handler and set level to debug
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)


def remove_html_elements(string):
    cleaner = re.compile('<.*?>')
    cleaned_text = re.sub(cleaner, '', string)
    cleaned_text = cleaned_text.strip()
    return cleaned_text


def sasac():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    db.result_data.create_index([('date', -1), ('title_text', 1)])

    session = HTMLSession()
    url = 'http://search.sasac.gov.cn:8080/searchweb/search'
    for each_keyword in config.keywords_list:
        for key_type in ['title', 'fullText']:
            data_json = {'fullText': each_keyword, 'indexDB': 'css', 'sortType': 0, 'sortKey': 'showtime',
                         'sortFlag': -1, 'pageSize': 50, 'pageNow': 1, 'searchType': 0, 'keywordNavigation': 1,
                         'checkSearch': 1, 'timeRange': 0, 'keyType': key_type}
            flag = 0
            while flag < 3:
                try:
                    r = session.post(url, data=data_json, timeout=5)
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            result_content = json.loads(r.content)
            logger.info('国务院国有资产监督管理委员会 关键词: %s 公告总个数: %d 关键词类别: %s'
                        % (each_keyword, int(result_content['num']), key_type))
            count = 0
            for num in range(int(math.ceil(result_content['num'] / 50))):
                data_json['pageNow'] = num + 1
                flag = 0
                while flag < 3:
                    try:
                        r = session.post(url, data=data_json, timeout=5)
                        flag = 3
                    except (ReadTimeout, ConnectionError) as e:
                        logger.error(e)
                        flag += 1
                        if flag == 3:
                            logger.info('Sleeping...')
                            time.sleep(60 * 10)
                            flag = 0
                result_content = json.loads(r.content)
                bulk_list = []
                for each_result in result_content.get('array', []):
                    if '://www.sasac.gov.cn' in each_result['url']:
                        flag = False
                        for each_deleted_keyword in config.deleted_keywords_list:
                            if each_deleted_keyword in remove_html_elements(each_result['name']):
                                flag = True
                                break
                        if not flag:
                            flag = 0
                            while flag < 3:
                                try:
                                    r = session.post(each_result['url'], data=data_json, timeout=5)
                                    flag = 3
                                except (ReadTimeout, ConnectionError) as e:
                                    logger.error(e)
                                    flag += 1
                                    if flag == 3:
                                        logger.info('Sleeping...')
                                        time.sleep(60 * 10)
                                        flag = 0
                            if len(r.html.find('.zsy_cotitle')) > 0:
                                title = r.html.find('.zsy_cotitle')[0].text.split('\n')[0]
                                content = r.html.find('.zsy_comain')[0].text
                                tag_text = r.html.find('.sjw-mnav')[0].text
                                if each_keyword in title or each_keyword in content:
                                    print(each_result['url'])
                                    bulk_list.append(UpdateOne({'url': each_result['url']},
                                                               {
                                                                   '$set': {'url': each_result['url'],
                                                                            'title': title,
                                                                            'content': content,
                                                                            'tag_text': tag_text,
                                                                            'abstract': each_result['summaries'],
                                                                            'abstract_text': remove_html_elements(
                                                                                each_result['summaries']),
                                                                            'site': '国家、省、市、区国资委网站-中央-国务院国有资产监督管理委员会',
                                                                            'date': each_result['showTime']},
                                                                   '$addToSet': {'keyword': each_keyword}
                                                               },
                                                               upsert=True))
                count += len(bulk_list)
                logger.info('关键词: %s 关键词类别: %s 爬取进度: %d/%d'
                            % (each_keyword, key_type, count, int(result_content['num'])))
                if len(bulk_list) != 0:
                    db.result_data.bulk_write(bulk_list)


# 北京国资委
def bjgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://gzw.beijing.gov.cn/QtCommonAction.do?method=xxcx&type=0000005010&flag_qt=5',
        'http://gzw.beijing.gov.cn/QtCommonAction.do?method=xxcx&type=0000008020&flag_qt=9']
    url2_list = [
        'http://ztwz.bjgzw.gov.cn/web/static/catalogs/catalog_ff808081563088bf01589aaa72dd052e/ff808081563088bf01589aaa72dd052e']
    url3_list = [
        'http://zfxxgk.beijing.gov.cn/110025/gfxwj22/list.shtml',
        'http://zfxxgk.beijing.gov.cn/110025/qtwj22/list.shtml',
        'http://zfxxgk.beijing.gov.cn/110025/gh32/list.shtml',
        'http://zfxxgk.beijing.gov.cn/110025/jh32/list.shtml'
    ]
    logger.info('北京国资委 数据抓取')
    for index, each_url in enumerate(url_list):
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                # r.html.render()
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.displaydivpage1')[0].text)[1])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + '&__PageNum=' + str(i + 1)
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    r2.html.render()
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            dl_content = r2.html.find('.aa')[0]

            for each_tr in dl_content.find('tr')[1:]:
                announcement_url = list(each_tr.absolute_links)[0]
                if 'http://gzw.beijing.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_tr.find('a')[0].text
                    announcement_date = each_tr.find('td')[1].text.replace('-', '').replace('[', '').replace(']', '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.top')[-1].text

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-北京-北京市国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': '',
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')
    for index, each_url in enumerate(url2_list):
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url + '.html', timeout=5)
                # r.html.render()
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.displaydivpage1')[0].text)[1])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + '_' + str(i + 1) + '.html' if i != 0 else each_url + '.html'
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    r2.html.render()
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            dl_content = r2.html.find('.aa')[0]

            for each_tr in dl_content.find('tr')[1:]:
                announcement_url = list(each_tr.absolute_links)[0]
                if 'http://ztwz.bjgzw.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_tr.find('a')[0].text
                    announcement_date = each_tr.find('td')[1].text.replace('-', '').replace('[', '').replace(']', '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.top')[-1].text

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-北京-北京市国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': '',
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(20)
    for index, each_url in enumerate(url3_list):
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                driver.get(each_url)
                flag = 3
            except:
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        if len(driver.find_elements_by_class_name('laypage_main')) > 0:
            page_count = int(
                driver.find_elements_by_class_name('laypage_main')[0].find_elements_by_tag_name('a')[-2].text)
        else:
            page_count = 1
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + '#!page=' + str(i + 1)
            flag = 0
            while flag < 3:
                try:
                    driver.get(url)
                    flag = 3
                except:
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            dl_content = driver.find_elements_by_id('colList')[0]
            li_list = dl_content.find_elements_by_tag_name('li')
            for each_tr in li_list:
                announcement_url = each_tr.find_elements_by_tag_name('a')[0].get_attribute('href')
                if 'http://zfxxgk.beijing.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_tr.find_elements_by_tag_name('a')[0].text
                    announcement_date = each_tr.find_elements_by_class_name('date')[0].text. \
                        replace('-', '').replace('[', '').replace(']', '')
                    flag = 0
                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                               executable_path=config.chromeDriver_path)
                    driver2.set_page_load_timeout(200)
                    driver.implicitly_wait(10)
                    while flag < 3:
                        try:
                            driver2.get(announcement_url)
                            flag = 3
                        except:
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = driver2.find_elements_by_id('content')[0].text
                    content = '\n'.join(content.split('\n')[1:-1])
                    tag_text = driver2.find_elements_by_class_name('wz')[0].text
                    tag_text = '\n'.join(tag_text.split('\n')[1:-1])

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-北京-北京市国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': driver2.page_source
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 天津国资委
def tjgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://sasac.tj.gov.cn/gzjg/', 'http://sasac.tj.gov.cn/gqdt/',
        'http://sasac.tj.gov.cn/zcfg/gfxwj/',
        'http://sasac.tj.gov.cn/zcfg/zcjd/', 'http://sasac.tj.gov.cn/gzsy/']
    logger.info('天津国资委 数据抓取')
    for each_url in url_list:
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                r.html.render()
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.fy')[0].text)[2])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + 'index.html' if i == 0 else each_url + 'index_' + str(i + 1) + '.html'
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    r2.html.render()
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            if each_url == 'http://sasac.tj.gov.cn/zcfg/gfxwj/' or each_url == 'http://sasac.tj.gov.cn/zcfg/zcjd/':
                dl_content = r2.html.find('.l_t_r')[0]
            else:
                dl_content = r2.html.find('.l_jz')[0]

            for each_dd in dl_content.find('dd'):
                announcement_url = list(each_dd.absolute_links)[0]
                if 'http://sasac.tj.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_dd.find('a')[0].text
                    announcement_date = each_dd.find('.time')[0].text.replace('-', '').replace('[', '').replace(']', '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.qw')[0].text
                    tag_text = announcement_r.html.find('.dqwz')[0].text

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-天津-天津市国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 山西国资委
def sxgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://www.sxgzw.gov.cn/new-web/list-gk.jsp?urltype=tree.TreeTempUrl&wbtreeid=1390']
    logger.info('山西国资委 数据抓取')
    for each_url in url_list:
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                # r.html.render()
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.govnewslisthead1240')[0].text)[2])
        logger.info(each_url + ' 一共有%d页' % page_count)
        base_url = 'http://www.sxgzw.gov.cn/new-web/list-gk.jsp?a1240t=2&a1240c=15&urltype=tree.TreeTempUrl&wbtreeid=1390'
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(base_url + '&a1240p=' + str(i + 1), timeout=5)
                    # r2.html.render()
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0

            for each_dd in r2.html.find('.govnewslist1240')[0].find('tr')[1:]:
                announcement_url = list(each_dd.absolute_links)[0]
                if 'http://www.sxgzw.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_dd.find('a')[1].text
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.newscontent_s')[0].text
                    tag_text = announcement_r.html.find('.winstyle1236')[0].text
                    announcement_date = announcement_r.html.find('.govvaluefont1242')[0].text.replace('-', '')

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-山西-山西省国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 河北国资委
def hebeigzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://www.hbsa.gov.cn/JiGuanXinXi/',
        'http://www.hbsa.gov.cn/GuoQiGaiGe/',
        'http://www.hbsa.gov.cn/GuoZiYunYing/']
    logger.info('河北国资委 数据抓取')
    for each_url in url_list:
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.pagecss')[0].text)[2])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + '?pi=' + str(i + 1)
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    r2.html.render(timeout=20)
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0
            dl_content = r2.html.find('.listnews-content')[0]
            for each_dd in dl_content.find('li'):
                announcement_url = list(each_dd.absolute_links)[0]
                if 'http://www.hbsa.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_dd.find('a')[0].text
                    announcement_date = each_dd.find('span')[0].text.replace('-', '').replace('[', '').replace(']', '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            announcement_r.html.render()
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.listinfo-content')[0].text
                    tag_text = announcement_r.html.find('.floft_l')[-1].text
                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-河北-河北省国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 内蒙古国资委
def neimenggugzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://gzw.nmg.gov.cn/gzzx2/msgz/',
        'http://gzw.nmg.gov.cn/bsfw/bsznbd/',
        'http://gzw.nmg.gov.cn/gzzx2/gzyw/']
    logger.info('内蒙古国资委 数据抓取')
    for each_url in url_list:
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.fy')[0].text)[4])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + 'index.html' if i == 0 else each_url + 'index_' + str(i) + '.html'
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    r2.html.render(timeout=20)
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0
            dl_content = r2.html.find('.right_two')[0]
            for each_dd in dl_content.find('li'):
                announcement_url = list(each_dd.absolute_links)[0]
                if 'http://gzw.nmg.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_dd.find('a')[0].text
                    announcement_date = each_dd.find('.time1')[0].text.replace('-', '').replace('[', '').replace(']',
                                                                                                                 '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    if len(announcement_r.html.find('.neirong')) > 0:
                        content = announcement_r.html.find('.neirong')[0].text
                    else:
                        content = announcement_r.html.find('.TRS_PreAppend')[0].text

                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    if len(announcement_r.html.find('.one')) > 0:
                        tag_text = announcement_r.html.find('.one')[0].text
                    else:
                        tag_text = announcement_r.html.find('.lj')[0].text

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-内蒙古-内蒙古自治区国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 辽宁省国资委
def lngzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]

    session = HTMLSession()
    url_list = [
        'http://www.lngzw.gov.cn/xxgk/zc/zcfb/',
        'http://www.lngzw.gov.cn/xxgk/zc/zcjd/',
        'http://www.lngzw.gov.cn/gzjg/gqgg/',
        'http://www.lngzw.gov.cn/gzjg/zbyy/',
        'http://www.lngzw.gov.cn/gzjg/cqgl/']
    logger.info('辽宁省国资委 数据抓取')
    for each_url in url_list:
        logger.info(each_url)
        flag = 0
        while flag < 3:
            try:
                r = session.get(each_url, timeout=5)
                flag = 3
            except (ReadTimeout, ConnectionError) as e:
                logger.error(e)
                flag += 1
                if flag == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag = 0

        page_count = int(re.findall('\d+', r.html.find('.page2')[0].text)[0])
        logger.info(each_url + ' 一共有%d页' % page_count)
        for i in range(page_count):
            logger.info('第%d页' % (i + 1))
            url = each_url + 'index.html' if i == 0 else each_url + 'index_' + str(i) + '.html'
            flag = 0
            while flag < 3:
                try:
                    r2 = session.get(url, timeout=5)
                    flag = 3
                except (ReadTimeout, ConnectionError) as e:
                    logger.error(e)
                    flag += 1
                    if flag == 3:
                        logger.info('Sleeping...')
                        time.sleep(60 * 10)
                        flag = 0
            dl_content = r2.html.find('.govLLList')[0]
            for each_dd in dl_content.find('li'):
                announcement_url = list(each_dd.absolute_links)[0]
                if 'http://www.lngzw.gov.cn/' in announcement_url and \
                        db.result_data.find({'url': announcement_url}).count() == 0:
                    title = each_dd.find('a')[0].text
                    announcement_date = each_dd.find('.sublistLTime')[0].text.replace('-', '').replace('[', ''). \
                        replace(']', '')
                    flag = 0
                    while flag < 3:
                        try:
                            announcement_r = session.get(announcement_url, timeout=5)
                            flag = 3
                        except (ReadTimeout, ConnectionError) as e:
                            logger.error(e)
                            flag += 1
                            if flag == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag = 0

                    content = announcement_r.html.find('.govxlTextBox')[0].text
                    matched_keywords_list = []
                    for each_keyword in config.keywords_list:
                        if each_keyword in title or each_keyword in content:
                            matched_keywords_list.append(each_keyword)

                    tag_text = announcement_r.html.find('.govcurrent')[0].text

                    if len(matched_keywords_list) > 0:
                        db.result_data.insert_one({
                            'url': announcement_url,
                            'title': title,
                            'date': announcement_date,
                            'site': '国家、省、市、区国资委网站-辽宁-辽宁省国有资产监督管理委员会',
                            'keyword': matched_keywords_list,
                            'tag_text': tag_text,
                            'content': content,
                            'html': str(r.content)
                        })
                        logger.info(announcement_url + ' Inserted into DB!')


# 吉林省国资委
def jlgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://gzw.jl.gov.cn/zcjd/',
        'http://gzw.jl.gov.cn/gzyj/']
    logger.info('吉林省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('pagesize')[0].text)[0])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url + 'index.html' if i == 0 else each_url + 'index_' + str(i) + '.html'
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)

                            dl_content = driver.find_elements_by_class_name('qrn_column_long')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('li'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'http://gzw.jl.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_tag_name('span')[0].text.replace('-',
                                                                                                                  ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver2.set_page_load_timeout(200)
                                    driver2.implicitly_wait(10)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)

                                            content = driver2.find_elements_by_id('zoom')[0].text
                                            tag_text = driver2.find_elements_by_class_name('current_sub')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-吉林-吉林省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')

                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 黑龙江省国资委
def hljgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url1_list = [
        'http://www.hljgzw.gov.cn/gzjg/gzjgyyj/'
    ]
    url2_list = [
        'http://www.hljgzw.gov.cn/zcfg/zcjd/zcjd/index.html',
        'http://www.hljgzw.gov.cn/zcfg/zcjd/zjjd/index.html',
        'http://www.hljgzw.gov.cn/zcfg/zcjd/mtjd/index.html'
    ]
    url3_list = [
        'http://mange.hljgzw.gov.cn/webpage/gkmlList.aspx',
        'http://mange.hljgzw.gov.cn/webpage/flgfxwjList.aspx'
    ]
    logger.info('黑龙江省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url1_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('nr2')[0].
                                            find_elements_by_tag_name('span')[-1].text)[-1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url + 'index.html' if i == 0 else \
                        'http://www.hljgzw.gov.cn/system/more/gzjg/gzjgyyj/index/page_0' + str(i) + '.html'
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)

                            dl_content = driver.find_elements_by_class_name('nr2')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('div'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'http://www.hljgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_class_name('lie-time')[0].text.replace(
                                        '-',
                                        ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)

                                            content = driver2.find_elements_by_class_name('xly-mid')[0].text
                                            tag_text = driver2.find_elements_by_class_name('mid-up')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-黑龙江-黑龙江省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')

                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0

                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0

    for each_url in url2_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)

                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('lie-nr')[0].
                                            find_elements_by_tag_name('span')[-1].text)[-1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url if i == 0 else each_url
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            dl_content = driver.find_elements_by_class_name('lie-nr')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('div'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'http://www.hljgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_class_name('lie-time')[0].text.replace(
                                        '-',
                                        ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            content = driver2.find_elements_by_class_name('xly-mid')[0].text
                                            tag_text = driver2.find_elements_by_class_name('mid-up')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-黑龙江-黑龙江省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0

    for each_url in url3_list:
        session = HTMLSession()
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                r = session.post(each_url, data={'__EVENTARGUMENT': 1})
                page_count = int(re.findall('\d+', r.html.find('#AspNetPager1')[0].find('a')[-1].attrs['href'])[-1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            r = session.post(each_url, data={'__EVENTARGUMENT': i + 1, '__EVENTTARGET': 'AspNetPager1',
                                                             '__VIEWSTATEGENERATOR': 'BF66C835',
                                                             '__EVENTVALIDATION': '/wEdAAbCoiG9E9Nk6wVIenqP3tDIF4LQWSIZX2OxlErrKwwfbcAQKR4NCXhQo+zP+DtK426Pt9R1fwk6eBe8h4UwuJ1t2DUooC87b3nZH79wbNIn4OmQAq8eUWZ5ZSknq1PiLioABj1zsYsJ/m1SE1abcUN46vpdGpiV6LOwH6MUu0PCaQ==',
                                                             '__VIEWSTATE': '/wEPDwUJMTE5NjUyMDE2D2QWAgIDD2QWBAILDxYCHgtfIUl0ZW1Db3VudAIUFihmD2QWAmYPFQUBMQExKuWNgeS4ieS6lOKAneaXtuacn+aIkeWbvee7j+a1juekvuS8muWPkeWxlQARMjAxNeW5tDA35pyIMzDml6VkAgEPZBYCZg8VBQEyATIn5LyB5Lia55uR552j5bGA5Z+56K6t5Yi25bqm77yI6K+V6KGM77yJABEyMDA35bm0MDnmnIgwNOaXpWQCAg9kFgJmDxUFATMBMzPlhbPkuo7miJHnnIHlnLDmlrnlm73mnInkvIHkuJrmlLnpnannmoTosIPnoJTmiqXlkYoAETIwMDflubQwOeaciDA05pelZAIDD2QWAmYPFQUBNAE0NuecgeWbvei1hOWnlOezu+e7n+S8geS4muWFmuW7uuW3peS9nOS/oeaBr+aKpemAgeWItuW6pgARMjAwN+W5tDA55pyIMTHml6VkAgQPZBYCZg8VBQE1ATUk5Lit5Y2O5Lq65rCR5YWx5ZKM5Zu95Yqz5Yqo5ZCI5ZCM5rOVABEyMDA35bm0MDnmnIgxMuaXpWQCBQ9kFgJmDxUFATYBNk7lhbPkuo7lu7rnq4vmiafooYzogZTliqjmnLrliLbliIflrp7op6PlhrPkurrmsJHms5XpmaLmiafooYzpmr7pl67popjnmoTmhI/op4EAETIwMDjlubQwM+aciDI35pelZAIGD2QWAmYPFQUBNwE3NuecgeWbvei1hOWnlOWHuui1hOS8geS4muWGhemDqOWuoeiuoeeuoeeQhuaaguihjOWKnuazlQARMjAwOOW5tDAz5pyIMjfml6VkAgcPZBYCZg8VBQE4AThI5YWz5LqO5o6o6L+b5YWo55yB5Zu95pyJ6LWE5pys6LCD5pW05ZKM5Zu95pyJ5LyB5Lia6YeN57uE55qE5oyH5a+85oSP6KeBABEyMDA45bm0MDPmnIgyN+aXpWQCCA9kFgJmDxUFATkBOTzlhbPkuo7nnIHlm73otYTlp5Tlh7rotYTkvIHkuJrosIPmlbTlkozph43nu4TnmoTmjIflr7zmhI/op4EAETIwMDjlubQwM+aciDI35pelZAIJD2QWAmYPFQUCMTACMTAq5Lit5Y2O5Lq65rCR5YWx5ZKM5Zu95LyB5Lia5Zu95pyJ6LWE5Lqn5rOVABEyMDA45bm0MTHmnIgwNOaXpWQCCg9kFgJmDxUFAjExAjExWuWFs+S6juWNsOWPkeOAiuiRo+S6i+S8muivleeCueS4reWkruS8geS4muiBjOW3peiRo+S6i+WxpeihjOiBjOi0o+euoeeQhuWKnuazleOAi+eahOmAmuefpQARMjAwOeW5tDA05pyIMTPml6VkAgsPZBYCZg8VBQIxMgIxMl3lhbPkuo7lrp7mlr3jgIrlhbPkuo7op4TojIPlm73mnInkvIHkuJrogYzlt6XmjIHogqHjgIHmipXotYTnmoTmhI/op4HjgIvmnInlhbPpl67popjnmoTpgJrnn6UAETIwMDnlubQwNOaciDIw5pelZAIMD2QWAmYPFQUCMTMCMTM25YWz5LqO6KeE6IyD5Zu95pyJ5LyB5Lia6IGM5bel5oyB6IKh44CB5oqV6LWE55qE5oSP6KeBABEyMDA55bm0MDTmnIgyMOaXpWQCDQ9kFgJmDxUFAjE0AjE0NuWFs+S6juWNsOWPkeOAiuiRo+S6i+S8muivleeCueS4reWkruS8geS4muS4k+iBjOWklumDqAARMjAxMOW5tDAx5pyIMjLml6VkAg4PZBYCZg8VBQIxNQIxNT/lm73otYTlp5TlsaXooYzlpJrlhYPmipXotYTkuLvkvZPlhazlj7jogqHkuJzogYzotKPmmoLooYzlip7ms5UAETIwMTDlubQwN+aciDE55pelZAIPD2QWAmYPFQUCMTYCMTYq5Lit5Y2O5Lq65rCR5YWx5ZKM5Zu95L+d5a6I5Zu95a6256eY5a+G5rOVABEyMDEw5bm0MDfmnIgyMeaXpWQCEA9kFgJmDxUFAjE3AjE3S+m7kem+meaxn+ecgeS6uuawkeaUv+W6nOWFs+S6juS/g+i/m+S6p+adg+S6pOaYk+W4guWcuuinhOiMg+WPkeWxleeahOaEj+ingQARMjAxMOW5tDA35pyIMjbml6VkAhEPZBYCZg8VBQIxOAIxOD/nnIHlm73otYTlp5Tmjqjov5vlh7rotYTkvIHkuJrnqLPlop7plb/kv4Plj5HlsZXnmoToi6XlubLmjqrmlr0AETIwMTTlubQwOOaciDI35pelZAISD2QWAmYPFQUCMTkCMTlU6buR6b6Z5rGf55yB5Zu95pyJ5LyB5Lia5rOV5b6L6aG+6Zeu6IGM5Lia5bKX5L2N562J57qn6LWE5qC86K+E5a6h566h55CG5a6e5pa957uG5YiZABEyMDE05bm0MDjmnIgyN+aXpWQCEw9kFgJmDxUFAjIwAjIwPOm7kem+meaxn+ecgeWbvei1hOWnlOWHuui1hOS8geS4mui0n+i0o+S6uuiWqumFrOeuoeeQhuWKnuazlQARMjAxNOW5tDEx5pyIMjfml6VkAg0PDxYCHgtSZWNvcmRjb3VudAIxZGQYAQUeX19Db250cm9sc1JlcXVpcmVQb3N0QmFja0tleV9fFgEFDEltYWdlQnV0dG9uMY/NmEWgt/+UkoHpvK3+kDo+tq3Yc7XSSjzp+r0WYCUn'})
                            dl_content = r.html.find('#_fill')[0]
                            for each_dd in dl_content.find('tr')[1:]:
                                announcement_url = list(each_dd.find('a')[0].absolute_links)[0]
                                logger.info(announcement_url)
                                if 'http://mange.hljgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0 and \
                                        announcement_url != 'http://mange.hljgzw.gov.cn/webpage/gkmlview.aspx?id=621B9886E6415256':
                                    title = each_dd.find('a')[0].text
                                    announcement_date = each_dd.find('td')[-1].text.replace('-', ''). \
                                        replace('[', '').replace(']', '').replace('年', '').replace('月', '').replace('日',
                                                                                                                    '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver.set_page_load_timeout(200)
                                    driver.implicitly_wait(10)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            content = driver2.find_elements_by_class_name('zwnr')[0].text
                                            tag_text = driver2.find_elements_by_class_name('mid-up2')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-黑龙江-黑龙江省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0

                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0

                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 上海市国资委
def shgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'https://www.shgzw.gov.cn/website/html/shgzw/shgzw_fzjs_zcjd/',
        'https://www.shgzw.gov.cn/website/html/shgzw/shgzw_flfg_zcfg_gfxwj/',
        'https://www.shgzw.gov.cn/website/html/shgzw/shgzw_xxgk_ghjh/']
    logger.info('上海市国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('style1')[0].text)[0])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url + 'List/list_' + str(i) + '.htm'
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            dl_content = driver.find_elements_by_class_name('gqzc_list_right')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('li'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'https://www.shgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_tag_name('span')[0].text.replace('-',
                                                                                                                  ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver.set_page_load_timeout(200)
                                    driver.implicitly_wait(10)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            content = driver2.find_elements_by_class_name('f12H')[0].text
                                            tag_text = driver2.find_elements_by_class_name('localbox')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-上海-上海市国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 江苏省国资委
def jsgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://jsgzw.jiangsu.gov.cn/col/col11769/index.html?uid=247686&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11777/index.html?uid=247686&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11776/index.html?uid=247686&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11832/index.html?uid=247686&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11788/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11787/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11790/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11789/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11792/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11791/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11780/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11782/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11781/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11784/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11783/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11786/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11800/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11804/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col63902/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11785/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11794/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11795/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11796/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11797/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11798/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11799/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11793/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11704/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11703/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11702/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11708/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11707/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11706/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11705/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11711/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11712/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11713/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11714/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11709/index.html?uid=253948&pageNum=',
        'http://jsgzw.jiangsu.gov.cn/col/col11710/index.html?uid=253948&pageNum='
    ]
    url2_list = [
        'http://jsgzw.jiangsu.gov.cn/col/col61490/index.html',
    ]
    url3_list = [
        '0801',
        '10'
    ]
    logger.info('江苏省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url + '1')
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                if len(driver.find_elements_by_class_name('default_pgPanel')) > 0:
                    page_count = int(
                        re.findall('\d+', driver.find_elements_by_class_name('default_pgPanel')[0].text)[-2])
                else:
                    page_count = 1
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url + str(i + 1)
                    logger.info(url)
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            time.sleep(3)
                            dl_content = driver.find_elements_by_class_name('default_pgContainer')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('li'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'http://jsgzw.jiangsu.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_class_name('fr')[0].text.replace('-',
                                                                                                                  ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver2.set_page_load_timeout(200)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            time.sleep(3)
                                            content = driver2.find_elements_by_id('zoom')[0].text
                                            tag_text = driver2.find_elements_by_class_name('currentpath')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-江苏-江苏省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0

                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0

                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0

    for each_url in url2_list:
        logger.info(each_url)
        logger.info(each_url + ' 一共有%d页' % 1)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                dl_content = driver.find_elements_by_class_name('default_pgContainer')[0]
                for each_dd in dl_content.find_elements_by_tag_name('li'):
                    announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                    logger.info(announcement_url)
                    if 'http://jsgzw.jiangsu.gov.cn/' in announcement_url and \
                            db.result_data.find({'url': announcement_url}).count() == 0:
                        title = each_dd.find_elements_by_tag_name('a')[0].text
                        announcement_date = each_dd.find_elements_by_class_name('fr')[0].text.replace('-', ''). \
                            replace('[', '').replace(']', '')
                        flag2 = 0
                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                   executable_path=config.chromeDriver_path)
                        driver2.set_page_load_timeout(200)
                        while flag2 < 3:
                            try:
                                driver2.get(announcement_url)
                                time.sleep(3)
                                content = driver2.find_elements_by_id('zoom')[0].text
                                tag_text = driver2.find_elements_by_class_name('currentpath')[0].text
                                matched_keywords_list = []
                                for each_keyword in config.keywords_list:
                                    if each_keyword in title or each_keyword in content:
                                        matched_keywords_list.append(each_keyword)

                                if len(matched_keywords_list) > 0:
                                    db.result_data.insert_one({
                                        'url': announcement_url,
                                        'title': title,
                                        'date': announcement_date,
                                        'site': '国家、省、市、区国资委网站-江苏-江苏省国有资产监督管理委员会',
                                        'keyword': matched_keywords_list,
                                        'tag_text': tag_text,
                                        'content': content,
                                        'html': str(driver2.page_source)
                                    })
                                    logger.info(announcement_url + ' Inserted into DB!')
                                flag2 = 3
                            except:
                                flag2 += 1
                                if flag2 == 3:
                                    logger.info('Sleeping...')
                                    time.sleep(60 * 10)
                                    flag2 = 0

                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0

    session = HTMLSession()
    for each_url in url3_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                r = session.post(
                    'http://jsgzw.jiangsu.gov.cn/module/xxgk/search.jsp',
                    data={'currpage': 1, 'divid': 'div125', 'infotypeId': each_url, 'jdid': 39})
                time.sleep(3)
                page_count = int(re.findall('\d+', r.html.find('.tb_title')[0].text)[1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            r = session.post(
                                'http://jsgzw.jiangsu.gov.cn/module/xxgk/search.jsp',
                                data={'currpage': i + 1, 'divid': 'div125', 'infotypeId': each_url, 'jdid': 39})
                            time.sleep(3)
                            dl_content = r.html.find('.xlt_table0')[0]
                            for each_dd in dl_content.find('tr')[1:]:
                                announcement_url = list(each_dd.find('a')[0].absolute_links)[0]
                                logger.info(announcement_url)
                                if 'http://jsgzw.jiangsu.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find('a')[0].text
                                    announcement_date = each_dd.find('td')[-1].text.replace('-', ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver2.set_page_load_timeout(200)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            time.sleep(3)
                                            content = driver2.find_elements_by_id('zoom')[0].text
                                            tag_text = driver2.find_elements_by_class_name('currentpath')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-江苏-江苏省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 浙江省国资委
def zjgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        {'col': 1, 'appid': 1, 'webid': 1, 'path': '/', 'columnid': 569, 'sourceContentType': 1, 'unitid': 2057,
         'webname': '浙江省国资委', 'permissiontype': 0},
        {'col': 1, 'appid': 1, 'webid': 1, 'path': '/', 'columnid': 538, 'sourceContentType': 1, 'unitid': 1843,
         'webname': '浙江省国资委', 'permissiontype': 0},
        {'col': 1, 'appid': 1, 'webid': 1, 'path': '/', 'columnid': 16, 'sourceContentType': 1, 'unitid': 131,
         'webname': '浙江省国资委', 'permissiontype': 0},
    ]
    logger.info('浙江省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    session = HTMLSession()
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                r = session.post(
                    'http://www.zjsgzw.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?startrecord=1&endrecord=75&perpage=25',
                    data=each_url)
                time.sleep(3)
                root = ET.fromstring(r.text)
                doc_count = int(root[0].text)
                logger.info('一共有%d个公告' % doc_count)
                for i in range(int(doc_count / 25) + 1):
                    logger.info('第%d页' % (i + 1))
                    url = 'http://www.zjsgzw.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?startrecord=' + \
                          str(i * 25 + 1) + '&endrecord=' + str(i * 25 + 25) + '&perpage=25'
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            r = session.post(url, data=each_url)
                            time.sleep(3)
                            root = ET.fromstring(r.text)
                            for each_record in root[2][:25]:
                                record_html = HTML(html=each_record.text)
                                announcement_url = 'http://www.zjsgzw.gov.cn' + record_html.find('a')[0].attrs['href']
                                logger.info(announcement_url)
                                if 'http://www.zjsgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = record_html.find('a')[0].text
                                    announcement_date = record_html.find('td')[-1].text.replace('-', ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver2.set_page_load_timeout(200)
                                    driver2.implicitly_wait(10)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            time.sleep(3)
                                            if len(driver2.find_elements_by_css_selector(
                                                    'div[style="padding:15px; border-top:1px solid #cccccc; text-align:left; font-size:10.5pt; line-height:24px; width:85%"]')) > 0:
                                                content = driver2.find_elements_by_css_selector(
                                                    'div[style="padding:15px; border-top:1px solid #cccccc; text-align:left; font-size:10.5pt; line-height:24px; width:85%"]')[
                                                    0].text
                                                tag_text = driver2.find_elements_by_tag_name('table')[15].text
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-浙江-浙江省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 江西省国资委
def jxgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://www.jxgzw.gov.cn/xxgk/gzjg/',
        'http://www.jxgzw.gov.cn/xxgk/gzwwj/']
    logger.info('江西省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('pagecon')[0].text)[0])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url + 'index.htm' if i == 0 else each_url + 'index_' + str(i) + '.htm'
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            time.sleep(3)
                            dl_content = driver.find_elements_by_class_name('gllist')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('li'):
                                announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                logger.info(announcement_url)
                                if 'http://www.jxgzw.gov.cn/' in announcement_url and \
                                        db.result_data.find({'url': announcement_url}).count() == 0:
                                    title = each_dd.find_elements_by_tag_name('a')[0].text
                                    announcement_date = each_dd.find_elements_by_tag_name('span')[0].text.replace('-',
                                                                                                                  ''). \
                                        replace('[', '').replace(']', '')
                                    flag3 = 0
                                    driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                               executable_path=config.chromeDriver_path)
                                    driver.set_page_load_timeout(200)
                                    driver.implicitly_wait(10)
                                    while flag3 < 3:
                                        try:
                                            driver2.get(announcement_url)
                                            time.sleep(3)
                                            content = driver2.find_elements_by_class_name('xl-nr')[0].text
                                            tag_text = driver2.find_elements_by_class_name('curmb')[0].text
                                            matched_keywords_list = []
                                            for each_keyword in config.keywords_list:
                                                if each_keyword in title or each_keyword in content:
                                                    matched_keywords_list.append(each_keyword)

                                            if len(matched_keywords_list) > 0:
                                                db.result_data.insert_one({
                                                    'url': announcement_url,
                                                    'title': title,
                                                    'date': announcement_date,
                                                    'site': '国家、省、市、区国资委网站-江西-江西省国有资产监督管理委员会',
                                                    'keyword': matched_keywords_list,
                                                    'tag_text': tag_text,
                                                    'content': content,
                                                    'html': str(driver2.page_source)
                                                })
                                                logger.info(announcement_url + ' Inserted into DB!')
                                            flag3 = 3
                                        except:
                                            flag3 += 1
                                            if flag3 == 3:
                                                logger.info('Sleeping...')
                                                time.sleep(60 * 10)
                                                flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 福建省国资委
def fjgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://www.fjgzw.gov.cn/ca/20151009000029.htm',
        'http://www.fjgzw.gov.cn/ca/20130729958022.htm',
        'http://www.fjgzw.gov.cn/ca/20130915484040.htm',
        'http://www.fjgzw.gov.cn/ca/20130915481002.htm',
        'http://www.fjgzw.gov.cn/ca/20130912713983.htm',
        'http://www.fjgzw.gov.cn/ca/20130912714318.htm',
        'http://www.fjgzw.gov.cn/ca/20130912714426.htm',
        'http://www.fjgzw.gov.cn/ca/20130912707185.htm',
        'http://www.fjgzw.gov.cn/ca/20130912709533.htm',
        'http://www.fjgzw.gov.cn/ca/20130912709409.htm',
        'http://www.fjgzw.gov.cn/ca/20130912711379.htm',
        'http://www.fjgzw.gov.cn/ca/20130912713821.htm',
        'http://www.fjgzw.gov.cn/ca/20130912713743.htm'
    ]
    url2_list = [
        'http://www.fjgzw.gov.cn/ca/20130729214889.htm'
    ]
    url3_list = ['http://www.fjgzw.gov.cn/ca/20170518000004.htm', 'http://www.fjgzw.gov.cn/ca/20170518000005.htm']
    logger.info('福建省国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                page_count = int(re.findall('\d+', driver.find_elements_by_id('data_page_1')[0].text)[1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url if i == 0 else each_url.replace('.htm', '_' + str(i + 1) + '.htm')
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            time.sleep(3)
                            dl_content = driver.find_elements_by_class_name('newslist')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('li'):
                                if len(each_dd.find_elements_by_tag_name('a')) > 0:
                                    announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                    logger.info(announcement_url)
                                    if 'http://www.fjgzw.gov.cn/' in announcement_url and \
                                            db.result_data.find({'url': announcement_url}).count() == 0:
                                        title = each_dd.find_elements_by_tag_name('a')[0].text
                                        announcement_date = each_dd.find_elements_by_tag_name('span')[0].text. \
                                            replace('-', '').replace('[', '').replace(']', '')
                                        flag3 = 0
                                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                                   executable_path=config.chromeDriver_path)
                                        driver2.set_page_load_timeout(200)
                                        driver2.implicitly_wait(10)
                                        while flag3 < 3:
                                            try:
                                                driver2.get(announcement_url)
                                                time.sleep(3)
                                                content = driver2.find_elements_by_id('data_article_content')[0].text
                                                tag_text = driver2.find_elements_by_id('data_weizhi')[0].text
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-福建-福建省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                                flag3 = 3
                                            except:
                                                flag3 += 1
                                                if flag3 == 3:
                                                    logger.info('Sleeping...')
                                                    time.sleep(60 * 10)
                                                    flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0
    for each_url in url2_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                page_count = int(re.findall('\d+', driver.find_elements_by_id('data_page_1')[0].text)[1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    url = each_url if i == 0 else each_url.replace('.htm', '_' + str(i + 1) + '.htm')
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(url)
                            time.sleep(3)
                            dl_content = driver.find_elements_by_id('data_gov_list04')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('tr'):
                                if len(each_dd.find_elements_by_tag_name('a')) > 0:
                                    announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                    logger.info(announcement_url)
                                    if 'http://www.fjgzw.gov.cn/' in announcement_url and \
                                            db.result_data.find({'url': announcement_url}).count() == 0:
                                        title = each_dd.find_elements_by_tag_name('a')[0].text
                                        announcement_date = each_dd.find_elements_by_tag_name('td')[-2].text. \
                                            replace('-', '').replace('[', '').replace(']', '')
                                        flag3 = 0
                                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                                   executable_path=config.chromeDriver_path)
                                        driver2.set_page_load_timeout(200)
                                        driver2.implicitly_wait(10)
                                        while flag3 < 3:
                                            try:
                                                driver2.get(announcement_url)
                                                time.sleep(3)
                                                content = driver2.find_elements_by_id('data_article_content')[0].text
                                                tag_text = driver2.find_elements_by_id('data_weizhi')[0].text
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-福建-福建省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                                flag3 = 3
                                            except:
                                                flag3 += 1
                                                if flag3 == 3:
                                                    logger.info('Sleeping...')
                                                    time.sleep(60 * 10)
                                                    flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0
    for each_url in url3_list:
        logger.info(each_url + ' 一共有%d页' % 1)
        flag2 = 0
        while flag2 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                dl_content = driver.find_elements_by_class_name('newslist')
                for each_newslist in dl_content:
                    for each_dd in each_newslist.find_elements_by_tag_name('li'):
                        if len(each_dd.find_elements_by_tag_name('a')) > 0:
                            announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                            logger.info(announcement_url)
                            if 'http://www.fjgzw.gov.cn/' in announcement_url and \
                                    db.result_data.find({'url': announcement_url}).count() == 0:
                                title = each_dd.find_elements_by_tag_name('a')[0].text
                                announcement_date = each_dd.find_elements_by_tag_name('span')[0].text. \
                                    replace('-', '').replace('[', '').replace(']', '')
                                flag3 = 0
                                driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                           executable_path=config.chromeDriver_path)
                                driver2.set_page_load_timeout(200)
                                driver2.implicitly_wait(10)
                                while flag3 < 3:
                                    try:
                                        driver2.get(announcement_url)
                                        time.sleep(3)
                                        content = driver2.find_elements_by_id('data_article_content')[0].text
                                        tag_text = driver2.find_elements_by_id('data_weizhi')[0].text
                                        matched_keywords_list = []
                                        for each_keyword in config.keywords_list:
                                            if each_keyword in title or each_keyword in content:
                                                matched_keywords_list.append(each_keyword)

                                        if len(matched_keywords_list) > 0:
                                            db.result_data.insert_one({
                                                'url': announcement_url,
                                                'title': title,
                                                'date': announcement_date,
                                                'site': '国家、省、市、区国资委网站-福建-福建省国有资产监督管理委员会',
                                                'keyword': matched_keywords_list,
                                                'tag_text': tag_text,
                                                'content': content,
                                                'html': str(driver2.page_source)
                                            })
                                            logger.info(announcement_url + ' Inserted into DB!')

                                        flag3 = 3
                                    except:
                                        flag3 += 1
                                        if flag3 == 3:
                                            logger.info('Sleeping...')
                                            time.sleep(60 * 10)
                                            flag3 = 0
                flag2 = 3
            except:
                flag2 += 1
                if flag2 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                flag2 = 0


# 安徽国资委
def ahgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'ac90308a65b44765bf6de44bdd0fe73d',
        '9c75575c5c8f47399fe0fdbe01062110',
        '256e364eb9614bc78c8f96f5ea7591f2',
        '82614276dd8147b28b217e89e6391223'
    ]
    url2_list = [
        {'colid': '13863261142054858', 'strWebSiteId': '1448866116912004'},
        {'colid': '13863280544714813', 'strWebSiteId': '1448866116912004'},
        {'colid': '14116140687053329', 'strWebSiteId': '1448866116912004'},
        {'colid': '14115469167987514', 'strWebSiteId': '1448866116912004'},
        {'colid': '14742512881193827', 'strWebSiteId': '1448866116912004'},
    ]
    logger.info('安徽国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    session = HTMLSession()
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                r = session.post('http://www.ahgzw.gov.cn/gzwweb/bmzz/bmzz.jsp',
                                 data={'strWebSiteId': each_url, 'PageSizeIndex': 1})
                time.sleep(3)
                page_count = int(re.findall('\d+', r.html.find('.bm_page')[0].text)[2])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            r = session.post('http://www.ahgzw.gov.cn/gzwweb/bmzz/bmzz.jsp',
                                             data={'strWebSiteId': each_url, 'PageSizeIndex': i + 1})
                            time.sleep(3)
                            dl_content = r.html.find('.xxgk_ul')[0]
                            for each_dd in dl_content.find('li'):
                                if len(each_dd.find('a')) > 0:
                                    announcement_url = list(each_dd.find('a')[0].absolute_links)[0]
                                    logger.info(announcement_url)
                                    if 'http://www.ahgzw.gov.cn/' in announcement_url and \
                                            db.result_data.find({'url': announcement_url}).count() == 0:
                                        title = each_dd.find('a')[0].text
                                        announcement_date = each_dd.find('span')[0].text. \
                                            replace('-', '').replace('[', '').replace(']', '')
                                        flag3 = 0
                                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                                   executable_path=config.chromeDriver_path)
                                        driver2.set_page_load_timeout(200)
                                        driver2.implicitly_wait(10)
                                        while flag3 < 3:
                                            try:
                                                driver2.get(announcement_url)
                                                time.sleep(3)
                                                content = driver2.find_elements_by_class_name('s_article')[0].text
                                                tag_text = driver2.find_elements_by_class_name('where')[0].text
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-安徽-安徽省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                                flag3 = 3
                                            except:
                                                flag3 += 1
                                                if flag3 == 3:
                                                    logger.info('Sleeping...')
                                                    time.sleep(60 * 10)
                                                    flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0
    for each_url in url2_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                r = session.post('http://www.ahgzw.gov.cn/gzwweb/xxgk/list.jsp',
                                 data={
                                     'strWebSiteId': each_url['strWebSiteId'],
                                     'PageSizeIndex': 1,
                                     'strColId': each_url['colid']
                                 })
                time.sleep(3)
                page_count = int(re.findall('\d+', r.html.find('.pagenav')[0].text)[-1])
                logger.info(str(each_url) + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            r = session.post('http://www.ahgzw.gov.cn/gzwweb/xxgk/list.jsp',
                                             data={
                                                 'strWebSiteId': each_url['strWebSiteId'],
                                                 'PageSizeIndex': i + 1,
                                                 'strColId': each_url['colid']
                                             })
                            time.sleep(3)
                            dl_content = r.html.find('.mail_director2')[0]
                            for each_dd in dl_content.find('tr')[1:]:
                                if len(each_dd.find('a')) > 0:
                                    announcement_url = list(each_dd.find('a')[0].absolute_links)[0]
                                    logger.info(announcement_url)
                                    if 'http://www.ahgzw.gov.cn/' in announcement_url and \
                                            db.result_data.find({'url': announcement_url}).count() == 0:
                                        title = each_dd.find('a')[0].text
                                        announcement_date = each_dd.find('td')[-1].text. \
                                            replace('-', '').replace('[', '').replace(']', '')
                                        flag3 = 0
                                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                                   executable_path=config.chromeDriver_path)
                                        driver2.set_page_load_timeout(200)
                                        driver2.implicitly_wait(10)
                                        while flag3 < 3:
                                            try:
                                                driver2.get(announcement_url)
                                                time.sleep(3)
                                                content = driver2.find_elements_by_class_name('s_article')[0].text
                                                tag_text = driver2.find_elements_by_class_name('where')[0].text
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-安徽-安徽省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                                flag3 = 3
                                            except:
                                                flag3 += 1
                                                if flag3 == 3:
                                                    logger.info('Sleeping...')
                                                    time.sleep(60 * 10)
                                                    flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 山东国资委
def sdgzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://www.sdsgzw.gov.cn/channels/ch00043/',
        'http://www.sdsgzw.gov.cn/channels/ch00043/index_1.html?page=41',
        'http://www.sdsgzw.gov.cn/channels/ch00023/',
        'http://www.sdsgzw.gov.cn/channels/ch00025/',
        'http://www.sdsgzw.gov.cn/channels/ch00214/',
        'http://www.sdsgzw.gov.cn/channels/ch00215/',
        'http://www.sdsgzw.gov.cn/channels/ch00219/'
    ]
    logger.info('山东国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url)
                time.sleep(3)
                dl_content = driver.find_elements_by_tag_name('table')[5]
                for each_dd in dl_content.find_elements_by_tag_name('table')[3:]:
                    if len(each_dd.find_elements_by_tag_name('a')) > 0:
                        announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                        logger.info(announcement_url)
                        if 'http://www.sdsgzw.gov.cn/' in announcement_url and \
                                db.result_data.find({'url': announcement_url}).count() == 0:
                            title = each_dd.find_elements_by_tag_name('a')[0].text
                            logger.info(title)
                            announcement_date = each_dd.find_elements_by_tag_name('td')[2].text. \
                                replace('-', '').replace('[', '').replace(']', '').replace('/', '')
                            flag3 = 0
                            driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                       executable_path=config.chromeDriver_path)
                            driver2.set_page_load_timeout(200)
                            driver2.implicitly_wait(10)
                            while flag3 < 3:
                                try:
                                    driver2.get(announcement_url)
                                    time.sleep(3)
                                    content = driver2.find_elements_by_id('content')[-1].text
                                    tag_text = driver2.find_elements_by_tag_name('table')[4].text
                                    matched_keywords_list = []
                                    for each_keyword in config.keywords_list:
                                        if each_keyword in title or each_keyword in content:
                                            matched_keywords_list.append(each_keyword)

                                    if len(matched_keywords_list) > 0:
                                        db.result_data.insert_one({
                                            'url': announcement_url,
                                            'title': title,
                                            'date': announcement_date,
                                            'site': '国家、省、市、区国资委网站-山东-山东省国有资产监督管理委员会',
                                            'keyword': matched_keywords_list,
                                            'tag_text': tag_text,
                                            'content': content,
                                            'html': str(driver2.page_source)
                                        })
                                        logger.info(announcement_url + ' Inserted into DB!')

                                    flag3 = 3
                                except:
                                    flag3 += 1
                                    if flag3 == 3:
                                        logger.info('Sleeping...')
                                        time.sleep(60 * 10)
                                        flag3 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


# 河南国资委
def henangzw():
    db = MongoClient(host=config.mongodb_host, port=config.mongodb_port, username=config.mongodb_username,
                     password=config.mongodb_password)[config.mongodb_db_name]
    url_list = [
        'http://www.hnsasac.gov.cn/home.do?xxgk&classId=103&pageSize=1&pageNo=',
        'http://www.hnsasac.gov.cn/home.do?xxgk&classId=104&pageSize=1&pageNo=',
        'http://www.hnsasac.gov.cn/home.do?xxgk&classId=105&pageSize=1&pageNo=',
        'http://www.hnsasac.gov.cn/home.do?xxgk&classId=107&pageSize=1&pageNo='
    ]
    logger.info('河南国资委 数据抓取')
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1440,900')
    chrome_options.add_argument('--silent')
    driver = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
    driver.set_page_load_timeout(200)
    driver.implicitly_wait(10)
    for each_url in url_list:
        logger.info(each_url)
        flag1 = 0
        while flag1 < 3:
            try:
                driver.get(each_url + '1')
                time.sleep(3)
                page_count = int(re.findall('\d+', driver.find_elements_by_class_name('connetbox')[
                    0].find_elements_by_tag_name('div')[-1].text)[1])
                logger.info(each_url + ' 一共有%d页' % page_count)
                for i in range(page_count):
                    logger.info('第%d页' % (i + 1))
                    flag2 = 0
                    while flag2 < 3:
                        try:
                            driver.get(each_url + str(i + 1))
                            time.sleep(3)
                            dl_content = driver.find_elements_by_class_name('wnjg')[0]
                            for each_dd in dl_content.find_elements_by_tag_name('tr')[1:]:
                                if len(each_dd.find_elements_by_tag_name('a')) > 0:
                                    announcement_url = each_dd.find_elements_by_tag_name('a')[0].get_attribute('href')
                                    logger.info(announcement_url)
                                    if 'http://www.hnsasac.gov.cn/' in announcement_url and \
                                            db.result_data.find({'url': announcement_url}).count() == 0:
                                        title = each_dd.find_elements_by_tag_name('a')[0].text
                                        announcement_date = each_dd.find_elements_by_tag_name('td')[2].text. \
                                            replace('-', '').replace('[', '').replace(']', '')
                                        flag3 = 0
                                        driver2 = webdriver.Chrome(chrome_options=chrome_options,
                                                                   executable_path=config.chromeDriver_path)
                                        driver2.set_page_load_timeout(200)
                                        driver2.implicitly_wait(10)
                                        while flag3 < 3:
                                            try:
                                                driver2.get(announcement_url)
                                                time.sleep(3)
                                                content = driver2.find_elements_by_class_name('tablePage')[0]. \
                                                    find_elements_by_tag_name('tr')[-1].text
                                                logger.info(content)
                                                tag_text = driver2.find_elements_by_class_name('pageskin')[0].text
                                                logger.info(tag_text)
                                                matched_keywords_list = []
                                                for each_keyword in config.keywords_list:
                                                    if each_keyword in title or each_keyword in content:
                                                        matched_keywords_list.append(each_keyword)

                                                if len(matched_keywords_list) > 0:
                                                    db.result_data.insert_one({
                                                        'url': announcement_url,
                                                        'title': title,
                                                        'date': announcement_date,
                                                        'site': '国家、省、市、区国资委网站-河南-河南省国有资产监督管理委员会',
                                                        'keyword': matched_keywords_list,
                                                        'tag_text': tag_text,
                                                        'content': content,
                                                        'html': str(driver2.page_source)
                                                    })
                                                    logger.info(announcement_url + ' Inserted into DB!')

                                                flag3 = 3
                                            except:
                                                flag3 += 1
                                                if flag3 == 3:
                                                    logger.info('Sleeping...')
                                                    time.sleep(60 * 10)
                                                    flag3 = 0
                            flag2 = 3
                        except:
                            flag2 += 1
                            if flag2 == 3:
                                logger.info('Sleeping...')
                                time.sleep(60 * 10)
                                flag2 = 0
                flag1 = 3
            except:
                flag1 += 1
                if flag1 == 3:
                    logger.info('Sleeping...')
                    time.sleep(60 * 10)
                    flag1 = 0


if __name__ == "__main__":
    # sasac()
    # bjgzw()
    # tjgzw()
    # hebeigzw()
    # neimenggugzw()
    # sxgzw()
    # lngzw()
    # jlgzw()
    # hljgzw()
    # shgzw()
    # jsgzw()
    # zjgzw()
    # fjgzw()
    # jxgzw()
    # ahgzw()
    sdgzw()
    henangzw()
