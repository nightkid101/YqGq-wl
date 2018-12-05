# 将各种格式转化为txt

import re
import os
import oss2
import xlrd
import json
import time
import codecs
import shutil
import logging
import zipfile
import patoolib
# import datetime
# import dateutil
import requests
import subprocess
import pdfplumber
import concurrent.futures
from bs4 import BeautifulSoup as bs
from urllib.parse import unquote
from PIL import Image, ImageSequence
from utility.utility_ocr import ocr
import config

PARENT_FOLDER = 'announce'


# 将pdf转为txt
# 旧版 不用了
# 一个页面可能会有上万张图片
def convert_pdf_to_txt_deprecated(output_path):
    # 输出文件
    output_txt = output_path.replace('.pdf', '.txt')
    # 这里判断一下输出文件的是否存在以及大小？
    if os.path.exists(output_txt) and os.path.getsize(output_txt) > 100:
        return read_text_file(output_txt)

    # 总页数
    page_number = get_page_number(output_path)
    # 有图片的页
    image_pages = get_image_page(output_path)

    all_text = list()
    # 遍历所有页面
    for page in range(1, page_number + 1):
        # 下面的代码 如果一个页面内既有文本又有图片 就只会解析图片 导致信息不全
        # if page in image_pages:
        #     # 是图片，ocr
        #     page_text = parse_pdf_image(output_path, page)
        # else:
        #     # 是文本，直接拿
        #     page_text = parse_pdf_text(output_path, page)

        # 修改后
        # 先获取文本
        page_text = parse_pdf_text(output_path, page)
        all_text.extend(page_text)
        # 如果有图片 获取图片
        if page in image_pages:
            page_text = parse_pdf_image(output_path, page)
            all_text.extend(page_text)

    # 输出到文件
    output_text_file(all_text, output_txt)

    # # pdf直接转txt
    # convert_pdf_to_txt_directly(output_path, output_path.replace('.pdf', '_directly.txt'))
    # logging.info('')
    return all_text


# 将pdf转为txt
# 舍弃图片 只提取全部文本
def convert_pdf_to_txt_only(output_path):
    # 输出文件
    output_txt = output_path.replace('.pdf', '.txt')
    # 这里判断一下输出文件的是否存在以及大小？
    if os.path.exists(output_txt) and os.path.getsize(output_txt) > 100:
        return read_text_file(output_txt)

    # 总页数
    page_number = get_page_number(output_path)
    all_text = list()
    # 遍历所有页面
    for page in range(1, page_number + 1):
        page_text = parse_pdf_text(output_path, page)
        all_text.extend(page_text)

    # 输出到文件
    output_text_file(all_text, output_txt)

    return all_text


# 将pdf转为txt
# 舍弃图片 只提取全部文本
# 使用pdfplumber
def convert_pdf_to_txt_only_pdfplumber(pdf_path):
    # 输出文件
    output_txt = pdf_path.replace('.pdf', '.txt')
    # 这里判断一下输出文件的是否存在以及大小？
    if os.path.exists(output_txt) and os.path.getsize(output_txt) > 100:
        return read_text_file(output_txt)

    pdf_dir = os.path.dirname(pdf_path)
    pdf_file_name = os.path.basename(pdf_path).replace('.pdf', '')
    txt_dir = os.path.join(pdf_dir, pdf_file_name)
    if not os.path.exists(txt_dir):
        os.mkdir(txt_dir)

    all_text = list()
    try:
        # 遍历所有页面
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_number = page.page_number
                page_text_str = page.extract_text()
                if '\n' in page_text_str:
                    page_text = page_text_str.split('\n')
                else:
                    page_text = [page_text_str]

                # 按页输出到文件
                txt_name = 'page' + ('%03d' % page_number) + '.txt'
                txt_path = os.path.join(txt_dir, txt_name)
                output_text_file(page_text, txt_path)
                all_text.extend(page_text)
            pdf.close()
    except Exception as exc:
        return None
    # 输出到文件
    output_text_file(all_text, output_txt)

    return all_text


