"""
一键清洗 + 归一化流水线
1. 从 PostgreSQL 拉前复权日K
2. 停牌补全（交易所日历）
3. 衍生特征（MA/MACD/RSI + 日期循环编码）
4. 滚动窗口归一化（训练段 fit，保存 scaler）
5. 写回 daily_kline（只存 clean 列）
6. 训练/推理：load 旧 scaler，不再重算
"""
import akshare as ak
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import joblib
from datetime import date
from utils.db_conn import postgres
from utils.logger import logger
import pathlib
import time

# -------------- 常量 --------------
SCALER_PATH = pathlib.Path(__file__).with_name("scaler_X.pkl")
DATE_COLS = ['list_date', 'delist_date']          # 需要 None 化的日期列
TECH_COLS_RAW = ['open_raw', 'high_raw', 'low_raw', 'close_raw', 'volumn_raw', 'amount_raw',
                 'amplitude_raw', 'pct_change_raw', 'change_raw', 'turnover_raw']  # 原始列
TECH_COLS_CLEAN = [f"{c.replace('_raw', '_clean')}" for c in TECH_COLS_RAW]  # 归一化后列
DERIV_COLS = ['ma5', 'ma10', 'macd_dif', 'rsi14']         # 衍生指标
CYCLE_COLS = ['month_sin', 'month_cos', 'day_sin', 'day_cos', 'dow_sin', 'dow_cos']

# -------------- 交易所日历（一次性加载） --------------
def get_trade_cal():
    """返回 DATE 列表，只含真实开盘日"""
    cal = ak.tool_trade_date_hist_sina()
    cal['trade_date'] = pd.to_datetime(cal['trade_date']).dt.date
    return cal['trade_date'].tolist()

TRADE_CAL = get_trade_cal()

# -------------- 1. 从 PostgreSQL 拉取前复权日K --------------
def load_raw_from_pg(ts_code: str, start: date, end: date) -> pd.DataFrame:
    """
    只拉 raw 列，不含 clean
    """
    sql = """
        SELECT trade_date, ts_code, is_st, open_raw, high_raw, low_raw, close_raw,
               volumn_raw, amount_raw, amplitude_raw, pct_change_raw, change_raw, turnover_raw
        FROM   daily_kline
        WHERE  ts_code = %s
          AND  trade_date BETWEEN %s AND %s
        ORDER  BY trade_date
    """
    # print(f"sql: {sql%(ts_code, start, end)}")
    logger.info(f"getting {ts_code} raw data from pg. begin_date: {start}, end_date:{end}.")
    df = postgres.select_df(sql, [ts_code, start, end])
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    return df

# -------------- 2. 停牌补全（对齐交易所日历） --------------
# def align_and_fill(df: pd.DataFrame) -> pd.DataFrame:
#     """
#     输入：前复权日K（可能缺停牌日）
#     输出：与交易所日历对齐，停牌日价格=前收，量=0，比率=0
#     """
#     df = df.set_index('trade_date').reindex(TRADE_CAL, method='ffill')
#     # 价格前填，量/额填 0，比率填 0
#     price_cols = [c for c in df.columns if c.endswith('_raw') and c != 'volumn_raw']  # 此处需要看下为何只剔除volumn_raw
#     df['ts_code'] = df['ts_code'].ffill()
#     vol_cols = ['volumn_raw', 'amount_raw']
#     ratio_cols = ['amplitude_raw', 'pct_change_raw', 'change_raw', 'turnover_raw']
#     close_col = 'close_raw'

#     df[price_cols] = df[close_col].ffill()
#     df[vol_cols] = df[vol_cols].fillna(0)
#     df[ratio_cols] = df[ratio_cols].fillna(0)
#     df.reset_index(inplace=True)
#     df.rename(columns={'index': 'trade_date'}, inplace=True)
#     # 此处output df 会把1990-12-19开始的数据填为空，至2025-12-31的数据填为当前的数据，因为交易日期是1990-12-19~2025-12-31，会更新到之后的数据，是否影响归一化和训练？
#     # 这里是否要进行筛选填充？当前日期后和上市日期前的数据不进行补充？
#     return df

