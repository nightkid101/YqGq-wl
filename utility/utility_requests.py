import time
import requests
from bs4 import BeautifulSoup as bs

# timeout retry times limit
RETRY_LIMIT = 5
# sleep seconds
SLEEP_SECOND = 1
# timeout limit
TIMEOUT_LIMIT = 5

# 自定义的请求方法
# 主要是为了方便retry
def retry_requests(method, url, params=None, timeout=TIMEOUT_LIMIT, msg=''):
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,ja;q=0.6',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Host': 'www.csrc.gov.cn',
        'Pragma': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36',
    }

    retry = 0
    while retry < RETRY_LIMIT:
        try:
            if method.lower() == 'get':
                resp = requests.get(url, headers=headers, params=params, timeout=timeout)
                return resp
            elif method.lower() == 'post':
                resp = requests.post(url, headers=headers, data=params, timeout=timeout)
                return resp
            else:
                return
        except requests.RequestException or requests.Timeout or requests.ReadTimeout or requests.ConnectionError as exc:
            # 网络异常
            # 直接retry
            retry = retry + 1
            if retry >= RETRY_LIMIT:
                logging.error(exc)
                logging.error('failed(%s): %s %s' % (retry, url, msg))
            time.sleep(SLEEP_SECOND)  # 停5秒再retry
        except Exception as exc:
            # 解析异常
            # 需要关注
            logging.error(exc)
            retry = retry + 1
            if retry >= RETRY_LIMIT:
                logging.error('failed(%s): %s %s' % (retry, url, msg))
            else:
                logging.error('retry(%s): %s %s' % (retry, url, msg))
            time.sleep(SLEEP_SECOND)  # 停5秒再retry
        else:
            # 正常通过 跳出while循环
            retry = RETRY_LIMIT
    return


# 拼接url
def connect_urls(forward, backward):
    if backward.startswith('./'):
        return forward + backward.replace('./', '')
    elif backward.startswith('../'):
        # 去掉一层
        if forward.endswith('/'):
            forward = forward[:-1]
        forward = forward[:forward.rfind('/')]
        backward = backward[3:]
        return connect_urls(forward, backward)
    else:
        return forward + '/' + backward


# 读取本地html
def read_html(html_path, encoding='utf-8'):
    with open(html_path, 'r', encoding=encoding) as html_file:
        html_content = html_file.read()
        soup = bs(html_content, 'lxml')
        return soup