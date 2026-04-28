#!/usr/bin/env python3
"""
测试数据集加载功能（不依赖PyTorch）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db_conn import postgres
import pandas as pd
import numpy as np

def test_dataset_loading():
    """测试从数据库加载清洗后的数据"""
    print("=" * 60)
    print("测试数据集加载功能")
    print("=" * 60)

    # 测试股票代码
    test_codes = ['000001', '000002']

    for ts_code in test_codes:
        print(f"\n加载股票 {ts_code} 的清洗后数据:")

        # 查询清洗后的特征数据
        query = """
            SELECT trade_date, open_clean, high_clean, low_clean, close_clean,
                   volumn_clean, amount_clean, amplitude_clean, pct_change_clean,
                   change_clean, turnover_clean, ma5, ma10, macd_dif, rsi14,
                   month_sin, month_cos, day_sin, day_cos, dow_sin, dow_cos
            FROM daily_kline
            WHERE ts_code = %s AND close_clean IS NOT NULL
            ORDER BY trade_date
        """

        df = postgres.select_df(query, [ts_code])

        print(f"  数据量: {len(df)} 条记录")
        print(f"  日期范围: {df['trade_date'].iloc[0]} 到 {df['trade_date'].iloc[-1]}")
        print(f"  特征数量: {len(df.columns) - 1}")  # 减去trade_date列

        # 检查数据质量
        print(f"  缺失值统计:")
        for col in df.columns:
            if col != 'trade_date':
                null_count = df[col].isnull().sum()
                if null_count > 0:
                    print(f"    {col}: {null_count} 个缺失值")

        # 显示特征统计
        print(f"  特征统计:")
        numeric_cols = [col for col in df.columns if col != 'trade_date']
        stats = df[numeric_cols].describe().loc[['mean', 'std', 'min', 'max']]
        print(stats.to_string())

        # 测试滑动窗口生成
        print(f"\n  测试滑动窗口生成:")
        seq_len = 30
        pred_len = 10

        if len(df) > seq_len + pred_len:
            # 简单的滑动窗口生成逻辑
            features = df[numeric_cols].values

            # 生成样本
            samples = []
            targets = []

            for i in range(len(features) - seq_len - pred_len):
                X = features[i:i+seq_len]
                y = features[i+seq_len:i+seq_len+pred_len, 3]  # 预测close_clean
                samples.append(X)
                targets.append(y)

            print(f"    生成 {len(samples)} 个样本")
            print(f"    输入形状: {samples[0].shape}")
            print(f"    输出形状: {targets[0].shape}")
            print(f"    第一个样本的close_clean值范围: {samples[0][:, 3].min():.3f} 到 {samples[0][:, 3].max():.3f}")
        else:
            print(f"    数据量不足，需要至少 {seq_len + pred_len} 条记录，当前只有 {len(df)} 条")

def test_feature_columns():
    """测试特征列配置"""
    print("\n" + "=" * 60)
    print("测试特征列配置")
    print("=" * 60)

    # 从config.yaml读取特征列配置
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        feature_cols = config.get('model', {}).get('training', {}).get('feature_columns', [])
        print(f"配置文件中的特征列: {feature_cols}")
        print(f"特征数量: {len(feature_cols)}")

        # 验证特征列是否存在于数据库中
        test_ts_code = '000001'
        test_query = f"""
            SELECT {', '.join(feature_cols[:5])}  -- 只测试前5个特征
            FROM daily_kline
            WHERE ts_code = '{test_ts_code}' AND close_clean IS NOT NULL
            LIMIT 1
        """

        result = postgres.select_df(test_query)
        if not result.empty:
            print("特征列验证通过")
        else:
            print("特征列验证失败")

    except Exception as e:
        print(f"读取配置文件失败: {e}")

def main():
    test_dataset_loading()
    test_feature_columns()

    print("\n" + "=" * 60)
    print("数据集加载测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()