# Phase 1 实现计划 — 方案 C：混合分阶段并行

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通从数据到预测的完整链路，修复关键 bug，用 3 只精选个股训练 4 个模型，选出最优接入前端展示。

**Architecture:** 三阶段推进。阶段一修复代码缺陷和补齐数据，阶段二清洗+训练四模型对比选优，阶段三将最优模型接入推荐系统和 FastAPI，前端替换 mock 数据展示真实预测。

**Tech Stack:** Python 3.8+, PyTorch, PostgreSQL, FastAPI, Vue 3 + ECharts

---

## Phase 1: 准备 & 修复

### Task 1: 修复 is_cleaned() SQL 注入 [CRITICAL]

**Files:**
- Modify: `data_process/clean_normalize.py:277-284`

- [ ] **Step 1: 将 f-string SQL 改为参数化查询，加空结果保护**

将第 277-284 行：
```python
def is_cleaned(ts_code, train_date):
    sql = f"""SELECT close_clean FROM daily_kline WHERE ts_code = '{ts_code}' AND trade_date = '{train_date}' ORDER BY trade_date DESC"""
    date = postgres.select(sql)[0]['close_clean']
    print(f"ts_code: {ts_code}, date: {date}, type: {type(date)}")
    if date:
        return True
    else:
        return False
```

替换为：
```python
def is_cleaned(ts_code, train_date):
    sql = """SELECT close_clean FROM daily_kline WHERE ts_code = %s AND trade_date = %s ORDER BY trade_date DESC"""
    rows = postgres.select(sql, [ts_code, train_date])
    if not rows:
        return False
    val = rows[0]['close_clean']
    return val is not None
```

- [ ] **Step 2: 验证修复 — 脚本语法检查**

```bash
python -c "from data_process.clean_normalize import is_cleaned; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add data_process/clean_normalize.py
git commit -m "fix: replace f-string SQL with parameterized query in is_cleaned()"
```

---

### Task 2: 硬编码日期改为动态

**Files:**
- Modify: `data_process/clean_normalize.py:309-310`

- [ ] **Step 1: 将 `'2025-09-30'` 改为 `date.today()`**

将第 309-310 行：
```python
if not is_cleaned(ts_code, '2025-09-30'):
    clean_data = clean_one_stock(ts_code, first_date, '2025-09-30')
```

替换为：
```python
today = date.today().strftime('%Y-%m-%d')
if not is_cleaned(ts_code, today):
    clean_data = clean_one_stock(ts_code, first_date, today)
```

并在文件顶部确认 `from datetime import date` 已导入（检查 line ~13）。

- [ ] **Step 2: 验证**

```bash
python -c "from data_process.clean_normalize import date; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add data_process/clean_normalize.py
git commit -m "fix: replace hardcoded date 2025-09-30 with dynamic date.today()"
```

---

### Task 3: 更新交易日历

- [ ] **Step 1: 运行 trade_date 更新命令**

```bash
python main.py update --trade-date
```

验证 trade_date 最新日期覆盖到今天：
```bash
python -c "
from utils.db_conn import postgres
r = postgres.select('SELECT MAX(trade_date) FROM trade_date')
print(f'trade_date max: {r[0][\"max\"]}')
"
```

- [ ] **Step 2: Commit (如 trade_date 表有变更则记录)**

```bash
git add -A && git commit -m "chore: update trade_date calendar to latest"
```

---

### Task 4: 增量补齐精选个股缺失数据

- [ ] **Step 1: 对 000001, 000002, 000004 增量拉取**

```bash
python main.py update --stock-kline --ts-codes 000001,000002,000004
```

注意：此命令会逐支拉取缺失区间，间隔 2-3 秒避免限流。如果数据已是最新（到 2026-02-27），则自动跳过。

- [ ] **Step 2: 验证数据完整性**

```bash
python -c "
from utils.db_conn import postgres
for code in ['000001', '000002', '000004']:
    r = postgres.select('SELECT MAX(trade_date) as md, COUNT(*) as cnt FROM daily_kline WHERE ts_code = %s', [code])
    print(f'{code}: {r[0][\"cnt\"]} rows, latest={r[0][\"md\"]}')
"
```

---

### Task 5: 清理冗余文件和旧模块

