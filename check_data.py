#!/usr/bin/env python3
"""
检查数据库数据状态
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db_conn import postgres
import pandas as pd

def check_trade_date_table():
    """检查交易日历表"""
    print("=" * 60)
    print("检查 trade_date 表")
    print("=" * 60)

    try:
        # 检查记录数量
        count_result = postgres.select("SELECT COUNT(*) FROM trade_date", fetch_one=True)
        count = count_result['count'] if count_result else 0
        print(f"trade_date 表记录数: {count}")

        # 检查日期范围
        date_range = postgres.select("SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date FROM trade_date", fetch_one=True)
        if date_range:
            print(f"日期范围: {date_range['min_date']} 到 {date_range['max_date']}")

        # 显示前5个和后5个日期
        dates = postgres.select("SELECT trade_date FROM trade_date ORDER BY trade_date LIMIT 5")
        print("前5个交易日:")
        for d in dates:
            print(f"  {d['trade_date']}")

        dates = postgres.select("SELECT trade_date FROM trade_date ORDER BY trade_date DESC LIMIT 5")
        print("后5个交易日:")
        for d in dates:
            print(f"  {d['trade_date']}")

    except Exception as e:
        print(f"查询 trade_date 表失败: {e}")
        import traceback
        traceback.print_exc()

def check_daily_kline_clean_status():
    """检查 daily_kline 表的清洗状态"""
    print("\n" + "=" * 60)
    print("检查 daily_kline 表清洗状态")
    print("=" * 60)

    try:
        # 检查有多少记录有 raw 数据但没有 clean 数据
        dirty_result = postgres.select("""
            SELECT COUNT(*)
            FROM daily_kline
            WHERE close_raw IS NOT NULL AND close_clean IS NULL
        """, fetch_one=True)
        dirty_count = dirty_result['count'] if dirty_result else 0

        total_result = postgres.select("SELECT COUNT(*) FROM daily_kline", fetch_one=True)
        total_count = total_result['count'] if total_result else 0

        clean_result = postgres.select("""
            SELECT COUNT(*)
            FROM daily_kline
            WHERE close_clean IS NOT NULL
        """, fetch_one=True)
        clean_count = clean_result['count'] if clean_result else 0

        print(f"总记录数: {total_count}")
        print(f"已清洗记录数: {clean_count}")
        print(f"待清洗记录数: {dirty_count}")

        # 按股票统计
        stock_stats = postgres.select_df("""
            SELECT ts_code,
                   COUNT(*) as total,
                   SUM(CASE WHEN close_clean IS NOT NULL THEN 1 ELSE 0 END) as cleaned,
                   SUM(CASE WHEN close_clean IS NULL AND close_raw IS NOT NULL THEN 1 ELSE 0 END) as dirty,
                   MIN(trade_date) as min_date,
                   MAX(trade_date) as max_date
            FROM daily_kline
            GROUP BY ts_code
            ORDER BY ts_code
            LIMIT 10
        """)

        print("\n前10支股票清洗状态:")
        print(stock_stats.to_string())

    except Exception as e:
        print(f"查询清洗状态失败: {e}")
        import traceback
        traceback.print_exc()

def check_stock_list():
    """检查股票列表"""
    print("\n" + "=" * 60)
    print("检查 stock_list 表")
    print("=" * 60)

    try:
        count_result = postgres.select("SELECT COUNT(*) FROM stock_list", fetch_one=True)
        count = count_result['count'] if count_result else 0
        print(f"股票数量: {count}")

        # 检查是否有上市日期
        null_result = postgres.select("SELECT COUNT(*) FROM stock_list WHERE list_date IS NULL", fetch_one=True)
        null_list_date = null_result['count'] if null_result else 0
        print(f"缺失上市日期的股票数量: {null_list_date}")

        # 显示一些样本
        samples = postgres.select_df("""
            SELECT ts_code, ts_name, list_date, industry, is_hs300
            FROM stock_list
            ORDER BY ts_code
            LIMIT 5
        """)
        print("\n样本股票:")
        print(samples.to_string())

    except Exception as e:
        print(f"查询 stock_list 表失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("股票预测系统数据状态检查")
    print("=" * 60)

    check_trade_date_table()
    check_daily_kline_clean_status()
    check_stock_list()

    print("\n" + "=" * 60)
    print("数据状态检查完成")
    print("=" * 60)

if __name__ == "__main__":
    main()