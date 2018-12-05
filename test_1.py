import requests
import json
def craw_data(url):
    headers = {
        'User-Agent': 'ozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    response = requests.post(url, headers=headers, data={'key': '国企改革', 'pageindex': '1'})
    response.encoding = 'utf-8'
    if response.status_code == 404:
        return ''
    else:
        data = json.loads(response.text)
        print(data)
craw_data('http://www.wri.com.cn/cn/tools/submit_self_ajax.ashx?action=search_list')