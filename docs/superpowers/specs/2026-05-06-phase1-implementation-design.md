# Phase 1 实施设计 — 方案 C：混合分阶段并行

> 日期：2026-05-06 | 基于：`docs/phase1-plan.md`

## 背景

数据库已恢复（13.2M 行 / 4559 只股票），但代码从未在真实数据上完整运行。清洗率仅 1.5%，推荐系统静默回退随机数。目标：打通从数据到预测的完整链路，产出可用的个股预测和推荐。

## 架构

```
数据准备(0.5天)       核心训练(2天)          集成展示(1天)
─────────────      ──────────────        ──────────────
修复 SQL 注入 ─┐                          
更新交易日历   ├──→ 清洗 3 只个股 ──→ 接入推荐系统
补齐缺失数据   │   训练 4 模型对比      实现 predict CLI
清理冗余文件 ─┘   选出 best_model      更新 API + 前端
                                        浏览器 E2E 验证
```

## 阶段一：准备 & 修复

### 1.1 修复 SQL 注入 [CRITICAL]
- **文件**: `data_process/clean_normalize.py:277-284`
- **改法**: f-string → `%s` 参数化查询
- **附带修复**: 空结果集 IndexError 保护

### 1.2 动态日期
- **文件**: `data_process/clean_normalize.py:309-310`
- **改法**: `'2025-09-30'` → `date.today().strftime('%Y-%m-%d')`

### 1.3 更新交易日历
- 命令: `python main.py update --trade-date`
- 使 trade_date 覆盖到当前日期

### 1.4 增量补齐数据
- 对 000001, 000002, 000004 补齐 2025-10-01 至今缺失
- 命令: `python main.py update --stock-kline --ts-codes 000001,000002,000004`

### 1.5 清理冗余文件
- 删除: `get_exchange_data/` `get_tranning_data/` `data_process/sql_utils.py`
- 删除: `*.backup` (3个) `test_output.txt`

## 阶段二：核心训练

### 2.1 精选个股
- 000001 (平安银行, 8557 天, 最新 2026-02-27)
- 000002 (万科 A, 8612 天)
- 000004 (国华网安, 8619 天)

### 2.2 数据清洗
- 命令: `python main.py clean --ts-codes 000001,000002,000004 --start-date 2020-01-01 --end-date 2026-05-06`
- 产出: MA5/MA10/MACD/RSI14 + scaler_X.pkl

### 2.3 模型训练
- 统一参数: `--seq-len 30 --pred-len 10 --epochs 50 --batch-size 32`
- 顺序: LSTM → GRU → CNN-LSTM → Transformer
- 每模型记录: MSE, MAE, RMSE, 方向准确率

### 2.4 选优 & 保存
- 方向准确率 ≥ 55% 的模型中选 RMSE 最低
- 保存为 `output/models/best_model.pth`

## 阶段三：集成展示

### 3.1 推荐系统接入模型
- `app/main.py:118` 初始化时传入 `model_path`
- `recommendation_system.py` 已有 `_load_model()` 方法，直接使用

### 3.2 CLI 实现
- `main.py predict` 命令: 批量预测 + 表格输出

### 3.3 前端改造
- 移除 `app.js` 中 5 处 mock 回退
- 保留 API 失败时的友好错误提示（非随机数）
- K 线图 + 预测趋势叠加

### 3.4 验证
- `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 浏览器访问 http://localhost:8000
- 验证: 预测页 / 推荐列表 / K线图 / 健康检查

## 文件改动清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `data_process/clean_normalize.py` | 修改 | SQL 注入修复 + 动态日期 |
| `main.py` | 修改 | 实现 predict 命令 |
| `app/main.py` | 修改 | 加载 best_model，健康检查报告模型状态 |
| `recommendation_system.py` | 不改 | 已有 _load_model()，只需调用方传 model_path |
| `frontend/static/js/app.js` | 修改 | 移除 mock 回退 |
| `frontend/templates/index.html` | 修改 | 预测趋势叠加图 |
| `get_exchange_data/` | 删除 | 冗余旧模块 |
| `get_tranning_data/` | 删除 | 冗余旧模块 |
| `data_process/sql_utils.py` | 删除 | 冗余旧模块 |
| `*.backup` (3个) | 删除 | 备份文件 |
