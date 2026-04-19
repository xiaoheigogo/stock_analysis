#!/usr/bin/env python3
"""
股票预测系统主入口
支持数据更新、模型训练、预测等功能
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import logger


def update_data(args):
    """更新数据"""
    from data_process.raw_data_utils import (
        update_trade_date_data,
        update_stock_list_data,
        update_index_daily_kline,
        update_stocks_daily_kline
    )

    logger.info("开始更新数据...")

    if args.all or args.trade_date:
        update_trade_date_data()

    if args.all or args.stock_list:
        update_stock_list_data()

    if args.all or args.index_kline:
        update_index_daily_kline()

    if args.all or args.stock_kline:
        # 解析股票代码列表
        stock_codes = None
        if args.ts_codes:
            stock_codes = args.ts_codes.split(',')

        update_stocks_daily_kline(
            stock_codes=stock_codes,
            incremental=not args.full_update,
            batch_size=args.batch_size
        )

    logger.info("数据更新完成")


def clean_data(args):
    """清洗和归一化数据"""
    from data_process.clean_normalize import clean_one_stock, find_dirty_stocks

    logger.info("开始清洗数据...")

    if args.all_stocks:
        # 清洗所有未清洗的股票
        dirty_stocks = find_dirty_stocks()
        logger.info(f"找到 {len(dirty_stocks)} 支需要清洗的股票")

        for i, ts_code in enumerate(dirty_stocks, 1):
            logger.info(f"清洗第 {i}/{len(dirty_stocks)} 支股票: {ts_code}")
            try:
                clean_one_stock(ts_code, args.start_date, args.end_date)
            except Exception as e:
                logger.error(f"清洗股票 {ts_code} 失败: {e}")
    elif args.ts_codes:
        # 清洗指定股票
        ts_codes = args.ts_codes.split(',')
        for ts_code in ts_codes:
            logger.info(f"清洗股票: {ts_code}")
            try:
                clean_one_stock(ts_code.strip(), args.start_date, args.end_date)
            except Exception as e:
                logger.error(f"清洗股票 {ts_code} 失败: {e}")
    else:
        logger.error("请指定要清洗的股票或使用 --all-stocks")

    logger.info("数据清洗完成")


def train_model(args):
    """训练模型"""
    from train_src.train import main as train_main

    logger.info("开始训练模型...")

    # 将args转换为train.py需要的格式
    train_args = []
    if args.model:
        train_args.extend(['--model', args.model])
    if args.ts_codes:
        train_args.extend(['--ts_codes', args.ts_codes])
    if args.stock_file:
        train_args.extend(['--stock_file', args.stock_file])
    if args.seq_len:
        train_args.extend(['--seq_len', str(args.seq_len)])
    if args.pred_len:
        train_args.extend(['--pred_len', str(args.pred_len)])
    if args.epochs:
        train_args.extend(['--epochs', str(args.epochs)])
    if args.batch_size:
        train_args.extend(['--batch_size', str(args.batch_size)])
    if args.output_dir:
        train_args.extend(['--output_dir', args.output_dir])

    # 设置sys.argv并调用train_main
    sys.argv = ['train.py'] + train_args
    train_main()


def predict(args):
    """使用模型进行预测"""
    logger.info("开始预测...")

    # TODO: 实现预测功能
    logger.warning("预测功能尚未实现")

    logger.info("预测完成")


def run_server(args):
    """启动Web服务器"""
    logger.info("启动Web服务器...")

    # TODO: 实现Web服务器
    logger.warning("Web服务器功能尚未实现")

    logger.info("Web服务器已启动")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="股票预测系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 更新所有数据（增量更新）
  python main.py update --all

  # 全量更新所有股票数据
  python main.py update --stock-kline --full-update

  # 更新指定股票数据
  python main.py update --stock-kline --ts-codes 000001,000002

  # 更新指定股票数据，批量大小100
  python main.py update --stock-kline --ts-codes 000001,000002,000003 --batch-size 100

  # 清洗指定股票数据
  python main.py clean --ts-codes 000001,000002

  # 训练LSTM模型
  python main.py train --model lstm --ts-codes 000001,000002 --epochs 50

  # 启动Web服务器
  python main.py server --port 8000
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # update 命令
    update_parser = subparsers.add_parser('update', help='更新数据')
    update_parser.add_argument('--all', action='store_true', help='更新所有数据')
    update_parser.add_argument('--trade-date', action='store_true', help='更新交易日历')
    update_parser.add_argument('--stock-list', action='store_true', help='更新股票列表')
    update_parser.add_argument('--index-kline', action='store_true', help='更新指数K线')
    update_parser.add_argument('--stock-kline', action='store_true', help='更新股票K线')
    update_parser.add_argument('--ts-codes', type=str, help='指定股票代码列表，逗号分隔')
    update_parser.add_argument('--full-update', action='store_true', help='全量更新（默认增量更新）')
    update_parser.add_argument('--batch-size', type=int, default=50, help='批量处理大小')

    # clean 命令
    clean_parser = subparsers.add_parser('clean', help='清洗数据')
    clean_parser.add_argument('--all-stocks', action='store_true', help='清洗所有股票')
    clean_parser.add_argument('--ts-codes', type=str, help='股票代码列表，逗号分隔')
    clean_parser.add_argument('--start-date', type=str, default='2020-01-01',
                             help='开始日期')
    clean_parser.add_argument('--end-date', type=str, default='2024-12-31',
                             help='结束日期')

    # train 命令
    train_parser = subparsers.add_parser('train', help='训练模型')
    train_parser.add_argument('--model', type=str, default='lstm',
                             choices=['lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer'],
                             help='模型类型')
    train_parser.add_argument('--ts-codes', type=str, help='股票代码列表，逗号分隔')
    train_parser.add_argument('--stock-file', type=str, help='股票代码文件')
    train_parser.add_argument('--seq-len', type=int, default=30, help='输入序列长度')
    train_parser.add_argument('--pred-len', type=int, default=10, help='预测序列长度')
    train_parser.add_argument('--epochs', type=int, default=50, help='训练轮数')
    train_parser.add_argument('--batch-size', type=int, default=32, help='批量大小')
    train_parser.add_argument('--output-dir', type=str, default='./output',
                             help='输出目录')

    # predict 命令
    predict_parser = subparsers.add_parser('predict', help='预测')
    predict_parser.add_argument('--model-path', type=str, required=True,
                               help='模型路径')
    predict_parser.add_argument('--ts-codes', type=str, required=True,
                               help='股票代码列表，逗号分隔')
    predict_parser.add_argument('--days', type=int, default=10,
                               help='预测天数')

    # server 命令
    server_parser = subparsers.add_parser('server', help='启动Web服务器')
    server_parser.add_argument('--host', type=str, default='0.0.0.0',
                              help='主机地址')
    server_parser.add_argument('--port', type=int, default=8000,
                              help='端口号')
    server_parser.add_argument('--debug', action='store_true',
                              help='调试模式')

    # 解析参数
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 执行命令
    try:
        if args.command == 'update':
            update_data(args)
        elif args.command == 'clean':
            clean_data(args)
        elif args.command == 'train':
            train_model(args)
        elif args.command == 'predict':
            predict(args)
        elif args.command == 'server':
            run_server(args)
        else:
            parser.print_help()
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(0)
    except Exception as e:
        logger.error(f"执行命令失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()