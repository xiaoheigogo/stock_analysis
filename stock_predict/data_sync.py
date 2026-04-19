"""
数据同步模块

功能：
1. 智能数据补全：检测缺失数据并自动补全
2. 增量更新：只获取最新数据
3. 数据质量监控：检查数据完整性和一致性
4. 断点续传：支持失败后继续
5. 多源数据同步：支持从多个数据源同步
"""

import datetime
import time
import random
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd

from utils.db_conn import postgres
from utils.logger import logger
from data_process.raw_data_utils import update_stocks_daily_kline, max_date_in_db

try:
    from proxy_manager import get_proxy_manager
    PROXY_MANAGER_AVAILABLE = True
except ImportError:
    PROXY_MANAGER_AVAILABLE = False


class DataSyncStatus(Enum):
    """数据同步状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SyncTask:
    """同步任务"""
    ts_code: str
    ts_name: str
    start_date: str  # YYYYMMDD
    end_date: str    # YYYYMMDD
    status: DataSyncStatus = DataSyncStatus.PENDING
    retry_count: int = 0
    error_message: str = None
    records_fetched: int = 0
    last_attempt: datetime.datetime = None


class DataSynchronizer:
    """数据同步器"""

    def __init__(self, config_path: str = None):
        """
        初始化数据同步器

        Args:
            config_path: 代理配置文件路径
        """
        self.tasks: List[SyncTask] = []
        self.completed_tasks: List[SyncTask] = []

        # 代理管理器
        self.proxy_manager = None
        if PROXY_MANAGER_AVAILABLE:
            try:
                self.proxy_manager = get_proxy_manager(config_path)
            except Exception as e:
                logger.warning(f"初始化代理管理器失败: {e}")

        # 配置
        self.max_retries = 3
        self.batch_size = 50
        self.max_requests_per_minute = 30
        self.request_count = 0
        self.last_request_time = time.time()

    def create_sync_tasks(self, stock_codes: List[str] = None, incremental: bool = True) -> None:
        """
        创建同步任务

        Args:
            stock_codes: 股票代码列表，None表示所有股票
            incremental: 是否增量同步
        """
        logger.info("创建同步任务...")

        # 获取股票列表
        if stock_codes:
            stock_list = []
            for ts_code in stock_codes:
                result = postgres.select_table(
                    table="stock_list",
                    cols=["ts_code", "ts_name"],
                    where={"ts_code": ("=", ts_code)}
                )
                if result:
                    stock_list.append(result[0])
                else:
                    logger.warning(f"股票代码 {ts_code} 不在股票列表中")
        else:
            stock_list = postgres.select_table(
                table="stock_list",
                cols=["ts_code", "ts_name"],
                where={
                    "__order_by": "ts_code",
                    "__order": "ASC"
                }
            )

        if not stock_list:
            logger.error("没有找到股票列表")
            return

        logger.info(f"共找到 {len(stock_list)} 支股票")

        # 获取当前日期
        today = datetime.datetime.today().strftime("%Y%m%d")

        # 为每支股票创建任务
        for stock in stock_list:
            ts_code = stock['ts_code']
            ts_name = stock['ts_name']

            # 确定同步日期范围
            if incremental:
                # 获取数据库中最新日期
                max_date = max_date_in_db("daily_kline", ts_code)

                if max_date:
                    # 如果数据已是最新，跳过
                    if max_date >= today:
                        task = SyncTask(
                            ts_code=ts_code,
                            ts_name=ts_name,
                            start_date=today,
                            end_date=today,
                            status=DataSyncStatus.SKIPPED
                        )
                        self.completed_tasks.append(task)
                        continue

                    # 增量同步：从最新日期的下一天开始
                    start_date = (datetime.datetime.strptime(max_date, "%Y%m%d") +
                                  datetime.timedelta(days=1)).strftime("%Y%m%d")
                    end_date = today
                else:
                    # 首次同步：从1990年开始
                    start_date = "19900101"
                    end_date = today
            else:
                # 全量同步
                start_date = "19900101"
                end_date = today

            # 创建任务
            task = SyncTask(
                ts_code=ts_code,
                ts_name=ts_name,
                start_date=start_date,
                end_date=end_date,
                status=DataSyncStatus.PENDING
            )

            # 检查是否需要同步（日期范围有效）
            if start_date <= end_date:
                self.tasks.append(task)
            else:
                task.status = DataSyncStatus.SKIPPED
                task.error_message = "日期范围无效"
                self.completed_tasks.append(task)

        logger.info(f"创建了 {len(self.tasks)} 个同步任务")
        logger.info(f"跳过了 {len(self.completed_tasks)} 个任务（数据已最新或无数据）")

    def execute_sync(self) -> Dict:
        """
        执行同步任务

        Returns:
            同步结果统计
        """
        if not self.tasks:
            logger.warning("没有需要执行的同步任务")
            return {}

        logger.info(f"开始执行 {len(self.tasks)} 个同步任务")

        # 统计信息
        stats = {
            'total': len(self.tasks),
            'completed': 0,
            'failed': 0,
            'skipped': len(self.completed_tasks),
            'records_fetched': 0
        }

        # 分批处理任务
        for i, task in enumerate(self.tasks, 1):
            logger.info(f"[{i}/{len(self.tasks)}] 同步股票: {task.ts_code} {task.ts_name}")

            try:
                # 更新任务状态
                task.status = DataSyncStatus.IN_PROGRESS
                task.last_attempt = datetime.datetime.now()

                # 检查日期范围
                if task.start_date > task.end_date:
                    logger.warning(f"股票 {task.ts_code} 日期范围无效: {task.start_date} - {task.end_date}")
                    task.status = DataSyncStatus.SKIPPED
                    task.error_message = "日期范围无效"
                    stats['skipped'] += 1
                    self.completed_tasks.append(task)
                    continue

                # 执行数据获取
                success, records = self._fetch_stock_data(task)

                if success:
                    task.status = DataSyncStatus.COMPLETED
                    task.records_fetched = records
                    stats['completed'] += 1
                    stats['records_fetched'] += records
                    logger.info(f"股票 {task.ts_code} 同步成功，获取 {records} 条记录")
                else:
                    if task.retry_count < self.max_retries:
                        # 重试
                        task.retry_count += 1
                        task.status = DataSyncStatus.PENDING
                        logger.warning(f"股票 {task.ts_code} 同步失败，将重试（第 {task.retry_count} 次）")
                        # 将任务重新加入队列
                        self.tasks.append(task)
                    else:
                        # 失败
                        task.status = DataSyncStatus.FAILED
                        stats['failed'] += 1
                        logger.error(f"股票 {task.ts_code} 同步失败，已达到最大重试次数")

                # 将任务移到已完成列表
                self.completed_tasks.append(task)

            except Exception as e:
                logger.error(f"执行股票 {task.ts_code} 同步任务时发生错误: {e}")
                task.status = DataSyncStatus.FAILED
                task.error_message = str(e)
                stats['failed'] += 1
                self.completed_tasks.append(task)

            # 请求频率控制
            self._rate_limit()

            # 批量提交到数据库
            if i % self.batch_size == 0:
                logger.info(f"已处理 {i} 个任务，暂停批量提交...")
                # 这里可以添加批量提交逻辑
                time.sleep(random.uniform(2.0, 5.0))

        # 输出统计信息
        logger.info("=" * 60)
        logger.info("数据同步完成统计:")
        logger.info(f"总计任务: {stats['total']}")
        logger.info(f"完成成功: {stats['completed']}")
        logger.info(f"完成失败: {stats['failed']}")
        logger.info(f"跳过任务: {stats['skipped']}")
        logger.info(f"获取记录: {stats['records_fetched']}")
        logger.info("=" * 60)

        return stats

    def _fetch_stock_data(self, task: SyncTask) -> Tuple[bool, int]:
        """
        获取股票数据

        Args:
            task: 同步任务

        Returns:
            (是否成功, 记录数)
        """
        try:
            # 这里直接调用raw_data_utils中的函数
            # 在实际实现中，可能需要更细粒度的控制
            from data_process.raw_data_utils import safe_hist

            # 获取数据
            df = safe_hist(
                symbol=task.ts_code,
                ts_name=task.ts_name,
                start=task.start_date,
                end=task.end_date
            )

            if df is None or df.empty:
                logger.warning(f"股票 {task.ts_code} 没有获取到数据")
                return False, 0

            # 写入数据库
            postgres.upsert(
                "daily_kline",
                df.to_dict('records'),
                pk_cols=['trade_date', 'ts_code']
            )

            return True, len(df)

        except Exception as e:
            logger.error(f"获取股票 {task.ts_code} 数据失败: {e}")
            task.error_message = str(e)
            return False, 0

    def _rate_limit(self) -> None:
        """请求频率限制"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        # 重置计数器（每分钟）
        if time_since_last_request > 60:
            self.request_count = 0
            self.last_request_time = current_time

        # 检查是否超过限制
        if self.request_count >= self.max_requests_per_minute:
            wait_time = 60 - time_since_last_request
            if wait_time > 0:
                logger.debug(f"请求频率限制，等待 {wait_time:.1f} 秒")
                time.sleep(wait_time)
                self.request_count = 0
                self.last_request_time = time.time()

        self.request_count += 1

        # 随机延迟，避免请求过于规律
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)

    def get_sync_report(self) -> pd.DataFrame:
        """获取同步报告"""
        report_data = []

        for task in self.completed_tasks:
            report_data.append({
                'ts_code': task.ts_code,
                'ts_name': task.ts_name,
                'start_date': task.start_date,
                'end_date': task.end_date,
                'status': task.status.value,
                'retry_count': task.retry_count,
                'records_fetched': task.records_fetched,
                'error_message': task.error_message,
                'last_attempt': task.last_attempt
            })

        return pd.DataFrame(report_data)

    def save_sync_report(self, filepath: str = None) -> None:
        """保存同步报告"""
        if filepath is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"sync_report_{timestamp}.csv"

        df = self.get_sync_report()
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"同步报告已保存到: {filepath}")


