#!/usr/bin/env python3
"""测试PyTorch安装"""

import sys
print(f"Python版本: {sys.version}")

try:
    import torch
    print(f"PyTorch版本: {torch.__version__}")
    print(f"CUDA可用: {torch.cuda.is_available()}")
    print(f"CUDA版本: {torch.version.cuda if torch.cuda.is_available() else 'N/A'}")
    print("PyTorch导入成功")

    # 简单测试张量操作
    x = torch.tensor([1, 2, 3])
    y = torch.tensor([4, 5, 6])
    z = x + y
    print(f"张量加法测试: {z}")

except Exception as e:
    print(f"PyTorch导入失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()