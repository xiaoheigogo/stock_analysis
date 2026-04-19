# !/usr/bin/python3
# -*- coding:utf-8 -*-
# @Author: 小黑
# @Time: 2024/11/16 20:58
# @File: get_exchange_data_stock.py
"""
获取股票交易数据
"""

import akshare as ak
import pymysql



get_roll_yield_bar_df = ak.get_roll_yield_bar(type_method="date", var="RB", start_day="20241110", end_day="20241116")
print(get_roll_yield_bar_df)
"""#
# print(type(get_roll_yield_bar_df))

# 将 DataFrame 导出到 Excel 文件，不包括索引列
df = get_roll_yield_bar_df
# df.to_excel('output.xlsx', index=True)

# 如果需要按多列排序，首先对 DataFrame 进行排序
# sorted_df = df.sort_values(by=['roll_yield', 'near_by'], ascending=[True, False])
# 然后导出排序后的 DataFrame
# sorted_df.to_excel('sorted_output.xlsx', index=True)

import mysql.connector
db_config = {
    'user': 'root',
    'password': 'admin',
    'port': '3306',
    'host': '127.0.0.1',
    'database': 'stock_prediction',
    'raise_on_warnings': True
}
print("已配置数据库。。。")
# 建立数据库连接

# connection = pymysql.connect(host='localhost',
#                              user='root',
#                              password='admin',
#                              database='stock_prediction',
#                              charset='utf8mb4',
#                              cursorclass=pymysql.cursors.DictCursor)
# # cnx = mysql.connector.connect(**db_config)
# # print("已创建数据库连接。。。")
# # 创建一个游标对象
# cursor = connection.cursor()

# 执行查询
# query = "SELECT * FROM stock_market"
# cursor.execute(query)
# # 获取查询结果
# results = cursor.fetchall()
# # print("已获取到数据\n", results)
# for row in results:
#     print(row)


update_sql = f"INSERT stock_market SET stock_type = '2'"
# cursor.execute(update_sql)
# connection.commit()

import sql_func
# import mysql_func.sql_func

data = sql_func.get_data_from_table("*", "stock_market")
print("数据已返回\n", data)
print(type(data))
# for i in data:
#     print(i)

# sql_func.insert_data_to_table(f"insert into stock_market (close_price) values (62)")

# 关闭游标和连接
# cursor.close()
# connection.close()

from sqlalchemy import create_engine

# 数据库配置信息
username = 'root'
password = 'admin'
host = '127.0.0.1'
database = 'stock_prediction'

# 创建数据库引擎
engine = create_engine(f'mysql+pymysql://{username}:{password}@{host}/{database}')
df.rename(columns={'roll_yield':'open_price', 'near_by':'stock_type', 'deferred':'stock_name'}, inplace=True)
df.to_sql('stock_market', con=engine, if_exists='append', index=False)
print("write database done...")"""

"""
以上内容，可以读取ak库，并返回pd格式，并写入本地database
"""


# hk_stock_code = ak.stock_zh_ah_name()  # 港指、港股通
# print("stock_code\n", hk_stock_code)
# print("stock_code\n", type(hk_stock_code))

import requests, py_mini_racer
import pandas as pd


# print("stock_history_df\n", stock_history_df)
# print("stock_history_df\n", type(stock_history_df))

# stock_list = ak.stock_zh_a_spot_em()  # 返回股票列表，代码、名称、最新的价格等。缺少行业信息
# print("stock_list\n", stock_list)

# stock_list = ["000001", "399001", "002230"]
stock_list = ["002230"]
print(f"stock_list:{stock_list}")
# stock_name = "000001"
# stock_scyy = ak.stock_zh_a_hist(stock_name, start_date="20241001", end_date="20241201")  # 获取个股全部历史K线数据
from sqlalchemy import create_engine

username = 'root'
password = 'admin'
host = 'localhost'
database = 'stock_prediction'

for stock_name in stock_list:
    stock_scyy = ak.stock_zh_a_hist(stock_name)  # 获取个股全部历史K线数据
    print("stock_scyy", stock_scyy)

    # 创建数据库引擎
    engine = create_engine(f'mysql+pymysql://{username}:{password}@{host}/{database}')
    from sqlalchemy.exc import IntegrityError

    # # 表名
    # table_name = stock_name
    # # 将DataFrame写入数据库，如果表不存在则创建，如果存在则追加
    # try:
    #     stock_scyy.to_sql(table_name, con=engine, if_exists='append', index=False)
    #     print(f"已写入数据库{table_name}")
    # except IntegrityError as e:
    #     print(f"Error: {e}")
    #     # 处理重复数据的情况，这里可以根据需要进行自定义处理
    #     # 例如，可以删除重复的数据或更新现有数据