- [ ] **Step 1: 删除冗余目录和文件**

```bash
rm -rf get_exchange_data/ get_tranning_data/
rm -f data_process/sql_utils.py
rm -f data_process/raw_data_utils.py.backup
rm -f train_src/dataset.py.backup
rm -f train_src/model.py.backup
rm -f test_output.txt
```

- [ ] **Step 2: 确认无残留引用**

```bash
grep -r "get_exchange_data\|get_tranning_data\|sql_utils" --include="*.py" . || echo "No references found - clean"
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: remove redundant old modules and backup files"
```

---

## Phase 2: 核心训练

### Task 6: 清洗精选个股数据

- [ ] **Step 1: 对 3 只股票运行清洗管道**

```bash
python main.py clean --ts-codes 000001,000002,000004 --start-date 2020-01-01 --end-date 2026-05-06
```

- [ ] **Step 2: 验证清洗结果**

```bash
python -c "
from utils.db_conn import postgres
for code in ['000001', '000002', '000004']:
    r = postgres.select('SELECT COUNT(*) as total, SUM(CASE WHEN close_clean IS NULL THEN 1 ELSE 0 END) as nulls FROM daily_kline WHERE ts_code = %s', [code])
    print(f'{code}: {r[0][\"total\"]} rows, {r[0][\"nulls\"]} nulls')
"
```

期望：nulls = 0（或极少，仅边界日期）。

- [ ] **Step 3: 验证 scaler_X.pkl 存在且可加载**

```bash
python -c "
import joblib
from pathlib import Path
scaler = joblib.load(Path('data_process/scaler_X.pkl'))
print(f'scaler loaded: n_features_in={scaler.n_features_in_}, scale_={scaler.scale_.shape}')
"
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: clean data for 000001/000002/000004 and save scaler"
```

---

### Task 7: 训练 LSTM 模型

- [ ] **Step 1: 运行 LSTM 训练**

```bash
python main.py train --model lstm --ts-codes 000001,000002,000004 --seq-len 30 --pred-len 10 --epochs 50 --batch-size 32 --lr 0.001 --output-dir ./output
```

- [ ] **Step 2: 记录指标**

查看 `output/logs/` 下的最新日志，记录最终 epoch 的 MSE / MAE / RMSE / 方向准确率。

---

### Task 8: 训练 GRU 模型

- [ ] **Step 1: 运行 GRU 训练**

```bash
python main.py train --model gru --ts-codes 000001,000002,000004 --seq-len 30 --pred-len 10 --epochs 50 --batch-size 32 --lr 0.001 --output-dir ./output
```

- [ ] **Step 2: 记录指标**

---

### Task 9: 训练 CNN-LSTM 模型

- [ ] **Step 1: 运行 CNN-LSTM 训练**

```bash
python main.py train --model cnn_lstm --ts-codes 000001,000002,000004 --seq-len 30 --pred-len 10 --epochs 50 --batch-size 32 --lr 0.001 --output-dir ./output
```

- [ ] **Step 2: 记录指标**

---

### Task 10: 训练 Transformer 模型

- [ ] **Step 1: 运行 Transformer 训练**

```bash
python main.py train --model transformer --ts-codes 000001,000002,000004 --seq-len 30 --pred-len 10 --epochs 50 --batch-size 32 --lr 0.001 --output-dir ./output
```

- [ ] **Step 2: 记录指标**

---

### Task 11: 模型对比 & 选优

- [ ] **Step 1: 汇总 4 模型指标，选出最优**

查看 `output/models/` 下的检查点文件，以方向准确率 ≥ 55% 为前提、选 RMSE 最低的模型。

- [ ] **Step 2: 将最优检查点复制为 best_model.pth**

```bash
cp output/models/<best_checkpoint>.pth output/models/best_model.pth
```

- [ ] **Step 3: 验证 best_model.pth 可加载**

```bash
python -c "
import torch
from train_src.model import get_model
ckpt = torch.load('output/models/best_model.pth', map_location='cpu')
args = ckpt.get('args', {})
model = get_model(model_name=args.get('model','lstm'), input_dim=args.get('input_dim',20), hidden_dim=args.get('hidden_dim',128), num_layers=args.get('num_layers',1), output_dim=args.get('pred_len',10), task_type=args.get('task_type','regression'))
model.load_state_dict(ckpt['model_state_dict'])
model.eval()
print(f'Model loaded: {args.get(\"model\")}, epoch={ckpt.get(\"epoch\")}')
"
```