# 将pdf转为txt
# 如果某页面存在图片，那么把这个页面转为一张图片去ocr，而不是提取所有图片
def convert_pdf_to_txt(output_path):
    # 输出文件
    output_txt = output_path.replace('.pdf', '.txt')
    # 这里判断一下输出文件的是否存在以及大小？
    if os.path.exists(output_txt) and os.path.getsize(output_txt) > 100:
        return read_text_file(output_txt)

    # 总页数
    page_number = get_page_number(output_path)
    page_bit = len(str(page_number))
    # 有图片的页
    image_pages = get_image_page(output_path)

    all_text = list()
    # 遍历所有页面
    for page in range(1, page_number + 1):
        # 文本结果比较差的情况，就直接ocr
        # page_text = pdf_page_to_png(output_path, page, page_bit)
        if page in image_pages:
            # 包含图片，把该页转成图片然后ocr
            page_text = pdf_page_to_png(output_path, page, page_bit)
        else:
            # 是文本，直接拿
            page_text = parse_pdf_text(output_path, page)

        # 把这一页内容输出到文件'pageXXX.txt'
        page_txt_path = os.path.join(output_path.replace('.pdf', ''), 'page%03d.txt' % page)
        output_text_file(page_text, page_txt_path)
        # 保存到总文件
        all_text.extend(page_text)

    # 输出到文件
    output_text_file(all_text, output_txt)

    return all_text


# 直接转
def convert_pdf_to_txt_directly(output_path, output_txt):
    try:
        subprocess.call(['pdftotext', '-enc', 'UTF-8', output_path, output_txt])
    except Exception as exc:
        logging.error('pdf直接转txt失败 %s' % output_path)
        logging.error(exc)
    else:
        logging.debug('pdf直接转txt成功 %s' % output_txt)


def convert_doc_to_txt(download_path):
    file_name = os.path.basename(download_path)
    file_dir = os.path.dirname(download_path)

    out_dir = download_path[:download_path.rfind('.')]
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    if file_name.endswith('.doc'):
        html_path = os.path.join(out_dir, file_name.replace('.doc', '.html'))
    else:
        if file_name.endswith('.docx'):
            html_path = os.path.join(out_dir, file_name.replace('.docx', '.html'))
        else:
            logging.info('不需要转化的文件格式 %s' % file_name)
            pass

    # doc/docx/wps/rtf to html
    if not os.path.exists(html_path):
        # convert to html
        try:
            subprocess.call([config.soffice_path, \
                             '--headless', '--convert-to', 'html:HTML:UTF8', '--outdir', out_dir, download_path])
        except Exception as exc:
            logging.error('docs转html失败 %s' % download_path)
            logging.error(exc)
        else:
            logging.debug('docs转html成功 %s' % download_path)

    # html to text
    return convert_html_to_txt(html_path)


def convert_rar_to_txt(download_path):
    # 解压内容放到同名的目录
    output_dir = download_path[:download_path.rfind('.')]
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    # 如果文件夹下为空 解压
    if len(os.listdir(output_dir)) < 1:
        patoolib.extract_archive(download_path, outdir=output_dir)

    # 检查是不是多了一层目录
    if len(os.listdir(output_dir)) == 1:
        for extra in os.listdir(output_dir):
            if extra.endswith('.DS_Store'):
                continue
            else:
                # 多余的一层目录 把下面的文件考出来 然后目录删掉
                tobe_del_dir = os.path.join(output_dir, extra)
                if os.path.isdir(tobe_del_dir):
                    for pdf_file in os.listdir(tobe_del_dir):
                        if not pdf_file.endswith('.DS_Store'):
                            # 拷贝到父目录
                            shutil.move(os.path.join(tobe_del_dir, pdf_file), os.path.join(output_dir, pdf_file))
                    # 删除
                    os.removedirs(tobe_del_dir)

    # 筛选
    logging.info(output_dir)
    for pdf_file in os.listdir(output_dir):
        if os.path.isfile(os.path.join(output_dir, pdf_file)):
            if pdf_file.endswith('.DS_Store'):
                continue
            elif pdf_file.endswith('.tif'):
                # 图片合并转化
                merge_dir_pic_to_txt(output_dir)
                # 图片转化完成后 就break
                break
            elif pdf_file.endswith('.jpg') or pdf_file.endswith('.png'):
                # 图片合并转化
                merge_dir_pic_to_txt(output_dir)
                # 图片转化完成后 就break
                break
            elif pdf_file.endswith('.doc') or pdf_file.endswith('.docx'):
                if need_to_save(pdf_file):
                    doc_path = os.path.join(output_dir, pdf_file)
                    convert_doc_to_txt(doc_path)
            elif pdf_file.endswith('.pdf'):
                if need_to_save(pdf_file):
                    pdf_path = os.path.join(output_dir, pdf_file)
                    convert_pdf_to_txt(pdf_path)
            elif pdf_file.endswith('.txt'):
                continue
            else:
                logging.info('解压出来的文件不知道怎么处理 %s/%s' % (output_dir, pdf_file))

    logging.info('')
    return


