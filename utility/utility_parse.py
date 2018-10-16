# 解析文本用的一些通用方法

import re
import os
import csv
import codecs
import logging
import subprocess


# 去除行中的无效字符
def strip_file_line(line):
    # line = line.strip().strip('"').lstrip('(').lstrip('|')
    # line = line.replace('-', '').replace('—', '')
    line = line.replace('—', '')
    line = line.replace('\x03', '').replace('\xa0', '').replace(' ', '')
    line = line.strip().strip('\n')
    return line


# 读当前页
# 用于信息不会跨页的情况
def read_one_txt(txt_path):
    txt1_all_line = list()
    # text 1
    if os.path.exists(txt_path):
        with codecs.open(txt_path, 'r', 'utf-8') as txt_file:
            for line in txt_file:
                stripped_line = strip_file_line(line)
                if stripped_line == '':
                    # 去掉空行
                    continue
                else:
                    txt1_all_line.append(stripped_line)
    # 去除页眉 页脚
    txt1_all_line = skip_header_footer(txt_path, txt1_all_line)

    return txt1_all_line


# 去除页眉 页脚
def skip_header_footer(txt_path, all_line):
    if len(all_line) > 0:
        # 页眉
        header_line = all_line[0]
        remove_header = False
        if '招股说明书' in header_line or '上市公告书' in header_line or \
            '招股意向书' in header_line or '首次公开发行股票' in header_line:
            remove_header = True
        # 如有公司名称 去掉第一行
        elif '公司' in txt_path:
            company_name = txt_path[txt_path.rfind('_') + 1:txt_path.rfind('公司') + 2]
            if company_name in header_line:
                remove_header = True

        if remove_header:
            all_line = all_line[1:]

    if len(all_line) > 0:
        # 页脚
        footer_line = all_line[-1]
        remove_footer = False
        if re.search('\d{1}\-+\d{1}\-+\d+', footer_line):
            remove_footer = True
        if re.search('\d{1}\－\d{1}\－\d+', footer_line):
            remove_footer = True
        elif footer_line.isnumeric() and len(footer_line) <=3:
            # 去掉页码 但是要避开邮政编码等
            remove_footer = True

        if remove_footer:
            all_line = all_line[:-1]

    return all_line


# 读取当前页和下一页
# 信息可能会有跨两页
def read_two_txt(txt_path):
    # text 1
    txt1_all_line = read_one_txt(txt_path)

    # text 2
    txt2_all_line = list()
    name_root_search = re.search('page(\d+)\.txt', txt_path)
    if name_root_search:
        name_root_str = name_root_search.group(1)
        name_root_int = int(name_root_str)
        txt2_path = re.sub('page(\d+)\.txt', 'page%03d.txt' % (name_root_int + 1), txt_path)
        txt2_all_line = read_one_txt(txt2_path)

    # merge
    txt1_all_line.extend(txt2_all_line)
    return txt1_all_line


# 读取n个连续的txt
def read_n_txt(txt_path, n):
    # text 1
    txt1_all_line = read_one_txt(txt_path)

    # text 2:n
    name_root_search = re.search('page(\d+)\.txt', txt_path)
    if name_root_search:
        for delta in range(1, n):
            name_root_str = name_root_search.group(1)
            name_root_int = int(name_root_str)
            txt2_path = re.sub('page(\d+)\.txt', 'page%03d.txt' % (name_root_int + delta), txt_path)
            txt2_all_line = read_one_txt(txt2_path)
            # merge
            txt1_all_line.extend(txt2_all_line)

    return txt1_all_line


# 列表中有一个长度为1的元素
def has_length_one_str(original_list):
    for item in original_list:
        if len(item) == 1 and item != '[':
            return True
    return False


# 把单独的冒号合并到key后面
def merge_colon(target_range):
    if '：' in target_range:
        length = len(target_range)
        new_target_range = list()
        is_colon = False
        for idx in range(length-1, -1, -1):
            current = target_range[idx]
            if current == '：':
                is_colon = True
                continue
            if is_colon:
                new_target_range.insert(0, current + '：')
                is_colon = False
            else:
                new_target_range.insert(0, current)
        target_range = new_target_range
    return target_range


