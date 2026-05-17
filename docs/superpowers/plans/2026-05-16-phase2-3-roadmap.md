# Phase 2-3 后续开发路线图

> **制定日期**: 2026-05-16 | **基于**: Phase 1 完成状态
>
> Phase 1 全部 16 个任务已完成 ✅ — 数据管道、4 模型训练 (LSTM 最优)、FastAPI 端点、前端预测叠加图均可正常运行。

---

## Phase 1 完成状态总结

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据采集 | ✅ | akshare → PostgreSQL，增量更新，重试机制 |
| 数据清洗 | ✅ | 滚动 StandardScaler，MA/MACD/RSI14/时间编码 |
| 模型训练 | ✅ | LSTM/GRU/CNN-LSTM/Transformer，LSTM 最优 (val_loss=0.000129) |
| API 端点 | ✅ | /health, /predict, /recommend, /stock/{code} |
| 前端展示 | ✅ | Vue3+ECharts，K线+预测叠加，推荐列表，个股搜索 |
| 安全性 | ✅ | SQL 参数化查询，CORS 配置 |

**已知限制** (Phase 1 scope):
- 仅 3 只精选个股 (000001/000002/000004)
- 推荐系统置信度/风险评分硬编码为常量 (0.7/0.3)
- batch_predict 硬编码 LIMIT 10 只
- 无历史预测追踪/回测
- auto_trainer.run_training() 为哑实现
- 前端用户系统按钮非功能性

---

## Phase 2: 核心能力强化 (预计 18 天)

### Task 2.1: 模型预测质量改进 [P0] [4天]

**问题**: 当前置信度和风险评分硬编码为常量，缺乏实际意义；预测仅覆盖 10 只股票。

**Files:** `recommendation_system.py`, `train_src/train.py`, `metrics.py`

- [ ] **2.1.1 基于模型不确定性计算置信度**
  - 回归模式：使用预测序列的标准差/方差作为不确定性度量，映射到 [0,1] 置信度区间
  - 分类模式：使用 softmax 概率最大值作为置信度
  - 移除 `_predict_with_model()` 中硬编码的 `confidence=0.7`

- [ ] **2.1.2 基于波动率计算风险评分**
  - 使用最近 30 日历史波动率 (std of daily returns) 计算风险
  - 归一化到 [0,1] 区间，低波动→低风险
  - 移除硬编码的 `risk_score=0.3`

- [ ] **2.1.3 移除 batch_predict 硬编码 LIMIT**
  - 将 `if processed >= 10: break` 改为可配置参数 `max_stocks`
  - `/api/recommend` 的 `stock_list LIMIT 20` 改为可配置

- [ ] **2.1.4 验证 & Commit**
  ```bash
  curl -X POST http://localhost:8000/api/predict -H "Content-Type: application/json" \
    -d '{"ts_code":"000001"}' | python -m json.tool
  # 期望: confidence 和 risk_score 为实际计算值，非固定 0.7/0.3
  ```

---

### Task 2.2: 历史预测追踪 & 评估 [P0] [3天]

**问题**: 前端"历史预测"页面显示"功能开发中"，无法评估模型长期表现。

**Files:** `recommendation_system.py`, `app/main.py`, `utils/tables.py`, `frontend/static/js/app.js`

- [ ] **2.2.1 启用 recommendations 表持久化**
  - 取消 `save_recommendations()` 中注释掉的 `upsert` 代码
  - 在 `utils/tables.py` 添加 `recommendations` 表 schema

- [ ] **2.2.2 新增 `/api/history` 端点**
  - 参数: `start_date`, `end_date`, `ts_code`(可选), `limit`
  - 返回历史预测记录 + 实际收益对比 (需连接 K 线数据获取真实结果)
  - 计算命中率/平均误差统计

- [ ] **2.2.3 实现 evaluate_recommendations()**
  - 当前是 `TODO STUB`，返回 zeros
  - 实现: 查询 predictions 表中 past_date 的预测 + actual return from daily_kline
  - 计算方向准确率、MSE、RMSE