def merge_dir_pic_to_txt(output_dir):
    pic_lines = list()

    # 所有tif合并到一个list里面
    for pic_file in os.listdir(output_dir):
        if pic_file.endswith('.tif'):
            tif_texts = convert_tif_to_txt(os.path.join(output_dir, pic_file))
            pic_lines.extend(tif_texts)
        elif pic_file.endswith('.jpg'):
            jpg_texts = convert_jpg_to_txt(os.path.join(output_dir, pic_file))
            pic_lines.extend(jpg_texts)
        elif pic_file.endswith('.png'):
            png_texts = convert_png_to_txt(os.path.join(output_dir, pic_file))
            pic_lines.extend(png_texts)

    # 输出一个文件
    txt_name = os.path.basename(output_dir) + '.txt'
    txt_path = os.path.join(output_dir, txt_name)
    output_text_file(pic_lines, txt_path)

    return pic_lines


def need_to_save(file_name):
    if '辅导备案申请' in file_name or '辅导协议' in file_name or '辅导备案情况表' in file_name or '辅导工作进展报告' in file_name or '基本情况备案表' in file_name:
        return True
    elif '工作报告' in file_name or '工作总结报告' in file_name:
        return True
    elif '终止协议' in file_name:
        return True
    elif '变更辅导人员' in file_name or '新增辅导人' in file_name:
        return True
    else:
        return False


def convert_zip_to_txt(download_path):
    # 解压内容放到同名的目录
    output_dir = download_path[:download_path.rfind('.')]
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    # 如果文件夹下为空 解压
    if len(os.listdir(output_dir)) < 1:
        un_zip(download_path, output_dir)

    # 检查是不是多了一层目录
    if len(os.listdir(output_dir)) == 1:
        for extra in os.listdir(output_dir):
            if extra.endswith('.DS_Store'):
                continue
            else:
                # 多余的一层目录 把下面的文件考出来 然后目录删掉
                tobe_del_dir = os.path.join(output_dir, extra)
                if os.path.isdir(tobe_del_dir):
                    for pdf_file in os.listdir(tobe_del_dir):
                        if not pdf_file.endswith('.DS_Store'):
                            # 拷贝到父目录
                            shutil.move(os.path.join(tobe_del_dir, pdf_file), os.path.join(output_dir, pdf_file))
                    # 删除
                    os.removedirs(tobe_del_dir)

    # 筛选
    logging.info(output_dir)
    for pdf_file in os.listdir(output_dir):
        if os.path.isfile(os.path.join(output_dir, pdf_file)):
            if pdf_file.endswith('.DS_Store'):
                continue
            elif pdf_file.endswith('.tif'):
                # 图片合并转化
                merge_dir_pic_to_txt(output_dir)
                # 图片转化完成后 就break
                break
            elif pdf_file.endswith('.jpg') or pdf_file.endswith('.png'):
                # 图片合并转化
                merge_dir_pic_to_txt(output_dir)
                # 图片转化完成后 就break
                break
            elif pdf_file.endswith('.doc') or pdf_file.endswith('.docx'):
                if need_to_save(pdf_file):
                    doc_path = os.path.join(output_dir, pdf_file)
                    convert_doc_to_txt(doc_path)
            elif pdf_file.endswith('.pdf'):
                if need_to_save(pdf_file):
                    pdf_path = os.path.join(output_dir, pdf_file)
                    convert_pdf_to_txt(pdf_path)
            elif pdf_file.endswith('.txt'):
                continue
            else:
                logging.info('解压出来的文件不知道怎么处理 %s/%s' % (output_dir, pdf_file))

    logging.info('')
    return


