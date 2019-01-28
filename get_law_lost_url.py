# -!- coding: utf-8 -!-
import argparse
import concurrent.futures
import os
import sys
import re
import datetime
from datetime import date
import time
from urllib.parse import urljoin
import requests

import xlsxwriter
import xlrd

path = os.path.abspath(os.path.join(os.getcwd(), ".."))
sys.path.append(path)

from bs4 import BeautifulSoup
from collections import OrderedDict
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
import config

szse_url_search = 'http://www.szse.cn/application/search/index.html'
sse_url_search = 'http://www.sse.com.cn/home/search/?webswd='
neeq_url_search = 'http://www.neeq.com.cn/index/searchInfo.do'
mof_url_search = 'http://www.mof.gov.cn/was5/web/czb/wassearch.jsp'
csrc_url_search = 'http://www.csrc.gov.cn/wcm/websearch/advsearch.htm'
retry_const = 3
proxy = 'http://171.37.135.94:8123'
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1440,900')
chrome_options.add_argument('--silent')
# chrome_options.add_argument('--proxy-server={}'.format(proxy))
chrome_options.add_argument('lang=zh_CN.UTF-8')
chrome_options.add_argument('user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) '
                            'AppleWebKit/537.36 (KHTML, like Gecko)Chrome/66.0.3359.181 Safari/537.360"')
regex = re.compile('text ellipsis.*')


def format_str_date(str_date):
    str_date = str_date.replace(' ', '').replace('　', '')
    zero_str = '200'
    if len(str_date) < 4:
        date_list = ['1000', '01', '01']
    else:
        str_date = str_date.replace('年', '-').replace('月', '-').replace('日', '')
        str_date = re.sub(r'[^\d-]', '', str_date)
        if '/' in str_date:
            date_list = [d if len(d) > 1 else ('0' + d) for d in str_date.split('/')]
        elif '-' in str_date:
            date_list = [d if len(d) > 1 else ('0' + d) for d in str_date.split('-')]
        else:
            date_list = [str_date, '01', '01']

        if len(date_list) < 3:
            for i in range(3 - len(date_list)):
                date_list.append('01')
        else:
            if len(date_list[0]) < 4:
                date_list[0] = zero_str[:4 - len(date_list[0])] + date_list[0]
            else:
                date_list[0] = date_list[0][-4:]
            if int(date_list[1]) > 12:
                date_list[1] = '12'
            if int(date_list[2]) > 31:
                date_list[2] = '31'

    str_date = '-'.join(date_list)
    # print('format_date:', str_date)
    return str_date


def www_szse_extractor(keyword, p_date, retry_times=0):
    print('crawling {}....'.format(keyword))
    original_url = ''
    try:
        # browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.set_page_load_timeout(50)
        browser.get(szse_url_search)
        input = WebDriverWait(browser, 1). \
            until(EC.visibility_of_element_located((By.XPATH, "//input[starts-with(@class,'form-control')]")))
        # input = browser.find_element_by_xpath("//input[starts-with(@class,'form-control')]")
        input.send_keys(keyword)
        input.send_keys(Keys.ENTER)
        wait = WebDriverWait(browser, 1)
        # wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'article-search-result')))
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[class='article-item index-length2']")))
        soup = BeautifulSoup(browser.page_source, 'html.parser')

        div = soup.find('div', attrs={'class': 'article-search-result'})
        # with open('r.html', 'w') as f:
        #     f.write(str(soup))
        if div:
            sub_divs = div.find_all('div', attrs={'class': 'article-item index-length2'})
            for sub_div in sub_divs:
                text_date = sub_div.find('span', class_='pull-right')
                if text_date and format_str_date(text_date.text) == p_date:
                    a = sub_div.find('a', attrs={'class': regex})
                    original_url = a.attrs['href']
                    break
    except Exception as e:
        print(str(e))
        retry_times += 1
        if retry_times < retry_const:
            www_szse_extractor(keyword, p_date, retry_times)

    print(original_url)
    return original_url


