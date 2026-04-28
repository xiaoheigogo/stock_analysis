# 安装和设置指南

## 环境要求

- Python 3.8 或更高版本
- PostgreSQL 12+ (用于数据存储)
- Git (用于版本控制)

## 1. 克隆项目

```bash
git clone <项目地址>
cd stock_predict
```

## 2. 创建Python虚拟环境

```bash
# 使用conda
conda create -n stock_predict python=3.8
conda activate stock_predict

# 或使用venv
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

## 3. 安装依赖

### 基础依赖
```bash
pip install -r requirements.txt
```

### PyTorch安装（根据系统选择）

#### 有CUDA的Linux/Windows
```bash
# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### CPU版本
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

#### Mac (Apple Silicon)
```bash
pip install torch torchvision torchaudio
```

### 验证安装
```bash
python -c "import torch; print(f'PyTorch版本: {torch.__version__}'); print(f'CUDA可用: {torch.cuda.is_available()}')"
```

## 4. 数据库设置

### 安装PostgreSQL

#### Windows
1. 下载并安装 [PostgreSQL](https://www.postgresql.org/download/windows/)
2. 安装时记住设置的密码
3. 安装 pgAdmin（可选，用于图形化管理）

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Mac
```bash
brew install postgresql
brew services start postgresql
```

### 创建数据库和用户

```bash
# 登录PostgreSQL
sudo -u postgres psql

# 创建数据库
CREATE DATABASE stock;

# 创建用户（如果尚未创建）
CREATE USER stock_user WITH PASSWORD 'your_password';

# 授予权限
GRANT ALL PRIVILEGES ON DATABASE stock TO stock_user;

# 退出
\q
```

### 配置数据库连接

编辑 `.env` 文件（如果不存在则创建）：

```bash
# 复制示例配置
cp .env.example .env
```

编辑 `.env` 文件：

```env
# PostgreSQL配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=stock
POSTGRES_USER=postgres
POSTGRES_PASSWORD=123456
POSTGRES_MINCONN=1
POSTGRES_MAXCONN=50

# MySQL配置（可选）
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DB=stock_prediction
MYSQL_USER=root
MYSQL_PASSWORD=admin
```

## 5. 初始化数据库表

```bash
# 运行表创建脚本
python utils/tables.py
```

这会创建以下表：
- `stock_list`: 股票基本信息
- `daily_kline`: 日K线数据
- `trade_date`: 交易日历

## 6. 数据获取和清洗

### 更新数据
```bash
# 更新所有数据
python main.py update --all

# 或分别更新
python main.py update --trade-date      # 交易日历
python main.py update --stock-list      # 股票列表
python main.py update --index-kline     # 指数K线
python main.py update --stock-kline     # 股票K线
```

### 清洗数据
```bash
# 清洗所有股票
python main.py clean --all-stocks

# 清洗指定股票
python main.py clean --ts-codes 000001,000002
```

## 7. 模型训练

### 快速开始
```bash
# 使用默认参数训练LSTM模型
python main.py train --model lstm --ts-codes 000001,000002 --epochs 10
```

### 完整训练示例
```bash
python main.py train \
  --model lstm \
  --ts-codes 000001,000002,000003,000004 \
  --seq-len 30 \
  --pred-len 10 \
  --epochs 50 \
  --batch-size 32 \
  --output-dir ./output
```

### 训练参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | 模型类型：lstm, gru, bilstm, cnn_lstm, transformer | lstm |
| `--ts-codes` | 股票代码列表，逗号分隔 | 000001,000002 |
| `--seq-len` | 输入序列长度（历史天数） | 30 |
| `--pred-len` | 预测序列长度（未来天数） | 10 |
| `--epochs` | 训练轮数 | 50 |
| `--batch-size` | 批量大小 | 32 |
| `--output-dir` | 输出目录 | ./output |

## 8. 使用训练好的模型进行预测

```bash
# 预测功能（待实现）
python main.py predict --model-path ./output/models/best_model.pth --ts-codes 000001 --days 10
```

## 9. 启动Web服务器

```bash
# Web服务器（待实现）
python main.py server --host 0.0.0.0 --port 8000 --debug
```

## 10. 云部署（阿里云PAI）

### 前提条件
1. 阿里云账号
2. 开通PAI、OSS、DLC、EAS服务
3. 配置AccessKey

### 部署步骤
1. 将代码上传到OSS
2. 配置PAI-DLC训练任务
3. 部署PAI-EAS推理服务
4. 配置自动化流水线

详细步骤参考 [云端部署指南](readme/cloud_deployment.md)（待创建）

## 故障排除

### 常见问题

#### 1. 数据库连接失败
```bash
# 检查PostgreSQL服务状态
sudo systemctl status postgresql

# 检查连接配置
python -c "from utils.db_conn import postgres; print(postgres._params)"
```

#### 2. PyTorch安装失败
```bash
# 使用清华镜像
pip install torch torchvision torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 3. 内存不足
- 减少 `batch_size`
- 减少 `seq_len`
- 使用更小的模型

#### 4. 数据获取失败
- 检查网络连接
- 检查代理设置
- 降低请求频率

### 日志查看

```bash
# 查看应用日志
tail -f logs/stock.log

# 查看训练日志
tail -f output/logs/training_history.json
```

## 开发指南

### 项目结构
```
stock_predict/
├── data_process/     # 数据处理
├── train_src/        # 模型训练
├── utils/           # 工具函数
├── config.yaml      # 配置文件
├── main.py         # 主入口
└── requirements.txt # 依赖列表
```

### 添加新模型
1. 在 `train_src/model.py` 中定义模型类
2. 在 `get_model()` 函数中注册模型
3. 更新 `train.py` 中的参数解析器

### 添加新特征
1. 在 `data_process/clean_normalize.py` 中添加特征计算函数
2. 更新 `feature_columns` 配置
3. 重新清洗数据

## 获取帮助

- 查看详细文档：[README.md](README.md)
- 查看需求文档：[readme/requirements.md](readme/requirements.md)
- 查看开发计划：[readme/outline.md](readme/outline.md)

如遇问题，请提供以下信息：
1. 错误信息
2. 操作系统和Python版本
3. 相关配置
4. 日志文件内容