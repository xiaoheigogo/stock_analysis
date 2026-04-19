#!/usr/bin/env python3
"""
测试数据库连接
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db_conn import postgres

def test_database_connection():
    """测试数据库连接"""
    print("测试数据库连接...")

    try:
        # 测试基本连接
        print("1. 测试基本连接...")
        with postgres.get_cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()
            print(f"   PostgreSQL版本: {version[0]}")

        # 测试表是否存在
        print("2. 测试表是否存在...")
        with postgres.get_cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = cur.fetchall()
            print(f"   数据库中有 {len(tables)} 个表:")
            for table in tables:
                print(f"   - {table[0]}")

        # 测试stock_list表数据
        print("3. 测试stock_list表...")
        try:
            with postgres.get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM stock_list")
                count = cur.fetchone()[0]
                print(f"   stock_list表中有 {count} 条记录")

                # 获取前5条记录
                cur.execute("SELECT ts_code, ts_name, industry FROM stock_list LIMIT 5")
                stocks = cur.fetchall()
                print(f"   前5条记录:")
                for stock in stocks:
                    print(f"   - {stock[0]} {stock[1]} ({stock[2]})")
        except Exception as e:
            print(f"   查询stock_list表失败: {e}")

        # 测试daily_kline表数据
        print("4. 测试daily_kline表...")
        try:
            with postgres.get_cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM daily_kline")
                count = cur.fetchone()[0]
                print(f"   daily_kline表中有 {count} 条记录")

                # 获取最近日期
                cur.execute("SELECT MAX(trade_date) FROM daily_kline")
                max_date = cur.fetchone()[0]
                print(f"   最新数据日期: {max_date}")

                # 按股票分组统计
                cur.execute("""
                    SELECT ts_code, COUNT(*) as cnt, MIN(trade_date), MAX(trade_date)
                    FROM daily_kline
                    GROUP BY ts_code
                    LIMIT 5
                """)
                stats = cur.fetchall()
                print(f"   前5支股票数据统计:")
                for stat in stats:
                    print(f"   - {stat[0]}: {stat[1]}条记录, 日期范围 {stat[2]} ~ {stat[3]}")
        except Exception as e:
            print(f"   查询daily_kline表失败: {e}")

        return True

    except Exception as e:
        print(f"数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("股票预测系统数据库连接测试")
    print("=" * 60)

    success = test_database_connection()

    print("\n" + "=" * 60)
    print(f"测试结果: {'成功' if success else '失败'}")
    print("=" * 60)