- [ ] **Step 4: Commit**

```bash
git add output/models/best_model.pth && git commit -m "feat: select and save best_model.pth from 4-model comparison"
```

---

## Phase 3: 集成展示

### Task 12: 推荐系统接入真实模型

**Files:**
- Modify: `app/main.py:118`

- [ ] **Step 1: 修改 FastAPI 启动代码，传入模型路径**

将 `app/main.py` 第 118 行：
```python
recommendation_system = RecommendationSystem()
```

替换为：
```python
model_path = project_root / "output" / "models" / "best_model.pth"
if model_path.exists():
    recommendation_system = RecommendationSystem(model_path=str(model_path))
else:
    logger.warning(f"模型文件不存在: {model_path}，使用随机预测")
    recommendation_system = RecommendationSystem()
```

- [ ] **Step 2: 验证 /api/health 报告模型可用**

```bash
# 启动服务后测试
curl -s http://localhost:8000/api/health | python -m json.tool
```

期望 `model_available: true`。

- [ ] **Step 3: Commit**

```bash
git add app/main.py && git commit -m "feat: wire best_model.pth into recommendation system on startup"
```

---

### Task 13: 实现 main.py predict 命令

**Files:**
- Modify: `main.py:116-123`

- [ ] **Step 1: 实现 predict 命令**

将 `main.py` 第 116-123 行替换为：
```python
def predict(args):
    """使用模型进行批量预测"""
    from recommendation_system import RecommendationSystem
    from utils.db_conn import postgres

    model_path = args.model_path or "output/models/best_model.pth"
    rs = RecommendationSystem(model_path=model_path)

    # 获取待预测股票
    if args.ts_codes:
        codes = [c.strip() for c in args.ts_codes.split(",")]
    else:
        rows = postgres.select("SELECT DISTINCT ts_code FROM daily_kline WHERE close_clean IS NOT NULL ORDER BY ts_code LIMIT 20")
        codes = [r['ts_code'] for r in rows]

    logger.info(f"预测 {len(codes)} 只股票...")
    df = rs.batch_predict(codes, seq_len=args.seq_len, pred_len=args.pred_len)

    # 输出结果
    if df is not None and len(df) > 0:
        print("\n" + "=" * 80)
        print("预测结果 (按预期收益排序)")
        print("=" * 80)
        for _, row in df.iterrows():
            ret = row.get('predicted_return', 0)
            conf = row.get('confidence', 0)
            risk = row.get('risk_score', 0)
            direction = "▲" if ret > 0 else "▼"
            print(f"{direction} {row.get('ts_code','?'):8s} {row.get('ts_name','?'):10s} 预期收益:{ret:+.2%}  置信度:{conf:.0%}  风险:{risk:.2f}")
        print("=" * 80)
    else:
        logger.warning("预测结果为空")

    logger.info("预测完成")
```

并在 `main()` 的 argparser 中更新 predict 子命令的参数（约 line 180-186），添加 `--model-path`、`--ts-codes`、`--seq-len`、`--pred-len` 参数。

- [ ] **Step 2: 语法检查**

```bash
python -c "from main import predict; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add main.py && git commit -m "feat: implement predict CLI command with real model"
```

---

### Task 14: 前端替换模拟数据

**Files:**
- Modify: `frontend/static/js/app.js`

- [ ] **Step 1: 移除 K 线图的 mock 回退 (约 line 333-355)**

将 `loadChart()` 中 mock 数据生成逻辑替换为仅显示"No data"提示：
```javascript
// 替换 mock 回退
if (response.data && response.data.data && response.data.data.length > 0) {
    // 使用真实数据
    chartData = response.data.data;
} else {
    chartData = []; // 不再生成随机数据
}
```

- [ ] **Step 2: 移除推荐列表的 mock 回退 (约 line 261-293)**

将 `fetchRecommendations()` 中 catch 块的 hardcoded 3 条记录替换为空数组：
```javascript
.catch(error => {
    console.error('获取推荐失败:', error);
    recommendations.value = []; // 不再返回 mock 数据
    loading.value = false;
});
```

