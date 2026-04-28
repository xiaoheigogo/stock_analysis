#!/usr/bin/env python3
"""
批量清洗股票数据（前N只股票）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_process.clean_normalize import clean_one_stock, find_dirty_stocks
from utils.db_conn import postgres
from utils.logger import logger
import pandas as pd
from datetime import date
import time

def clean_batch_stocks(num_stocks=10, train_end_date=None):
    """清洗前N只需要清洗的股票"""
    if train_end_date is None:
        train_end_date = date(2024, 12, 31)  # 默认训练结束日期

    print("=" * 60)
    print(f"批量清洗前{num_stocks}只股票")
    print("=" * 60)

    # 查找需要清洗的股票
    dirty_stocks = find_dirty_stocks()
    print(f"发现 {len(dirty_stocks)} 只需要清洗的股票")

    if not dirty_stocks:
        print("没有需要清洗的股票")
        return

    # 只取前N只股票
    test_stocks = dirty_stocks[:num_stocks]
    print(f"清洗股票列表: {test_stocks}")

    success_count = 0
    fail_count = 0

    for i, ts_code in enumerate(test_stocks, 1):
        print(f"\n处理第 {i}/{len(test_stocks)} 只股票: {ts_code}")

        try:
            # 获取该股票的最早日期
            first_date_result = postgres.select_df(
                "SELECT trade_date FROM daily_kline WHERE ts_code = %s ORDER BY trade_date",
                [ts_code]
            )

            if first_date_result.empty:
                print(f"股票 {ts_code} 没有数据，跳过")
                fail_count += 1
                continue

            first_date = first_date_result['trade_date'].iloc[0]
            print(f"最早交易日期: {first_date}")

            # 运行清洗
            clean_df = clean_one_stock(ts_code, first_date, train_end_date)

            if clean_df is not None:
                print(f"清洗完成，处理了 {len(clean_df)} 条记录")
                # 检查清洗后的数据
                check_result = postgres.select_df(
                    "SELECT COUNT(*) as cleaned_count FROM daily_kline WHERE ts_code = %s AND close_clean IS NOT NULL",
                    [ts_code]
                )
                cleaned_count = check_result['cleaned_count'].iloc[0]
                print(f"股票 {ts_code} 已清洗记录数: {cleaned_count}")
                success_count += 1
            else:
                print(f"股票 {ts_code} 清洗失败")
                fail_count += 1

            # 短暂暂停，避免数据库压力
            time.sleep(0.5)

        except Exception as e:
            print(f"处理股票 {ts_code} 时出错: {e}")
            import traceback
            traceback.print_exc()
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"批量清洗完成")
    print(f"成功: {success_count}, 失败: {fail_count}, 总计: {len(test_stocks)}")
    print("=" * 60)

def main():
    # 清洗前10只股票
    clean_batch_stocks(num_stocks=10, train_end_date=date(2024, 12, 31))

if __name__ == "__main__":
    main()