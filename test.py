import requests
from bs4 import BeautifulSoup
import urllib

if __name__=="__main__":
    baseUrl = 'https://www.crmsc.com.cn/mark_search.asp'
    pageNum = 1
    dict = urllib.parse.quote('国企改革', encoding='gb2312')
    print(dict)
    data = {'key': dict}
    r = requests.post(baseUrl, data=data)
    r.encoding = r.apparent_encoding
    basesoup = BeautifulSoup(r.text, 'lxml')
    basesoup.prettify()
    print(r.text)