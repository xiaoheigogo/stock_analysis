# Phase 1：技术面模型跑通

> 创建日期：2026-04-29 | 状态：设计完成，待实施

## 0. 背景

项目代码框架完整，但从未在真实数据上完整运行过——模型训练使用 Mock 数据，预测推荐返回随机数。Phase 1 目标是 **打通从数据到预测的完整链路**。

### 当前数据约束

| 约束 | 详情 | 应对 |
|------|------|------|
| 数据范围 | 仅部分 A 股，非全市场 | 先聚焦已有数据的个股，后续增量扩展 |
| 数据截止 | 2025-09-30，近 7 个月缺失 | 增量拉取 2025-10-01 ~ 至今数据 |
| akshare 限流 | 单 IP 请求频率受限，全量拉取极慢 | 使用代理 + 分批 + tenacity 重试，拉取缺口即可 |

**数据策略**：不重拉历史数据，仅用 `data_sync.py` 增量补齐 2025-10-01 之后的缺口。老数据在旧电脑中，从 dump 文件恢复。

---

## 1. 目标

将现有代码从"写了但没跑"变成"跑通且有效"，产出可用的个股预测模型和推荐结果。

## 2. 分步计划

### Step 1 — 数据就位

**输入**：旧电脑 PostgreSQL dump 文件（用户提供）

**步骤**：
1. 从 dump 文件恢复数据到 WSL PostgreSQL
2. 验证数据量和日期覆盖
3. 补齐 2025-10-01 ~ 今日缺失数据（`data_sync.py` 增量模式）
4. 确认 `trade_date` 表覆盖完整交易日历

**验收**：
- `stock_list` 表有数据
- `daily_kline` 表覆盖至少 20 支个股，每支 200+ 交易日
- 最新数据日期 ≤ 最近 3 个交易日内

### Step 2 — 数据清洗验证

**步骤**：
1. 对真实数据运行 `clean_normalize.py` 全流程
2. 验证 MA5 / MA10 / MACD / RSI14 计算正确（抽查几支对比 akshare 源数据）
3. 检查 `scaler_X.pkl` 正确拟合和持久化
4. 修复 `is_cleaned()` 的 SQL 注入风险（f-string → 参数化查询）
5. 修复硬编码日期 `2025-09-30` → 动态 `date.today()`

**验收**：
- `daily_kline` 表中 `_clean` 列全部非 NULL
- `scaler_X.pkl` 可正常加载和反序列化

### Step 3 — 模型训练（核心）

**步骤**：
1. 用真实数据按顺序训练 4 种模型：LSTM → GRU → CNN-LSTM → Transformer
2. 统一参数：`seq_len=30, pred_len=10, epochs=50, batch_size=32`
3. 记录每个模型指标：MSE / MAE / RMSE / 方向准确率
4. 可视化对比，选出最优模型
5. 保存 `best_model.pth`（含 optimizer/scheduler 状态）
6. 训练过程日志保存到 `output/logs/`

**验收**：

| 指标 | 目标 |
|------|------|
| 所有模型完成 50 epoch | 无报错 |
| 方向准确率 | ≥ 55% |
| 单支个股预测 | < 500ms |
| best_model.pth | 存在且可加载 |

### Step 4 — 预测管线打通 + Web 展示

**步骤**：
1. 将 `best_model.pth` 接入 `recommendation_system.py`，替换随机 fallback
2. 实现 `main.py predict` 命令：真正批量预测
3. FastAPI `/api/predict` 和 `/api/recommend` 端点返回真实预测结果
4. 前端展示真实预测数据（涨跌幅、置信度、风险评分）
5. 新增前端功能：
   - 预测列表页：展示模型推荐 TOP-10
   - 个股详情页：历史 K 线 + 未来预测趋势叠加图

**验收**：
- 推荐系统不再 fallback 随机数
- 前端展示真实模型预测结果
- `/api/health` 返回模型加载状态

### Step 5 — Bug 修复 & 代码清理

**步骤**：
1. 修复 `test_db_connection.py` 的 cursor 类型问题（RealDictCursor vs tuple 索引）
2. 移除冗余旧模块：`get_exchange_data/`、`get_tranning_data/`、`sql_utils.py`
3. 更新 `README.md`（当前描述的"空模块"已实现）
4. 清理 `data_process/raw_data_utils.py.backup` 等备份文件

---

## 3. 数据拉取方案

### 增量补齐策略

```
已有数据范围: 2018-01-01 ~ 2025-09-30
缺失范围:     2025-10-01 ~ 2026-04-29 (约 140 个交易日)

步骤:
1. 先跑 trade_date 更新，获取完整交易日历
2. 对已有数据的个股，逐支拉取缺失区间
3. 每支间隔 2-3 秒，避免触发 akshare 限流
4. 使用代理池（airport.yaml / free.yaml）轮换
5. tenacity 重试：最多 5 次，指数退避
```

### 后续每日更新

```bash
# 收盘后（17:00）自动执行
python main.py update --trade-date
python main.py update --stock-kline --incremental
python main.py clean --incremental
```

---

## 4. 技术决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 训练执行位置 | WSL 本地 | 单机 GPU 足够，Phase 2 再考虑云端 |
| 模型框架 | PyTorch（保持现有） | 代码已完整，无需重写 |
| 数据格式 | PostgreSQL（保持现有） | 已配置完成，连接稳定 |
| 前端框架 | Vue.js（保持现有） | 界面已开发，只需改数据源 |
| 训练范围 | 先 HS300 成分股中已有数据的 | 控制训练时间，快速验证 |

---

## 5. Phase 1 时间估算

| 步骤 | 预计耗时 |
|------|---------|
| Step 1 数据就位 | 1 天（含 dump 导入 + 增量拉取等待） |
| Step 2 清洗验证 | 0.5 天 |
| Step 3 模型训练 | 2 天（4 个模型各训练 + 调参对比） |
| Step 4 预测管线 | 1 天 |
| Step 5 Bug 修复 | 0.5 天 |
| **合计** | **约 5 天** |

---

## 6. 下一步

Phase 1 完成后进入 **Phase 2：产品化上线**：
- 用户注册/登录（JWT）
- 会员等级与付费（微信支付接入）
- 每日自动数据更新 + 模型重训练（cron）
- 盯盘提醒（WebSocket 推送）