def un_zip(zip_file_path, release_file_dir):
    is_zip = zipfile.is_zipfile(zip_file_path)
    if is_zip:
        zip_file_contents = zipfile.ZipFile(zip_file_path, 'r')
        for sub_file in zip_file_contents.namelist():
            # 先解压缩ZIP文件
            zip_file_contents.extract(sub_file, release_file_dir)

            # 处理乱码问题
            # 原来编码不能被正确识别为utf-8的时候，会被是被识别并decode为cp437编码，如果原来是gbk编码的话就会变成乱码。
            sub_file_name = sub_file.encode('cp437').decode('gbk')
            # 重命名乱码文件
            os.rename(os.path.join(release_file_dir, sub_file), os.path.join(release_file_dir, sub_file_name))


def convert_tif_to_txt(download_path):
    output_txt = download_path.replace('.tif', '.txt')
    text_lines = list()

    file_dir = os.path.dirname(download_path)
    file_name = os.path.basename(download_path)
    # tif 可能包含多个图片
    im = Image.open(download_path)
    for page, frame in enumerate(ImageSequence.Iterator(im), start=1):
        png_name = file_name.replace('.tif', '') + str(page) + '.png'
        # tif转png
        temp_file = os.path.join(os.path.dirname(download_path), png_name)
        frame.thumbnail(frame.size)
        frame.save(temp_file, optimize=True)
        # png转txt
        png_path = os.path.join(file_dir, png_name)
        png_lines = convert_png_to_txt(png_path)
        #
        text_lines.extend(png_lines)
        # 删掉png
        if os.path.exists(png_path) and os.path.isfile(png_path):
            os.remove(png_path)

    # 输出
    output_text_file(text_lines, output_txt)
    return text_lines


def convert_jpg_to_txt(download_path):
    all_text = ocr(download_path)
    output_txt = download_path.replace('.jpg', '.txt')
    output_text_file(all_text, output_txt)
    return all_text


def convert_png_to_txt(download_path):
    all_text = ocr(download_path)
    output_txt = download_path.replace('.png', '.txt')
    output_text_file(all_text, output_txt)
    return all_text


def convert_et_to_xlsx(download_path):
    xlsx_path = download_path.replace('.et', '.xlsx')
    output_dir = os.path.dirname(download_path)
    # et to xlsx
    if not os.path.exists(xlsx_path):
        try:
            subprocess.call(['/Applications/LibreOffice.app/Contents/MacOS/soffice', '--headless', '--convert-to',
                             'xlsx:Calc MS Excel 2007 XML', '--outdir', output_dir, download_path])
        except Exception as exc:
            logging.error('et转xlsx失败 %s' % download_path)
            logging.error(exc)
        else:
            logging.debug('et转xlsx成功 %s' % download_path)


# 获取文档页数
def get_page_number(output_path):
    page_number = 0
    if os.path.exists(output_path):
        try:
            pdf_info_bytes = subprocess.check_output(['pdfinfo', '-box', output_path])
            pdf_info_text = pdf_info_bytes.decode(encoding='utf-8', errors='ignore')
            page_number_search = re.search('Pages:\s*(\d+)', pdf_info_text)
            if page_number_search:
                page_number_str = page_number_search.group(1)
            else:
                page_number_str = '0'
            page_number = int(page_number_str)

        except Exception as exc:
            logging.error('获取文档页数失败 %s' % output_path)
            logging.error(exc)
        else:
            logging.debug('获取文档页数成功 %s' % page_number)
    return page_number


