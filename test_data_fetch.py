#!/usr/bin/env python3
"""
测试数据获取接口
测试代理设置和akshare数据获取功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import datetime
import requests
import akshare as ak
from utils.logger import logger
from data_process.raw_data_utils import safe_hist, setup_proxy

def test_proxy():
    """测试代理设置"""
    print("=" * 60)
    print("测试代理设置")
    print("=" * 60)

    try:
        # 测试代理连接
        proxies = {
            'http': os.environ.get('HTTP_PROXY'),
            'https': os.environ.get('HTTPS_PROXY')
        }

        print(f"HTTP_PROXY: {proxies['http']}")
        print(f"HTTPS_PROXY: {proxies['https']}")

        # 测试网络连接
        response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=10)
        print(f"代理测试响应: {response.json()}")

        print("[OK] 代理设置正常")
        return True

    except Exception as e:
        print(f"[FAIL] 代理测试失败: {e}")
        return False

def test_akshare_connection():
    """测试akshare连接"""
    print("\n" + "=" * 60)
    print("测试akshare连接")
    print("=" * 60)

    try:
        # 设置代理
        setup_proxy()

        # 测试获取交易日历（简单请求）
        df = ak.tool_trade_date_hist_sina()

        if df is not None and not df.empty:
            print(f"[OK] akshare连接正常，获取到 {len(df)} 个交易日")
            print(f"  最新交易日: {df['trade_date'].iloc[0]}")
            print(f"  最旧交易日: {df['trade_date'].iloc[-1]}")
            return True
        else:
            print("[FAIL] akshare连接失败，返回空数据")
            return False

    except Exception as e:
        print(f"[FAIL] akshare连接失败: {e}")
        return False

def test_stock_data_fetch():
    """测试股票数据获取"""
    print("\n" + "=" * 60)
    print("测试股票数据获取")
    print("=" * 60)

    try:
        # 设置代理
        setup_proxy()

        # 测试获取平安银行(000001)的一小段历史数据
        symbol = "000001"
        ts_name = "平安银行"
        start_date = "2025-01-01"
        end_date = "2025-01-10"

        print(f"获取股票数据: {symbol} {ts_name}")
        print(f"日期范围: {start_date} 到 {end_date}")

        # 转换日期格式（YYYYMMDD）
        start_ymd = start_date.replace("-", "")
        end_ymd = end_date.replace("-", "")

        df = safe_hist(symbol=symbol, ts_name=ts_name, start=start_ymd, end=end_ymd)

        if df is not None and not df.empty:
            print(f"[OK] 股票数据获取成功，获取到 {len(df)} 条记录")
            print(f"  数据列: {', '.join(df.columns.tolist())}")
            print(f"  日期范围: {df['trade_date'].iloc[0]} 到 {df['trade_date'].iloc[-1]}")
            print(f"  数据样例:")
            print(df[['trade_date', 'ts_code', 'open_raw', 'close_raw', 'volumn_raw']].head())
            return True
        else:
            print("[FAIL] 股票数据获取失败，返回空数据")
            return False

    except Exception as e:
        print(f"[FAIL] 股票数据获取失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_connection():
    """测试数据库连接"""
    print("\n" + "=" * 60)
    print("测试数据库连接")
    print("=" * 60)

    try:
        from utils.db_conn import postgres

        # 测试查询
        result = postgres.select("SELECT version()")

        if result:
            print(f"[OK] 数据库连接正常")
            print(f"  PostgreSQL版本: {result[0]['version']}")

            # 检查表
            tables_result = postgres.select("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)

            tables = [row['table_name'] for row in tables_result]
            print(f"  数据库表: {', '.join(tables)}")

            # 检查数据量
            for table in ['stock_list', 'daily_kline', 'trade_date']:
                if table in tables:
                    count_result = postgres.select(f"SELECT COUNT(*) as cnt FROM {table}")
                    print(f"  {table}: {count_result[0]['cnt']} 条记录")

            return True
        else:
            print("[FAIL] 数据库连接失败")
            return False

    except Exception as e:
        print(f"[FAIL] 数据库连接失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("股票预测系统数据接口测试")
    print("=" * 60)

    # 配置日志
    logger.setLevel("WARNING")  # 减少日志输出

    results = {}

    # 运行测试
    results['proxy'] = test_proxy()
    results['akshare'] = test_akshare_connection()
    results['stock_data'] = test_stock_data_fetch()
    results['database'] = test_database_connection()

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for test_name, success in results.items():
        status = "[PASS] 通过" if success else "[FAIL] 失败"
        print(f"{test_name:15} {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n[OK] 所有测试通过，数据接口正常！")
    else:
        print("\n[WARN] 部分测试失败，请检查配置。")
        failed_tests = [name for name, success in results.items() if not success]
        print(f"  失败测试: {', '.join(failed_tests)}")

    print("=" * 60)

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)