- [ ] **2.2.4 前端历史页面接入真实数据**
  - `loadHistory()` 当前返回 `historyData.value = []`
  - 改为调用 `/api/history`，渲染表格和统计卡片
  - 误差和方向正确标记用颜色区分

---

### Task 2.3: 自动训练管道 [P0] [3天]

**问题**: `auto_trainer.run_training()` 是哑实现，返回 mock 数据。模型无法自动更新。

**Files:** `auto_trainer.py`, `main.py`, `app/main.py`

- [ ] **2.3.1 实现真实的 run_training()**
  - 调用 `train_src/train.py` 的 `main()` 进行实际训练
  - 传入当前最佳模型的参数作为继续训练的起点
  - 支持 fine-tuning 模式 (从已有 checkpoint 加载权重继续训练)

- [ ] **2.3.2 实现 should_retrain() 真实判断逻辑**
  - 检查模型年龄 (max_age_days)
  - 检查最新数据的预测表现 (方向准确率是否 < threshold)
  - 检查数据增量 (新增交易日 > min_new_days)

- [ ] **2.3.3 集成 APScheduler 定时任务**
  - 在 FastAPI startup 中启动调度器
  - 每交易日 17:30: 数据更新 → 清洗 → 评估 → (如需)重训练 → 新预测
  - 添加 `/api/admin/train-status` 端点查看训练状态

- [ ] **2.3.4 验证**
  ```bash
  # 手动触发自动训练检查
  python -c "from auto_trainer import AutoTrainer; at = AutoTrainer(None); at.run_daily_check()"
  ```

---

### Task 2.4: 扩展股票覆盖 [P1] [2天]

**问题**: 仅覆盖 3 只股票，推荐列表缺乏多样性。

**Files:** `data_sync.py`, `main.py`, `config.yaml`

- [ ] **2.4.1 批量同步沪深300成分股数据**
  - 在 `data_sync.py` 中添加 `sync_index_constituents(index_code="000300")` 方法
  - 获取沪深300成分股列表 → 分批同步原始数据 → 清洗

- [ ] **2.4.2 修改推荐系统覆盖范围**
  - `/api/recommend` 不再 LIMIT 20，改为 `LIMIT 300`
  - `batch_predict` 添加进度日志

- [ ] **2.4.3 添加行业分散逻辑**
  - `generate_recommendations()` 中已注释的行业分散代码取消注释
  - 同行业最多推荐 top_k 只，确保多样性

---

### Task 2.5: 测试框架 + 代码质量 [P1] [3天]

**问题**: 10 个 `test_*.py` 是独立脚本，无 pytest 框架，无 CI。

**Files:** 新建 `tests/` 目录, `.github/workflows/`

- [ ] **2.5.1 迁移到 pytest**
  - 创建 `tests/` 目录，将现有 test_*.py 改造为 pytest 测试函数
  - `tests/test_data_pipeline.py`, `tests/test_models.py`, `tests/test_api.py`, `tests/test_recommendation.py`

- [ ] **2.5.2 添加模型评估测试**
  - 测试模型加载/推理一致性
  - 测试数据加载器输出形状
  - 测试分类/回归模式切换

- [ ] **2.5.3 添加 API 集成测试**
  - 使用 `fastapi.testclient.TestClient` 测试所有端点
  - Mock 数据库连接，测试异常路径

- [ ] **2.5.4 GitHub Actions CI**
  - `.github/workflows/ci.yml`: ruff lint + pytest + 模型加载 smoke test
  - 非 GPU 环境，仅 CPU 推理验证

---

### Task 2.6: 前端体验优化 [P1] [3天]

**Files:** `frontend/templates/index.html`, `frontend/static/js/app.js`

- [ ] **2.6.1 自选股关注列表**
  - 浏览器 localStorage 存储用户自选股票列表
  - 首页快速查看自选股最新预测
  - 添加/移除自选股按钮

- [ ] **2.6.2 K 线图增强**
  - 添加成交量柱状图 (volumn sub-chart)
  - MACD 指标子图
  - 支持多股票对比 (overlay 模式)

