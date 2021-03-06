# coding: utf-8
from __future__ import division
import datetime
import re
import json
import os
import ssl
from subprocess import getoutput
import sys
import uuid

import six
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager

from .log import log

if six.PY2:
    from io import open


class EntrustProp(object):
    Limit = 'limit'
    Market = 'market'


class Ssl3HttpAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(num_pools=connections,
                                       maxsize=maxsize,
                                       block=block,
                                       ssl_version=ssl.PROTOCOL_TLSv1)


def file2dict(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def get_stock_type(stock_code):
    """判断股票ID对应的证券市场
    匹配规则
    ['50', '51', '60', '90', '110'] 为 sh
    ['00', '13', '18', '15', '16', '18', '20', '30', '39', '115'] 为 sz
    ['5', '6', '9'] 开头的为 sh， 其余为 sz
    :param stock_code:股票ID, 若以 'sz', 'sh' 开头直接返回对应类型，否则使用内置规则判断
    :return 'sh' or 'sz'"""
    assert type(stock_code) is str, 'stock code need str type'
    if stock_code.startswith(('sh', 'sz')):
        return stock_code[:2]
    if stock_code.startswith(('50', '51', '60', '73', '90', '110', '113', '132', '204', '78')):
        return 'sh'
    if stock_code.startswith(('00', '13', '18', '15', '16', '18', '20', '30', '39', '115', '1318')):
        return 'sz'
    if stock_code.startswith(('5', '6', '9')):
        return 'sh'
    return 'sz'


def recognize_verify_code(image_path, broker='ht'):
    """识别验证码，返回识别后的字符串，使用 tesseract 实现
    :param image_path: 图片路径
    :param broker: 券商 ['ht', 'yjb', 'gf', 'yh']
    :return recognized: verify code string"""
    if broker == 'ht':
        return detect_ht_result(image_path)
    elif broker == 'yib':
        return detect_yjb_result(image_path)
    elif broker == 'gf':
        return detect_gf_result(image_path)
    elif broker == 'yh':
        return detect_yh_result(image_path)
    # 调用 tesseract 识别
    return default_verify_code_detect(image_path)


def detect_ht_result(image_path):
    code = detect_verify_code_by_java(image_path, 'ht')
    if not code:
        return default_verify_code_detect(image_path)
    return code


def detect_yjb_result(image_path):
    code = detect_verify_code_by_java(image_path, 'yjb')
    if not code:
        return default_verify_code_detect(image_path)
    return code


def detect_verify_code_by_java(image_path, broker):
    jars = {
        'ht': ('getcode_jdk1.5.jar', ''),
        'yjb': ('yjb_verify_code.jar', 'guojin')
    }
    verify_code_tool, param = jars[broker]
    # 检查 java 环境，若有则调用 jar 包处理 (感谢空中园的贡献)
    # noinspection PyGlobalUndefined
    global getoutput
    if six.PY2:
        if sys.platform == 'win32':
            from subprocess import PIPE, Popen, STDOUT

            def getoutput(cmd, input=None, cwd=None, env=None):
                pipe = Popen(cmd, shell=True, cwd=cwd, env=env, stdout=PIPE, stderr=STDOUT)
                (output, err_out) = pipe.communicate(input=input)
                return output.decode().rstrip('\r\n')
        else:
            import commands
            getoutput = commands.getoutput
    out_put = getoutput('java -version')
    log.debug('java detect result: %s' % out_put)
    if out_put.find('java version') != -1 or out_put.find('openjdk') != -1:
        tool_path = os.path.join(os.path.dirname(__file__), 'thirdlibrary', verify_code_tool)
        out_put = getoutput('java -jar "{}" {} {}'.format(tool_path, param, image_path))
        log.debug('recognize output: %s' % out_put)
        verify_code_start = -4
        return out_put[verify_code_start:]


def default_verify_code_detect(image_path):
    from PIL import Image
    import pytesseract
    img = Image.open(image_path)
    code = pytesseract.image_to_string(img)
    valid_chars = re.findall('[0-9a-z]', code, re.IGNORECASE)
    return ''.join(valid_chars)


def detect_gf_result(image_path):
    from PIL import ImageFilter, Image
    import pytesseract
    img = Image.open(image_path)
    if hasattr(img, "width"):
        width, height = img.width, img.height
    else:
        width, height = img.size
    for x in range(width):
        for y in range(height):
            if img.getpixel((x, y)) < (100, 100, 100):
                img.putpixel((x, y), (256, 256, 256))
    gray = img.convert('L')
    two = gray.point(lambda x: 0 if 68 < x < 90 else 256)
    min_res = two.filter(ImageFilter.MinFilter)
    med_res = min_res.filter(ImageFilter.MedianFilter)
    for _ in range(2):
        med_res = med_res.filter(ImageFilter.MedianFilter)
    res = pytesseract.image_to_string(med_res)
    return res.replace(' ', '')


def detect_yh_result(image_path):
    from PIL import Image
    import pytesseract

    img = Image.open(image_path)

    brightness = list()
    for x in range(img.width):
        for y in range(img.height):
            (r, g, b) = img.getpixel((x, y))
            brightness.append(r + g + b)
    avg_brightness = sum(brightness) // len(brightness)

    for x in range(img.width):
        for y in range(img.height):
            (r, g, b) = img.getpixel((x, y))
            if ((r + g + b) > avg_brightness / 1.5) or (y < 3) or (y > 17) or (x < 5) or (x > (img.width - 5)):
                img.putpixel((x, y), (256, 256, 256))

    res = pytesseract.image_to_string(img)
    return res


def get_mac():
    # 获取mac地址 link: http://stackoverflow.com/questions/28927958/python-get-mac-address
    return ("".join(c + "-" if i % 2 else c for i, c in enumerate(hex(
        uuid.getnode())[2:].zfill(12)))[:-1]).upper()


def grep_comma(num_str):
    return num_str.replace(',', '')


def str2num(num_str, convert_type='float'):
    num = float(grep_comma(num_str))
    return num if convert_type == 'float' else int(num)


def get_30_date():
    """
    获得用于查询的默认日期, 今天的日期, 以及30天前的日期
    用于查询的日期格式通常为 20160211
    :return:
    """
    now = datetime.datetime.now()
    end_date = now.date()
    start_date = end_date - datetime.timedelta(days=30)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