# 获取包含图片的页码
def get_image_page(output_path):
    image_pages = list()
    if os.path.exists(output_path):
        try:
            images_info_bytes = subprocess.check_output(['pdfimages', '-list', output_path])
            images_info_text = images_info_bytes.decode('utf-8')
            # logging.info(images_info_text)
            line_list = images_info_text.split('\n')
            for line in line_list:
                # logging.info(line)
                line = line.strip()
                line_comma, times = re.subn('\s+', ',', line)
                if ',' in line_comma:
                    cells = line_comma.split(',')
                    page_str = cells[0]
                    if page_str.isnumeric():  # header行和分割线不用
                        page = int(page_str)
                        if page not in image_pages:
                            image_pages.append(page)
        except Exception as exc:
            logging.error('获取包含图片的页码失败 %s' % output_path)
            logging.error(exc)
        else:
            image_pages_str = [str(page) for page in image_pages]
            logging.debug('获取包含图片的页码成功 %s' % ','.join(image_pages_str))
    return image_pages


# 获取page页面图片上的文本
def pdf_page_to_png(pdf_path, page, page_bit):
    pdf_dir = os.path.dirname(pdf_path)
    pdf_file_name = os.path.basename(pdf_path).replace('.pdf', '')
    png_dir = os.path.join(pdf_dir, pdf_file_name)
    png_name_root = os.path.join(png_dir, 'page')
    png_name = (png_name_root + '-%0' + str(page_bit) + 'd.png') % page
    if not os.path.exists(png_dir):
        os.mkdir(png_dir)
    if not os.path.exists(png_name):
        try:
            subprocess.check_output(['pdftoppm',
                                     '-f', str(page),
                                     '-l', str(page),
                                     '-png',
                                     pdf_path,
                                     png_name_root])
        except Exception as exc:
            logging.error(exc)

    ocr_result = ocr(png_name)

    return ocr_result


