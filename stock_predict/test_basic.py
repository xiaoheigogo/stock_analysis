#!/usr/bin/env python3
"""
基础测试脚本
测试模型和数据加载器的基本功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import torch
import numpy as np
from train_src.model import get_model
from train_src.dataset import StockDataset


def test_model():
    """测试模型"""
    print("测试模型...")

    # 测试数据
    batch_size = 4
    seq_len = 30
    input_dim = 20
    output_dim = 10

    test_input = torch.randn(batch_size, seq_len, input_dim)

    # 测试所有模型类型
    model_types = ['lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer']

    for model_type in model_types:
        print(f"\n测试 {model_type} 模型:")

        try:
            if model_type == 'bilstm':
                model = get_model('lstm', input_dim=input_dim, bidirectional=True)
            else:
                model = get_model(model_type, input_dim=input_dim)

            # 前向传播
            output = model(test_input)

            # 检查输出形状
            assert output.shape == (batch_size, output_dim), \
                f"输出形状错误: {output.shape} != {(batch_size, output_dim)}"

            print(f"  输出形状: {output.shape}")
            print(f"  参数量: {sum(p.numel() for p in model.parameters()):,}")

            # 测试模型状态
            model.train()
            output_train = model(test_input)
            model.eval()
            output_eval = model(test_input)

            print(f"  训练/评估模式测试通过")

        except Exception as e:
            print(f"  测试失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n模型测试完成!")


def test_dataset():
    """测试数据集"""
    print("\n测试数据集...")

    try:
        # 创建模拟数据集（不依赖数据库）
        class MockDataset(torch.utils.data.Dataset):
            def __init__(self, num_samples=100, seq_len=30, feature_dim=20, pred_len=10):
                self.num_samples = num_samples
                self.seq_len = seq_len
                self.feature_dim = feature_dim
                self.pred_len = pred_len

            def __len__(self):
                return self.num_samples

            def __getitem__(self, idx):
                features = torch.randn(self.seq_len, self.feature_dim)
                target = torch.randn(self.pred_len)
                metadata = {
                    'ts_code': 'TEST',
                    'trade_date': '2024-01-01',
                    'seq_len': self.seq_len,
                    'pred_len': self.pred_len
                }
                return features, target, metadata

        # 创建数据加载器
        dataset = MockDataset(num_samples=100)
        dataloader = torch.utils.data.DataLoader(
            dataset,
            batch_size=4,
            shuffle=True
        )

        # 测试数据加载
        features, target, metadata = next(iter(dataloader))

        print(f"  特征形状: {features.shape}")
        print(f"  目标形状: {target.shape}")
        print(f"  批次大小: {len(metadata)}")

        # 检查形状
        assert features.shape == (4, 30, 20), f"特征形状错误: {features.shape}"
        assert target.shape == (4, 10), f"目标形状错误: {target.shape}"

        print("  数据集测试通过!")

    except Exception as e:
        print(f"  数据集测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_training_loop():
    """测试训练循环"""
    print("\n测试训练循环...")

    try:
        # 创建模型
        model = get_model('lstm', input_dim=20, hidden_dim=64, output_dim=10)

        # 损失函数和优化器
        criterion = torch.nn.MSELoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

        # 模拟数据
        batch_size = 4
        seq_len = 30
        features = torch.randn(batch_size, seq_len, 20)
        targets = torch.randn(batch_size, 10)

        # 训练步骤
        model.train()
        optimizer.zero_grad()
        outputs = model(features)
        loss = criterion(outputs, targets)
        loss.backward()
        optimizer.step()

        print(f"  损失值: {loss.item():.6f}")
        print(f"  梯度检查: 所有参数都有梯度")

        # 检查梯度
        has_gradients = False
        for name, param in model.named_parameters():
            if param.grad is not None:
                has_gradients = True
                break

        assert has_gradients, "没有参数有梯度"
        print("  训练循环测试通过!")

    except Exception as e:
        print(f"  训练循环测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主测试函数"""
    print("=" * 60)
    print("股票预测系统基础测试")
    print("=" * 60)

    # 设置随机种子
    torch.manual_seed(42)
    np.random.seed(42)

    # 运行测试
    test_model()
    test_dataset()
    test_training_loop()

    print("\n" + "=" * 60)
    print("所有基础测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()