def align_and_fill_v2(df: pd.DataFrame, list_date: date, today: date) -> pd.DataFrame:
    """
    只补 【list_date → today】 区间，其余丢弃
    df 必须含 trade_date 列（datetime.date）
    """
    if isinstance(list_date, pd.Series):
        list_date = list_date.iloc[0]
    list_date = pd.to_datetime(list_date).date()
    if isinstance(today, pd.Series):
        today = today.iloc[0]
    today = pd.to_datetime(today).date()

    # 1. 生成本股有效日历
    valid_cal = pd.date_range(list_date, today, freq='D').date.tolist()
    valid_cal = [d for d in valid_cal if d in TRADE_CAL]   # 只保留开盘日

    # 2. 截取原始数据（剔除上市前、未来）
    df = df[(df['trade_date'] >= list_date) & (df['trade_date'] <= today)].copy()

    # 3. 对齐有效日历
    df = df.set_index('trade_date').reindex(valid_cal)
    df['ts_code'] = df['ts_code'].ffill()
    df['is_st'] = df['is_st'].ffill()
    # 将NaN转换为None，以匹配数据库的BOOL类型
    df['is_st'] = df['is_st'].where(pd.notna(df['is_st']), None)
    # print(f"fill date df: {df}")

    # 4. 填充规则
    # price_cols = [c for c in df.columns if c.endswith('_raw') and 'volumn' not in c]
    price_cols = ['open_raw', 'high_raw', 'low_raw', 'close_raw']
    # vol_cols = [c for c in df.columns if 'volumn' in c or 'amount' in c]
    vol_cols = ['volumn_raw', 'amount_raw']
    ratio_cols = ['amplitude_raw', 'pct_change_raw', 'change_raw', 'turnover_raw']
    close_col = 'close_raw'

    df[close_col] = df[close_col].ffill()  # 空白日期填前一日的收盘价
    df['open_raw'] = df['open_raw'].fillna(df[close_col]) # 与收盘价统一
    df['high_raw'] = df['high_raw'].fillna(df[close_col])
    df['low_raw'] = df['low_raw'].fillna(df[close_col])
    df[vol_cols] = df[vol_cols].fillna(0)
    df[ratio_cols] = df[ratio_cols].fillna(0)

    df.reset_index(inplace=True)
    df.rename(columns={'index': 'trade_date'}, inplace=True)

    # 补全停牌日的数据后更新进数据库
    data = df.to_dict('records')
    postgres.upsert("daily_kline", data, pk_cols=['trade_date', 'ts_code'])
    return df

# -------------- 3. 衍生指标 --------------
def add_technical(df: pd.DataFrame) -> pd.DataFrame:
    """MA5/MA10/MACD/RSI14"""
    df = df.copy()
    close = df['close_raw']

    # MA
    df['ma5'] = close.rolling(5).mean()
    df['ma10'] = close.rolling(10).mean()

    # MACD
    exp1 = close.ewm(span=12).mean()
    exp2 = close.ewm(span=26).mean()
    df['macd_dif'] = exp1 - exp2

    # RSI14
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    rs = pd.Series(gain).rolling(14).mean() / pd.Series(loss).rolling(14).mean()
    df['rsi14'] = 100 - (100 / (1 + rs))
    return df

def add_cyclic_date(df: pd.DataFrame) -> pd.DataFrame:
    """sin/cos 循环编码：month/day/dow"""
    dt = pd.to_datetime(df['trade_date'])
    # 直接调用 .dt.<属性>，不要用下标
    for col, period in [('month', 12), ('day', 31), ('dow', 7)]:
        if col == 'month':
            x = dt.dt.month
        elif col == 'day':
            x = dt.dt.day
        elif col == 'dow':
            x = dt.dt.dayofweek
        df[f'{col}_sin'] = np.sin(2 * np.pi * x / period)
        df[f'{col}_cos'] = np.cos(2 * np.pi * x / period)
    return df

# -------------- 4. 滚动窗口归一化（训练段 fit） --------------
def fit_scaler(train_df: pd.DataFrame) -> StandardScaler:
    """
    只在训练段 fit，保存 scaler
    特征 = TECH_COLS_RAW + DERIV_COLS + CYCLE_COLS
    """
    feat_cols = TECH_COLS_RAW + DERIV_COLS + CYCLE_COLS
    scaler = StandardScaler()
    scaler.fit(train_df[feat_cols])
    joblib.dump(scaler, SCALER_PATH)
    logger.info(f"scaler saved → {SCALER_PATH}")
    return scaler

def apply_scaler(df: pd.DataFrame, scaler: StandardScaler) -> pd.DataFrame:
    """用已有 scaler 归一化，返回新 DataFrame（仅 clean 列）"""
    feat_cols = TECH_COLS_RAW + DERIV_COLS + CYCLE_COLS
    # print(f"feat_cols: {feat_cols}")
    # df = df.reset_index() 
    clean_df = df[['trade_date', 'ts_code']].copy()  # 主键先留着

    # clean_df[TECH_COLS_CLEAN] = scaler.transform(df[TECH_COLS_RAW])
    # # 衍生指标也归一化
    # clean_df[DERIV_COLS] = scaler.transform(df[DERIV_COLS])
    # clean_df[CYCLE_COLS] = scaler.transform(df[CYCLE_COLS])
    X = df[feat_cols].fillna(0)  # ← 先填 0
    X_scaled = scaler.transform(X)  # ← 现在无 NaN，形状 = (n_samples, n_features)
    clean_df[TECH_COLS_CLEAN] = X_scaled[:, :len(TECH_COLS_RAW)]
    clean_df[DERIV_COLS] = X_scaled[:, len(TECH_COLS_RAW):len(TECH_COLS_RAW) + len(DERIV_COLS)]
    clean_df[CYCLE_COLS] = X_scaled[:, -len(CYCLE_COLS):]
    return clean_df

