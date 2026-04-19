"""
股票预测模型训练脚本
支持命令行参数，可在本地和云端PAI-DLC运行
"""

import os
import sys
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import numpy as np
import pandas as pd

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import logger
from train_src.model import get_model
from train_src.dataset import create_data_loaders


class Trainer:
    """模型训练器"""

    def __init__(self, args):
        """
        初始化训练器

        Args:
            args: 命令行参数或配置字典
        """
        self.args = args
        self.device = self._setup_device()

        # 创建输出目录
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 模型保存路径
        self.model_dir = self.output_dir / "models"
        self.model_dir.mkdir(exist_ok=True)

        # 日志和结果保存路径
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)

        # 初始化模型、数据等
        self.model = None
        self.criterion = None
        self.optimizer = None
        self.scheduler = None
        self.train_loader = None
        self.val_loader = None
        self.test_loader = None

        # 训练状态
        self.best_val_loss = float('inf')
        self.train_losses = []
        self.val_losses = []
        self.learning_rates = []

        # 保存配置
        self._save_config()

        logger.info(f"训练器初始化完成，设备: {self.device}")
        logger.info(f"输出目录: {self.output_dir}")

    def _setup_device(self):
        """设置训练设备（GPU/CPU）"""
        if torch.cuda.is_available() and not self.args.no_cuda:
            device = torch.device('cuda')
            if self.args.gpu_id is not None:
                torch.cuda.set_device(self.args.gpu_id)
            logger.info(f"使用GPU: {torch.cuda.get_device_name()}")
        else:
            device = torch.device('cpu')
            logger.info("使用CPU")

        return device

    def _save_config(self):
        """保存训练配置"""
        config_path = self.output_dir / "config.json"

        # 转换args为字典
        if isinstance(self.args, argparse.Namespace):
            config_dict = vars(self.args)
        else:
            config_dict = dict(self.args)

        # 添加额外信息
        config_dict['train_start_time'] = datetime.now().isoformat()
        config_dict['device'] = str(self.device)
        config_dict['project_root'] = str(project_root)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"配置已保存到: {config_path}")

    def setup_data(self):
        """设置数据加载器"""
        logger.info("设置数据加载器...")

        # 获取股票列表
        if self.args.stock_file:
            # 从文件读取股票列表
            with open(self.args.stock_file, 'r') as f:
                ts_codes = [line.strip() for line in f if line.strip()]
        elif self.args.ts_codes:
            # 从命令行参数读取
            ts_codes = self.args.ts_codes.split(',')
        else:
            # 默认使用几只股票进行测试
            ts_codes = ["000001", "000002", "000003"]
            logger.warning(f"未指定股票代码，使用默认: {ts_codes}")

        logger.info(f"使用股票代码: {ts_codes[:5]}... (共{len(ts_codes)}支)")

        # 创建数据加载器
        self.train_loader, self.val_loader, self.test_loader = create_data_loaders(
            ts_codes=ts_codes,
            seq_len=self.args.seq_len,
            pred_len=self.args.pred_len,
            batch_size=self.args.batch_size,
            train_ratio=self.args.train_ratio,
            num_workers=self.args.num_workers,
            start_date=self.args.start_date,
            end_date=self.args.end_date,
            task_type=self.args.task_type
        )

        # 获取特征维度
        if self.train_loader:
            sample_features, _, _ = next(iter(self.train_loader))
            self.feature_dim = sample_features.shape[2]
            logger.info(f"特征维度: {self.feature_dim}")
        else:
            self.feature_dim = 20  # 默认值
            logger.warning("无法获取特征维度，使用默认值20")

    def setup_model(self):
        """设置模型、损失函数、优化器"""
        logger.info("设置模型...")

        # 创建模型
        # 对于分类任务，如果未指定num_classes，默认为3（上涨、持平、下跌）
        if self.args.task_type == 'classification' and self.args.num_classes is None:
            self.args.num_classes = 3

        self.model = get_model(
            model_name=self.args.model,
            input_dim=self.feature_dim,
            hidden_dim=self.args.hidden_dim,
            num_layers=self.args.num_layers,
            output_dim=self.args.pred_len if self.args.task_type == 'regression' else self.args.num_classes,
            dropout=self.args.dropout,
            bidirectional=self.args.bidirectional,
            task_type=self.args.task_type,
            num_classes=self.args.num_classes
        )

        self.model = self.model.to(self.device)

        # 损失函数
        if self.args.task_type == 'classification':
            # 分类任务使用交叉熵损失
            self.criterion = nn.CrossEntropyLoss()
        elif self.args.loss == 'mse':
            self.criterion = nn.MSELoss()
        elif self.args.loss == 'mae':
            self.criterion = nn.L1Loss()
        elif self.args.loss == 'huber':
            self.criterion = nn.SmoothL1Loss()
        else:
            raise ValueError(f"未知损失函数: {self.args.loss}")

        # 优化器
        if self.args.optimizer == 'adam':
            self.optimizer = optim.Adam(
                self.model.parameters(),
                lr=self.args.lr,
                weight_decay=self.args.weight_decay
            )
        elif self.args.optimizer == 'adamw':
            self.optimizer = optim.AdamW(
                self.model.parameters(),
                lr=self.args.lr,
                weight_decay=self.args.weight_decay
            )
        elif self.args.optimizer == 'sgd':
            self.optimizer = optim.SGD(
                self.model.parameters(),
                lr=self.args.lr,
                momentum=0.9,
                weight_decay=self.args.weight_decay
            )
        else:
            raise ValueError(f"未知优化器: {self.args.optimizer}")

        # 学习率调度器
        if self.args.scheduler == 'step':
            self.scheduler = optim.lr_scheduler.StepLR(
                self.optimizer,
                step_size=self.args.step_size,
                gamma=self.args.gamma
            )
        elif self.args.scheduler == 'reduce':
            self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer,
                mode='min',
                factor=0.5,
                patience=5,
                verbose=True
            )
        elif self.args.scheduler == 'cosine':
            self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer,
                T_max=self.args.epochs
            )
        else:
            self.scheduler = None

        # 打印模型信息
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)

        logger.info(f"模型: {self.args.model}")
        logger.info(f"总参数量: {total_params:,}")
        logger.info(f"可训练参数量: {trainable_params:,}")
        logger.info(f"损失函数: {self.args.loss}")
        logger.info(f"优化器: {self.args.optimizer}, LR: {self.args.lr}")
        logger.info(f"学习率调度器: {self.args.scheduler}")

    def train_epoch(self, epoch: int):
        """训练一个epoch"""
        self.model.train()
        total_loss = 0
        num_batches = 0

        start_time = time.time()

        for batch_idx, (features, targets, metadata) in enumerate(self.train_loader):
            # 移动到设备
            features = features.to(self.device)
            targets = targets.to(self.device)

            # 前向传播
            self.optimizer.zero_grad()
            outputs = self.model(features)
            loss = self.criterion(outputs, targets)

            # 反向传播
            loss.backward()

            # 梯度裁剪
            if self.args.grad_clip is not None:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(),
                    self.args.grad_clip
                )

            # 更新参数
            self.optimizer.step()

            # 记录损失
            total_loss += loss.item()
            num_batches += 1

            # 打印进度
            if batch_idx % self.args.log_interval == 0:
                avg_loss = total_loss / num_batches
                elapsed = time.time() - start_time
                logger.info(f"Epoch {epoch:03d} | Batch {batch_idx:04d}/{len(self.train_loader):04d} | "
                          f"Loss: {avg_loss:.6f} | Time: {elapsed:.2f}s")

        avg_loss = total_loss / max(num_batches, 1)
        self.train_losses.append(avg_loss)

        # 记录学习率
        current_lr = self.optimizer.param_groups[0]['lr']
        self.learning_rates.append(current_lr)

        logger.info(f"Epoch {epoch:03d} 训练完成 | 平均损失: {avg_loss:.6f} | "
                  f"学习率: {current_lr:.6f}")

        return avg_loss

    def validate(self, epoch: int, loader: DataLoader, mode: str = 'val'):
        """验证模型"""
        self.model.eval()
        total_loss = 0
        num_batches = 0

        # 分类任务专用指标
        if self.args.task_type == 'classification':
            total_correct = 0
            total_samples = 0

        all_predictions = []
        all_targets = []
        all_metadata = []

        with torch.no_grad():
            for features, targets, metadata in loader:
                features = features.to(self.device)
                targets = targets.to(self.device)

                outputs = self.model(features)
                loss = self.criterion(outputs, targets)

                total_loss += loss.item()
                num_batches += 1

                # 分类任务：计算准确率
                if self.args.task_type == 'classification':
                    _, predicted = torch.max(outputs.data, 1)
                    total_correct += (predicted == targets).sum().item()
                    total_samples += targets.size(0)

                # 保存预测结果用于分析
                all_predictions.append(outputs.cpu().numpy())
                all_targets.append(targets.cpu().numpy())
                all_metadata.extend(metadata)

        avg_loss = total_loss / max(num_batches, 1)

        # 分类任务：计算准确率
        if self.args.task_type == 'classification':
            accuracy = total_correct / max(total_samples, 1) * 100
            logger.info(f"Epoch {epoch:03d} {mode.upper()} | 平均损失: {avg_loss:.6f} | 准确率: {accuracy:.2f}%")
        else:
            logger.info(f"Epoch {epoch:03d} {mode.upper()} | 平均损失: {avg_loss:.6f}")

        if mode == 'val':
            self.val_losses.append(avg_loss)

        # 如果是验证集且损失更好，保存模型
        if mode == 'val' and avg_loss < self.best_val_loss:
            self.best_val_loss = avg_loss
            self.save_model(epoch, avg_loss, is_best=True)
            logger.info(f"新最佳模型! 验证损失: {avg_loss:.6f}")

        # 保存预测结果
        if mode == 'test' or (mode == 'val' and epoch % self.args.save_interval == 0):
            self.save_predictions(
                epoch, all_predictions, all_targets, all_metadata, mode
            )

        return avg_loss

    def save_model(self, epoch: int, val_loss: float, is_best: bool = False):
        """保存模型"""
        # 常规保存
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.scheduler.state_dict() if self.scheduler else None,
            'val_loss': val_loss,
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'args': vars(self.args) if isinstance(self.args, argparse.Namespace) else self.args
        }

        # 每save_interval个epoch保存一次
        if epoch % self.args.save_interval == 0:
            checkpoint_path = self.model_dir / f"checkpoint_epoch_{epoch:03d}.pth"
            torch.save(checkpoint, checkpoint_path)
            logger.info(f"模型已保存到: {checkpoint_path}")

        # 保存最佳模型
        if is_best:
            best_path = self.model_dir / "best_model.pth"
            torch.save(checkpoint, best_path)
            logger.info(f"最佳模型已保存到: {best_path}")

        # 保存最后一个模型
        last_path = self.model_dir / "last_model.pth"
        torch.save(checkpoint, last_path)

    def save_predictions(self, epoch: int, predictions, targets, metadata, mode: str):
        """保存预测结果"""
        # 合并所有batch的预测结果
        predictions_np = np.concatenate(predictions, axis=0)
        targets_np = np.concatenate(targets, axis=0)

        # 创建DataFrame
        results = []
        for i, meta in enumerate(metadata):
            results.append({
                'epoch': epoch,
                'ts_code': meta['ts_code'],
                'trade_date': meta['trade_date'],
                'seq_len': meta['seq_len'],
                'pred_len': meta['pred_len'],
                'prediction': predictions_np[i].tolist(),
                'target': targets_np[i].tolist(),
                'mse': np.mean((predictions_np[i] - targets_np[i]) ** 2),
                'mae': np.mean(np.abs(predictions_np[i] - targets_np[i]))
            })

        df = pd.DataFrame(results)

        # 保存到CSV
        csv_path = self.log_dir / f"{mode}_predictions_epoch_{epoch:03d}.csv"
        df.to_csv(csv_path, index=False, encoding='utf-8')

        # 保存汇总统计
        summary = {
            'epoch': epoch,
            'mode': mode,
            'total_samples': len(df),
            'avg_mse': df['mse'].mean(),
            'avg_mae': df['mae'].mean(),
            'timestamp': datetime.now().isoformat()
        }

        summary_path = self.log_dir / f"{mode}_summary_epoch_{epoch:03d}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    def train(self):
        """主训练循环"""
        logger.info("开始训练...")

        # 设置数据和模型
        self.setup_data()
        self.setup_model()

        # 训练循环
        for epoch in range(1, self.args.epochs + 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Epoch {epoch}/{self.args.epochs}")
            logger.info(f"{'='*60}")

            # 训练
            train_loss = self.train_epoch(epoch)

            # 验证
            if self.val_loader is not None:
                val_loss = self.validate(epoch, self.val_loader, 'val')

                # 更新学习率调度器
                if self.scheduler is not None:
                    if isinstance(self.scheduler, optim.lr_scheduler.ReduceLROnPlateau):
                        self.scheduler.step(val_loss)
                    else:
                        self.scheduler.step()

            # 保存模型检查点
            if epoch % self.args.save_interval == 0:
                self.save_model(epoch, val_loss if 'val_loss' in locals() else train_loss)

            # 测试集评估
            if self.test_loader is not None and epoch % self.args.test_interval == 0:
                self.validate(epoch, self.test_loader, 'test')

        # 训练完成，在测试集上评估最终模型
        logger.info("\n训练完成，在测试集上评估最终模型...")
        if self.test_loader is not None:
            test_loss = self.validate(self.args.epochs, self.test_loader, 'test')
            logger.info(f"最终测试损失: {test_loss:.6f}")

        # 保存训练历史
        self.save_training_history()

        logger.info("训练完成!")

    def save_training_history(self):
        """保存训练历史"""
        history = {
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'learning_rates': self.learning_rates,
            'best_val_loss': self.best_val_loss,
            'total_epochs': len(self.train_losses)
        }

        history_path = self.log_dir / "training_history.json"
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        # 保存损失曲线数据
        loss_df = pd.DataFrame({
            'epoch': range(1, len(self.train_losses) + 1),
            'train_loss': self.train_losses,
            'val_loss': self.val_losses[:len(self.train_losses)],
            'learning_rate': self.learning_rates[:len(self.train_losses)]
        })
        loss_path = self.log_dir / "loss_history.csv"
        loss_df.to_csv(loss_path, index=False)

        logger.info(f"训练历史已保存到: {history_path}")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="股票预测模型训练")

    # 数据参数
    parser.add_argument('--ts_codes', type=str, default='',
                       help='股票代码列表，逗号分隔')
    parser.add_argument('--stock_file', type=str, default='',
                       help='股票代码文件，每行一个代码')
    parser.add_argument('--seq_len', type=int, default=30,
                       help='输入序列长度（历史天数）')
    parser.add_argument('--pred_len', type=int, default=10,
                       help='预测序列长度（未来天数）')
    parser.add_argument('--start_date', type=str, default='2020-01-01',
                       help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end_date', type=str, default='2024-12-31',
                       help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--train_ratio', type=float, default=0.8,
                       help='训练集比例')

    # 模型参数
    parser.add_argument('--model', type=str, default='lstm',
                       choices=['lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer'],
                       help='模型类型')
    parser.add_argument('--task_type', type=str, default='regression',
                       choices=['regression', 'classification'],
                       help='任务类型：regression(回归)或classification(分类)')
    parser.add_argument('--num_classes', type=int, default=None,
                       help='分类任务类别数（默认为3，如果为回归任务则忽略）')
    parser.add_argument('--hidden_dim', type=int, default=128,
                       help='LSTM/GRU隐藏层维度')
    parser.add_argument('--num_layers', type=int, default=1,
                       help='LSTM/GRU层数')
    parser.add_argument('--dropout', type=float, default=0.2,
                       help='Dropout概率')
    parser.add_argument('--bidirectional', action='store_true',
                       help='是否使用双向LSTM/GRU')

    # 训练参数
    parser.add_argument('--epochs', type=int, default=50,
                       help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=32,
                       help='批量大小')
    parser.add_argument('--lr', type=float, default=0.001,
                       help='学习率')
    parser.add_argument('--weight_decay', type=float, default=1e-4,
                       help='权重衰减')
    parser.add_argument('--loss', type=str, default='mse',
                       choices=['mse', 'mae', 'huber', 'cross_entropy'],
                       help='损失函数（分类任务使用cross_entropy）')
    parser.add_argument('--optimizer', type=str, default='adam',
                       choices=['adam', 'adamw', 'sgd'],
                       help='优化器')
    parser.add_argument('--scheduler', type=str, default='reduce',
                       choices=['step', 'reduce', 'cosine', 'none'],
                       help='学习率调度器')
    parser.add_argument('--step_size', type=int, default=10,
                       help='StepLR步长')
    parser.add_argument('--gamma', type=float, default=0.5,
                       help='StepLR衰减率')
    parser.add_argument('--grad_clip', type=float, default=None,
                       help='梯度裁剪阈值')

    # 设备参数
    parser.add_argument('--no_cuda', action='store_true',
                       help='禁用CUDA')
    parser.add_argument('--gpu_id', type=int, default=None,
                       help='GPU ID（默认为0）')
    parser.add_argument('--num_workers', type=int, default=0,
                       help='数据加载工作进程数')

    # 日志和保存参数
    parser.add_argument('--output_dir', type=str, default='./output',
                       help='输出目录')
    parser.add_argument('--log_interval', type=int, default=10,
                       help='日志打印间隔（批次数）')
    parser.add_argument('--save_interval', type=int, default=5,
                       help='模型保存间隔（epoch数）')
    parser.add_argument('--test_interval', type=int, default=10,
                       help='测试集评估间隔（epoch数）')

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 创建训练器并开始训练
    trainer = Trainer(args)
    trainer.train()


if __name__ == "__main__":
    main()