# 合并key被拆分到前后的情况
def merge_continues(target_range):
    new_target_range = list()
    length = len(target_range)

    if length > 2:
        skip_next = False
        next = ''
        for idx in range(0, length-1):
            current = target_range[idx]
            next = target_range[idx+1]
            if skip_next:
                skip_next = False
                continue
            elif current.endswith('名') and next.startswith('称'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('住') and next.startswith('所'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('地') and next.startswith('址'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('传') and next.startswith('真'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('电') and next.startswith('话'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('联') and next.startswith('系电话'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('联') and next.startswith('系人'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('负') and next.startswith('责人'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('户') and next.startswith('名'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('账') and next.startswith('号'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('帐') and next.startswith('号'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('邮') and next.startswith('编'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('签字') and next.startswith('律师'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('经办') and next.startswith('律师'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('经') and next.startswith('办律师'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('经办注册资产评估') and next.startswith('师'):
                new_target_range.append(current + next)
                skip_next = True
            elif current.endswith('经办注册土地评估') and next.startswith('师'):
                new_target_range.append(current + next)
                skip_next = True
            else:
                new_target_range.append(current)
        if not skip_next:
            new_target_range.append(next)
        target_range = new_target_range

    return target_range


# 把一个长度为1的元素合并到应该去的名称里面
def merge_target(target_range):
    # 把单独的冒号合并到key后面
    target_range = merge_colon(target_range)

    # 合并key名称中单个词语
    new_target_range = list()
    length = len(target_range)

    insert_next = False
    for idx in range(length-1, 0, -1):
        current = target_range[idx]
        if current in ['帐', '账', '传', '电', '名', '住', '地', '负', '责', '联', '系', '办', '经', '整体变更为股份有限']:
            continue
        elif current.startswith('号') and '帐' in target_range[:idx-1]:
            # 帐(*)号 中间夹着真实的帐号
            new_target_range.insert(0, '帐' + current)
            insert_next = True
        elif current.startswith('号') and '账' in target_range[:idx-1]:
            # 账(*)号 中间夹着真实的帐号
            new_target_range.insert(0, '账' + current)
            insert_next = True
        elif current.startswith('号') and '账' in target_range[idx-1]:
            # 账号
            new_target_range.insert(0, '账' + current)
        elif current.startswith('真') and '传' in target_range[idx-1]:
            # 传真
            new_target_range.insert(0, '传' + current)
        elif current.startswith('真') and '传' in target_range[:idx-1]:
            # 传(*)真 中间夹着真实的电话
            new_target_range.insert(0, '传' + current)
            insert_next = True
        elif current.startswith('话') and '电' == target_range[idx-1]:
            # 电话
            new_target_range.insert(0, '电' + current)
        elif current.startswith('话') and '电' in target_range[:idx-1]:
            # 电(*)话 中间夹着真实的电话
            new_target_range.insert(0, '电' + current)
            insert_next = True
        elif current.startswith('址') and '地' == target_range[idx-1]:
            # 地址
            new_target_range.insert(0, '地' + current)
        elif current.startswith('址') and '地' == target_range[idx-2]:
            # 地(*)址 中间夹着真实的地址
            new_target_range.insert(0, '地' + current)
            insert_next = True
        elif current.startswith('址') and '地' in target_range[:idx-2]:
            # 地(*)(*)址 中间夹着其他内容
            new_target_range.insert(0, '地' + current)
        elif current.startswith('所') and '住' == target_range[idx-1]:
            # 住所
            new_target_range.insert(0, '住' + current)
        elif current.startswith('所') and '住' == target_range[idx-2]:
            # 住(*)所 中间夹着真实的住所
            new_target_range.insert(0, '住' + current)
            insert_next = True
        elif current.startswith('所') and '住' in target_range[:idx-2]:
            # 住(*)(*)所 中间夹着其他内容
            new_target_range.insert(0, '住' + current)
        elif current.startswith('人') and '责' in target_range and '负' in target_range:
            # 负责人
            if '联' in target_range:
                if abs(target_range.index('负') - idx) < abs(target_range.index('联') - idx):
                    new_target_range.insert(0, '负责' + current)
                else:
                    # 联系人
                    new_target_range.insert(0, '联系' + current)
            else:
                new_target_range.insert(0, '负责' + current)
        elif current.startswith('人') and '联' in target_range and '系' in target_range:
            # 联系人
            if '负' in target_range:
                if abs(target_range.index('负') - idx) > abs(target_range.index('联') - idx):
                    new_target_range.insert(0, '联系' + current)
                else:
                    # 负责人
                    new_target_range.insert(0, '负责' + current)
            else:
                new_target_range.insert(0, '联系' + current)
        elif current.startswith('人') and '经' in target_range and '办' in target_range:
            new_target_range.insert(0, '经办' + current)
        elif current.startswith('称') and '名' in target_range[:idx]:
            # 名称
            new_target_range.insert(0, '名' + current)
        elif current == '公司日期' and target_range[idx-1] == '整体变更为股份有限':
            # 整体变更为股份有限公司日期
            new_target_range.insert(0, '整体变更为股份有限公司日期')
        else:
            if insert_next:
                new_target_range.insert(1, target_range[idx])
                insert_next = False
            else:
                new_target_range.insert(0, target_range[idx])
    new_target_range.insert(0, target_range[0])
    return new_target_range


# 把一个长度为1的元素合并到应该去的名称里面
# 收款银行专用
def merge_target_cash_bank(target_range):
    # 把单独的冒号合并到key后面
    target_range = merge_colon(target_range)

    # 合并key名称中单个词语
    new_target_range = list()
    length = len(target_range)
    skip_before = False
    for idx in range(length-1, 0, -1):
        current = target_range[idx]
        if skip_before:
            if '户' == target_range[idx] and '开' == target_range[idx - 1]:
                skip_before = True
            else:
                skip_before = False
            continue
        elif current.startswith('名') and '户' in target_range[idx-1]:
            # 户名
            new_target_range.insert(0, '户' + current)
            skip_before = True
        elif current.startswith('户') and '账' in target_range[idx-1]:
            # 账户
            new_target_range.insert(0, '账' + current)
            skip_before = True
        elif current.startswith('号') and '账' in target_range[idx-1]:
            # 账号
            new_target_range.insert(0, '账' + current)
            skip_before = True
        elif current.startswith('行') and '户' == target_range[idx-1] and '开' == target_range[idx-2]:
            # 开|户|行
            new_target_range.insert(0, '开户' + current)
            skip_before = True
        else:
            new_target_range.insert(0, target_range[idx])

    new_target_range.insert(0, target_range[0])
    return new_target_range


# 提取pdf中指定页码范围的页面 同时去除拷贝密码
def pdf_slice(src_pdf, start_page, end_page, dst_pdf):
    if start_page == end_page:
        page_range_str = '%d' % start_page
    elif start_page < end_page:
        page_range_str = '%d-%d' % (start_page, end_page)
    else:
        logging.error('开始页码[%d]不可以大于结束页码[%d] 中止提取' % (start_page, end_page))
        return

    # 调用qpdf去除密码 缩小范围
    if not os.path.exists(dst_pdf):
        try:
            subprocess.check_output(['qpdf',
                                     '--decrypt',
                                     src_pdf,
                                     '--pages', src_pdf, page_range_str, '--',
                                     dst_pdf])
        except Exception as exc:
            logging.error('提取页面范围失败')
            logging.error(exc)


# 调用abbyy提取表格到xlsx
# 注意这个不能指定页码
def pdf_to_xlsx(src_pdf, dst_xlsx):
    if not os.path.exists(dst_xlsx):
        try:
            subprocess.check_output(['CommandLineInterface',
                                     '-rl', 'ChinesePRC+English',
                                     '-if', src_pdf,
                                     '-f', 'XLSX', '-xlto', '-xlks'
                                     '-of', dst_xlsx])
        except Exception as exc:
            logging.error('提取xlsx失败')
            logging.error(exc)


def parse_name_in_title(title):
    company_title = ''
    post_date_str = ''
    anc_subcate = ''

    # 标题中的上市公司名称
    company_search_1 = re.search('(.*?)公司', title)
    if company_search_1:
        company_title = company_search_1.group(1) + '公司'
        logging.info('上市公司名称 %s' % company_title)

    # 标题中的报送日期
    post_date_search_1 = re.search('\d+年\d+月\d+日', title)
    if post_date_search_1:
        post_date_str = post_date_search_1.group()
    logging.info('日期 %s' % post_date_str)

    if '预先披露更新' in title:
        anc_subcate = '初次预披露后多次披露'
    elif '预先披露' in title or '首次公开发行股票招股说明书' in title or '首次公开发行股票并在创业板上市招股说明书' in title:
        anc_subcate = '初次预披露'
    else:
        logging.info('不知道是什么子分类 %s' % title)
    logging.info('子分类 %s' % anc_subcate)

    return company_title, post_date_str, anc_subcate


# key-value顺序固定 但是key或者value中可能有换行
def parse_detail_list(text_list, regex_dict):
    key_names = regex_dict.keys()
    keys = list()
    values = list()

    for text in text_list:
        matched = False
        for section_name, section_regex in regex_dict.items():
            search = re.search(section_regex, text)
            # 匹配到了某个结果
            if search:
                matched = True
                if search.group(3) != '':
                    # 有key 也有value
                    keys.append(section_name)
                    values.append(search.group(3))
                else:
                    # 有key 没有value
                    keys.append(section_name)
                # 跳出内层for
                break
        # end for

        # 是value或者是value的一部分
        # if not matched:
        #     values.append(text)

    return keys, values


def main():
    # 保荐机构
    text_list = '保荐人（主承销商）：招商证券股份有限公司|法定代表人：宫少林|住|深圳市福田区益田路江苏大厦A座38-45楼|所：|联系电话：0755-82943666|传真：0755-82943121|项目负责人：朱权炼|保荐代表人：陈里强、涂军涛|项目协办人：李少杰|项目经办人：肖雁、张健、赖旸希、杨华伟|（二）'.split('|')
    regex_dict = {
        'section': '([^副]主承销商）|[^副]主承销商|保荐人（承销商）|保荐人（主承销商）|保荐人\(主承销商\)|保荐人|保荐机构)(：|:)?(.*)',
        'name': '(^名称|、名称|中文名称|公司名称)(：|:)?(.*)',
        'leader': '(法定代表人)(：|:)?(.*)',
        'reg_addr': '(住所|注册地址|^地址)(：|:)?(.*)',
        'ofs_addr': '(联系地址|办公地址|通讯地址)(：|:)?(.*)',
        'tel': '(联系电话|电话号码|电话)(：|:)?(.*)',
        'fax': '(联系传真|传真号码|传真)(：|:)?(.*)',
        'representor': '(保荐代表人)(：|:)?(.*)',
        'cooperator': '(项目协办人)(：|:)?(.*)',
        'member': '(项目组成员|项目组人员|项目人员|项目承办人|经办人员|经办人|联系人|其他成员|其他人员|其他项目人员|其他项目成员|项目组其它成员)(：|:)?(.*)',
    }


    # 会计师事务所
    # text_list = '审计机构：|执行事务合伙人：|住所：|经办会计师：|联系电话：|传真：|天健会计师事务所（特殊普通合伙）|胡少先|杭州市西溪路128号新湖商务大厦9楼|杨克晶、禤文欣|020-37600380|020-37606120|（五）'.split('|')
    # regex_dict = {
    #     'section': '(发行人审计机构|发行人会计师|会计师事务所及验资机构|审计机构\/验资机构|审计机构、验资机构|会计师事务所|审计机构|验资机构|验资复核机构|发行人会计师)(：|:)?(.*)',
    #     'name': '(^名称|、名称|中文名称|公司名称)(：|:)?(.*)',
    #     'leader': '(法定代表人|执行事务合伙人|执业事务合伙人|执行合伙人|首席合伙人|单位负责人|会计师事务所负责人|负责人)(：|:)?(.*)',
    #     'reg_addr': '(住所|注册地址|^地址|主要经营场所)(：|:)?(.*)',
    #     'ofs_addr': '(联系地址|办公地址)(：|:)?(.*)',
    #     'tel': '(联系电话|电话号码|电话)(：|:)?(.*)',
    #     'fax': '(联系传真|传真号码|传真)(：|:)?(.*)',
    #     'accountant': '(经办注册会计师|经办会计师|签字会计师|签字注册会计师|经办人员|经办人|联系人)(：|:)?(.*)',
    # }

    keys, values = parse_detail_list(text_list, regex_dict)
    logging.info('|'.join(keys))
    logging.info('|'.join(values))
    # for key, value in zip(keys, values):
    #     logging.info('%s : %s' % (key, value))


if __name__ == '__main__':
    # file
    log_file_name = os.path.join('logs', 'utility_parse.log')
    logging.basicConfig(level=logging.INFO, format='%(message)s', filename=log_file_name, filemode='w')

    # console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    main()