def www_sse_extractor(keyword, p_date, retry_times=0):
    print('crawling {}....'.format(keyword))
    original_url = ''
    try:
        # browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.set_page_load_timeout(50)
        browser.get(sse_url_search)
        tag = WebDriverWait(browser, 1)
        input = tag.until(EC.visibility_of_element_located((By.CLASS_NAME, 'query_input')))
        time.sleep(1)
        input.send_keys(keyword)
        input.send_keys(Keys.ENTER)
        wait = WebDriverWait(browser, 1)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'allTitle')))
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        # with open('r.html', 'w') as f:
        #     f.write(str(soup))

        div = soup.find('div', attrs={'class': 'sse_query_list'})
        if div:
            a_list = div.find_all('a', attrs={'title': keyword})
            for a in a_list:
                text_date = a.find('span').text
                print(text_date)
                if format_str_date(text_date) == p_date:
                    original_url = 'http://www.sse.com.cn' + a.attrs['href']
                    break
    except Exception as e:
        print(str(e))
        retry_times += 1
        if retry_times < retry_const:
            www_sse_extractor(keyword, p_date, retry_times)
    print(original_url)
    time.sleep(5)
    return original_url


def www_neeq_extractor(keyword, p_date, retry_times=0):
    print('crawling {}....'.format(keyword))
    original_url = ''
    try:
        # browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.set_page_load_timeout(50)
        browser.get(neeq_url_search)
        select = WebDriverWait(browser, 1).until(EC.presence_of_element_located((By.ID, 'type')))
        Select(select).select_by_value('1')
        input = WebDriverWait(browser, 1).until(EC.visibility_of_element_located((By.ID, 'keyword')))
        input.send_keys(keyword)
        input.send_keys(Keys.ENTER)
        # time.sleep(10)
        wait = WebDriverWait(browser, 1)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[class='mt20 f-16']")))
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        # print(soup)
        div = soup.find('div', id='list_info')
        if div:
            div_list = div.find_all('div', class_='mt20 f-16')
            for div_each in div_list:
                if div_each.find('a') and div_each.find('a').font.text.strip()==keyword:
                    print(div_each.find('span', class_='mf10').text)
                    print(re.search(r'\d{4}-\d{2}-\d{2}', div_each.find('span', class_='mf10').text).group())
                    # if div_each.find('span', class_='mf10') and re.search(r'\d{4}-\d{2]-\d{2}', div_each.find('span', class_='mf10').text) and re.search(r'\d{4}-\d{2}-\d{2}', div_each.find('span', class_='mf10').text).group()==p_date:
                    if re.search(
                            r'\d{4}-\d{2}-\d{2}', div_each.find('span', class_='mf10').text).group() == p_date:
                        original_url = urljoin('http://www.neeq.com.cn/index/searchInfo.do', div_each.find('a')['href'])
                        break
    except Exception as e:
        print(str(e))
        retry_times += 1
        if retry_times < retry_const:
            www_neeq_extractor(keyword, p_date, retry_times)
    print(original_url)
    return original_url