- [ ] **2.6.3 移动端响应式适配**
  - K 线图移动端手势 (缩放/平移)
  - 表格横向滚动优化
  - 推荐卡片适配小屏

- [ ] **2.6.4 前端构建优化**
  - 将 CDN 引用的 Vue3/ECharts/Bootstrap 改为本地打包
  - 减少首屏加载时间

---

## Phase 3: 高级特性 (预计 22 天)

### Task 3.1: 回测引擎 [P0] [5天]

**问题**: 无法评估模型在历史数据上的真实表现。这是量化交易系统的核心组件。

**Files:** 新建 `backtest/` 模块

- [ ] **3.1.1 回测引擎核心**
  - `backtest/engine.py`: 时间顺序遍历历史数据，模拟每日预测→持仓→平仓循环
  - 支持配置: 持仓周期 (N天)、选股数量 (top_k)、止损/止盈
  - 交易成本建模 (佣金 0.03% + 印花税 0.1%)

- [ ] **3.1.2 回测指标**
  - 累计收益率曲线、年化收益率、夏普比率、最大回撤、胜率
  - 基准对比 (沪深300 同期表现)
  - 集成 `metrics.py` 中已有指标

- [ ] **3.1.3 API 端点**
  - `POST /api/backtest`: 触发回测任务 (async)
  - `GET /api/backtest/{task_id}`: 查询回测进度/结果
  - 返回收益曲线数据供前端渲染

- [ ] **3.1.4 前端回测面板**
  - 参数配置表单 (日期范围、选股数、持仓周期)
  - 收益曲线对比图 (策略 vs 基准)
  - 月度/年度收益热力图

---

### Task 3.2: 多模型集成预测 [P1] [3天]

**问题**: 当前仅使用单个 LSTM 模型，未利用其他模型的知识。

**Files:** `recommendation_system.py`, 新建 `ensemble.py`

- [ ] **3.2.1 模型集成模块**
  - `ensemble.py`: 加载多个模型 (LSTM/GRU/CNN-LSTM/Transformer)
  - 等权重平均 / 加权平均 (基于 val_loss) 两种融合策略
  - 预测方差作为不确定性估计，用于置信度计算

- [ ] **3.2.2 集成模式开关**
  - `RecommendationSystem` 支持 `ensemble_mode=True`
  - 配置文件 `config.yaml` 添加 `ensemble` 配置段

- [ ] **3.2.3 对比评估**
  - 回测单模型 vs 集成模型表现
  - 记录到 `output/ensemble_comparison.json`

---

### Task 3.3: 多维度因子分析 [P1] [4天]

**问题**: 当前仅使用技术面特征 (价格+成交量)，缺乏基本面、情绪面数据。

**Files:** 新建 `factors/` 模块

- [ ] **3.3.1 基本面因子**
  - 通过 akshare 获取 PE/PB/ROE/ROA/营收增长率
  - `factors/fundamental.py`: 定期同步到 PostgreSQL
  - 作为模型输入特征的扩展维度

- [ ] **3.3.2 情绪面因子**
  - 通过 akshare 获取个股新闻/公告
  - `factors/sentiment.py`: SnowNLP 情感分析 → 每日情绪得分
  - 作为模型辅助特征

- [ ] **3.3.3 因子有效性验证**
  - IC (Information Coefficient) / IR (Information Ratio) 分析
  - 单因子分层回测
  - 因子相关性矩阵

---

### Task 3.4: 模型架构升级 [P2] [4天]

**问题**: 当前 LSTM 为基础架构，可尝试更先进的时序模型。

**Files:** `train_src/model.py`

- [ ] **3.4.1 Informer 模型**
  - 针对长序列预测的 ProbSparse self-attention
  - 适合处理 30+ 天序列长度

- [ ] **3.4.2 增量学习支持**
  - 从已有 checkpoint 继续训练
  - 仅在新数据上 fine-tune (冻结底层，更新顶层)
  - 避免每次全量重训练

- [ ] **3.4.3 Monte Carlo Dropout**
  - 推理时保持 dropout 开启，多次采样
  - 预测分布 → 更准确的不确定性估计
  - 替代当前单一前向传播

