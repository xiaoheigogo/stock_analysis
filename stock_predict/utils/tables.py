from utils.logger import logger
from utils.db_conn import *
import copy

stock_list = {
    'table_name': "stock_list",
    'headers': {
        'market': 'VARCHAR(9) NOT NULL',
        'ts_code': 'VARCHAR(9) NOT NULL',
        'ts_name': 'VARCHAR(9) NOT NULL',
        'board': 'VARCHAR(8)',
        'list_date': 'DATE',
        'delist_date': 'DATE',
        'industry': 'VARCHAR(8)',
        'is_hs300': 'BOOL',
        'update_time': 'timestamptz',
    },
    'primary_key': ['ts_code'],
}

daily_kline = {
    'table_name': "daily_kline",
    'headers': {
        'trade_date': "DATE NOT NULL",  # 交易日期
        'ts_code': "VARCHAR(9) NOT NULL",
        'is_st': "BOOL",  # 是否为ST
        'open_raw': "FLOAT8",
        'high_raw': "FLOAT8",
        'low_raw': "FLOAT8",
        'close_raw': "FLOAT8",
        'volumn_raw': "BIGINT",  # 成交量
        'amount_raw': "BIGINT",  # 成交额
        'amplitude_raw': "FLOAT8",  # 振幅
        'pct_change_raw': "FLOAT8",  # 涨跌幅
        'change_raw': "FLOAT8",  # 涨跌额
        'turnover_raw': "FLOAT8",  # 换手率
        'open_clean': "FLOAT8",  # clean
        'high_clean': "FLOAT8",
        'low_clean': "FLOAT8",
        'close_clean': "FLOAT8",
        'volumn_clean': "FLOAT8",  # 成交量
        'amount_clean': "FLOAT8",  # 成交额
        'amplitude_clean': "FLOAT8",  # 振幅
        'pct_change_clean': "FLOAT8",  # 涨跌幅
        'change_clean': "FLOAT8",  # 涨跌额
        'turnover_clean': "FLOAT8",  # 换手率
        'ma5': "FLOAT8",  # 新增技术指标
        'ma10': "FLOAT8",
        'macd_dif': "FLOAT8",
        'rsi14': "FLOAT8",
        # 'year_sin': "FLOAT8",  # 年，30天k线时，可不参与计算
        # 'year_cos': "FLOAT8",
        'month_sin': "FLOAT8",
        'month_cos': "FLOAT8",
        'day_sin': "FLOAT8",
        'day_cos': "FLOAT8",
        'dow_sin': "FLOAT8",  # 星期
        'dow_cos': "FLOAT8",
    },
    'primary_key': ['trade_date', 'ts_code']
}


trade_date = {
    'table_name': "trade_date",
    'headers': {
        'trade_date': "DATE NOT NULL",  # 交易日期
    },
    'primary_key': ['trade_date']
}


def creat_tables(table_list):
    for table in table_list:
        postgres.create_table(table['table_name'], table['headers'], table['primary_key'])

def update_table(table, data, pk_cols):
    postgres.upsert(table, data, pk_cols)


if __name__ == "__main__":
    tables = [stock_list, daily_kline, trade_date]
    creat_tables(tables)