#!/usr/bin/env python3
"""
测试数据清洗功能（只清洗前2只股票）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_process.clean_normalize import clean_one_stock, find_dirty_stocks
from utils.db_conn import postgres
from utils.logger import logger
import pandas as pd
from datetime import date

def test_clean_small_batch():
    """测试清洗少量股票"""
    print("=" * 60)
    print("测试数据清洗功能")
    print("=" * 60)

    # 查找需要清洗的股票
    dirty_stocks = find_dirty_stocks()
    print(f"发现 {len(dirty_stocks)} 只需要清洗的股票")

    if not dirty_stocks:
        print("没有需要清洗的股票")
        return

    # 只取前2只股票进行测试
    test_stocks = dirty_stocks[:2]
    print(f"测试清洗前2只股票: {test_stocks}")

    # 设置训练日期范围（使用历史数据）
    train_end = date(2024, 12, 31)  # 使用2024年底作为训练结束日期

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
                continue

            first_date = first_date_result['trade_date'].iloc[0]
            print(f"最早交易日期: {first_date}")

            # 运行清洗
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

    print("\n" + "=" * 60)
    print("测试清洗完成")
    print("=" * 60)

def check_scaler():
    """检查scaler文件"""
    print("\n检查scaler文件...")
    scaler_path = os.path.join(os.path.dirname(__file__), 'data_process', 'scaler_X.pkl')
    if os.path.exists(scaler_path):
        print(f"scaler文件存在: {scaler_path}")
        # 尝试加载
        import joblib
        scaler = joblib.load(scaler_path)
        print(f"scaler类型: {type(scaler)}")
        print(f"特征数量: {scaler.n_features_in_}")
    else:
        print(f"scaler文件不存在: {scaler_path}")

def main():
    test_clean_small_batch()
    check_scaler()

if __name__ == "__main__":
    main()