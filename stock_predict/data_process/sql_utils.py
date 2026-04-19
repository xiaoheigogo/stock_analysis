import pymysql
import pandas as pd

"""
mysql 数据库操作
"""


connection = pymysql.connect(host='localhost',
                             user='root',
                             password='admin',
                             database='stock_prediction',
                             charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor)

# 创建一个游标对象
cursor = connection.cursor()

def get_data_from_table(condition, table):
    sql = f"SELECT {condition} FROM {table}"
    cursor.execute(sql)
    data = pd.DataFrame(cursor.fetchall())
    return data

def update_data_to_table(condition, table):
    sql = f"UPDATE {table} SET {condition}"
    cursor.execute(sql)
    connection.commit()
    return print(f"数据已更新至{table}表")

def insert_data_to_table(sql):
    # sql = f"INSERT INTO {table} VALUES {condition}"
    cursor.execute(sql)
    connection.commit()
    return print(f"数据已插入表")

