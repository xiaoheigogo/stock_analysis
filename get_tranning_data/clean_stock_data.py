# !/usr/bin/python3
# -*- coding:utf-8 -*-
# @Author: 小黑
# @Time: 2024/12/8 14:56
# @File: clean_stock_data.py

"""
将原始的个股数据，整理为可以用于训练的数据
"""


# 读取数据库，指定表名的数据
from sqlalchemy import create_engine
username = 'root'
password = 'admin'
host = 'localhost'
database = 'stock_prediction'
original_table_name = "002230"  # 原始stock表名
new_table_name = "clean_"+original_table_name
print(new_table_name)
# 创建数据库引擎
engine = create_engine(f'mysql+pymysql://{username}:{password}@{host}/{database}')
from sqlalchemy.exc import IntegrityError

# 将数据重新整理，归一化


# 将归一化后的数据写入数据库