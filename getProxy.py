import re
import requests
import random
import urllib3
import argparse
import time
import sys
from lxml import etree
import concurrent.futures as cf
import multiprocessing as mp
from bs4 import BeautifulSoup as bs
import pymongo
import schedule
import config


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

###########################################################################
############################ global Variables #############################
pageStart5 = pageStart4 = pageStart3 = pageStart2 = pageStart1 = 1  # current page number
pageNum = 50  # number of pages to be processed once a time
timeout = 3  # valid proxy test timeout param in seconds
remoteTrigger = 0
sleepTime = 5
maxProxySize = 50000
# testUrl = 'http://three.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice-emergent'
testUrl = 'http://www.baidu.com/duty/index.html'
validString = 'baidu'
# validString = 'cninfo'
scanningPorts = [80, 1080, 8080, 3128, 8081]
proxySize = 0


def initProxyMongoDB():
    if config.dev_mongo == '1':
        mongo_client = \
        pymongo.MongoClient(config.ali_mongodb_url, username=config.ali_mongodb_username,
                            password=config.ali_mongodb_password,
                            port=int(config.ali_mongodb_port))
    else:
        mongo_client = pymongo.MongoClient(
            host=config.mongodb_host,
            port=int(config.mongodb_port),
            username=None if config.mongodb_username == '' else config.mongodb_username,
            password=None if config.mongodb_password == '' else config.mongodb_password)['proxypool']
    collProxy = mongo_client['proxypool']
    return collProxy


def initProxyTZWMongoDB():
    db = pymongo.MongoClient('mongodb://localhost:6666', connect=False, serverSelectionTimeoutMS=1000)
    collProxyRemote = db['touzhiwang']['proxypool']
    return collProxyRemote


def getOneProxy():
    collProxy = initProxyMongoDB()
    while True:
        try:
            tot_num = collProxy.count({'_id': {"$exists": 1}})
            proxy = collProxy.find().skip(random.randrange(tot_num - 1)).limit(1).next()
            if proxy.pop('_id') == '1':
                return None
            proxyStatus, proxies = validUsefulProxy(proxy)
            if proxyStatus:
                return proxy
            # collProxy.delete_many(proxy)
        except:
            return None


def verifyProxyFormat(proxy):
    """
    :param proxy:
    :return:
    """
    verify_regex = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}"
    return True if re.findall(verify_regex, proxy) else False


def errorPageOrNot(text):
    """
    检测广告代理以及运营商劫持
    return True if not ad page..
    """
    if 'null({"baseinfo' in text:  # special for neeq company info
        return True
    if not re.findall(r"那家网", text) and text != 'NO' and \
            not re.findall(r"{\"rtn\":", text) and not re.findall(r"大数据操作系统", text) and \
            not re.findall(r"针对点一点扫一扫", text) and not re.findall(r"惠惠助手", text) and \
            not re.findall(r"The requested URL could not be retrieved", text) and text != '^@' and \
            not re.findall(r"无效用户", text) and not re.findall(r"禁止外部用户", text) and \
            not re.findall(r"Unauthorized", text) and not re.findall(r"推猫多品营销系统", text) and \
            not re.findall(r"Authorization", text) and not re.findall(r"迅格云视频", text) and \
            not re.findall(r"系统异常", text) and not re.findall(r"Page Not found", text) and \
            not re.findall(r"无法访问", text) and not re.findall(r"网易有道", text) and \
            not re.findall(r"错误页面", text):
        return True
    return False


def user_agent():
    """
    return an User-Agent at random
    :return:
    """
    ua_list = [
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.101',
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/38.0.2125.122',
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71',
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95',
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.1 (KHTML, like Gecko) Chrome/21.0.1180.71',
        'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; QQDownload 732; .NET4.0C; .NET4.0E)',
        'Mozilla/5.0 (Windows NT 5.1; U; en; rv:1.8.1) Gecko/20061208 Firefox/2.0.0 Opera 9.50',
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:34.0) Gecko/20100101 Firefox/34.0',
    ]
    return random.choice(ua_list)