def www_mof_extractor(keyword, p_date, retry_times=0):
    print('crawling {}....'.format(keyword))
    original_url = ''
    try:
        # browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.set_page_load_timeout(50)
        browser.get(mof_url_search)
        input = WebDriverWait(browser, 1).until(EC.visibility_of_element_located((By.ID, 'swd')))
        input.send_keys(keyword)
        # input.send_keys(Keys.ENTER)
        enter = WebDriverWait(browser, 1).until(EC.visibility_of_element_located((By.ID, 'simplesearch')))
        enter.click()
        time.sleep(1)
        wait = WebDriverWait(browser, 1)
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'Jsuo_DMid_topzi')))
        # time.sleep(10)
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        # print(soup)
        td_list = soup.find_all('td', class_='Jsuo_DMid_topzi')
        for td in td_list:
            # print(td.a.text.strip())
            # print(re.search(r'\d{4}\.\d{2}\.\d{2}', td.find('span', class_='Jsuo_DMid_Content').text).group().replace('.','-'))
            # print(keyword)
            # if td.a.text.strip() == keyword:
            #     print('hall')
            if td.a and td.a.text.strip()==keyword:
                if td.find('span', class_='Jsuo_DMid_Content') and re.search(r'\d{4}\.\d{2}\.\d{2}', td.find('span', class_='Jsuo_DMid_Content').text) and re.search(r'\d{4}\.\d{2}\.\d{2}', td.find('span', class_='Jsuo_DMid_Content').text).group().replace('.','-')==p_date:
                    original_url = urljoin('http://www.mof.gov.cn/was5/web/czb/wassearch.jsp', td.a['href'])
                    break
    except Exception as e:
        print(str(e))
        retry_times += 1
        if retry_times < retry_const:
            www_mof_extractor(keyword, p_date, retry_times)
    print(original_url)
    return original_url


def www_csrc_extractor(keyword, p_date, retry_times=0):
    print('crawling {}....'.format(keyword))
    original_url = ''
    try:
        # browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=config.chromeDriver_path)
        browser = webdriver.Chrome(chrome_options=chrome_options)
        browser.set_page_load_timeout(50)
        browser.get(csrc_url_search)
        input = WebDriverWait(browser, 1).until(EC.visibility_of_element_located((By.ID, 'searchword1')))
        s = keyword if len(keyword)<50 else keyword[0:50]
        input.send_keys(s)
        input.send_keys(Keys.ENTER)
        time.sleep(1)
        wait = WebDriverWait(browser, 1)
        wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'jieguolist')))
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        div_list = soup.find_all('div', class_='jieguolist')
        for div in div_list:
            # if div.a and div.a.text.strip() == keyword:
            if div.find('div', class_='fileinfo') and re.search(r'\d{4}年\d{2}月\d{2}日', div.find('div',
                                                                                                class_='fileinfo').text).group().replace(
                    '年', '-').replace('月', '-').replace('日', '') == p_date:
                original_url = urljoin('http://www.csrc.gov.cn/wcm/websearch/advsearch.htm', div.a['href'])
                break
    except Exception as e:
        print(str(e))
        retry_times += 1
        if retry_times < retry_const:
            www_csrc_extractor(keyword, p_date, retry_times)
    print(original_url)
    return original_url

# def www_mof_extractor(keyword, p_date, retry_times=0):
#     print('crawling {}....'.format(keyword))
#     original_url = ''
#     try:
#
#         data = {'channelid': '273753',
#                 'page': '1',
#                 'prepage': '10',
#                 'outlinepage':'10',
#                 'sortfield':'-loder;-crtime',
#                 'searchword': 'doctitle/3=like("{}",80)'.format(keyword)}
#         response = requests.post('http://www.mof.gov.cn/was5/web/search',data=data)
#         soup = BeautifulSoup(response.text,'html.parser')
#         td_list = soup.find_all('td', class_='Jsuo_DMid_topzi')
#         for td in td_list:
#             if td.a and td.a.text.strip()==keyword:
#                 if td.find('span', class_='Jsuo_DMid_Content') and re.search(r'\d{4}\.\d{2}\.\d{2}', td.find('span', class_='Jsuo_DMid_Content').text) and re.search(r'\d{4}\.\d{2}\.\d{2}', td.find('span', class_='Jsuo_DMid_Content').text).group().replace('.','-')==p_date:
#                     original_url = urljoin('http://www.mof.gov.cn/was5/web/czb/wassearch.jsp', td.a['href'])
#                     break
#     except Exception as e:
#         print(str(e))
#         retry_times += 1
#         if retry_times < retry_const:
#             www_mof_extractor(keyword, p_date, retry_times)
#     print(original_url)
#     return original_url




