# 股票预测系统 (Stock Prediction System)

## 项目概述

这是一个基于机器学习的股票预测系统，旨在构建一个完整的LSTM预测+自动选股系统。项目目前处于开发中期阶段，已经实现了数据获取、清洗、特征工程和数据库管理等核心基础设施。

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 设置数据库
```bash
# 创建数据库表
python utils/tables.py
```

### 3. 更新数据
```bash
# 更新股票列表和日K线数据
python main.py update --all
```

### 4. 清洗数据
```bash
# 清洗所有股票数据
python main.py clean --all-stocks
```

### 5. 训练模型
```bash
# 训练LSTM模型
python main.py train --model lstm --ts-codes 000001,000002 --epochs 10
```

详细安装指南请参考 [INSTALL.md](INSTALL.md)

## 目录结构

```
stock_predict/
├── 00-reference/              # 参考文献和学术论文
├── get_exchange_data/         # 数据获取模块（akshare API）
│   ├── get_stock_exchange_data.py  # 获取股票数据并存入MySQL
│   ├── sql_func.py            # MySQL数据库操作函数
│   └── test.py                # 测试文件
├── get_tranning_data/         # 数据清洗和预处理模块
│   ├── clean_stock_data.py    # 清洗股票数据（基础框架）
│   ├── name.py                # 股票名称拼音处理
│   └── output.xlsx            # 输出文件
├── data_process/              # 数据处理和特征工程核心模块
│   ├── stock.py               # Stock类定义（骨架）
│   ├── raw_data_utils.py      # 原始数据更新工具（从akshare→PostgreSQL）
│   ├── clean_normalize.py     # 数据清洗和归一化流水线（核心）
│   ├── train_data_utils.py    # 训练数据工具（未完善）
│   ├── sql_utils.py           # MySQL工具函数
│   ├── scaler_X.pkl           # 归一化参数
│   └── *.yaml                 # 代理配置文件
├── utils/                     # 工具模块
│   ├── db_conn.py             # PostgreSQL数据库连接池封装
│   ├── logger.py              # 日志配置（控制台彩色+文件分割）
│   ├── tables.py              # 数据库表结构定义
│   └── __init__.py
├── train_src/                 # 模型训练源代码（LSTM/GRU/Transformer等）
├── logs/                      # 日志文件
├── readme/outline.md          # 详细项目计划和7天冲刺指南
└── 配置文件
    ├── requirements.txt       # 项目依赖
    ├── pyproject.toml         # 项目构建配置
    └── setup.cfg
```

## 技术栈

- **数据获取**: `akshare`、`requests`
- **数据库**:
  - **主数据库**: PostgreSQL（使用连接池`psycopg2`）
  - **遗留数据库**: MySQL（`pymysql`）
- **数据处理**: `pandas`、`numpy`、`scikit-learn`（归一化）
- **工具库**:
  - `colorlog`（彩色日志）
  - `tenacity`（重试机制）
  - `joblib`（模型保存）
  - `sqlalchemy`（ORM）

## 数据流程

1. **数据获取** (`raw_data_utils.py`)
   - 从akshare API获取A股列表、日K线数据
   - 支持代理切换和防封机制
   - 数据存入PostgreSQL的`daily_kline`表

2. **数据清洗** (`clean_normalize.py`)
   - 停牌日补全（对齐交易所日历）
   - 技术指标计算（MA5/MA10/MACD/RSI14）
   - 日期循环编码（月/日/星期sin/cos）
   - 滚动窗口归一化（保存scaler到`scaler_X.pkl`）

3. **数据库设计** (`utils/tables.py`)
   - `stock_list`: 股票基本信息表
   - `daily_kline`: 日K线数据表（包含raw和clean字段）
   - `trade_date`: 交易日历表

## 当前状态

### ✅ 已完成部分

- 数据获取管道（akshare → PostgreSQL）
- 数据库连接池和表结构
- 日志系统
- 数据清洗和归一化框架

### ⚠️ 已知问题

1. **项目不完整**
   - `main.py`是PyCharm示例代码，非真实入口
   - `train_src/`目录为空，缺乏模型训练代码
   - 许多函数只有骨架或注释掉的代码

2. **数据库混乱**
   - 同时使用PostgreSQL和MySQL，存在不一致
   - PostgreSQL配置硬编码在`utils/db_conn.py:203-211`
   - MySQL配置硬编码在多个文件中

3. **安全隐患**
   - 数据库密码硬编码（PostgreSQL: '123456', MySQL: 'admin'）
   - 代理配置暴露在yaml文件中

4. **代码质量问题**
   - 缺乏错误处理和输入验证
   - SQL注入风险（如`sql_utils.py:20`使用f-string拼接）
   - 函数命名不一致（`get_tranning_data`应为`get_training_data`）

5. **配置管理**
   - 日期硬编码（如`clean_normalize.py:230`的`"2025-09-30"`）
   - 代理配置分散在多个地方

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 数据库设置

1. 安装并启动PostgreSQL
2. 创建数据库 `stock`
3. 更新`utils/db_conn.py`中的数据库连接配置

### 运行数据管道

```python
# 更新股票列表
python data_process/raw_data_utils.py - update_stock_list_data

# 更新日K线数据
python data_process/raw_data_utils.py - update_stocks_daily_kline

# 清洗和归一化数据
python data_process/clean_normalize.py
```

## 开发计划

详细开发计划请参考 [readme/outline.md](readme/outline.md)，该文件提供了一个完整的7天冲刺指南，包括：

1. Day-0: 前置准备（云环境配置）
2. Day-1: 数据管道（数据同步和特征工程）
3. Day-2: 单机双卡训练（LSTM模型实现）
4. Day-3: 自动再训练 & 每日预测
5. Day-4: 监控与回测
6. Day-5: 网页Demo（Flask + ECharts）
7. Day-6: 模型上线（PAI-EAS部署）

## 改进建议

### 短期优先级
1. 创建统一配置文件（如`.env`或`config.yaml`）
2. 修复SQL注入漏洞
3. 实现`train_src/`中的模型训练代码
4. 创建统一的入口脚本

### 中期优化
1. 统一数据库（推荐使用PostgreSQL）
2. 添加单元测试
3. 实现数据验证和监控
4. 完善错误处理和重试机制

### 架构建议
1. 按照`outline.md`的7天计划继续开发
2. 考虑使用消息队列处理数据更新
3. 添加模型版本管理和A/B测试
4. 实现自动化的每日数据更新和模型再训练

## 许可证

[待添加]

## 贡献指南

[待添加]

---

**注意**: 本项目处于活跃开发阶段，API和架构可能会有较大变化。