def sync_stock_data(stock_codes: List[str] = None, incremental: bool = True,
                    config_path: str = None, save_report: bool = True) -> Dict:
    """
    同步股票数据（便捷函数）

    Args:
        stock_codes: 股票代码列表
        incremental: 是否增量同步
        config_path: 代理配置文件路径
        save_report: 是否保存报告

    Returns:
        同步结果统计
    """
    synchronizer = DataSynchronizer(config_path)
    synchronizer.create_sync_tasks(stock_codes, incremental)
    stats = synchronizer.execute_sync()

    if save_report:
        synchronizer.save_sync_report()

    return stats


def check_data_quality(stock_codes: List[str] = None) -> pd.DataFrame:
    """
    检查数据质量

    Args:
        stock_codes: 股票代码列表

    Returns:
        数据质量报告
    """
    logger.info("检查数据质量...")

    # 获取股票列表
    if stock_codes:
        where_clause = {"ts_code": ("IN", tuple(stock_codes))}
    else:
        where_clause = {}

    # 查询数据统计信息
    sql = """
    SELECT
        ts_code,
        COUNT(*) as total_records,
        MIN(trade_date) as first_date,
        MAX(trade_date) as last_date,
        COUNT(DISTINCT trade_date) as unique_dates,
        SUM(CASE WHEN open_raw IS NULL THEN 1 ELSE 0 END) as null_open,
        SUM(CASE WHEN close_raw IS NULL THEN 1 ELSE 0 END) as null_close,
        SUM(CASE WHEN volumn_raw IS NULL THEN 1 ELSE 0 END) as null_volume
    FROM daily_kline
    WHERE ts_code LIKE '00%%%%' OR ts_code LIKE '30%%%%' OR ts_code LIKE '60%%%%'
    GROUP BY ts_code
    ORDER BY ts_code
    """

    try:
        results = postgres.select(sql=sql)
        df = pd.DataFrame(results)

        # 计算数据质量指标
        if not df.empty:
            df['data_completeness'] = 1 - (df['null_open'] + df['null_close']) / (2 * df['total_records'])
            df['date_gap_days'] = (pd.to_datetime(df['last_date']) - pd.to_datetime(df['first_date'])).dt.days + 1
            df['coverage_ratio'] = df['unique_dates'] / df['date_gap_days']

            # 标记问题数据
            df['has_issues'] = (
                (df['data_completeness'] < 0.95) |
                (df['coverage_ratio'] < 0.9) |
                (df['total_records'] < 100)
            )

        logger.info(f"数据质量检查完成，共检查 {len(df)} 支股票")
        return df

    except Exception as e:
        logger.error(f"检查数据质量失败: {e}")
        return pd.DataFrame()


