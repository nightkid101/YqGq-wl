import requests
import json
import re
import os
from utility import utility_convert

def craw_data(url):
    headers = {
        'User-Agent': 'ozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }

    try:
        r = requests.get(url,headers=headers)
        print(r.status_code)

        a = 'kahgkaldg'

        b = re.search('\d+',a)[0]
    except (Exception, ConnectionError, RuntimeError) as e:
        print(5)

if __name__=='__main__':
    #craw_data('http://www.sasac.gov.cn/n86114/n326638/c2585484/content.html')
    articleText = ''
    docID = '附件2.《关于深化会计人员职称制度改革的指导意见（征求意见稿）》起草说明.docx'
    if not os.path.exists(
            './file_data') and 'file_data' not in os.getcwd():  # 没有file_data目录且不在其子目录中
        os.mkdir('./file_data')
        os.chdir('./file_data')
    if os.path.exists(
            './file_data') and 'file_data' not in os.getcwd():  # 有file_data目录且不在子目录中
        os.chdir('./file_data')
    # 解析docx文件
    utility_convert.convert_doc_to_txt('./' + docID)
    if os.path.exists('./' + docID + '/' + docID + '.txt'):
        f = open('./' + docID + '/' + docID + '.txt', encoding='utf-8')
        docText = f.read()
        articleText += '\n\n\n\附件内容：\n' + docText
        f.close()