# 获取page页面图片上的文本
def parse_pdf_image(pdf_path, page):
    pdf_dir = os.path.dirname(pdf_path)
    pdf_file_name = os.path.basename(pdf_path).replace('.pdf', '')
    png_dir = os.path.join(pdf_dir, pdf_file_name)
    if not os.path.exists(png_dir):
        os.mkdir(png_dir)

    png_root = 'page' + ('%03d' % page)
    png_path_root = os.path.join(png_dir, png_root)

    txt_file = png_root + '.txt'
    txt_path = os.path.join(png_dir, txt_file)
    # 在此判断解析结果是否存在以及文件大小？
    if os.path.exists(txt_path) and os.path.getsize(txt_path) > 100:
        return read_text_file(txt_path)

    if os.path.exists(pdf_path):
        # 优先输出png
        if not os.path.exists(png_path_root + '-000.png'):
            try:
                subprocess.call(['pdfimages', '-f', str(page), '-l', str(page), '-png', pdf_path, png_path_root])
            except Exception as exc:
                logging.error('抽出png失败 page:%s %s' % (page, pdf_path))
                logging.error(exc)
            else:
                logging.debug('抽出png到文件 %s' % (png_path_root + 'pageXXX' + '.png'))

        # 有些pdf一个页面能够抽出一万多个图片
        # 这里只处理抽出图片数目小于100的
        too_many_file_path = os.path.join(png_dir, png_root + '-100.png')
        if os.path.exists(too_many_file_path):
            logging.info('skip %s' % too_many_file_path)
        else:
            # ocr api的file size限制为 4M
            # 400 Request payload size exceeds the limit: 10485760 bytes
            # 判断png file size
            # 如果超过 4M 就用jpg
            need_small_size = False
            for png_file_name in os.listdir(png_dir):
                png_path = os.path.join(png_dir, png_file_name)
                if png_file_name.startswith(png_root) and png_file_name.endswith('.png') and os.path.exists(png_path):
                    fsize = os.path.getsize(png_path)
                    # 文档里面说ocr支持10M 10485760
                    # 但是8M的图片识别不了啊
                    # 我换成4M 4194304
                    if fsize >= 4194304:
                        need_small_size = True
                        break

            if not need_small_size:
                # 安全解析png
                if not os.path.exists(txt_path) or os.path.getsize(txt_path) <= 10:
                    png_list = list()
                    for png_result in os.listdir(png_dir):
                        png_path = os.path.join(png_dir, png_result)
                        if png_result.startswith(png_root) and png_result.endswith('.png') and os.path.exists(png_path):
                            ocr_result = ocr(png_path)
                            # logging.info(png_path)
                            # logging.info(ocr_result)
                            png_list.extend(ocr_result)

                    output_text_file(png_list, txt_path)
                    return png_list
                else:
                    return read_text_file(txt_path)
            else:
                # 用jpg
                if not os.path.exists(png_path_root + '-000.jpg'):
                    try:
                        subprocess.call(['pdfimages', '-f', str(page), '-l', str(page), '-j', pdf_path, png_path_root])
                    except Exception as exc:
                        logging.error('抽出jpg失败 page:%s %s' % (page, pdf_path))
                        logging.error(exc)
                    else:
                        logging.debug('抽出jpg到文件 %s' % (png_path_root + 'pageXXX' + '.jpg'))

                # 有些pdf一个页面能够抽出一万多个图片
                # 这里只处理抽出图片数目是小于100的
                too_many_file_path = os.path.join(png_dir, png_root + '-100.jpg')
                if os.path.exists(too_many_file_path):
                    logging.info('skip %s' % too_many_file_path)
                else:
                    if not os.path.exists(txt_path) or os.path.getsize(txt_path) <= 1:
                        jpg_list = list()
                        for jpg_result in os.listdir(png_dir):
                            jpg_path = os.path.join(png_dir, jpg_result)
                            if jpg_result.startswith(png_root) and jpg_result.endswith('.jpg') and os.path.exists(
                                    jpg_path):
                                jpg_list.extend(ocr(jpg_path))

                        output_text_file(jpg_list, txt_path)
                        return jpg_list
                    else:
                        return read_text_file(txt_path)

    return list()


# 获取page页面上的文本
def parse_pdf_text(pdf_path, page):
    pdf_dir = os.path.dirname(pdf_path)
    pdf_file_name = os.path.basename(pdf_path).replace('.pdf', '')
    txt_dir = os.path.join(pdf_dir, pdf_file_name)
    if not os.path.exists(txt_dir):
        os.mkdir(txt_dir)

    txt_name = 'page' + ('%03d' % page) + '.txt'
    txt_path = os.path.join(txt_dir, txt_name)
    try:
        subprocess.call(['pdftotext', '-f', str(page), '-l', str(page), '-enc', 'UTF-8', pdf_path, txt_path])
    except Exception as exc:
        logging.error('提取文本失败 page:%s %s' % (page, pdf_path))
        logging.error(exc)
    else:
        logging.debug('提取文本成功 page:%s %s' % (page, txt_path))
    return read_text_file(txt_path)


# 读取文本文件
def read_text_file(txt_path):
    all_text = list()
    if os.path.exists(txt_path):
        with codecs.open(txt_path, 'r', 'utf-8') as txt_file:
            for line in txt_file:
                all_text.append(line)

    return all_text


# 写入文本文件
def output_text_file(all_text, output_txt):
    if os.path.exists(output_txt):
        os.remove(output_txt)

    with codecs.open(output_txt, 'w', 'utf-8') as txt_file:
        for line in all_text:
            if line != '\n':
                if not line.endswith('\n'):
                    line = line + '\n'
                txt_file.write(line)

    logging.info('最终结果写入 %s' % output_txt)


