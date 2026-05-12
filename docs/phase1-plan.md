# Phase 1：技术面模型跑通

> 创建日期：2026-04-29 | 最后更新：2026-05-12 | 状态：基本完成，收尾中

## 0. 背景

项目代码框架完整，但从未在真实数据上完整运行过——模型训练使用 Mock 数据，预测推荐返回随机数。Phase 1 目标是 **打通从数据到预测的完整链路**。

### 当前数据约束

| 约束 | 详情 | 应对 |
|------|------|------|
| 数据范围 | 仅部分 A 股，非全市场 | 先聚焦已有数据的个股（000001, 000002, 000004），后续增量扩展 |
| 数据截止 | 2024-12-31，2025 年后为占位数据（vol=0） | 增量拉取 2025-01-01 ~ 至今数据 |
| akshare 限流 | 单 IP 请求频率受限，全量拉取极慢 | 使用代理 + 分批 + tenacity 重试 |

---

## 1. 目标

将现有代码从"写了但没跑"变成"跑通且有效"，产出可用的个股预测模型和推荐结果。

---

## 2. 实施结果

### Step 1 — 数据就位 ✅ 已完成

- PostgreSQL 数据已恢复，`stock_list` 和 `daily_kline` 表有数据
- `data_sync.py` 增量同步功能完整（含速率限制、重试、批量提交）
- `trade_date` 表覆盖完整交易日历

**验收达成**：数据库连接正常，daily_kline 有真实历史数据。

### Step 2 — 数据清洗验证 ✅ 已完成

- `clean_normalize.py` 全流程跑通：交易日历对齐 → 技术指标计算（MA5/MA10/MACD/RSI14）→ 时间特征循环编码 → rolling StandardScaler
- `scaler_X.pkl` 已拟合并持久化（`data_process/scaler_X.pkl`）
- `_clean` 列写入 daily_kline 表

**验收达成**：清洗管线完整，scaler 可正常加载。

### Step 3 — 模型训练 ✅ 已完成

4 种模型全部训练完成，均使用 3 支股票（000001, 000002, 000004），统一参数 `seq_len=30, pred_len=10, epochs=50, batch_size=32`，CUDA（RTX 5060）：

| 模型 | 参数量 | 最佳 val_loss | 最佳 Epoch | 输出目录 |
|------|--------|--------------|-----------|---------|
| **LSTM** | 210K | **0.000129** | 46 | `output/lstm/` |
| CNN-LSTM | 86K | 0.000142 | 44 | `output/cnn_lstm/` |
| GRU | 158K | 0.000434 | 35 | `output/models/` |
| Transformer | 1.19M | 0.005930 | 10 | `output/transformer/` |

每个模型目录含：完整 epoch 检查点、`best_model.pth`、`last_model.pth`、loss_history.csv、训练/验证预测 CSV、training_history.json。

**验收达成**：4 个模型全部完成 50 epoch 无报错，best_model.pth 可正常加载。

### Step 4 — 预测管线打通 + Web 展示 ✅ 已完成

- LSTM 最佳模型（val_loss=0.000129）接入 `recommendation_system.py`，替换随机 fallback
- `main.py predict` CLI 命令可用
- FastAPI 6 个端点全部实现：`/`, `/api/`, `/api/health`, `POST /api/predict`, `GET /api/recommend`, `GET /api/stock/{ts_code}`
- 前端 Vue.js 3 SPA 5 个视图：首页、个股预测、今日推荐、K 线图（ECharts + MA5/MA10 + 预测趋势叠加）、历史预测
- 所有前端视图通过 Axios 连接真实 API

**验收达成**：推荐系统不再 fallback 随机数（模型可用时），前端展示真实预测结果，`/api/health` 返回模型加载状态。

API 服务通过 `uvicorn app.main:app --host 0.0.0.0 --port 8000` 运行。

### Step 5 — Bug 修复 & 代码清理 ⚠️ 部分完成

**已完成**：
- `torch.load()` 安全加固（`weights_only=True`，修复反序列化漏洞）
- `recommendation_system.py` 模型参数映射修复（CNNLSTMModel、TransformerModel、BiLSTM 构造函数参数不匹配）
- `predicted_return` falsy guard 修复（`!= null` 替代 truthy 检查）
- 前端 K 线图预测趋势线使用实际预测序列 delta

**Phase 4 安全审查通过**：Architect / Security / Code Review 三方验证通过。

---

## 3. 剩余待办（Phase 1 收尾）

以下条目优先级从高到低排列，可在进入 Phase 2 前完成或并入 Phase 2 前置工作：

| # | 条目 | 位置 | 影响 |
|---|------|------|------|
| 1 | `batch_predict()` 硬编码限制 10 支股票 | `recommendation_system.py:227` | 推荐只能覆盖 10 支 |
| 2 | 模型加载硬编码旧 GRU 路径，应改为 LSTM 最佳模型 | `app/main.py:120` | API 启动加载非最优模型 |
| 3 | `main.py server` 命令是 no-op，指向未实现的 `run_server()` | `main.py` | CLI 入口误导 |
| 4 | 置信度/风险评分为硬编码常量（0.7/0.3） | `recommendation_system.py:273-274` | 预测结果缺乏真实置信度 |
| 5 | `save_recommendations()` DB 写入被注释 | `recommendation_system.py:507` | 推荐结果未持久化 |
| 6 | `evaluate_recommendations()` 是 TODO 存根 | `recommendation_system.py:522-541` | 无法评估推荐效果 |
| 7 | `data_process/train_data_utils.py` 为空文件 | `data_process/` | 死代码 |
| 8 | `auto_trainer.py` 训练/评估为模拟实现 | `auto_trainer.py:314-357` | 自动重训练未真正打通 |
| 9 | 前端"历史预测"视图为 UI 占位 | `frontend/static/js/app.js` | 用户体验不完整 |
| 10 | 缺少 `/api/stock/autocomplete` 端点，前端用 `/api/recommend` 迂回 | `frontend/static/js/app.js:134-148` | API 设计不规范 |
| 11 | BiLSTM 模型未训练 | - | 5 种模型中缺失 1 种 |

---

## 4. 技术决策（实际结果）

| 决策 | 选择 | 实际结果 |
|------|------|---------|
| 训练执行位置 | WSL 本地（RTX 5060） | CUDA 可用，4 模型训练顺利完成 |
| 模型框架 | PyTorch（保持现有） | 5 种架构（LSTM/GRU/BiLSTM/CNN-LSTM/Transformer），4 种已训练 |
| 数据格式 | PostgreSQL（保持现有） | 连接稳定，参数化查询 |
| 前端框架 | Vue.js 3 + Bootstrap 5 + ECharts 5 | SPA 5 视图，全部对接真实 API |
| 训练范围 | 3 支股票（000001, 000002, 000004） | 训练速度快，验证了管线可行性 |
| 最佳模型 | LSTM（val_loss=0.000129） | 参数量 210K，方向准确率待评估 |
| 预测类型 | 回归（预测未来 10 日归一化收盘价） | 分类模式代码就绪但未单独训练 |

---

## 5. 下一步

Phase 1 收尾后进入 **Phase 2：产品化上线**（详见 `docs/phase2-plan.md`）。
