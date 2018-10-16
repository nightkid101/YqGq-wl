import io
import os
import json
import time
import codecs
import logging
import requests
import subprocess


# Imports the Google Cloud client library
# from google.cloud import vision
# from google.cloud.vision import types
# baidu
from aip import AipOcr

from config_sample import ocr_method
from config_sample import azure_sub_key
from config_sample import baidu_app_id
from config_sample import baidu_api_key
from config_sample import baidu_secret_key
from utility.AbbyyOnlineSdk import AbbyyOnlineSdk, ProcessingSettings


# timeout retry times limit
RETRY_LIMIT = 5
# sleep seconds
SLEEP_SECOND = 1
# timeout limit
TIMEOUT_LIMIT = 10


# 根据config里面的配置 选择ocr方法
# 建议是google或者baidu
# 其他两个效果太差
# 返回值是list 一行文本就是一个元素
def ocr(png_path):
    retry = 0
    while retry < RETRY_LIMIT:
        try:
            if ocr_method == 'google':
                return ocr_with_google(png_path)
            elif ocr_method == 'baidu':
                return ocr_with_baidu(png_path)
            elif ocr_method == 'azure':
                return ocr_with_azure(png_path)
            elif ocr_method == 'tesseract':
                return ocr_with_tesseract(png_path)
            else:
                return ocr_with_google(png_path)
        except Exception as exc:
            retry = retry + 1
            if retry >= RETRY_LIMIT:
                logging.info('ocr失败 %s' % exc)
            time.sleep(SLEEP_SECOND)
        else:
            # 正常通过 跳出while循环
            retry = RETRY_LIMIT

    return list()


def ocr_with_google(png_path):
    """Detects document features in an image."""
    client = vision.ImageAnnotatorClient()

    with io.open(png_path, 'rb') as image_file:
        content = image_file.read()

    image = types.Image(content=content)

    response = client.document_text_detection(image=image)
    document = response.full_text_annotation

    all_text = list()
    for page in document.pages:
        for block in page.blocks:
            block_words = []
            for paragraph in block.paragraphs:
                block_words.extend(paragraph.words)

            block_symbols = []
            for word in block_words:
                block_symbols.extend(word.symbols)

            block_text = ''
            for symbol in block_symbols:
                block_text = block_text + symbol.text

            # print('Block Content: {}'.format(block_text))
            # print('Block Bounds:\n {}'.format(block.bounding_box))
            all_text.append(block_text)

    return all_text


def ocr_with_azure(png_path):
    vision_analyze_url = 'https://westcentralus.api.cognitive.microsoft.com/vision/v1.0/ocr'
    image_data = open(png_path, "rb").read()
    headers = {
        'Ocp-Apim-Subscription-Key': azure_sub_key,
        "Content-Type": "application/octet-stream",
    }
    params = {
        'language': 'zh-Hans',
        'detectOrientation': 'true',
    }
    response = requests.post(vision_analyze_url,
                             headers=headers,
                             params=params,
                             data=image_data)

    response.raise_for_status()

    analysis = response.json()
    line_infos = [region["lines"] for region in analysis["regions"]]
    all_text = []
    for line in line_infos:
        for word_metadata in line:
            line_text = ''
            for word_info in word_metadata["words"]:
                line_text = line_text + word_info['text']
            all_text.append(line_text)
            # logging.info('Block Content: ' + line_text)
    return all_text


def ocr_with_baidu(png_path):
    client = AipOcr(baidu_app_id, baidu_api_key, baidu_secret_key)

    with open(png_path, 'rb') as fp:
        content = fp.read()

    # 带参数调用通用文字识别, 图片参数为本地图片
    options = {
        'language_type': 'CHN_ENG',
        'detect_direction': 'true',
        'detect_language': 'true',
        'probability': 'false',
    }
    resp = client.basicGeneral(content, options)
    result = resp

    all_text = list()
    if result.get('words_result'):
        for line in result.get('words_result'):
            # logging.info('Block Content: ' + line.get('words'))
            all_text.append(line.get('words'))
    return all_text


