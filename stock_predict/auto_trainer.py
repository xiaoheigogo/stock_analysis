"""
模型自动训练和迭代系统

功能：
1. 模型版本管理
2. 性能监控
3. 自动重训练
4. 模型部署
"""

import os
import json
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from utils.logger import logger


class ModelVersion:
    """模型版本信息"""

    def __init__(self, version_id: str, model_path: str, metadata: Dict):
        self.version_id = version_id
        self.model_path = model_path
        self.metadata = metadata
        self.created_time = datetime.now()
        self.performance = {}  # 性能指标
        self.status = "active"  # active, deprecated, testing

    def to_dict(self) -> Dict:
        return {
            'version_id': self.version_id,
            'model_path': self.model_path,
            'metadata': self.metadata,
            'created_time': self.created_time.isoformat(),
            'performance': self.performance,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ModelVersion':
        version = cls(
            version_id=data['version_id'],
            model_path=data['model_path'],
            metadata=data['metadata']
        )
        version.created_time = datetime.fromisoformat(data['created_time'])
        version.performance = data.get('performance', {})
        version.status = data.get('status', 'active')
        return version


class AutoTrainer:
    """自动训练器"""

    def __init__(self, config: Dict, output_dir: str = "./output/auto_trainer"):
        """
        初始化自动训练器

        Args:
            config: 训练配置
            output_dir: 输出目录
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.versions_dir = self.output_dir / "versions"
        self.metadata_file = self.output_dir / "model_versions.json"

        # 创建目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(exist_ok=True)

        # 加载现有版本
        self.versions = self._load_versions()
        self.current_version = None
        self._load_current_version()

        logger.info(f"自动训练器初始化完成，目录: {self.output_dir}")
        logger.info(f"现有模型版本数: {len(self.versions)}")

    def _load_versions(self) -> List[ModelVersion]:
        """加载现有模型版本"""
        if not self.metadata_file.exists():
            return []

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            versions = []
            for version_data in data.get('versions', []):
                try:
                    version = ModelVersion.from_dict(version_data)
                    versions.append(version)
                except Exception as e:
                    logger.error(f"加载模型版本失败: {e}")

            return versions
        except Exception as e:
            logger.error(f"加载版本元数据失败: {e}")
            return []

    def _save_versions(self):
        """保存模型版本信息"""
        try:
            data = {
                'updated_time': datetime.now().isoformat(),
                'versions': [v.to_dict() for v in self.versions]
            }

            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"模型版本信息已保存: {self.metadata_file}")
        except Exception as e:
            logger.error(f"保存版本信息失败: {e}")

    def _load_current_version(self):
        """加载当前活跃版本"""
        active_versions = [v for v in self.versions if v.status == 'active']
        if active_versions:
            # 选择最新的活跃版本
            active_versions.sort(key=lambda v: v.created_time, reverse=True)
            self.current_version = active_versions[0]
            logger.info(f"当前活跃版本: {self.current_version.version_id}")
        else:
            logger.warning("没有活跃的模型版本")

    def create_new_version(self, model_path: str, metadata: Dict) -> ModelVersion:
        """
        创建新的模型版本

        Args:
            model_path: 模型文件路径
            metadata: 模型元数据

        Returns:
            ModelVersion: 新创建的版本
        """
        # 生成版本ID（时间戳 + 随机后缀）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        import random
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))
        version_id = f"v{timestamp}_{random_suffix}"

        # 复制模型文件到版本目录
        version_dir = self.versions_dir / version_id
        version_dir.mkdir(exist_ok=True)

        dest_model_path = version_dir / Path(model_path).name
        try:
            shutil.copy2(model_path, dest_model_path)
            logger.info(f"模型文件已复制到: {dest_model_path}")
        except Exception as e:
            logger.error(f"复制模型文件失败: {e}")
            # 如果复制失败，仍然记录原始路径
            dest_model_path = model_path

        # 创建版本对象
        version = ModelVersion(
            version_id=version_id,
            model_path=str(dest_model_path),
            metadata=metadata
        )

        # 添加到版本列表
        self.versions.append(version)

        # 保存更新
        self._save_versions()

        logger.info(f"新模型版本创建成功: {version_id}")
        return version

    def evaluate_version(self, version: ModelVersion,
                        eval_data: Dict,
                        metrics: Dict) -> bool:
        """
        评估模型版本

        Args:
            version: 模型版本
            eval_data: 评估数据
            metrics: 评估指标

        Returns:
            bool: 评估是否成功
        """
        try:
            # 这里应该实际评估模型性能
            # 目前先模拟评估

            # 模拟性能指标
            performance = {
                'accuracy': metrics.get('accuracy', 0.0),
                'loss': metrics.get('loss', 0.0),
                'sharpe_ratio': metrics.get('sharpe_ratio', 0.0),
                'evaluated_time': datetime.now().isoformat(),
                'eval_data_info': {
                    'samples': len(eval_data.get('samples', [])),
                    'date_range': eval_data.get('date_range', [])
                }
            }

            version.performance = performance

            # 保存更新
            self._save_versions()

            logger.info(f"模型版本 {version.version_id} 评估完成")
            return True

        except Exception as e:
            logger.error(f"评估模型版本失败 {version.version_id}: {e}")
            return False

    def should_retrain(self, version: ModelVersion,
                      performance_thresholds: Dict) -> Tuple[bool, str]:
        """
        判断是否需要重新训练

        Args:
            version: 模型版本
            performance_thresholds: 性能阈值

        Returns:
            Tuple[bool, str]: (是否需要重训练, 原因)
        """
        if not version.performance:
            return True, "没有性能数据"

        # 检查性能是否下降
        current_perf = version.performance

        # 检查准确率
        if 'accuracy' in current_perf and 'accuracy' in performance_thresholds:
            if current_perf['accuracy'] < performance_thresholds['accuracy']:
                return True, f"准确率过低: {current_perf['accuracy']:.4f} < {performance_thresholds['accuracy']}"

        # 检查损失
        if 'loss' in current_perf and 'loss' in performance_thresholds:
            if current_perf['loss'] > performance_thresholds['loss']:
                return True, f"损失过高: {current_perf['loss']:.4f} > {performance_thresholds['loss']}"

        # 检查模型年龄
        model_age = datetime.now() - version.created_time
        max_age_days = performance_thresholds.get('max_age_days', 30)
        if model_age.days > max_age_days:
            return True, f"模型过期: {model_age.days}天 > {max_age_days}天"

        return False, "性能满足要求"

    def deprecate_version(self, version: ModelVersion, reason: str = ""):
        """
        弃用模型版本

        Args:
            version: 模型版本
            reason: 弃用原因
        """
        version.status = 'deprecated'
        version.metadata['deprecation_reason'] = reason
        version.metadata['deprecated_time'] = datetime.now().isoformat()

        self._save_versions()
        logger.info(f"模型版本 {version.version_id} 已弃用，原因: {reason}")

    def promote_version(self, version: ModelVersion,
                       demote_current: bool = True):
        """
        提升模型版本为当前活跃版本

        Args:
            version: 模型版本
            demote_current: 是否降级当前活跃版本
        """
        if demote_current and self.current_version:
            # 降级当前版本
            self.current_version.status = 'deprecated'
            self.current_version.metadata['demoted_time'] = datetime.now().isoformat()
            self.current_version.metadata['demoted_by'] = version.version_id

        # 提升新版本
        version.status = 'active'
        self.current_version = version

        self._save_versions()
        logger.info(f"模型版本 {version.version_id} 已提升为活跃版本")

    def get_training_config(self) -> Dict:
        """
        获取训练配置

        Returns:
            Dict: 训练配置
        """
        # 从配置生成训练参数
        base_config = self.config.get('training', {})

        # 添加版本特定配置
        training_config = {
            **base_config,
            'output_dir': str(self.output_dir / "training_runs"),
            'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'auto_trainer': True
        }

        return training_config

    def run_training(self) -> Optional[ModelVersion]:
        """
        运行训练流程

        Returns:
            ModelVersion: 新训练的模型版本，或None（如果失败）
        """
        logger.info("开始自动训练流程...")

        try:
            # 这里应该调用实际的训练脚本
            # 目前返回模拟结果

            # 模拟训练输出
            model_path = self.output_dir / "dummy_model.pth"
            metadata = {
                'model_type': self.config.get('model_type', 'lstm'),
                'task_type': self.config.get('task_type', 'regression'),
                'training_date': datetime.now().isoformat(),
                'training_duration': '模拟训练',
                'parameters': self.config.get('training', {})
            }

            # 创建新版本
            new_version = self.create_new_version(str(model_path), metadata)

            # 模拟评估
            eval_data = {
                'samples': [1, 2, 3],  # 模拟数据
                'date_range': ['2024-01-01', '2024-01-31']
            }
            metrics = {
                'accuracy': 0.85,
                'loss': 0.12,
                'sharpe_ratio': 1.5
            }
            self.evaluate_version(new_version, eval_data, metrics)

            logger.info(f"自动训练完成，新版本: {new_version.version_id}")
            return new_version

        except Exception as e:
            logger.error(f"自动训练失败: {e}")
            return None

    def run_daily_check(self):
        """
        运行每日检查
        """
        logger.info("运行每日检查...")

        if not self.current_version:
            logger.warning("没有当前活跃版本，触发训练")
            self.run_training()
            return

        # 检查性能阈值
        performance_thresholds = self.config.get('performance_thresholds', {
            'accuracy': 0.7,
            'loss': 0.2,
            'max_age_days': 30
        })

        should_retrain, reason = self.should_retrain(
            self.current_version, performance_thresholds
        )

        if should_retrain:
            logger.info(f"需要重新训练: {reason}")

            # 运行训练
            new_version = self.run_training()

            if new_version:
                # 评估新版本
                # 这里应该在实际数据上评估

                # 如果新版本性能更好，提升为活跃版本
                new_perf = new_version.performance.get('accuracy', 0)
                current_perf = self.current_version.performance.get('accuracy', 0)

                if new_perf > current_perf:
                    self.promote_version(new_version)
                else:
                    logger.info(f"新版本性能 ({new_perf:.4f}) 不优于当前版本 ({current_perf:.4f})，保持当前版本")
                    self.deprecate_version(new_version, "性能未提升")
            else:
                logger.error("训练新版本失败")

        else:
            logger.info(f"当前版本性能正常: {reason}")


def create_default_config() -> Dict:
    """创建默认配置"""
    return {
        'model_type': 'lstm',
        'task_type': 'classification',
        'training': {
            'seq_len': 30,
            'pred_len': 10,
            'batch_size': 32,
            'epochs': 50,
            'learning_rate': 0.001,
            'train_ratio': 0.8
        },
        'performance_thresholds': {
            'accuracy': 0.7,
            'loss': 0.2,
            'max_age_days': 30
        },
        'auto_retrain': {
            'enabled': True,
            'schedule': 'daily',  # daily, weekly, monthly
            'check_time': '02:00'  # 每天凌晨2点检查
        }
    }


if __name__ == "__main__":
    # 测试自动训练器
    print("测试自动训练器...")

    config = create_default_config()
    trainer = AutoTrainer(config, output_dir="./test_auto_trainer")

    # 创建模拟版本
    dummy_model = "./test_auto_trainer/dummy_model.pth"
    Path(dummy_model).parent.mkdir(parents=True, exist_ok=True)
    Path(dummy_model).touch()  # 创建空文件

    version = trainer.create_new_version(dummy_model, {'test': True})
    print(f"创建版本: {version.version_id}")

    # 评估版本
    trainer.evaluate_version(version, {'samples': [1, 2, 3]}, {'accuracy': 0.8})
    print(f"版本性能: {version.performance}")

    # 检查是否需要重训练
    should_retrain, reason = trainer.should_retrain(
        version, {'accuracy': 0.7, 'loss': 0.2, 'max_age_days': 30}
    )
    print(f"需要重训练: {should_retrain}, 原因: {reason}")

    # 运行每日检查
    trainer.run_daily_check()

    print("\n测试完成")