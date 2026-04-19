# !/usr/bin/python3
# -*- coding:utf-8 -*-
# @Author: 小黑
# @Time: 2024/11/16 15:07
# @File: __init__.py.py


"""
get_data.py 用于获取各类金融数据，并返回，保存至本地数据库中
    get_market_data():
        获取市场行情数据，调用相关库的接口即可
    get_stock_data():
        获取个股交易数据，指定个股的编号，获取指定日期范围的数据
    get_stock_trend():
        获取个股指定日期的交易情况，有代码、日期、收盘价、换手率等数据
    get_index_data():
        获取指数的每日行情
    TODO:
        get_xxx_data():
            获取xxx数据，待定
wash_data.py 用于数据清洗、处理、归一化
    serlization_data():
        序列化数据，不一定需要
    data_normalization():
        同一类数据归一化处理
    data_unnormalization():
        同一类数据反归一化处理


"""