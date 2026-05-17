#!/bin/bash
# 自动激活 stock_analysis 项目虚拟环境脚本
# 用法: source activate.sh 或 . activate.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv38"

if [ -d "$VENV_DIR" ]; then
    echo "激活虚拟环境: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
    echo "虚拟环境已激活。Python路径: $(which python)"
    echo "Python版本: $(python --version)"
else
    echo "错误: 虚拟环境不存在: $VENV_DIR"
    echo "请先创建虚拟环境:"
    echo "  python -m venv venv38"
    echo "  source venv38/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "然后再次运行: source activate.sh"
    return 1 2>/dev/null || exit 1
fi