def getHeader():
    """
    basic header
    :return:
    """
    return {'User-Agent': user_agent(),
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'Accept-Language': 'zh-CN,zh;q=0.8'}


def genHeader():
    header = {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_3) AppleWebKit/537.36 (KHTML, like Gecko)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, sdch',
        'Accept-Language': 'zh-CN,zh;q=0.8',
    }
    headers = getHeader()
    headers.update(header)
    return headers


def oversizeChecker(func):
    def wrapper(*args, **kw):
        if proxySize >= maxProxySize:
            return None
        return func(*args, **kw)

    return wrapper


def validUsefulProxy(p):
    """
    :param proxy:
    :return:
    """
    headers = genHeader()
    try:
        pProxies = {"https": "https://{proxy}".format(proxy=p)} if not isinstance(p, dict) else p
        with requests.Session() as s:
            s.trust_env = False
            r = s.get(testUrl, proxies=pProxies, headers=headers, timeout=timeout, verify=False)
        if r.status_code == 200:
            if errorPageOrNot(r.content.decode()):
                if not re.findall(validString, r.content.decode()):
                    print(r.content.decode())
                else:
                    return True, pProxies
    except Exception as e:
        pass
    if isinstance(p, dict):
        return False, None
    try:
        pProxies = {"http": "http://{proxy}".format(proxy=p)} if not isinstance(p, dict) else p
        with requests.Session() as s:
            s.trust_env = False
            r = s.get(testUrl, proxies=pProxies, headers=headers, timeout=timeout)
        if r.status_code == 200:
            if errorPageOrNot(r.content.decode()):
                if not re.findall(validString, r.content.decode()):
                    print(r.content.decode())
                else:
                    return True, pProxies
    except Exception as e:
        pass
    return False, None


def getHtmlTree(url, **kwargs):
    """
    :param url:
    :param kwargs:
    :return:
    """
    headers = genHeader()
    try:
        with requests.Session() as s:
            s.trust_env = False
            html = s.get(url, headers=headers, timeout=timeout)
        return etree.HTML(html.content)
    except:
        return etree.HTML('')


def getHtmlSoup(url, **kwargs):
    """
    :param url:
    :param kwargs:
    :return:
    """
    headers = genHeader()
    try:
        with requests.Session() as s:
            s.trust_env = False
            html = s.get(url, headers=headers, timeout=timeout)
        soup = bs(html.content, 'lxml')
        return soup
    except:
        return bs('', 'lxml')


def checkAndAddProxy(proxy):
    """
    Check if the proxy is valid if so add to db
    :proxy string format should be like '17.23.198.1'
    """
    if proxySize <= maxProxySize:
        collProxy = initProxyMongoDB()
        collProxyRemote = initProxyTZWMongoDB()
        if verifyProxyFormat(proxy):
            rePattern = re.compile(re.escape(proxy.split(':')[0]))
            if not (collProxy.find_one({"https": rePattern}) or collProxy.find_one({"http": rePattern})):
                statusCode, proxies = validUsefulProxy(proxy)
                if statusCode == True:
                    print("{proxies} is ok".format(proxies=proxies))
                    result = collProxy.insert_one(proxies)
                    if remoteTrigger and not (collProxyRemote.find_one({"https": rePattern}) \
                                              or collProxyRemote.find_one({"http": rePattern})):
                        result = collProxyRemote.insert_one(proxies)
                    return True
    return False


def checkProxy(proxy):
    """
    Check of proxy in db is valid
    :proxy dict should be like '{"_id": id, "http": "http://17.23.198.1:80"}'
    """
    collProxy = initProxyMongoDB()
    try:
        dbID = proxy.pop('_id')
        statusCode, proxies = validUsefulProxy(proxy)
        if statusCode == True:
            return True
        collProxy.delete_one({'_id': dbID})
    except:
        pass
    return False


def freeProxy1():
    """
    :return proxy list generator:
    """
    global pageStart1
    url_list = ['http://www.xicidaili.com/nn',
                'http://www.xicidaili.com/nt',
                ]
    for each_url in url_list:
        try:
            tree = getHtmlTree(each_url)
            proxy_list = tree.xpath('.//table[@id="ip_list"]//tr') if tree != '' else []
            for proxy in proxy_list:
                yield ':'.join(proxy.xpath('./td/text()')[0:2])
        except:
            pass
    pageStart1 = -1