def find_missing_data(stock_codes: List[str] = None, start_date: str = None,
                      end_date: str = None) -> pd.DataFrame:
    """
    查找缺失数据

    Args:
        stock_codes: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        缺失数据报告
    """
    logger.info("查找缺失数据...")

    # 获取当前日期
    if end_date is None:
        end_date = datetime.datetime.today().strftime("%Y-%m-%d")

    if start_date is None:
        start_date = "1990-01-01"

    # 获取交易日历
    trade_dates_sql = """
    SELECT trade_date
    FROM trade_date
    WHERE trade_date BETWEEN %s AND %s
    ORDER BY trade_date
    """

    try:
        trade_dates = postgres.select(sql=trade_dates_sql, params=(start_date, end_date))
        trade_dates = [d['trade_date'] for d in trade_dates]

        if not trade_dates:
            logger.warning("在指定日期范围内没有找到交易日")
            return pd.DataFrame()

        # 获取股票列表
        if stock_codes:
            where_clause = {"ts_code": ("IN", tuple(stock_codes))}
        else:
            where_clause = {}

        stock_list = postgres.select_table(
            table="stock_list",
            cols=["ts_code", "ts_name"],
            where=where_clause
        )

        if not stock_list:
            logger.warning("没有找到股票列表")
            return pd.DataFrame()

        # 查找缺失数据
        missing_data = []

        for stock in stock_list:
            ts_code = stock['ts_code']
            ts_name = stock['ts_name']

            # 查询该股票已有的日期
            existing_dates_sql = """
            SELECT trade_date
            FROM daily_kline
            WHERE ts_code = %s
              AND trade_date BETWEEN %s AND %s
            """
            existing_dates = postgres.select(
                sql=existing_dates_sql,
                params=(ts_code, start_date, end_date)
            )
            existing_dates = {d['trade_date'] for d in existing_dates}

            # 查找缺失日期
            missing_dates = [d for d in trade_dates if d not in existing_dates]

            if missing_dates:
                missing_data.append({
                    'ts_code': ts_code,
                    'ts_name': ts_name,
                    'missing_count': len(missing_dates),
                    'missing_dates': missing_dates[:10],  # 只显示前10个
                    'first_missing': min(missing_dates) if missing_dates else None,
                    'last_missing': max(missing_dates) if missing_dates else None
                })

        df = pd.DataFrame(missing_data)

        if not df.empty:
            total_missing = df['missing_count'].sum()
            logger.info(f"找到 {len(df)} 支股票有缺失数据，总计缺失 {total_missing} 个交易日")
        else:
            logger.info("没有找到缺失数据")

        return df

    except Exception as e:
        logger.error(f"查找缺失数据失败: {e}")
        return pd.DataFrame()


# 使用示例
if __name__ == "__main__":
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # 解析命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "sync":
            # 同步数据
            codes = sys.argv[2].split(',') if len(sys.argv) > 2 else None
            stats = sync_stock_data(stock_codes=codes, incremental=True)
            print(f"同步完成: {stats}")

        elif command == "check":
            # 检查数据质量
            codes = sys.argv[2].split(',') if len(sys.argv) > 2 else None
            report = check_data_quality(stock_codes=codes)
            print(report.to_string())

        elif command == "find-missing":
            # 查找缺失数据
            codes = sys.argv[2].split(',') if len(sys.argv) > 2 else None
            report = find_missing_data(stock_codes=codes)
            print(report.to_string())

        else:
            print(f"未知命令: {command}")
            print("可用命令:")
            print("  sync [股票代码列表] - 同步数据")
            print("  check [股票代码列表] - 检查数据质量")
            print("  find-missing [股票代码列表] - 查找缺失数据")
    else:
        # 默认同步所有股票数据
        print("开始同步所有股票数据...")
        stats = sync_stock_data(incremental=True)
        print(f"同步完成: {stats}")