# -------------- 5. 写回 PostgreSQL（只存 clean 列） --------------
def upsert_clean(df: pd.DataFrame):
    """只写 clean 列 + 主键"""
    cols = ['trade_date', 'ts_code'] + TECH_COLS_CLEAN + DERIV_COLS + CYCLE_COLS
    data = df[cols].to_dict('records')
    # 空值 → None
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
    postgres.upsert("daily_kline", data, pk_cols=['trade_date', 'ts_code'])
    logger.info(f"upsert {len(data)} 条 clean 数据")

# -------------- 6. 一键清洗单股（训练段） --------------
def clean_one_stock(ts_code: str, train_start: date, train_end: date, batch_size: int = 1000):
    """
    训练阶段：拉 → 补 → 衍生 → fit scaler → 归一化 → 写库
    """
    logger.info(f"开始清洗 {ts_code} 训练段 {train_start}~{train_end}")

    # 1. 拉 raw
    raw_df = load_raw_from_pg(ts_code, train_start, train_end)
    if raw_df.empty:
        logger.warning(f"{ts_code} 无数据，跳过")
        return None

    # 2. 获取上市日期
    list_date_df = postgres.select_df(
        "SELECT list_date FROM stock_list WHERE ts_code = %s", [ts_code]
    )

    if list_date_df.empty or list_date_df['list_date'].iloc[0] is None:
        logger.warning(f"{ts_code} 无上市日期信息，跳过")
        return None

    list_date = list_date_df['list_date'].iloc[0]
    today = date.today()

    # 3. 补全停牌日数据
    filled = align_and_fill_v2(raw_df, list_date, today)

    # 4. 衍生技术指标
    tech = add_technical(filled)

    # 5. 增加时间循环特征
    full = add_cyclic_date(tech)

    # 6. 检查是否已有scaler，如果没有则创建
    if SCALER_PATH.exists():
        logger.info(f"加载已有scaler: {SCALER_PATH}")
        scaler = joblib.load(SCALER_PATH)
    else:
        logger.info(f"创建新scaler")
        scaler = fit_scaler(full)

    # 7. 归一化
    clean_df = apply_scaler(full, scaler)

    # 8. 写库
    upsert_clean(clean_df)

    logger.info(f"{ts_code} 清洗完成，处理 {len(clean_df)} 条数据")
    return clean_df


def find_dirty_stocks():
    """
    返回：有 raw 数据但 close_clean IS NULL 的 ts_code 列表
    """
    sql = """
        SELECT DISTINCT ts_code
        FROM   daily_kline
        WHERE  close_raw IS NOT NULL
          AND  close_clean IS NULL
    """
    rows = postgres.select(sql)
    return [r['ts_code'] for r in rows]

def is_cleaned(ts_code, train_date):
    sql = f"""SELECT close_clean FROM daily_kline WHERE ts_code = '{ts_code}' AND trade_date = '{train_date}' ORDER BY trade_date DESC"""
    date = postgres.select(sql)[0]['close_clean']
    print(f"ts_code: {ts_code}, date: {date}, type: {type(date)}")
    if date:
        return True
    else:
        return False


if __name__ == "__main__":
    # # -------------- 常量 --------------
    # SCALER_PATH = pathlib.Path(__file__).with_name("scaler_X.pkl")
    # DATE_COLS = ['list_date', 'delist_date']          # 需要 None 化的日期列
    # TECH_COLS_RAW = ['open', 'high', 'low', 'close', 'volumn', 'amount',
    #                 'amplitude', 'pct_change', 'turnover']  # 原始列
    # TECH_COLS_CLEAN = [f"{c}_clean" for c in TECH_COLS_RAW]  # 归一化后列
    # DERIV_COLS = ['ma5', 'ma10', 'macd_dif', 'rsi14']         # 衍生指标
    # CYCLE_COLS = ['month_sin', 'month_cos', 'day_sin', 'day_cos', 'dow_sin', 'dow_cos']

    raw_stocks = find_dirty_stocks()

    # print(f"raw_stocks: {raw_stocks}")
    print(f"len_raw_stocks: {len(raw_stocks)}")

    batch_size = 20
    chunk = pd.DataFrame()
    for i, ts_code in enumerate(raw_stocks, 1):
        first_date = postgres.select_df("SELECT trade_date FROM daily_kline WHERE ts_code = %s ORDER  BY trade_date" , [ts_code])['trade_date'].iloc[0]
        logger.info(f"====处理第 {i}/{len(raw_stocks)} 支====")
        print(f"ts_code: {ts_code}, first_date: {first_date}")
        # print(f"type: {type(list_date)}")
        if not is_cleaned(ts_code, '2025-09-30'):
            clean_data = clean_one_stock(ts_code, first_date, '2025-09-30')
            time.sleep(0.5)
        #     chunk = pd.concat([chunk, clean_data], axis=0, ignore_index=True)
        # if i == batch_size:
        #     # print(f"chunk: {chunk}")
        #     # print(type(chunk))
        #     # print(f"chunk_shape: {chunk.shape}")
        #     logger.info(f"chunk head: {chunk[:5]}")
        #     logger.info(f"chunk tail: {chunk[-5:]}")
        #     # upsert_clean(chunk)
        #     logger.info(f"chunk 清洗完成。")
        # if i == 40:
        #     break

    logger.info(f"Clean all raw data done!!")