def freeProxy2():
    """
    :param page:
    :return:
    """
    global pageStart2
    url_list = ['http://www.data5u.com/',
                'http://www.data5u.com/free/index.shtml',
                'http://www.data5u.com/free/gngn/index.shtml',
                'http://www.data5u.com/free/gnpt/index.shtml']
    for url in url_list:
        try:
            html_tree = getHtmlTree(url)
            ul_list = html_tree.xpath('//ul[@class="l2"]') if html_tree != '' else []
            for ul in ul_list:
                yield ':'.join(ul.xpath('.//li/text()')[0:2])
        except:
            pass
    pageStart2 = -1


def freeProxy3():
    """
    :param page:
    :return:
    """
    global pageStart3
    url = "http://www.goubanjia.com/free/index{page}.shtml"
    for page in range(pageStart3, pageStart3 + pageNum):
        page_url = url.format(page=page)
        soup = getHtmlSoup(page_url)
        for i in soup.findAll('td', attrs={'class': 'ip'}):
            ip = ''
            for span in i.children:
                try:
                    if 'style' in span.attrs and 'none' in span['style']:
                        continue
                    ip = ip + span.text
                except:
                    try:
                        ip = ip + span.text
                    except:
                        ip = ip + span
            yield ip
    pageStart3 += pageNum
    if pageStart3 > 90:
        pageStart3 = -1


def freeProxy4():
    """
    :param page:
    :return:
    """
    url = "http://www.ip181.com/daili/{page}.html"
    global pageStart4
    pageNum = 10  # 50 per page

    soup = getHtmlSoup('http://www.ip181.com/')
    for i in soup.findAll('tr', attrs={"class": "warning"}):
        ip = i.findAll('td')[0].text + ':' + i.findAll('td')[1].text
        yield ip

    for page in range(pageStart4, pageStart4 + pageNum):
        page_url = url.format(page=page)
        soup = getHtmlSoup(page_url)
        for i in soup.findAll('tr', attrs={"class": "warning"}):
            ip = i.findAll('td')[0].text + ':' + i.findAll('td')[1].text
            yield ip
    pageStart4 += pageNum
    if pageStart4 > 100:
        pageStart4 = -1


def freeProxy5():
    """
    :param page:
    :return:
    """
    baseUrl = "http://www.ip3366.net/?stype={type}&page={page}"
    global pageStart5
    url_list = []
    for stype in range(1, 5):
        for page in range(1, 11):
            url_list.append(baseUrl.format(type=stype, page=page))
    for url in url_list:
        try:
            tree = getHtmlTree(url)
            plist = tree.xpath('.//table/tbody//tr') if tree != '' else []
            for el in plist:
                yield ":".join(el.xpath('.//td/text()')[0:2])
            time.sleep(2 + random.random(5))
        except:
            pass
    pageStart5 = -1


# http://www.proxy360.cn/default.aspx


@oversizeChecker
def fetchProxy():
    print('Adding new proxies...')
    global pageStart1, pageStart2, pageStart3, pageStart4, pageStart5
    while True:
        if (proxySize) >= 40000:
            print('ProxyPool oversize and should be cleaned.')
            break
        if pageStart1 != -1:
            print('proxy-1:')
            with cf.ThreadPoolExecutor() as executor:
                result = executor.map(checkAndAddProxy, freeProxy1())
            time.sleep(5)
        if pageStart2 != -1:
            print('proxy-2:')
            with cf.ThreadPoolExecutor() as executor:
                result = executor.map(checkAndAddProxy, freeProxy2())
            time.sleep(5)
        if pageStart4 != -1:
            print('proxy-4:')
            with cf.ThreadPoolExecutor() as executor:
                result = executor.map(checkAndAddProxy, freeProxy4())
            time.sleep(5)
        if pageStart3 != -1:
            print('proxy-3:')
            with cf.ThreadPoolExecutor() as executor:
                result = executor.map(checkAndAddProxy, freeProxy3())
            time.sleep(5)
        if pageStart5 != -1:
            print('proxy-5:')
            with cf.ThreadPoolExecutor() as executor:
                result = executor.map(checkAndAddProxy, freeProxy5())
            time.sleep(5)
        if set({pageStart1, pageStart2, pageStart3, pageStart4, pageStart5}) == set({-1}):
            break
    pageStart5 = pageStart4 = pageStart3 = pageStart2 = pageStart1 = 1
    print('Proxy new list done!')


