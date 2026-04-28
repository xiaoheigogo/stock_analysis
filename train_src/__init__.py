"""
股票预测模型训练模块
"""

from .model import (
    BaseLSTM,
    GRUModel,
    CNNLSTMModel,
    TransformerModel,
    PositionalEncoding,
    get_model
)

from .dataset import (
    StockDataset,
    create_data_loaders
)

from .train import (
    Trainer,
    parse_args,
    main
)

__all__ = [
    # 模型
    'BaseLSTM',
    'GRUModel',
    'CNNLSTMModel',
    'TransformerModel',
    'PositionalEncoding',
    'get_model',

    # 数据集
    'StockDataset',
    'create_data_loaders',

    # 训练
    'Trainer',
    'parse_args',
    'main'
]

__version__ = '0.1.0'