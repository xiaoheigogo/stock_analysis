# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a stock prediction system using machine learning models (LSTM, GRU, Transformer) for stock price forecasting. The project is in mid-development stage with core data pipeline and model training infrastructure implemented.

## Key Architecture Components

### Data Pipeline
1. **Data Acquisition**: `akshare` API → PostgreSQL (`daily_kline` table)
   - Stock list and daily K-line data fetched via `akshare`
   - Proxy support and anti-blocking mechanisms
   - Raw data stored with `_raw` suffix columns

2. **Data Processing**: `data_process/clean_normalize.py`
   - Trading day alignment (fills suspended days)
   - Technical indicators: MA5, MA10, MACD, RSI14
   - Time cyclic encoding: month/day/day-of-week sin/cos
   - Rolling window normalization (StandardScaler)
   - Cleaned data stored with `_clean` suffix columns

3. **Database Schema** (`utils/tables.py`)
   - `stock_list`: Stock metadata (ts_code, name, list_date, etc.)
   - `daily_kline`: Daily K-line data (raw + clean columns)
   - `trade_date`: Trading calendar

### Model Training Framework
- **Location**: `train_src/` directory
- **Models**: LSTM, GRU, BiLSTM, CNN-LSTM, Transformer
- **Dataset**: `StockDataset` class loads from PostgreSQL with train/val/test split
- **Training**: `Trainer` class handles training loops, validation, model saving
- **Configuration**: Model hyperparameters in `config.yaml`

### Configuration System
- **Primary**: `config.yaml` - structured YAML configuration
- **Environment Variables**: `.env` file for sensitive data (database credentials)
- **Database**: PostgreSQL primary, MySQL legacy support
- **Paths**: Output directories, model paths, log paths configurable

## Common Development Commands

### Setup and Installation
```bash
# Install dependencies (PyTorch needs separate installation)
pip install -r requirements.txt

# Install PyTorch (choose appropriate version)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu  # CPU
# OR for CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Initialize database tables
python utils/tables.py
```

### Data Operations
```bash
# Update all data
python main.py update --all

# Update specific data types
python main.py update --trade-date      # Trading calendar
python main.py update --stock-list      # Stock list
python main.py update --stock-kline     # Stock K-line data

# Clean data (raw → clean transformation)
python main.py clean --all-stocks
python main.py clean --ts-codes 000001,000002 --start-date 2020-01-01 --end-date 2024-12-31
```

### Model Training
```bash
# Train with default parameters
python main.py train --model lstm --ts-codes 000001,000002 --epochs 10

# Full training example
python main.py train \
  --model transformer \
  --ts-codes 000001,000002,000003 \
  --seq-len 30 \
  --pred-len 10 \
  --epochs 50 \
  --batch-size 32 \
  --output-dir ./output
```

### Testing
```bash
# Run basic tests (requires PyTorch installed)
python test_basic.py

# Test individual components
python -c "from train_src.model import get_model; model = get_model('lstm'); print(model)"
```

## Development Workflow

### Adding New Models
1. Define model class in `train_src/model.py` (inherit from `nn.Module`)
2. Register in `get_model()` function
3. Add model configuration to `config.yaml`
4. Update `train_src/train.py` argument parser if needed

### Adding New Features
1. Add feature calculation in `data_process/clean_normalize.py`
2. Update `feature_columns` in `config.yaml`
3. Run data cleaning to apply new features

### Database Schema Changes
1. Modify table definitions in `utils/tables.py`
2. Update affected data processing functions
3. Consider migration strategy for existing data

## Configuration Details

### Database Connection
- PostgreSQL is primary database (configure in `config.yaml` or `.env`)
- Connection pooling managed by `utils/db_conn.py`
- Sensitive credentials should be in `.env` file, not hardcoded

### Model Parameters
- Configured in `config.yaml` under `model` section
- Each model type (lstm, gru, etc.) has its own parameter set
- Training parameters (seq_len, batch_size, etc.) in `model.training`

### Path Management
- Output directories configurable in `config.yaml` `paths` section
- Model checkpoints saved to `paths.model_dir`
- Training logs in `paths.log_dir`

## Important Implementation Notes

### Data Normalization
- `scaler_X.pkl` contains fitted StandardScaler for feature normalization
- Scaler is fitted once during first data cleaning, then reused
- Located at `data_process/scaler_X.pkl`

### Time Handling
- All dates are timezone-aware (Asia/Shanghai)
- Trading day alignment uses exchange calendar from `akshare`
- Time cyclic features encode temporal patterns

### Error Handling
- Logging configured via `utils/logger.py` (color console + file rotation)
- Database operations use connection pooling with retry logic
- Data fetching includes proxy support and rate limiting

## Testing Strategy

### Unit Tests
- `test_basic.py`: Basic model and dataset functionality
- Tests use mock data to avoid database dependency
- Focus on model forward pass, gradient flow, data loading

### Integration Testing
- Data pipeline testing requires PostgreSQL instance
- Model training tests require clean data
- Consider using test database for integration tests

## Deployment Considerations

### Cloud Deployment (Alibaba Cloud PAI)
- Configuration in `config.yaml` `cloud.pai` section
- OSS for model storage, DLC for training, EAS for inference
- Automation pipeline for daily retraining

### Environment Variables
Required for production:
- Database credentials (POSTGRES_* variables)
- API keys for external services
- Proxy configuration if needed

## Troubleshooting

### Common Issues
1. **Database Connection**: Check PostgreSQL service and credentials in `.env`
2. **PyTorch Installation**: Choose correct CUDA version or CPU-only
3. **Data Fetching**: Network issues, proxy configuration, rate limiting
4. **Memory**: Reduce batch_size or seq_len for large models

### Logging
- Application logs: `logs/stock.log`
- Training logs: `output/logs/training_history.json`
- Log level configurable in `config.yaml`