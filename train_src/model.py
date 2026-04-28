"""
股票预测模型定义
支持LSTM、GRU、BiLSTM、CNN-LSTM等多种时序模型
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class BaseLSTM(nn.Module):
    """基础LSTM模型，支持回归和分类任务"""

    def __init__(self, input_dim=20, hidden_dim=128, num_layers=1,
                 output_dim=10, dropout=0.2, bidirectional=False,
                 task_type='regression', num_classes=None):
        """
        初始化LSTM模型

        Args:
            input_dim: 输入特征维度（默认20个特征）
            hidden_dim: LSTM隐藏层维度
            num_layers: LSTM层数
            output_dim: 输出维度（回归时为预测天数，分类时为类别数）
            dropout: Dropout概率
            bidirectional: 是否使用双向LSTM
            task_type: 任务类型，'regression'或'classification'
            num_classes: 分类任务时的类别数（如果为None且task_type='classification'，则使用output_dim）
        """
        super().__init__()

        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.output_dim = output_dim
        self.bidirectional = bidirectional
        self.task_type = task_type

        # 确定实际输出维度
        if task_type == 'classification':
            self.num_classes = num_classes if num_classes is not None else output_dim
            # 分类任务时，输出维度为类别数
            final_output_dim = self.num_classes
        else:
            self.num_classes = None
            final_output_dim = output_dim

        self.final_output_dim = final_output_dim

        # LSTM层
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=bidirectional
        )

        # Dropout层
        self.dropout = nn.Dropout(dropout)

        # 全连接输出层
        lstm_output_dim = hidden_dim * 2 if bidirectional else hidden_dim
        self.fc = nn.Linear(lstm_output_dim, final_output_dim)

        # 初始化权重
        self._init_weights()

    def _init_weights(self):
        """初始化模型权重"""
        for name, param in self.lstm.named_parameters():
            if 'weight_ih' in name:
                nn.init.xavier_uniform_(param.data)
            elif 'weight_hh' in name:
                nn.init.orthogonal_(param.data)
            elif 'bias' in name:
                param.data.fill_(0)

        nn.init.xavier_uniform_(self.fc.weight)
        self.fc.bias.data.fill_(0)

    def forward(self, x):
        """
        前向传播

        Args:
            x: 输入张量，形状为 [batch_size, seq_len, input_dim]

        Returns:
            output: 预测输出，形状为 [batch_size, output_dim]
        """
        batch_size = x.size(0)

        # LSTM前向传播
        lstm_out, (hidden, cell) = self.lstm(x)

        # 如果是双向LSTM，需要合并最后两个时间步的输出
        if self.bidirectional:
            # 取前向和后向的最后一个时间步
            forward_out = lstm_out[:, -1, :self.hidden_dim]
            backward_out = lstm_out[:, 0, self.hidden_dim:]
            last_out = torch.cat([forward_out, backward_out], dim=1)
        else:
            # 取最后一个时间步的输出
            last_out = lstm_out[:, -1, :]

        # Dropout
        out = self.dropout(last_out)

        # 全连接层
        output = self.fc(out)

        return output


class GRUModel(nn.Module):
    """GRU模型，参数更少，训练更快"""

    def __init__(self, input_dim=20, hidden_dim=128, num_layers=1,
                 output_dim=10, dropout=0.2, bidirectional=False,
                 task_type='regression', num_classes=None):
        super().__init__()

        self.task_type = task_type

        # 确定实际输出维度
        if task_type == 'classification':
            self.num_classes = num_classes if num_classes is not None else output_dim
            # 分类任务时，输出维度为类别数
            final_output_dim = self.num_classes
        else:
            self.num_classes = None
            final_output_dim = output_dim

        self.final_output_dim = final_output_dim

        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=bidirectional
        )

        self.dropout = nn.Dropout(dropout)

        gru_output_dim = hidden_dim * 2 if bidirectional else hidden_dim
        self.fc = nn.Linear(gru_output_dim, final_output_dim)

        self._init_weights()

    def _init_weights(self):
        for name, param in self.gru.named_parameters():
            if 'weight_ih' in name:
                nn.init.xavier_uniform_(param.data)
            elif 'weight_hh' in name:
                nn.init.orthogonal_(param.data)
            elif 'bias' in name:
                param.data.fill_(0)

        nn.init.xavier_uniform_(self.fc.weight)
        self.fc.bias.data.fill_(0)

    def forward(self, x):
        gru_out, hidden = self.gru(x)

        if self.gru.bidirectional:
            forward_out = gru_out[:, -1, :self.gru.hidden_size]
            backward_out = gru_out[:, 0, self.gru.hidden_size:]
            last_out = torch.cat([forward_out, backward_out], dim=1)
        else:
            last_out = gru_out[:, -1, :]

        out = self.dropout(last_out)
        output = self.fc(out)

        return output


class CNNLSTMModel(nn.Module):
    """CNN-LSTM混合模型，CNN提取空间特征，LSTM处理时序"""

    def __init__(self, input_dim=20, cnn_channels=32, lstm_hidden=128,
                 output_dim=10, dropout=0.2,
                 task_type='regression', num_classes=None):
        """
        初始化CNN-LSTM模型

        Args:
            input_dim: 输入特征维度
            cnn_channels: CNN输出通道数
            lstm_hidden: LSTM隐藏层维度
            output_dim: 输出维度（回归时为预测天数，分类时为类别数）
            dropout: Dropout概率
            task_type: 任务类型，'regression'或'classification'
            num_classes: 分类任务时的类别数（如果为None且task_type='classification'，则使用output_dim）
        """
        super().__init__()

        self.task_type = task_type

        # 确定实际输出维度
        if task_type == 'classification':
            self.num_classes = num_classes if num_classes is not None else output_dim
            # 分类任务时，输出维度为类别数
            final_output_dim = self.num_classes
        else:
            self.num_classes = None
            final_output_dim = output_dim

        self.final_output_dim = final_output_dim

        # CNN部分：1D卷积提取特征
        self.conv1 = nn.Conv1d(
            in_channels=input_dim,
            out_channels=cnn_channels,
            kernel_size=3,
            padding=1
        )
        self.bn1 = nn.BatchNorm1d(cnn_channels)
        self.pool = nn.MaxPool1d(kernel_size=2)

        # LSTM部分
        self.lstm = nn.LSTM(
            input_size=cnn_channels,
            hidden_size=lstm_hidden,
            num_layers=1,
            batch_first=True,
            dropout=0
        )

        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(lstm_hidden, final_output_dim)

        self._init_weights()

    def _init_weights(self):
        nn.init.xavier_uniform_(self.conv1.weight)
        self.conv1.bias.data.fill_(0)

        for name, param in self.lstm.named_parameters():
            if 'weight_ih' in name:
                nn.init.xavier_uniform_(param.data)
            elif 'weight_hh' in name:
                nn.init.orthogonal_(param.data)
            elif 'bias' in name:
                param.data.fill_(0)

        nn.init.xavier_uniform_(self.fc.weight)
        self.fc.bias.data.fill_(0)

    def forward(self, x):
        # x形状: [batch, seq_len, features]
        # 转换为 [batch, features, seq_len] 用于CNN
        x = x.transpose(1, 2)

        # CNN特征提取
        cnn_out = F.relu(self.bn1(self.conv1(x)))
        cnn_out = self.pool(cnn_out)

        # 转换回 [batch, seq_len, features] 用于LSTM
        cnn_out = cnn_out.transpose(1, 2)

        # LSTM处理
        lstm_out, _ = self.lstm(cnn_out)
        last_out = lstm_out[:, -1, :]

        out = self.dropout(last_out)
        output = self.fc(out)

        return output


class TransformerModel(nn.Module):
    """Transformer时序预测模型"""

    def __init__(self, input_dim=20, d_model=128, nhead=8, num_layers=2,
                 output_dim=10, dropout=0.2,
                 task_type='regression', num_classes=None):
        """
        初始化Transformer模型

        Args:
            input_dim: 输入特征维度
            d_model: Transformer模型维度
            nhead: 注意力头数
            num_layers: Transformer编码器层数
            output_dim: 输出维度（回归时为预测天数，分类时为类别数）
            dropout: Dropout概率
            task_type: 任务类型，'regression'或'classification'
            num_classes: 分类任务时的类别数（如果为None且task_type='classification'，则使用output_dim）
        """
        super().__init__()

        self.task_type = task_type

        # 确定实际输出维度
        if task_type == 'classification':
            self.num_classes = num_classes if num_classes is not None else output_dim
            # 分类任务时，输出维度为类别数
            final_output_dim = self.num_classes
        else:
            self.num_classes = None
            final_output_dim = output_dim

        self.final_output_dim = final_output_dim

        # 输入投影层
        self.input_proj = nn.Linear(input_dim, d_model)

        # 位置编码
        self.pos_encoder = PositionalEncoding(d_model, dropout)

        # Transformer编码器
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dropout=dropout,
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers
        )

        # 输出层
        self.fc = nn.Linear(d_model, final_output_dim)
        self.dropout = nn.Dropout(dropout)

        self._init_weights()

    def _init_weights(self):
        nn.init.xavier_uniform_(self.input_proj.weight)
        self.input_proj.bias.data.fill_(0)

        nn.init.xavier_uniform_(self.fc.weight)
        self.fc.bias.data.fill_(0)

    def forward(self, x):
        # 输入投影
        x = self.input_proj(x)

        # 位置编码
        x = self.pos_encoder(x)

        # Transformer编码
        transformer_out = self.transformer_encoder(x)

        # 取最后一个时间步
        last_out = transformer_out[:, -1, :]

        out = self.dropout(last_out)
        output = self.fc(out)

        return output


class PositionalEncoding(nn.Module):
    """Transformer位置编码"""

    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        # 计算位置编码
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() *
                           (-torch.log(torch.tensor(10000.0)) / d_model))

        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # [1, max_len, d_model]

        self.register_buffer('pe', pe)

    def forward(self, x):
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


def get_model(model_name='lstm', **kwargs):
    """
    根据模型名称获取模型实例

    Args:
        model_name: 模型名称，可选 'lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer'
        **kwargs: 模型参数

    Returns:
        model: 模型实例
    """
    model_map = {
        'lstm': BaseLSTM,
        'gru': GRUModel,
        'bilstm': lambda **kw: BaseLSTM(bidirectional=True, **kw),
        'cnn_lstm': CNNLSTMModel,
        'transformer': TransformerModel
    }

    if model_name not in model_map:
        raise ValueError(f"未知模型: {model_name}，可选: {list(model_map.keys())}")

    return model_map[model_name](**kwargs)


if __name__ == "__main__":
    # 测试模型
    batch_size = 32
    seq_len = 30
    input_dim = 20
    output_dim = 10

    # 测试输入
    test_input = torch.randn(batch_size, seq_len, input_dim)

    # 测试所有模型
    for model_name in ['lstm', 'gru', 'bilstm', 'cnn_lstm', 'transformer']:
        print(f"\n测试 {model_name} 模型...")

        if model_name == 'bilstm':
            model = get_model('lstm', input_dim=input_dim, bidirectional=True)
        else:
            model = get_model(model_name, input_dim=input_dim)

        output = model(test_input)
        print(f"输入形状: {test_input.shape}")
        print(f"输出形状: {output.shape}")
        print(f"模型参数量: {sum(p.numel() for p in model.parameters()):,}")