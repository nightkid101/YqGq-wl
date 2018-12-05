from urllib import request
import schedule
import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urlparse
import time
# 记录上一次更新的时间
last_time = '2018-09-27'
url1 = 'http://www.cbrc.gov.cn/chinese/newListDoc/111003/%d.html'


def craw_data(url):
    headers = {
        'User-Agent': 'ozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    return response.text


def www_csrc_gov_cn_pub_newsite_extractor(url):
    display_content = ''
    extracted_data = {
        'raw_content': '',
        'display_content': '',
        'fulltext': '',
    }
    headers = {
        'User-Agent': 'ozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    content = response.text
    extracted_data['extracted'] = True
    extracted_data['raw_content'] = content
    extracted_data['display_content'] = ''
    extracted_data['fulltext'] = ''
    soup = BeautifulSoup(content, 'lxml')
    extracted_data['auto_law_status'] = 'success'
    div1 = soup.find('div', valign='top')  # 包含了发布时间 文章来源 文章类型的div
    if div1:
        div1_list = str(div1.text).split()
        # 发布时间
        extracted_data['release_date'] = div1_list[2]
        # 执行时间
        extracted_data['operation_data'] = ''
        # 发布来源
        extracted_data['auto_law_source'] = div1_list[5]
        extracted_data['release_departments'] = div1_list[5]
    # 正文
    section = 'Section%d'
    wordsection = 'WordSection%d'
    n = 1
    m = 1
    display_content_div = soup.find('div', class_='Section0')
    display_content_div1 = soup.find('div', class_='WordSection0')
    while display_content_div:
        display_content = display_content + display_content_div.text + '\n'
        class_section = section % n
        display_content_div = soup.find('div', class_=class_section)
        n = n + 1
    while display_content_div1:
        display_content = display_content + display_content_div1.text + '\n'
        class_wordsection = wordsection % m
        display_content_div1 = soup.find('div', class_=class_wordsection)
        m = m + 1
    if display_content:
        extracted_data['display_content'] = display_content
        extracted_data['fulltext'] = BeautifulSoup(extracted_data['display_content'], 'lxml').get_text(strip=True)
    return extracted_data


# 下载附件
def down_accessory(url, url_name):
    headers = {
        'User-Agent': 'ozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    url_in_parse = urlparse(url).path.split('/')
    search_url_in_database = url_in_parse[len(url_in_parse) - 1].split('.')[0]
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    content = response.text
    soup = BeautifulSoup(content, 'lxml')
    # 附件
    accessory_td = soup.find('td', colspan='2', style='padding:8px')
    if accessory_td:
        number = 1
        accessory_list = accessory_td.find_all(name='a')
        for accessory in accessory_list:
            # 附件下载链接
            accessory_url = 'http://www.cbrc.gov.cn' + accessory['href']
            # 保存到本地附件的名称
            file_path = url_name + '-' + search_url_in_database + '-' + str(number) + '.' + accessory.string.split('.')[-1]
            response = requests.get(accessory_url, headers=headers)
            with open(os.getcwd() + '/' + file_path, 'wb') as outfile:
                outfile.write(response.content)
            # with request.urlopen(accessory_url) as web:
            #     # 为保险起见使用二进制写文件模式，防止编码错误
            #     with open(os.getcwd() + '/' + file_path, 'wb') as outfile:
            #         outfile.write(web.read())


def timer_task():
    global last_time
    tag = 0  # 标记是否有遇到已更新的网页
    cout = 1  # 访问的页面
    update_time = ''
    url = url1 % cout
    data = craw_data(url)
    soup = BeautifulSoup(data, 'lxml')
    pattrn = re.compile(r'.*/(\d*)[\u4e00-\u9fa5]')
    # couts 表示总页数
    couts = int(''.join(pattrn.findall(str(soup.find('tr', valign="bottom").text).strip().replace(" ", ""))))
    while cout <= couts:
        url = url1 % cout
        url_list = []
        url_name_list = []
        data = craw_data(url)
        soup = BeautifulSoup(data, 'lxml')
        url_td = soup.find_all(class_='cc')
        for i in url_td:
            if i.a and i.img:
                url_list.append('http://www.cbrc.gov.cn' + str(i.a['href']))
                url_name_list.append(i.a['title'])
        for i, p in enumerate(url_list):
            extracted_data = www_csrc_gov_cn_pub_newsite_extractor(p)
            if extracted_data['release_date'] > last_time:
                extracted_data['name'] = url_name_list[i]
                import_database(extracted_data)
                if i == 0 and cout == 1:
                    update_time = extracted_data['release_date']
                down_accessory(p, url_name_list[i])
            else:
                tag = 1
                break
        if tag == 1:
            break
        cout = cout + 1
    if update_time:
        last_time = update_time
    print(last_time)


def import_database(extracted_data):
    print(extracted_data['name'])


def main():
    # schedule.every().day.at("10:30").do(timer_task)  # 每天10：30 扫描
    schedule.every(20).seconds.do(timer_task)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()