# 解析本地html文件
def convert_html_to_txt(html_path):
    result_list = list()
    output_txt = html_path.replace('.html', '.txt')
    if os.path.exists(html_path) and (not os.path.exists(output_txt) or os.path.getsize(output_txt) == 0):
        with open(html_path, 'r', encoding='utf-8') as html_file:
            html_content = html_file.read()
            soup = bs(html_content, 'lxml')
            for child in soup.find('p'):
                # if child.name == 'table':
                #     for tr in child.find_all('tr'):
                #         if tr.text != '\n':
                #             for td in tr.find_all('td'):
                #                 result_list.append(td.text.strip())
                # elif child.name == 'p':
                    # if child.img:
                    #     # ocr pic
                    #     # logging.info(child.img.get('src'))
                    #     html_dir = os.path.dirname(html_path)
                    # for img_tag in child.find_all('img'):
                    #     pic_name = img_tag.get('src')
                    #     pic_name = unquote(pic_name)
                    #
                    #     if pic_name.endswith('.png') or pic_name.endswith('.jpg'):
                    #         png_name = pic_name
                    #     elif pic_name.endswith('.gif'):
                    #         png_name = gif2png(html_dir, pic_name)
                    #     else:
                    #         logging.info('图片文件 %s' % pic_name)
                    #         png_name = pic_name
                    #
                    #     png_path = os.path.join(html_dir, png_name)
                    #     line_list = ocr(png_path)
                    #     result_list.extend(line_list)
                    if child.text and child.text.strip() != '':
                        result_list.append(child.text.strip())
            output_text_file(result_list, output_txt)

    return result_list


# ocr处理不了gif 先转为png
def gif2png(html_dir, gif_name):
    gif_path = os.path.join(html_dir, gif_name)
    png_name = gif_name.replace('.gif', '.png')
    png_path = os.path.join(html_dir, png_name)

    img = Image.open(gif_path)
    img.save(png_path, 'png', optimize=True, quality=70)
    return png_name


# 以下为测试用
def pdfs_cvrt():
    pdf_folder = os.path.join('announce', 'testpdf')
    for pdf_name in os.listdir(pdf_folder):
        if pdf_name.endswith('.pdf'):
            pdf_path = os.path.join(pdf_folder, pdf_name)
            convert_pdf_to_txt(pdf_path)


def et_cvrt():
    test_folder = os.path.join(PARENT_FOLDER, 'testet')
    for file_name in os.listdir(test_folder):
        file_path = os.path.join(test_folder, file_name)
        if file_name.endswith('.et'):
            xlsx_path = file_path.replace('.et', '.xlsx')
        elif file_name.endswith('.DS_Store'):
            continue
        else:
            logging.info('不需要转化的文件格式 %s' % file_name)
            continue

        # et to xlsx
        if not os.path.exists(xlsx_path):
            try:
                subprocess.call(['/Applications/LibreOffice.app/Contents/MacOS/soffice', '--headless', '--convert-to',
                                 'xlsx:Calc MS Excel 2007 XML', '--outdir', test_folder, file_path])
            except Exception as exc:
                logging.error('转xlsx失败 %s' % file_path)
                logging.error(exc)
            else:
                logging.error('转xlsx成功 %s' % file_path)


# doc/docx/rtf/wps 先用libre office转为html再解析
def doc_cvrt():
    test_folder = os.path.join(PARENT_FOLDER, 'testdoc')
    for file_name in os.listdir(test_folder):
        file_path = os.path.join(test_folder, file_name)
        # 保存html和png／jpg的临时目录
        out_dir = file_path[:file_path.rfind('.')]

        if file_name.endswith('.doc'):
            html_path = os.path.join(out_dir, file_name.replace('.doc', '.html'))
        elif file_name.endswith('.docx'):
            html_path = os.path.join(out_dir, file_name.replace('.docx', '.html'))
        elif file_name.endswith('.wps'):
            html_path = os.path.join(out_dir, file_name.replace('.wps', '.html'))
        elif file_name.endswith('.rtf'):
            html_path = os.path.join(out_dir, file_name.replace('.rtf', '.html'))
        elif file_name.endswith('.DS_Store'):
            continue
        else:
            logging.info('不需要转化的文件格式 %s' % file_name)
            continue

        # doc/docx/wps/rtf to html
        if not os.path.exists(html_path):
            # convert to html
            try:
                subprocess.call(['/Applications/LibreOffice.app/Contents/MacOS/soffice', '--headless', '--convert-to',
                                 'html:HTML:UTF8', '--outdir', test_folder, file_path])
            except Exception as exc:
                logging.error('转html失败 %s' % file_path)
                logging.error(exc)
            else:
                logging.error('转html成功 %s' % file_path)

        # html to text
        convert_html_to_txt(html_path)


