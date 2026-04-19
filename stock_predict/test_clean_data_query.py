#!/usr/bin/env python3
"""
测试清洗后的数据查询
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db_conn import postgres
import pandas as pd

def test_clean_data_availability():
    """测试清洗后数据的可用性"""
    print("=" * 60)
    print("测试清洗后数据可用性")
    print("=" * 60)

    # 测试股票代码
    test_codes = ["000001", "000002"]

    for ts_code in test_codes:
        print(f"\n股票 {ts_code}:")

        # 查询清洗后的数据
        df = postgres.select_df(f"""
            SELECT
                COUNT(*) as total_count,
                COUNT(close_clean) as clean_count,
                MIN(trade_date) as min_date,
                MAX(trade_date) as max_date
            FROM daily_kline
            WHERE ts_code = '{ts_code}'
        """)

        print(f"  总记录数: {df['total_count'].iloc[0]}")
        print(f"  清洗记录数: {df['clean_count'].iloc[0]}")
        print(f"  日期范围: {df['min_date'].iloc[0]} 到 {df['max_date'].iloc[0]}")

        # 检查特征列是否存在
        feature_cols = [
            'open_clean', 'high_clean', 'low_clean', 'close_clean',
            'volumn_clean', 'amount_clean', 'amplitude_clean',
            'pct_change_clean', 'change_clean', 'turnover_clean',
            'ma5', 'ma10', 'macd_dif', 'rsi14',
            'month_sin', 'month_cos', 'day_sin', 'day_cos',
            'dow_sin', 'dow_cos'
        ]

        # 检查每列的非空值数量
        for col in feature_cols:
            result = postgres.select(f"""
                SELECT COUNT({col}) as non_null_count
                FROM daily_kline
                WHERE ts_code = '{ts_code}' AND {col} IS NOT NULL
            """, fetch_one=True)
            if result:
                count = result['non_null_count']
                if count > 0:
                    print(f"  {col}: {count} 个非空值")
                else:
                    print(f"  {col}: 无数据")

        # 获取一些样本数据
        sample = postgres.select_df(f"""
            SELECT trade_date, close_raw, close_clean, ma5, ma10, rsi14
            FROM daily_kline
            WHERE ts_code = '{ts_code}' AND close_clean IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 5
        """)

        print(f"\n  最近5条清洗后记录:")
        print(sample.to_string(index=False))

def check_data_consistency():
    """检查数据一致性"""
    print("\n" + "=" * 60)
    print("检查数据一致性")
    print("=" * 60)

    # 检查是否有股票既有 raw 数据又有 clean 数据
    result = postgres.select("""
        SELECT
            COUNT(DISTINCT ts_code) as total_stocks,
            COUNT(DISTINCT CASE WHEN close_raw IS NOT NULL THEN ts_code END) as raw_stocks,
            COUNT(DISTINCT CASE WHEN close_clean IS NOT NULL THEN ts_code END) as clean_stocks,
            COUNT(DISTINCT CASE WHEN close_raw IS NOT NULL AND close_clean IS NOT NULL THEN ts_code END) as both_stocks
        FROM daily_kline
    """, fetch_one=True)

    if result:
        print(f"总股票数: {result['total_stocks']}")
        print(f"有 raw 数据的股票数: {result['raw_stocks']}")
        print(f"有 clean 数据的股票数: {result['clean_stocks']}")
        print(f"同时有 raw 和 clean 数据的股票数: {result['both_stocks']}")

def main():
    test_clean_data_availability()
    check_data_consistency()

    print("\n" + "=" * 60)
    print("清洗后数据测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()