# ocr tables with baidu
def ocr_table_with_baidu(png_path):
    logging.info('识别 %s' % png_path)
    client = AipOcr(baidu_app_id, baidu_api_key, baidu_secret_key)

    with open(png_path, 'rb') as fp:
        content = fp.read()

    # 表格文字识别 提交请求接口
    form_rec_async_resp = client.tableRecognitionAsync(content)
    if 'error_code' in form_rec_async_resp:
        logging.info('提交请求失败')
        return
    else:
        # logging.info(form_rec_async_resp)
        request_id = form_rec_async_resp['result'][0]['request_id']
        logging.info('结果id %s' % request_id)

        # 表格文字识别 获取结果
        # options = {
        #     'result_type': 'json',
        # }
        # for i in range(20):
        #     form_rec_result_resp = client.getTableRecognitionResult(request_id, options)
        #
        #     # 完成
        #     if int(form_rec_result_resp['result']['ret_code']) == 3:
        #         logging.info('第%s次请求' % i)
        #         json_str = form_rec_result_resp['result']['result_data']
        #         result_data = json.loads(json_str)
        #         body = result_data['forms']['body']
        #         logging.info(body)
        #
        #         break
        #     time.sleep(1)
        # logging.info('end')
        # return
        for i in range(200):
            time.sleep(1)
            form_rec_result_resp = client.getTableRecognitionResult(request_id)
            # 完成
            if int(form_rec_result_resp['result']['ret_code']) == 3:
                # result_data_str = form_rec_result_resp['result']['result_data']
                # result_data = json.loads(result_data_str)
                # file_url = result_data['file_url']
                file_url = form_rec_result_resp['result']['result_data']
                logging.info('第%s次请求得到 %s' % (i, file_url))

                output_path = png_path.replace('.jpg', '.xls').replace('.png', '.xls')
                if not os.path.exists(output_path):
                    try:
                        resp = requests.get(file_url)
                        with open(output_path, 'wb') as f:
                            for chunk in resp.iter_content(chunk_size=1024):
                                if chunk:
                                    f.write(chunk)
                        logging.info('下载 %s' % output_path)
                    except Exception as exc:
                        logging.error(exc)
                else:
                    logging.debug('已经存在 %s' % output_path)
                break


# ocr tables and text with abbyy
def ocr_table_with_abbyy(png_path):
    processor = AbbyyOnlineSdk()
    output_format = 'docx'
    source_file = png_path
    target_file = png_path.replace('.jpg', '.'+output_format).replace('.png', '.'+output_format)
    language = 'ChinesePRC'

    if os.path.isfile(source_file):
        logging.info("Uploading..")
        settings = ProcessingSettings()
        settings.Language = language
        settings.OutputFormat = output_format
        task = processor.process_image(source_file, settings)
        if task is None:
            logging.error("Error")
            return
        if task.Status == "NotEnoughCredits":
            logging.error("Not enough credits to process the document. Please add more pages to your application's account.")
            return

        logging.info("Id = {}".format(task.Id))
        logging.info("Status = {}".format(task.Status))

        # Wait for the task to be completed
        logging.info("Waiting..")
        time.sleep(2)
        # Note: it's recommended that your application waits at least 2 seconds
        # before making the first getTaskStatus request and also between such requests
        # for the same task. Making requests more often will not improve your
        # application performance.
        # Note: if your application queues several files and waits for them
        # it's recommended that you use listFinishedTasks instead (which is described
        # at http://ocrsdk.com/documentation/apireference/listFinishedTasks/).

        while task.is_active():
            time.sleep(5)
            logging.info(".")
            task = processor.get_task_status(task)

        logging.info("Status = {}".format(task.Status))

        if task.Status == "Completed":
            if task.DownloadUrl is not None:
                processor.download_result(task, target_file)
                logging.info("Result was written to {}".format(target_file))
        else:
            logging.info("Error processing task")

    else:
        logging.info('No such file: {}'.format(source_file))


# parse png with tesseract
def ocr_with_tesseract(png_path):
    txt_name = png_path.replace('.jpg', '')
    try:
        subprocess.call(['tesseract', png_path, txt_name, '-l', 'chi_sim'])
    except Exception as exc:
        logging.error('转化png失败 page:%s' % png_path)
        logging.error(exc)

    # 读取文本
    logging.info('抽出png到文件 %s' % (txt_name + '.txt'))
    return read_text_file(txt_name + '.txt')


# 读取文本文件
def read_text_file(txt_path):
    all_text = list()
    if os.path.exists(txt_path):
        with codecs.open(txt_path, 'r', 'utf-8') as txt_file:
            for line in txt_file:
                all_text.append(line)

    return all_text
