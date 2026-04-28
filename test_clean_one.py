#!/usr/bin/env python3
"""
测试清洗单只股票（修复is_st问题后）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_process.clean_normalize import clean_one_stock
from utils.db_conn import postgres
from utils.logger import logger
import pandas as pd
from datetime import date

def test_clean_single(ts_code='000004'):
    """测试清洗单只股票"""
    print("=" * 60)
    print(f"测试清洗股票 {ts_code}")
    print("=" * 60)

    try:
        # 获取该股票的最早日期
        first_date_result = postgres.select_df(
            "SELECT trade_date FROM daily_kline WHERE ts_code = %s ORDER BY trade_date",
            [ts_code]
        )

        if first_date_result.empty:
            print(f"股票 {ts_code} 没有数据")
            return

        first_date = first_date_result['trade_date'].iloc[0]
        print(f"最早交易日期: {first_date}")

        # 运行清洗
        train_end = date(2024, 12, 31)
        clean_df = clean_one_stock(ts_code, first_date, train_end)

        if clean_df is not None:
            print(f"清洗完成，处理了 {len(clean_df)} 条记录")
            # 检查清洗后的数据
            check_result = postgres.select_df(
                "SELECT COUNT(*) as cleaned_count FROM daily_kline WHERE ts_code = %s AND close_clean IS NOT NULL",
                [ts_code]
            )
            cleaned_count = check_result['cleaned_count'].iloc[0]
            print(f"股票 {ts_code} 已清洗记录数: {cleaned_count}")
        else:
            print(f"股票 {ts_code} 清洗失败")

    except Exception as e:
        print(f"处理股票 {ts_code} 时出错: {e}")
        import traceback
        traceback.print_exc()

def main():
    test_clean_single('000004')

if __name__ == "__main__":
    main()