---

### Task 3.5: 容器化部署 [P2] [3天]

**问题**: 当前无容器化方案，部署依赖手动环境配置。

**Files:** 新建 `Dockerfile`, `docker-compose.yml`, `nginx.conf`

- [ ] **3.5.1 Dockerfile**
  - 多阶段构建: PyTorch CPU 基础镜像 + 应用代码
  - 健康检查、优雅关闭

- [ ] **3.5.2 docker-compose.yml**
  - 服务: api (FastAPI), scheduler (APScheduler), db (PostgreSQL), redis (缓存)
  - nginx 反向代理配置
  - 数据卷持久化 (models, logs, postgres_data)

- [ ] **3.5.3 环境变量化配置**
  - 将所有 config.yaml 中的敏感配置迁移到环境变量
  - 兼容 docker-compose + K8s ConfigMap

---

### Task 3.6: 通知 & 告警 [P2] [3天]

**Files:** 新建 `notifications/` 模块, `frontend/`

- [ ] **3.6.1 WebSocket 实时推送**
  - 每日推荐结果推送
  - 自选股价格预警 (突破 MA/涨跌幅阈值)
  - 训练任务状态推送

- [ ] **3.6.2 多渠道通知**
  - 邮件通知 (SMTP)
  - 企业微信机器人 webhook
  - 浏览器 Notification API

- [ ] **3.6.3 异常告警**
  - 数据源故障 (akshare 连续失败 N 次)
  - 模型表现劣化 (方向准确率跌破阈值)
  - 数据库连接异常

---

## 优先级矩阵

| 优先级 | 任务 | 工时 | 影响 | 依赖 |
|--------|------|------|------|------|
| **P0** | 2.1 预测质量改进 | 4d | 直接提升推荐准确度 | 无 |
| **P0** | 2.2 历史预测追踪 | 3d | 可量化评估模型表现 | 2.1 |
| **P0** | 2.3 自动训练管道 | 3d | 模型可持续更新 | 2.1 |
| **P0** | 3.1 回测引擎 | 5d | 量化验证策略有效性 | 2.2 |
| **P1** | 2.4 扩展股票覆盖 | 2d | 推荐多样性、更广适用 | 2.1 |
| **P1** | 2.5 测试框架+CI | 3d | 代码质量保障 | 2.1 |
| **P1** | 2.6 前端体验优化 | 3d | 用户体验 | 无 |
| **P1** | 3.2 多模型集成 | 3d | 预测鲁棒性 | 2.1 |
| **P1** | 3.3 多维度因子 | 4d | 预测信息量 | 2.1 |
| **P2** | 3.4 模型架构升级 | 4d | 预测精度上限 | 3.2 |
| **P2** | 3.5 容器化部署 | 3d | 可维护性 | 2.3 |
| **P2** | 3.6 通知告警 | 3d | 用户体验 | 2.3 |

---

## 建议执行顺序

```
Week 1-2:  2.1 预测质量 → 2.2 历史追踪 → 2.4 扩展覆盖
Week 3:    2.3 自动训练管道 → 2.5 测试框架
Week 4-5:  3.1 回测引擎
Week 6:    2.6 前端优化 → 3.2 多模型集成
Week 7-8:  3.3 多维度因子 → 3.4 模型架构
Week 9:    3.5 容器化 → 3.6 通知告警
```

**总工时估计**: ~40 天 (Phase 2: 18天 + Phase 3: 22天)

---

## Risk Analysis

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| akshare API 不稳定/限流 | 高 | 数据更新失败 | 多重试+代理池+缓存备用数据 |
| 模型过拟合 (仅3只训练) | 高 | 泛化差 | 扩展沪深300覆盖 + L2正则 |
| 回测过拟合 (幸存者偏差) | 中 | 实盘表现远差于回测 | 样本外测试 + 前向验证 |
| GPU 资源不足 | 低 | 训练慢 | 全部模型支持 CPU 推理，训练可外接 GPU |
| 沪深300 全量数据清洗 OOM | 低 | 清洗中断 | 分批处理 + 流式写入 |
