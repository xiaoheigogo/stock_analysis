# !/usr/bin/python3
# -*- coding:utf-8 -*-
# @Author: 小黑
# @Time: 2025/9/30 17:07
# @File: test.py

from utils.logger import logger
from utils.db_conn import *
import pandas as pd
import os


import akshare as ak
# df = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20250915", end_date="20250930")
# print(df.head()) 

# from utils.db_conn import *
# 1. 代理地址去掉空格！
# os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7890'
# os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

# 2. 必须在第一次调 ak 之前覆盖 headers
# ak._HTTP_HEADERS = {
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
# }

def max_date_in_db(table_name, ts_code):
    sql = f"SELECT MAX(trade_date) FROM {table_name} WHERE ts_code='{ts_code}'"
    row = postgres.select(sql=sql)
    if len(row):
        return row[0]['max'].strftime("%Y%m%d")
    else:
        return None

# 3. 测试
# df = ak.stock_zh_a_hist('000021', start_date='20241001', end_date='20251007')
# print(df)   # 能打印出形状即代理生效

start = max_date_in_db("daily_kline", "000001")
print(f"start: {start}")
logger.info("Done")

