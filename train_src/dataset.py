"""
股票数据集加载和处理
从PostgreSQL加载清洗后的数据，生成训练样本
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from utils.db_conn import postgres
from utils.logger import logger


class StockDataset(Dataset):
    """股票时序数据集"""

    def __init__(self, ts_codes: List[str], seq_len: int = 30,
                 pred_len: int = 10, feature_cols: Optional[List[str]] = None,
                 start_date: Optional[str] = None, end_date: Optional[str] = None,
                 train_ratio: float = 0.8, mode: str = 'train',
                 normalize_target: bool = True,
                 task_type: str = 'regression',
                 classification_thresholds: List[float] = None):
        """
        初始化数据集

        Args:
            ts_codes: 股票代码列表
            seq_len: 输入序列长度（历史天数）
            pred_len: 预测序列长度（未来天数）
            feature_cols: 特征列名列表，如果为None则使用默认特征
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            train_ratio: 训练集比例（0-1）
            mode: 数据集模式，'train'或'val'或'test'
            normalize_target: 是否对目标进行归一化
        """
        super().__init__()

        self.ts_codes = ts_codes
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.mode = mode
        self.normalize_target = normalize_target
        self.task_type = task_type  # 'regression' 或 'classification'

        # 分类任务参数
        if task_type == 'classification':
            if classification_thresholds is None:
                # 默认三分类阈值：下跌(< -0.01), 持平(-0.01 ~ 0.01), 上涨(> 0.01)
                self.classification_thresholds = [-0.01, 0.01]
            else:
                self.classification_thresholds = sorted(classification_thresholds)
            # 计算类别数量：阈值数量 + 1
            self.num_classes = len(self.classification_thresholds) + 1
        else:
            self.classification_thresholds = None
            self.num_classes = None

        # 设置默认特征列
        if feature_cols is None:
            self.feature_cols = [
                # 基础特征
                'open_clean', 'high_clean', 'low_clean', 'close_clean',
                'volumn_clean', 'amount_clean', 'amplitude_clean',
                'pct_change_clean', 'change_clean', 'turnover_clean',
                # 技术指标
                'ma5', 'ma10', 'macd_dif', 'rsi14',
                # 时间特征
                'month_sin', 'month_cos', 'day_sin', 'day_cos',
                'dow_sin', 'dow_cos'
            ]
        else:
            self.feature_cols = feature_cols

        # 目标列
        self.target_col = 'close_clean'

        # 加载数据
        self.data = self._load_data(start_date, end_date)

        # 划分数据集
        self.samples = self._prepare_samples(train_ratio)

        logger.info(f"数据集初始化完成: mode={mode}, "
                   f"股票数={len(ts_codes)}, 样本数={len(self.samples)}, "
                   f"特征数={len(self.feature_cols)}")

    def _load_data(self, start_date: Optional[str], end_date: Optional[str]) -> pd.DataFrame:
        """
        从数据库加载股票数据

        Returns:
            DataFrame: 包含所有股票数据的DataFrame
        """
        all_data = []

        # 对于分类任务，需要原始收盘价计算涨跌幅
        # 去重：feature_cols 已经包含 close_clean，不要在 SQL 中重复选择
        if self.task_type == 'classification':
            select_cols = list(dict.fromkeys(self.feature_cols + ['close_raw']))
        else:
            select_cols = list(dict.fromkeys(self.feature_cols))

        for ts_code in self.ts_codes:
            # 构建SQL查询
            sql = f"""
                SELECT trade_date, ts_code, {', '.join(select_cols)}
                FROM daily_kline
                WHERE ts_code = %s
                  AND close_clean IS NOT NULL
            """

            params = [ts_code]

            if start_date:
                sql += " AND trade_date >= %s"
                params.append(start_date)
            if end_date:
                sql += " AND trade_date <= %s"
                params.append(end_date)

            sql += " ORDER BY trade_date"

            # 查询数据
            df = postgres.select_df(sql, params)

            if len(df) > 0:
                # 确保日期排序
                df = df.sort_values('trade_date')
                # 计算未来收盘价作为目标
                df['future_close'] = df[self.target_col].shift(-self.pred_len)
                # 对于分类任务，计算未来原始收盘价
                if self.task_type == 'classification':
                    df['future_close_raw'] = df['close_raw'].shift(-self.pred_len)
                all_data.append(df)

        if not all_data:
            raise ValueError("没有找到有效数据，请检查股票代码和日期范围")

        # 合并所有股票数据
        combined_df = pd.concat(all_data, ignore_index=True)

        # 删除包含NaN的行（特别是未来收盘价为NaN的行）
        combined_df = combined_df.dropna(subset=['future_close'] + self.feature_cols)

        return combined_df

    def _prepare_samples(self, train_ratio: float) -> List[Tuple]:
        """
        准备训练样本，按时间顺序划分

        Args:
            train_ratio: 训练集比例

        Returns:
            List[Tuple]: 样本列表，每个元素为(idx, ts_code, date)三元组
        """
        samples = []

        # 按股票分组处理
        for ts_code in self.ts_codes:
            stock_data = self.data[self.data['ts_code'] == ts_code].copy()

            if len(stock_data) < self.seq_len + self.pred_len:
                logger.warning(f"股票 {ts_code} 数据不足，跳过")
                continue

            # 按时间排序
            stock_data = stock_data.sort_values('trade_date')
            total_samples = len(stock_data) - self.seq_len - self.pred_len + 1

            if total_samples <= 0:
                continue

            # 按时间划分训练/验证/测试集
            train_cutoff = int(total_samples * train_ratio)
            val_cutoff = train_cutoff + int(total_samples * (1 - train_ratio) / 2)

            # 根据模式选择样本范围
            if self.mode == 'train':
                sample_range = range(0, train_cutoff)
            elif self.mode == 'val':
                sample_range = range(train_cutoff, val_cutoff)
            else:  # 'test'
                sample_range = range(val_cutoff, total_samples)

            # 创建样本索引
            for i in sample_range:
                date_idx = i + self.seq_len - 1  # 输入序列的结束日期
                if date_idx < len(stock_data):
                    trade_date = stock_data.iloc[date_idx]['trade_date']
                    samples.append((i, ts_code, trade_date))

        return samples

    def __len__(self) -> int:
        """返回数据集大小"""
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, dict]:
        """
        获取单个样本

        Args:
            idx: 样本索引

        Returns:
            tuple: (特征序列, 目标值, 元数据)
        """
        sample_idx, ts_code, trade_date = self.samples[idx]

        # 获取该股票的数据
        stock_data = self.data[self.data['ts_code'] == ts_code].copy()
        stock_data = stock_data.sort_values('trade_date').reset_index(drop=True)

        # 提取特征序列
        start_idx = sample_idx
        end_idx = sample_idx + self.seq_len

        # 检查索引范围
        if end_idx > len(stock_data):
            raise IndexError(f"索引超出范围: {end_idx} > {len(stock_data)}")

        # 获取特征
        features = stock_data.iloc[start_idx:end_idx][self.feature_cols].values
        features = features.astype(np.float32)

        # 根据任务类型获取目标
        target_idx = sample_idx + self.seq_len
        target_end_idx = target_idx + self.pred_len

        # 检查目标索引范围
        if target_end_idx > len(stock_data):
            raise IndexError(f"目标索引超出范围: {target_end_idx} > {len(stock_data)}")

        if self.task_type == 'regression':
            # 回归任务：未来pred_len天的归一化收盘价
            target = stock_data.iloc[target_idx:target_end_idx][self.target_col].values
            target = target.astype(np.float32)
            target_tensor = torch.from_numpy(target)

        elif self.task_type == 'classification':
            # 分类任务：计算未来pred_len天的累计涨跌幅，并分类
            # 获取当前收盘价（原始值）
            current_close_raw = stock_data.iloc[target_idx - 1]['close_raw']  # 输入序列的最后一天
            # 获取未来收盘价（原始值）
            future_close_raw = stock_data.iloc[target_end_idx - 1]['future_close_raw']  # 未来pred_len天后

            # 计算累计涨跌幅
            if current_close_raw > 0:
                cumulative_return = (future_close_raw - current_close_raw) / current_close_raw
            else:
                cumulative_return = 0.0

            # 根据阈值分类
            class_label = 0
            for i, threshold in enumerate(self.classification_thresholds):
                if cumulative_return < threshold:
                    break
                class_label = i + 1

            # 转换为类别标签（整数）
            target_tensor = torch.tensor(class_label, dtype=torch.long)

        else:
            raise ValueError(f"未知任务类型: {self.task_type}")

        # 转换为PyTorch张量
        features_tensor = torch.from_numpy(features)

        # 元数据
        metadata = {
            'ts_code': ts_code,
            'trade_date': str(trade_date),
            'seq_len': self.seq_len,
            'pred_len': self.pred_len
        }

        return features_tensor, target_tensor, metadata

    def get_feature_dim(self) -> int:
        """返回特征维度"""
        return len(self.feature_cols)

    def get_stock_stats(self) -> dict:
        """获取数据集中各股票的统计信息"""
        stats = {}

        for ts_code in self.ts_codes:
            stock_data = self.data[self.data['ts_code'] == ts_code]
            if len(stock_data) > 0:
                stats[ts_code] = {
                    'samples': len(stock_data) - self.seq_len - self.pred_len + 1,
                    'date_range': (stock_data['trade_date'].min(),
                                 stock_data['trade_date'].max()),
                    'feature_mean': stock_data[self.feature_cols].mean().to_dict(),
                    'feature_std': stock_data[self.feature_cols].std().to_dict()
                }

        return stats


def create_data_loaders(ts_codes: List[str], seq_len: int = 30,
                        pred_len: int = 10, batch_size: int = 32,
                        train_ratio: float = 0.8, num_workers: int = 0,
                        feature_cols: Optional[List[str]] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        task_type: str = 'regression',
                        classification_thresholds: List[float] = None):
    """
    创建训练、验证、测试DataLoader

    Args:
        ts_codes: 股票代码列表
        seq_len: 输入序列长度
        pred_len: 预测序列长度
        batch_size: 批量大小
        train_ratio: 训练集比例
        num_workers: 数据加载工作进程数
        feature_cols: 特征列列表
        start_date: 开始日期
        end_date: 结束日期
        task_type: 任务类型 'regression' 或 'classification'
        classification_thresholds: 分类任务阈值列表

    Returns:
        tuple: (train_loader, val_loader, test_loader)
    """
    # 创建数据集
    train_dataset = StockDataset(
        ts_codes=ts_codes,
        seq_len=seq_len,
        pred_len=pred_len,
        feature_cols=feature_cols,
        start_date=start_date,
        end_date=end_date,
        train_ratio=train_ratio,
        mode='train',
        task_type=task_type,
        classification_thresholds=classification_thresholds
    )

    val_dataset = StockDataset(
        ts_codes=ts_codes,
        seq_len=seq_len,
        pred_len=pred_len,
        feature_cols=feature_cols,
        start_date=start_date,
        end_date=end_date,
        train_ratio=train_ratio,
        mode='val',
        task_type=task_type,
        classification_thresholds=classification_thresholds
    )

    test_dataset = StockDataset(
        ts_codes=ts_codes,
        seq_len=seq_len,
        pred_len=pred_len,
        feature_cols=feature_cols,
        start_date=start_date,
        end_date=end_date,
        train_ratio=train_ratio,
        mode='test',
        task_type=task_type,
        classification_thresholds=classification_thresholds
    )

    # 创建DataLoader
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    logger.info(f"数据加载器创建完成: "
               f"训练集={len(train_dataset)}, "
               f"验证集={len(val_dataset)}, "
               f"测试集={len(test_dataset)}")

    return train_loader, val_loader, test_loader


if __name__ == "__main__":
    # 测试数据集
    test_codes = ["000001", "000002"]  # 测试用股票代码

    try:
        # 创建数据集
        dataset = StockDataset(
            ts_codes=test_codes,
            seq_len=30,
            pred_len=10,
            start_date="2024-01-01",
            end_date="2024-12-31",
            mode='train'
        )

        print(f"数据集大小: {len(dataset)}")
        print(f"特征维度: {dataset.get_feature_dim()}")

        # 获取一个样本
        if len(dataset) > 0:
            features, target, metadata = dataset[0]
            print(f"\n样本特征形状: {features.shape}")
            print(f"样本目标形状: {target.shape}")
            print(f"元数据: {metadata}")

            # 打印统计信息
            stats = dataset.get_stock_stats()
            for code, stat in stats.items():
                print(f"\n股票 {code}:")
                print(f"  样本数: {stat['samples']}")
                print(f"  日期范围: {stat['date_range']}")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()