# rar
def rar_cvrt():
    test_folder = os.path.join(PARENT_FOLDER, 'testrar')
    for file_name in os.listdir(test_folder):
        file_path = os.path.join(test_folder, file_name)
        if file_name.endswith('.rar'):
            extract_dir = file_path[:file_path.rfind('.')]
            if not os.path.exists(extract_dir):
                os.mkdir(extract_dir)
            patoolib.extract_archive(file_path, outdir=extract_dir)


# zip
def zip_cvrt():
    test_folder = os.path.join(PARENT_FOLDER, 'testzip')
    for file_name in os.listdir(test_folder):
        file_path = os.path.join(test_folder, file_name)
        if file_name.endswith('.zip'):
            extract_dir = file_path[:file_path.rfind('.')]
            if not os.path.exists(extract_dir):
                os.mkdir(extract_dir)
            un_zip(file_path, extract_dir)


def tif_cvrt():
    test_folder = os.path.join(PARENT_FOLDER, 'testrar', '2015-08-05_棒棰岛辅导第7期报告')
    for file_name in os.listdir(test_folder):
        file_path = os.path.join(test_folder, file_name)
        if file_name.endswith('.tif'):
            im = Image.open(file_path)
            for page, frame in enumerate(ImageSequence.Iterator(im), start=1):
                try:
                    temp_file = os.path.join(os.path.dirname(file_path),
                                             file_name.replace('.tif', '') + str(page) + '.png')
                    frame.thumbnail(frame.size)
                    frame.save(temp_file, optimize=True)
                except Exception as exc:
                    logging.error(exc)
                    logging.info(file_path)


def main():
    # 删除空文件
    # check_zero_file()

    # pdf_path = os.path.join(PARENT_FOLDER, '上海', 'pdf', '2017-08-18_兴业证券关于上海阿莱德实业股份有限公司辅导工作进展报告公示.pdf')
    # convert_pdf_to_txt(pdf_path)

    # 下面是测试ocr用
    # png_path = os.path.join('announce', 'test', '2014-04-02_摩根士丹利华鑫证券有限责任公司关于中节能太阳能科技股份有限公司首次公开发行股票并上市辅导基本情况表_page1-000.png')
    # ocr_with_google(png_path, '')
    # ocr_with_azure(png_path, '')
    # ocr_with_baidu(png_path, '')

    # 下面是测试文件格式转化用
    # pdfs_cvrt()
    # doc_cvrt()
    # zip_cvrt()
    # et_cvrt()
    # tif_cvrt()

    # 下面是测试rar解压并转化用
    # rar_dir = os.path.join('announce', 'testrar')
    # for rar_file in os.listdir(rar_dir):
    #     if rar_file.endswith('.rar'):
    #         rar_path = os.path.join(rar_dir, rar_file)
    #         convert_rar_to_txt(rar_path)

    # png_path = os.path.join('announce', 'testpdf',
    #                         '2014-04-02_摩根士丹利华鑫证券有限责任公司关于中节能太阳能科技股份有限公司首次公开发行股票并上市辅导基本情况表.pdf')
    # pdf_page_to_png(png_path, 1)
    png_path = os.path.join('announce_ipo_pre', '2014-04-18_安徽九华山旅游发展股份有限公司上交所上市预先披露.pdf')
    convert_pdf_to_txt_only(png_path)


if __name__ == '__main__':
    # file
    log_file_name = os.path.join('logs', 'utility_convert.log')
    logging.basicConfig(level=logging.INFO, format='%(message)s', filename=log_file_name, filemode='w')

    # console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    main()
