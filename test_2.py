import requests
import re
import os
from pymongo import MongoClient
from bs4 import BeautifulSoup
import config
from utility import utility_convert
import ast
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

#45.福建省福州市财政局
def FJFuzhouCZJ():
    # coding=utf8
    # the above tag defines encoding for this document and is for Python 2.x compatibility

    import re

    regex = r"http:\/\/.*?\.htm"

    test_str = "http://a.htm, http://abksdahgl.htm，http://jflsdjkgla.htm"

    matches = re.finditer(regex, test_str)

    for matchNum, match in enumerate(matches):
        matchNum = matchNum + 1

        print("Match {matchNum} was found at {start}-{end}: {match}".format(matchNum=matchNum, start=match.start(),
                                                                            end=match.end(), match=match.group()))

        for groupNum in range(0, len(match.groups())):
            groupNum = groupNum + 1

            print("Group {groupNum} found at {start}-{end}: {group}".format(groupNum=groupNum,
                                                                            start=match.start(groupNum),
                                                                            end=match.end(groupNum),
                                                                            group=match.group(groupNum)))

    # Note: for Python 2.7 compatibility, use ur"" to prefix the regex and u"" to prefix the test string and substitution.


if __name__ == '__main__':
    # 45.福建省福州市财政局
    FJFuzhouCZJ()