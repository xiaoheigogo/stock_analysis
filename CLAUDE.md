# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A stock prediction system using deep learning models (LSTM, GRU, BiLSTM, CNN-LSTM, Transformer) for stock price forecasting and recommendation. PostgreSQL-backed with a FastAPI web frontend. The primary working directory is `stock_predict/` — all commands assume you are in that directory.

## Environment

- **Virtual env**: `venv38/` (Python 3.8)
- Activate: `source venv38/bin/activate`
- Install deps: `pip install -r requirements.txt` (install PyTorch separately — CPU: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`, CUDA 12.1: use `cu121` index)
- **Config**: `config.yaml` for DB, proxy, model params. Database credentials can also come from env vars (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`).
- **Database**: Initialize tables with `python utils/tables.py`

## Architecture

### Data Pipeline (3 stages)

1. **Acquisition** — `data_process/raw_data_utils.py` fetches A-share data via `akshare` → PostgreSQL `daily_kline` table (columns suffixed `_raw`). Includes tenacity retry logic, proxy support (`proxy_manager.py`).
2. **Cleaning** — `data_process/clean_normalize.py` aligns suspended trading days to exchange calendar, computes MA5/MA10/MACD/RSI14, encodes cyclical time features (sin/cos), applies rolling StandardScaler (saved as `data_process/scaler_X.pkl`), writes back `_clean` columns + derived indicators.
3. **Database schema** — `utils/tables.py` defines 3 tables: `stock_list` (stock metadata), `daily_kline` (raw + clean K-line data), `trade_date` (trading calendar). Each table has a `table_name`, `headers` dict, and `primary_key`.

### Model Training (`train_src/`)
- **`model.py`**: `BaseLSTM`, `GRUModel`, `CNNLSTMModel`, `TransformerModel`, `PositionalEncoding`. All support regression and classification output. Factory: `get_model(name, **kwargs)`.
- **`dataset.py`**: `StockDataset` loads from PostgreSQL, splits train/val/test by time order. Supports regression (predicts future `pred_len` normalized close prices) and classification (3-class: down/flat/up via cumulative return thresholds).
- **`train.py`**: `Trainer` class with full training loop, validation, checkpointing (best/last/periodic), learning rate scheduling (step/reduce_on_plateau/cosine), gradient clipping. Saved as `.pth` checkpoints with optimizer/scheduler state.
- `create_data_loaders()` in `dataset.py` is the canonical way to get DataLoader triples.

### Other Modules
- **FastAPI app** (`app/main.py`): REST API with /predict, /recommend, /stock/{ts_code}, /health endpoints. Mounts `frontend/` dir for static files + Jinja2 templates.
- **Recommendation system** (`recommendation_system.py`): Batch prediction + stock ranking + risk scoring + reason generation.
- **Data synchronizer** (`data_sync.py`): Smart incremental sync, missing data detection, data quality checks, retry logic.
- **Auto-trainer** (`auto_trainer.py`): Model version management, performance monitoring, automatic retraining triggers, version promotion/deprecation.
- **Proxy manager** (`proxy_manager.py`): Multi-source proxy config (Clash YAML, env vars, direct lists) with health checking and failover.
- **DB layer** (`utils/db_conn.py`): Singleton `Postgres` class with connection pooling (`psycopg2`), context-managed cursors, typed SELECT/upsert/execute helpers. Module-level `postgres` instance is the global handle.

### Feature columns (hardcoded in `train_src/dataset.py`, ~line 63)
20 features: `open_clean`, `high_clean`, `low_clean`, `close_clean`, `volumn_clean`, `amount_clean`, `amplitude_clean`, `pct_change_clean`, `change_clean`, `turnover_clean`, `ma5`, `ma10`, `macd_dif`, `rsi14`, `month_sin`, `month_cos`, `day_sin`, `day_cos`, `dow_sin`, `dow_cos`.

## Common Commands

### Data operations
```bash
# Update all data (incremental)
python main.py update --all

# Update specific types only
python main.py update --trade-date
python main.py update --stock-list
python main.py update --stock-kline --ts-codes 000001,000002
python main.py update --stock-kline --full-update   # full refresh

# Clean/normalize data
python main.py clean --all-stocks
python main.py clean --ts-codes 000001,000002 --start-date 2020-01-01 --end-date 2024-12-31

# Data quality checks
python data_sync.py check              # quality report
python data_sync.py find-missing       # find data gaps
python data_sync.py sync 000001,000002 # manual sync
```

### Model training
```bash
# Regression (default)
python main.py train --model lstm --ts-codes 000001,000002 --epochs 50

# Classification (3-class: up/flat/down)
python main.py train --model lstm --task_type classification --ts-codes 000001,000002 --epochs 50

# Full example with all options
python main.py train --model transformer --ts-codes 000001,000002,000003 \
  --seq-len 30 --pred-len 10 --epochs 50 --batch-size 32 \
  --lr 0.001 --loss mse --optimizer adam --scheduler reduce \
  --output-dir ./output

# Directly via train module
python -m train_src.train --model lstm --ts_codes 000001,000002 --epochs 10
```

### Web server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Or: python main.py server --port 8000
```

### Testing
```bash
python test_basic.py          # model & dataset smoke test
python test_classification.py # classification mode test
python test_torch.py          # verify PyTorch installation
python test_db_connection.py  # database connectivity
python test_data_fetch.py     # akshare data retrieval
python test_dataset_load.py   # dataset loading pipeline
```

## Key Implementation Notes

- **Time handling**: All dates are `datetime.date` objects in Asia/Shanghai timezone. Trading calendar from `ak.tool_trade_date_hist_sina()` loaded once and reused.
- **Normalization**: `scaler_X.pkl` is fit once on the first stock cleaned, then reused across all stocks. Located at `data_process/scaler_X.pkl`.
- **Classification mode**: Uses `close_raw` (unnormalized) to compute cumulative return over `pred_len` days, then buckets into classes based on `[-0.01, 0.01]` thresholds by default.
- **Proxy**: Configured in `config.yaml` → `proxy` section. `proxy_manager.py` supports Clash YAML profiles (`data_process/airport.yaml`, `data_process/free.yaml`).
- **Logging**: `utils/logger.py` provides a pre-configured `logger` with color console output + file rotation. Import `from utils.logger import logger` everywhere.

## Adding new models

1. Define model class in `train_src/model.py` (inherit `nn.Module`), supporting both regression and classification output
2. Register in `get_model()` factory function
3. Add hyperparams to `config.yaml` under `model`
4. Update `train_src/train.py` argparser choices if needed
