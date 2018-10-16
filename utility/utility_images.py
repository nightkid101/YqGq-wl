import os
import csv
import logging
from PIL import Image


def contains_space(row):
    return '' in row


def read_csv(csv_path):
    org_csv = list()
    col_0 = list()
    col_1 = list()
    col_2 = list()
    with open(csv_path, newline='') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in spamreader:
            if '第一部分' in ''.join(row):
                continue
            elif '第二部分' in ''.join(row):
                break
            else:
                org_csv.append(row)
                col_0.append(row[0])
                col_1.append(row[1])
                col_2.append(row[2])

    # 第一个循环 把内容完整的提出来 有
    end_index = -1
    for i in range(len(org_csv)):
        if i > end_index:
            if not contains_space(org_csv[i]):
                logging.info('-'.join(org_csv[i]))
                continue
            for j in range(i + 1, len(org_csv)):
                if not contains_space(org_csv[j]):
                    end_index = j - 1
                    logging.info('%s ~ %s' % (i, end_index))
                    logging.info(''.join(col_0[i: end_index+1]))
                    logging.info(''.join(col_1[i: end_index+1]))
                    logging.info(''.join(col_2[i: end_index+1]))
                    break
            else:
                # till end
                logging.info(''.join(col_0[i: ]))
                logging.info(''.join(col_1[i: ]))
                logging.info(''.join(col_2[i: ]))
                break


# 把png_dir下的所有png都合并成一个 传给其他工具转化
def merge_pngs(png_dir):
    try:
        png_list = list()
        widths = list()
        heights = list()

        results = os.listdir(png_dir)
        results.sort()
        for png_name in results:
            if png_name.endswith('.png'):
                image = Image.open(os.path.join(png_dir, png_name))
                png_list.append(image)
                widths.append(image.size[0])
                heights.append(image.size[1])

        max_width = max(widths)
        total_height = sum(heights)

        new_im = Image.new('RGB', (max_width, total_height))

        y_offset = 0
        for im in png_list:
            new_im.paste(im, (0, y_offset))
            y_offset += im.size[1]

        new_im.save(png_dir + '/test.png')
    except Exception as exc:
        logging.error(exc)


def main():
    merge_pngs('png_dir')


if __name__ == '__main__':
    # file
    log_file_name = os.path.join('logs', 'announce_02_ipo_pre_parse_02_finance.log')
    logging.basicConfig(level=logging.INFO, format='%(message)s', filename=log_file_name, filemode='w')

    # console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    main()