def generate_slice_rows(sub_items, extractor_type):
    sub_result_list = []
    for item in sub_items:
        ri = [item['date'], item['keyword']]
        extractor = get_extractor(extractor_type)
        if extractor:
            url = extractor(item['keyword'], format_str_date(item['date']))
            ri.append(url)
        sub_result_list.append(ri)
    return sub_result_list


def get_extractor(extractor_type):
    for pattern in extractor_mapping:
        if extractor_type.find(pattern) >= 0:
            extractor = extractor_mapping[pattern]
            return extractor
    return None


extractor_mapping = OrderedDict({
    'szse': www_szse_extractor,
    'sse': www_sse_extractor,
    'neeq': www_neeq_extractor,
    'mof': www_mof_extractor,
    'csrc': www_csrc_extractor
})


def read_xlsx(file_name):
    print('processing file:', file_name)
    raw_data = xlrd.open_workbook(file_name)
    filename_prefix = os.path.splitext(file_name)[0].split('/')[-1]
    table = raw_data.sheets()[0]
    rows_data = table_analyzer(table)
    file_items_count = len(rows_data)
    print('processing file items:', file_items_count)
    processed_count = 0

    workbook = xlsxwriter.Workbook('{}_url_results_{}.xlsx'.format(filename_prefix, date.today().strftime('%Y-%m-%d')),
                                   {'strings_to_urls': False})
    print('{}_url_results_{}.xlsx'.format(filename_prefix, date.today().strftime('%Y-%m-%d')))
    worksheet = workbook.add_worksheet('first_sheet')
    worksheet.set_column('A:A', 30)
    worksheet.set_column('B:C', 120)

    total = len(rows_data)
    per_page = 1000
    pages = total // per_page if total % per_page == 0 else total // per_page + 1

    task_list = []
    for i in range(pages):
        start = i * per_page
        stop = (i + 1) * per_page
        task_list.append(rows_data[start:stop])

    print('slices:', len(task_list))

    final_rows = []
    # 线程池
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(generate_slice_rows, slice_item, filename_prefix) for slice_item in task_list]
        for index, future in enumerate(concurrent.futures.as_completed(futures)):
            final_rows += future.result()
            print('process pool{} processed: {}'.format(index, len(future.result())))

    try:
        for row_index, row in enumerate(final_rows):
            for col_index, col in enumerate(row):
                worksheet.write(row_index, col_index, col)
            processed_count += 1
    except Exception as e:
        print(e)
    finally:
        workbook.close()

    if processed_count == len(rows_data):
        print('done:%s' % processed_count)


def table_analyzer(table):
    row_num = table.nrows
    output_rows = []
    for index in range(0, row_num):
        data = table.row_values(index)
        if data[1]:
            if isinstance(data[0], float):
                # xldate_as_datetime() 第二个参数在mac上设置为0，否则日期会多出4年零一天
                data[0] = date.strftime(xlrd.xldate.xldate_as_datetime(data[0], 0), '%Y-%m-%d')
            # print('{}:{}'.format(type(data[0]), data[0]))
            output_rows.append({'date': data[0], 'keyword': data[1]})
    return output_rows


if __name__ == '__main__':
    '''
    根据提供的日期和法规名称获取法规original_url
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', default='')
    args = parser.parse_args()
    start_time = time.time()
    read_xlsx(args.filename)
    print('execution in ' + str(time.time() - start_time), 'seconds')

    # test
# www_szse_extractor('关于就指数熔断相关规定公开征求意见的通知', '2015-09-07')
# www_sse_extractor('关于发布《上海证券交易所技术规范白皮书》的通知', '2017-12-20')
# www_mof_extractor('关于做好2016年农业生产全程社会化服务试点工作的通知 ', '2016-06-04')
# www_neeq_extractor('全国中小企业股份转让系统有限责任公司管理暂行办法','2017-12-07')
# www_csrc_extractor('《关于深化新股发行体制改革的指导意见》', '2010-10-11')