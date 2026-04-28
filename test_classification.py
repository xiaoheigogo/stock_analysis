#!/usr/bin/env python3
"""
测试分类模型修改
"""

import sys
import os

# 尝试导入torch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    print("警告: PyTorch未安装，将跳过模型前向传播测试")
    TORCH_AVAILABLE = False

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from train_src.model import get_model

def test_model_with_classification():
    """测试模型是否支持分类任务"""
    if not TORCH_AVAILABLE:
        print("跳过模型测试（PyTorch未安装）")
        return

    print("测试模型分类任务支持...")

    batch_size = 4
    seq_len = 30
    input_dim = 20

    # 测试输入
    test_input = torch.randn(batch_size, seq_len, input_dim)

    # 测试所有模型类型
    model_names = ['lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer']

    for model_name in model_names:
        print(f"\n测试 {model_name} 模型分类任务...")

        # 创建分类模型
        if model_name == 'bilstm':
            model = get_model('lstm',
                             input_dim=input_dim,
                             output_dim=3,  # 3个类别
                             task_type='classification',
                             bidirectional=True)
        else:
            model = get_model(model_name,
                             input_dim=input_dim,
                             output_dim=3,  # 3个类别
                             task_type='classification')

        # 前向传播
        output = model(test_input)

        print(f"  输入形状: {test_input.shape}")
        print(f"  输出形状: {output.shape}")
        print(f"  模型参数量: {sum(p.numel() for p in model.parameters()):,}")

        # 检查输出维度是否正确
        if output.shape == (batch_size, 3):
            print(f"  ✓ 分类模型输出正确: {output.shape[1]}个类别")
        else:
            print(f"  ✗ 分类模型输出错误: 期望({batch_size}, 3), 实际{output.shape}")

    print("\n测试回归任务以确保向后兼容性...")

    # 测试回归任务
    for model_name in ['lstm', 'gru']:
        print(f"\n测试 {model_name} 模型回归任务...")

        model = get_model(model_name,
                         input_dim=input_dim,
                         output_dim=10,  # 预测10天
                         task_type='regression')

        output = model(test_input)

        print(f"  输入形状: {test_input.shape}")
        print(f"  输出形状: {output.shape}")

        if output.shape == (batch_size, 10):
            print(f"  ✓ 回归模型输出正确: {output.shape[1]}天预测")
        else:
            print(f"  ✗ 回归模型输出错误: 期望({batch_size}, 10), 实际{output.shape}")

def test_dataset_with_classification():
    """测试数据集分类任务支持"""
    if not TORCH_AVAILABLE:
        print("跳过数据集测试（PyTorch未安装）")
        return

    print("\n\n测试数据集分类任务支持...")

    try:
        from train_src.dataset import StockDataset

        # 使用模拟股票代码
        test_codes = ["000001", "000002"]

        # 尝试创建分类数据集
        dataset = StockDataset(
            ts_codes=test_codes,
            seq_len=30,
            pred_len=10,
            task_type='classification',
            mode='train'
        )

        print(f"  分类数据集创建成功")
        print(f"  数据集大小: {len(dataset)}")
        print(f"  任务类型: {dataset.task_type}")
        print(f"  类别数: {dataset.num_classes}")

        # 获取一个样本
        if len(dataset) > 0:
            features, target, metadata = dataset[0]
            print(f"  样本特征形状: {features.shape}")
            print(f"  样本目标: {target} (类型: {type(target)})")

            # 分类任务的目标应该是整数标签
            if isinstance(target, torch.Tensor) and target.dim() == 0:
                print(f"  ✓ 分类标签正确: {target.item()}")
            else:
                print(f"  ✗ 分类标签错误: 应为标量整数标签")

    except Exception as e:
        print(f"  数据集测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("股票预测系统分类模型测试")
    print("=" * 60)

    test_model_with_classification()
    test_dataset_with_classification()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)