def cleanProxy():
    global proxySize
    print('Cleaning up previous run...')
    proxylist = list(collProxy.find({'_id': {"$ne": '1'}}))
    print('Existing proxylist with size: {size}'.format(size=len(proxylist)))
    pool = mp.Pool(12)  # multi processing
    pool.map(checkProxy, proxylist)
    pool.close()
    pool.join()
    proxySize = len(list(collProxy.find({})))
    print('Valid proxylist with size: {size}'.format(size=proxySize))


@oversizeChecker
def childrenProxy():
    global proxySize
    proxy = getOneProxy()
    p = list(proxy.values())[0]
    base = re.compile('.*//(.*)\.[0-9]+\.[0-9]+:[0-9]+').findall(p)[0]
    proxyList = []
    for i in range(255):
        for j in range(255):
            for k in scanningPorts:
                proxyTmp = base + '.' + str(i) + '.' + str(j) + ':' + str(k)
                proxyList.append(proxyTmp)
    print('Scan proxy for IPs.')
    for i in proxyList:
        if proxySize >= maxProxySize:
            return
        result = checkAndAddProxy(i)
        if result:
            proxySize += 1


def checkProxySize():
    global proxySize
    collProxy = initProxyMongoDB()
    proxySize = collProxy.count({})
    if proxySize >= maxProxySize:
        print('ProxyPool oversize and should be cleaned.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--clean', action='store_true', help="clean up previous run.")
    parser.add_argument('-n', '--new', action='store_true', help='get new proxies.')
    parser.add_argument('-r', '--remote', action='store_true', help='add to remote server.')
    parser.add_argument('-s', '--scan', action='store_true', help='scan db reconstruct for new proxy.')
    parser.add_argument('web', nargs='?', help='valid string to be tested, like baidu, cninfo, csrc, cm, sse, szse...')
    args = parser.parse_args()

    if len(sys.argv) == 1 or args.web == None:
        opt = 'baidu'
    elif args.web not in ['baidu', 'cninfo', 'csrc', 'cm']:
        opt = 'baidu'
    else:
        opt = args.web
    if opt == 'baidu':
        testUrl = 'http://www.baidu.com/duty/index.html'
        validString = 'baidu'
    elif opt == 'cninfo':
        testUrl = 'http://three.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice-emergent'
        validString = 'cninfo'
    elif opt == 'csrc':
        testUrl = 'http://www.csrc.gov.cn/pub/newsite/fzlm/gywm/'
        validString = 'csrc'
    elif opt == 'cm':
        testUrl = 'http://www.chinamoney.com.cn/chinese/legaldeclaration/'
        validString = 'chinamoney'
    elif opt == 'neeq':
        testUrl = 'http://www.neeq.com.cn/company/introduce.html'
        validString = 'neeq'

    print('Initializing Proxy MongoDB..')
    collProxy = initProxyMongoDB()

    if args.remote:
        print('Initializing Remote Proxy MongoDB..')
        remoteTrigger = 1
        collProxyRemote = initProxyTZWMongoDB()
        cmdSSHTunnel = "ssh -fN -i ~/.ssh/id_rsa -L 6666:localhost:27017 mzy@dev.touzhiwang.com"

    if args.clean:
        cleanProxy()
        schedule.every(12).hours.do(cleanProxy)

    if args.new:
        fetchProxy()
        schedule.every(30).minutes.do(fetchProxy)

    print('Now scheduling..')
    while True:
        schedule.run_pending()
        time.sleep(1)