- [ ] **Step 3: 移除历史预测的 mock 数据 (约 line 616-653)**

将 `loadHistory()` 中的 30 天模拟数据生成逻辑替换为等待后端实现：
```javascript
function loadHistory() {
    // 暂时显示空列表，等待后端历史预测API
    historyData.value = [];
    historyStats.value = null;
}
```

- [ ] **Step 4: 移除自动完成的 mock 数据 (约 line 134-156)**

替换为从 `/api/recommend` 获取真实股票列表：
```javascript
async function autoCompleteStock(query) {
    // 从推荐列表获取真实股票代码
    if (query.length < 2) return [];
    try {
        const response = await axios.get('/api/recommend', { params: { top_n: 20 } });
        return (response.data.recommendations || []).map(r => ({
            code: r.ts_code,
            name: r.ts_name
        }));
    } catch {
        return [];
    }
}
```

- [ ] **Step 5: 验证 — 启动服务，浏览器测试**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
# 等待启动后访问 http://localhost:8000
```

- [ ] **Step 6: Commit**

```bash
git add frontend/static/js/app.js && git commit -m "feat: replace frontend mock data with real API responses"
```

---

### Task 15: 前端增强 — 预测趋势叠加图

**Files:**
- Modify: `frontend/templates/index.html` (K 线图区域, ~line 367-448)
- Modify: `frontend/static/js/app.js` (renderChart, ~line 386-522)

- [ ] **Step 1: 在 renderChart 中添加预测趋势线**

在 `renderChart()` 的 series 配置中，叠加一条预测收盘价折线：
```javascript
// 在原有 K 线图 series 中添加预测线
if (predictionData && predictionData.length > 0) {
    series.push({
        name: '预测趋势',
        type: 'line',
        data: predictionData, // [{xAxis: date_index, yAxis: predicted_close}]
        smooth: true,
        lineStyle: { color: '#ff6b6b', type: 'dashed', width: 2 },
        itemStyle: { color: '#ff6b6b' },
        symbol: 'diamond',
        symbolSize: 6
    });
}
```

- [ ] **Step 2: 在预测卡片中添加"查看预测详情"按钮**

在 index.html 的预测结果卡片中添加按钮，点击后调用 `/api/predict` 并渲染趋势图。

- [ ] **Step 3: Commit**

```bash
git add frontend/templates/index.html frontend/static/js/app.js
git commit -m "feat: add prediction trend overlay to K-line chart"
```

---

### Task 16: E2E 验证

- [ ] **Step 1: 启动 FastAPI 服务**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 验证所有端点**

```bash
# 健康检查
curl -s http://localhost:8000/api/health | python -m json.tool

# 单股预测
curl -s -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"ts_code":"000001","seq_len":30,"pred_len":10}' | python -m json.tool

# 推荐列表
curl -s "http://localhost:8000/api/recommend?top_n=10&max_risk=0.5&min_confidence=0.6" | python -m json.tool

# 个股 K 线数据
curl -s "http://localhost:8000/api/stock/000001?limit=30" | python -m json.tool
```

- [ ] **Step 3: 浏览器手动验证**

访问 http://localhost:8000，测试：
1. 个股预测页 — 输入 000001，点击预测
2. 今日推荐页 — 查看推荐列表
3. K 线图页 — 加载 000001 K 线图

- [ ] **Step 4: Commit (如有修正确认)**

---

## Verification Checklist

- [ ] `is_cleaned()` 使用参数化查询，无 SQL 注入风险
- [ ] `clean_normalize.py` 无硬编码日期
- [ ] `trade_date` 表覆盖到当前日期
- [ ] 000001/000002/000004 数据补齐到最新
- [ ] 冗余文件已清理 (0 个 .backup, 0 个旧模块)
- [ ] 3 只股票清洗完成，_clean 列非 NULL
- [ ] `scaler_X.pkl` 可正常加载
- [ ] 4 个模型训练完成，无报错
- [ ] `best_model.pth` 存在且可加载
- [ ] `/api/health` 返回 `model_available: true`
- [ ] `/api/predict` 返回真实预测数据（非随机数）
- [ ] `/api/recommend` 返回模型排序后的推荐
- [ ] 前端无 mock 回退
- [ ] 浏览器 E2E 验证通过
