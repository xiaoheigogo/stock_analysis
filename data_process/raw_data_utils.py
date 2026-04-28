from .stock import Stock as stock
from utils.db_conn import *
from utils.tables import *
from tenacity import retry, stop_after_attempt, wait_random, wait_random_exponential
import datetime, time
import akshare as ak
import random
import os, requests
import pandas as pd
import sys
import traceback

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from proxy_manager import get_proxy_manager, setup_proxy_for_akshare
    PROXY_MANAGER_AVAILABLE = True
except ImportError:
    PROXY_MANAGER_AVAILABLE = False
    logger.warning("proxy_manager模块不可用，将使用基础代理配置")

# ---------- 1. 智能代理配置 ----------
def setup_proxy():
    """设置智能代理"""
    if PROXY_MANAGER_AVAILABLE:
        try:
            # 尝试从多个配置文件加载代理
            config_paths = [
                "data_process/airport.yaml",
                "data_process/free.yaml"
            ]

            for config_path in config_paths:
                if os.path.exists(config_path):
                    setup_proxy_for_akshare(config_path)
                    logger.info(f"使用代理配置文件: {config_path}")
                    return

            # 如果没有配置文件，使用环境变量
            setup_proxy_for_akshare()
            logger.info("使用环境变量代理配置")

        except Exception as e:
            logger.error(f"设置代理失败: {e}")
            # 回退到基础代理配置
            setup_basic_proxy()
    else:
        setup_basic_proxy()

def setup_basic_proxy():
    """设置基础代理（兼容旧版本）"""
    # 从config.yaml读取代理配置
    import yaml
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if config.get('proxy', {}).get('enabled', False):
            http_proxy = config['proxy']['http_proxy']
            https_proxy = config['proxy']['https_proxy']

            os.environ['HTTP_PROXY'] = http_proxy
            os.environ['HTTPS_PROXY'] = https_proxy

            # 覆盖 ak 内部 headers
            ak._HTTP_HEADERS = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            logger.info(f"使用基础代理: {http_proxy}")
    except Exception as e:
        logger.warning(f"读取代理配置失败: {e}")
        # 不设置代理，使用直连

# ---------- 2. 长退避重试 ----------
@retry(stop=stop_after_attempt(5), wait=wait_random_exponential(multiplier=60, max=180))
def safe_hist(symbol, ts_name, start, end):
    """
    安全获取股票历史数据，包含重试机制

    Args:
        symbol: 股票代码
        ts_name: 股票名称
        start: 开始日期 (YYYYMMDD)
        end: 结束日期 (YYYYMMDD)

    Returns:
        DataFrame 或 None（失败时）
    """
    try:
        logger.debug(f"尝试获取股票 {symbol} 数据: {start} - {end}")

        # 确保代理已设置
        setup_proxy()

        # 获取数据
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start, end_date=end, adjust='qfq')

        if df is None or df.empty:
            logger.warning(f"股票 {symbol} 没有获取到数据（日期范围: {start} - {end}）")
            return None

        # 标记ST股票
        if "ST" in ts_name or "st" in ts_name:
            df['is_st'] = True
        else:
            df['is_st'] = False

        # 重命名列
        df = df[['日期', '股票代码', 'is_st', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率']].rename(columns={
            '日期': 'trade_date',
            '股票代码': 'ts_code',
            '开盘': 'open_raw',
            '收盘': 'close_raw',
            '最高': 'high_raw',
            '最低': 'low_raw',
            '成交量': 'volumn_raw',
            '成交额': 'amount_raw',
            '振幅': 'amplitude_raw',
            '涨跌幅': 'pct_change_raw',
            '涨跌额': 'change_raw',
            '换手率': 'turnover_raw'})

        logger.debug(f"股票 {symbol} 获取成功，共 {len(df)} 条记录")
        return df

    except Exception as e:
        logger.error(f"获取股票 {symbol} 数据失败: {e}")
        # 重新抛出异常让retry装饰器处理
        raise

def update_raw_data(table, data):
    today = datetime.datetime.today().strftime('%Y-%m-%d')
    print(f"today: {today}")
    postgres.upsert(table=table['table_name'], data=data, pk_cols=table['primary_key'])

def update_trade_date_data():
    logger.info("更新交易日期trade_date表")
    df = ak.tool_trade_date_hist_sina()
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date   # 转 date 类型
    data = df[['trade_date']].to_dict(orient='records')          # 转dict
    # print(data)
    postgres.execute_many("INSERT INTO trade_date (trade_date) VALUES (%s) ON CONFLICT DO NOTHING", 
                          [(d['trade_date'],) for d in data])
    logger.info(f"交易日期trade_date更新完成。")
    
def update_stock_list_data():
    """update stock_list table"""
    logger.info("更新股票列表stock_list表")
    # 1. 基础信息（代码、名称、市场、上市日期、行业）
    base_df = ak.stock_info_a_code_name()          # 深沪京A股列表，code、name, 5300+ 行
    base_df.columns = ['ts_code', 'ts_name']       # 统一列名

    # 深圳主板信息，板块、A股代码、A股简称、A股上市日期、A股总股本、A股流通股本、所属行业
    board_info_sz = ak.stock_info_sz_name_code()[['A股代码', 'A股上市日期']].rename(columns={
        'A股代码': 'ts_code',
        'A股上市日期': 'list_date_sz'})
    board_info_sz['market_sz'] = "sz"
    # logger.info(f"get board_info_sz: {board_info_sz.head()}")
    time.sleep(0.5)  

    # 北京主板信息，证券代码、证券简称、总股本、流通股本、上市日期、所属行业、地区、报告日期
    board_info_bj = ak.stock_info_bj_name_code()[['证券代码', '上市日期']].rename(columns={
        '证券代码': 'ts_code',
        '上市日期': 'list_date_bj'})
    board_info_bj['market_bj'] = "bj"
    # logger.info(f"get board_info_bj: {board_info_bj.head()}")
    time.sleep(0.5)  

    # 上海主板信息，证券代码、证券简称、公司全称、上市日期
    board_info_sh = ak.stock_info_sh_name_code()[['证券代码', '上市日期']].rename(columns={
        '证券代码': 'ts_code',
        '上市日期': 'list_date_sh'})
    board_info_sh['market_sh'] = "sh"
    # logger.info(f"get board_info_sh: {board_info_sh.head()}")
    time.sleep(0.5)  

    # 上海delist信息，公司代码、公司简称、上市日期、暂停上市日期
    delist_sh = ak.stock_info_sh_delist()[['公司代码', '暂停上市日期']].rename(columns={
        '公司代码': 'ts_code',
        '暂停上市日期': 'delist_date_sh',
    })
    # logger.info(f"get delist_sh: {delist_sh.head()}")
    time.sleep(0.5)  

    # 深圳delist信息，证券代码、上市日期、终止上市日期
    delist_sz = ak.stock_info_sz_delist()[['证券代码', '终止上市日期']].rename(columns={
        '证券代码': 'ts_code',
        '终止上市日期': 'delist_date_sz',
    })
    # logger.info(f"get delist_sz: {delist_sz.head()}")
    time.sleep(0.5)

    # 沪深300成分
    hs300_df = ak.index_stock_cons_csindex(symbol='000300')
    hs300_df = hs300_df[['成分券代码']].rename(columns={'成分券代码': 'ts_code'}).assign(is_hs300=True)
    # logger.info(f"get hs300_df: {hs300_df.head()}")

    merge_df = (base_df.merge(board_info_sz, on='ts_code', how='left')
                .merge(board_info_bj, on='ts_code', how='left')
                .merge(board_info_sh, on='ts_code', how='left')
                .merge(delist_sh, on='ts_code', how='left')
                .merge(delist_sz, on='ts_code', how='left')
                .merge(hs300_df, on='ts_code', how='left'))
    
    # 上市日期：SZ → SH → BJ 优先（可自己调顺序）, 避免无该列名
    merge_df['list_date'] = (merge_df['list_date_sz']
                             .fillna(merge_df['list_date_sh'])
                             .fillna(merge_df['list_date_bj']))
    merge_df['market'] = (merge_df['market_sz']
                          .fillna(merge_df['market_sh'])
                          .fillna(merge_df['market_bj']))
    # 退市日期：SZ → SH
    merge_df['delist_date'] = (merge_df['delist_date_sz']
                               .fillna(merge_df['delist_date_sh']))

    logger.info(f"merge_df: \n{merge_df}")

    merge_df['is_hs300'] = merge_df['is_hs300'].astype('boolean').fillna(False)
    merge_df['industry'] = "其它"
    merge_df['board'] = "主板"
    merge_df['update_time'] = pd.Timestamp.now('Asia/Shanghai')

    # # 板块推导
    # def board_map(c):
    #     if c.startswith('688'): return '科创板'
    #     if c[:3] in ('300','301'): return '创业板'
    #     if c[-2:] == 'BJ': return '北交所'
    #     return '主板'
    # df['board'] = df['ts_code'].map(board_map)

    # NaN → None
    for col in ['list_date', 'delist_date']:
        merge_df[col] = merge_df[col].apply(lambda x: x if pd.notnull(x) else None)

    # 只保留表里要的 9 列
    out_cols = ['market','ts_code','ts_name','board','list_date','delist_date',
                'industry','is_hs300','update_time']
    df_out = merge_df[out_cols]
    logger.info(f"stock list infos: \n{df_out}")
    postgres.upsert('stock_list', df_out.to_dict('records'), pk_cols=['ts_code'])

    logger.info("股票列表stock_list表更新完成。")

def max_date_in_db(table_name, ts_code):
    """
    获取数据库中指定股票的最新交易日期

    Args:
        table_name: 表名
        ts_code: 股票代码

    Returns:
        最新交易日期（格式: YYYYMMDD）或None
    """
    try:
        # 使用参数化查询避免SQL注入
        sql = "SELECT MAX(trade_date) as max_date FROM %s WHERE ts_code = %%s"
        row = postgres.select(sql=sql % table_name, params=(ts_code,))

        if row and row[0]['max_date']:
            max_date = row[0]['max_date']
            # 处理不同日期类型
            if hasattr(max_date, 'strftime'):
                return max_date.strftime("%Y%m%d")
            elif isinstance(max_date, str):
                # 如果已经是字符串，尝试转换格式
                try:
                    # 尝试解析常见日期格式
                    for fmt in ["%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"]:
                        try:
                            dt = datetime.datetime.strptime(max_date, fmt)
                            return dt.strftime("%Y%m%d")
                        except ValueError:
                            continue
                except:
                    pass
            return None
        else:
            return None
    except Exception as e:
        logger.error(f"查询 {table_name} 表中股票 {ts_code} 的最新日期失败: {e}")
        return None

def update_stocks_daily_kline(stock_codes: list = None, incremental: bool = True, batch_size: int = 50):
    """
    更新股票日K线数据

    Args:
        stock_codes: 要更新的股票代码列表，None表示更新所有股票
        incremental: 是否增量更新（只更新缺失的数据）
        batch_size: 批量处理大小
    """
    # 设置代理
    setup_proxy()

    # 获取当前日期
    today = datetime.datetime.today().strftime("%Y%m%d")
    logger.info(f"开始更新股票日K线数据，当前日期: {today}")

    # 获取股票列表
    if stock_codes:
        # 只更新指定的股票
        stock_list = []
        for ts_code in stock_codes:
            # 查询股票信息
            result = postgres.select_table(
                table="stock_list",
                cols=["ts_code", "ts_name"],
                where={"ts_code": ("=", ts_code)}
            )
            if result:
                stock_list.append(result[0])
            else:
                logger.warning(f"股票代码 {ts_code} 不在股票列表中，跳过")
    else:
        # 更新所有股票
        stock_list = postgres.select_table(
            table="stock_list",
            cols=["ts_code", "ts_name"],
            where={
                "__order_by": "ts_code",
                "__order": "ASC"
            }
        )

    if not stock_list:
        logger.error("没有找到股票列表")
        return

    logger.info(f"共找到 {len(stock_list)} 支股票需要更新")

    # 统计信息
    stats = {
        'total': len(stock_list),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'updated': 0
    }

    # 批量处理
    frames = []
    batch_count = 0

    for i, stock in enumerate(stock_list, 1):
        ts_code = stock['ts_code']
        ts_name = stock['ts_name']

        logger.info(f"[{i}/{len(stock_list)}] 处理股票: {ts_code} {ts_name}")

        try:
            # 确定需要获取的日期范围
            if incremental:
                # 获取数据库中该股票的最新日期
                max_date = max_date_in_db("daily_kline", ts_code)

                if max_date:
                    # 如果最新日期已经是今天或之后，跳过
                    if max_date >= today:
                        logger.info(f"股票 {ts_code} 数据已是最新（最新日期: {max_date}），跳过")
                        stats['skipped'] += 1
                        continue

                    # 增量更新：从最新日期的下一天开始
                    start_date = (datetime.datetime.strptime(max_date, "%Y%m%d") +
                                  datetime.timedelta(days=1)).strftime("%Y%m%d")
                    end_date = today

                    logger.info(f"增量更新 {ts_code}: {start_date} 到 {end_date}")
                else:
                    # 首次获取：从1990年开始
                    start_date = "19900101"
                    end_date = today
                    logger.info(f"首次获取 {ts_code}: {start_date} 到 {end_date}")
            else:
                # 全量更新
                start_date = "19900101"
                end_date = today
                logger.info(f"全量更新 {ts_code}: {start_date} 到 {end_date}")

            # 获取股票数据
            logger.info(f"获取股票 {ts_code} 数据: {start_date} - {end_date}")

            try:
                df = safe_hist(symbol=ts_code, ts_name=ts_name, start=start_date, end=end_date)

                if df is None or df.empty:
                    logger.warning(f"股票 {ts_code} 没有获取到数据")
                    stats['failed'] += 1
                    continue

                # 添加批次
                frames.append(df)
                stats['updated'] += len(df)
                stats['success'] += 1

                logger.info(f"股票 {ts_code} 获取成功，共 {len(df)} 条记录")

            except Exception as e:
                logger.error(f"获取股票 {ts_code} 数据失败: {e}")
                stats['failed'] += 1
                # 继续处理下一支股票
                continue

            # 批量提交到数据库
            if len(frames) >= batch_size or i == len(stock_list):
                if frames:
                    try:
                        batch_count += 1
                        logger.info(f"批量提交第 {batch_count} 批数据，共 {len(frames)} 支股票")

                        # 合并数据
                        big_df = pd.concat(frames, ignore_index=True)

                        # 写入数据库
                        postgres.upsert("daily_kline", big_df.to_dict('records'),
                                       pk_cols=['trade_date', 'ts_code'])

                        logger.info(f"第 {batch_count} 批数据提交成功，共 {len(big_df)} 条记录")
                        frames.clear()

                    except Exception as e:
                        logger.error(f"批量提交数据失败: {e}")
                        # 尝试逐条提交
                        logger.info("尝试逐条提交数据...")
                        for df_single in frames:
                            try:
                                postgres.upsert("daily_kline", df_single.to_dict('records'),
                                               pk_cols=['trade_date', 'ts_code'])
                            except Exception as e2:
                                logger.error(f"逐条提交失败: {e2}")
                        frames.clear()

                # 批次间延迟，避免请求过于频繁
                if i < len(stock_list):
                    delay = random.uniform(3.0, 8.0)
                    logger.debug(f"批次间延迟 {delay:.1f} 秒")
                    time.sleep(delay)

            # 单次请求后延迟
            delay = random.uniform(1.0, 3.0)
            time.sleep(delay)

        except Exception as e:
            logger.error(f"处理股票 {ts_code} 时发生错误: {e}")
            stats['failed'] += 1
            continue

    # 提交剩余数据
    if frames:
        try:
            batch_count += 1
            logger.info(f"提交最后一批数据，共 {len(frames)} 支股票")
            big_df = pd.concat(frames, ignore_index=True)
            postgres.upsert("daily_kline", big_df.to_dict('records'),
                           pk_cols=['trade_date', 'ts_code'])
            logger.info(f"最后一批数据提交成功，共 {len(big_df)} 条记录")
        except Exception as e:
            logger.error(f"提交最后一批数据失败: {e}")

    # 输出统计信息
    logger.info("=" * 60)
    logger.info("股票数据更新完成统计:")
    logger.info(f"总计股票: {stats['total']}")
    logger.info(f"成功更新: {stats['success']}")
    logger.info(f"更新失败: {stats['failed']}")
    logger.info(f"跳过更新: {stats['skipped']}")
    logger.info(f"新增记录: {stats['updated']}")
    logger.info("=" * 60)

index_dict = {
    '上证指数': "000001.sh",
    '深证成指': "399001",
    '沪深300': "000300",
    '创业板指': "399006",
    '北证50': "899050",
}

@retry(stop=stop_after_attempt(3), wait=wait_random(1, 3))
def safe_index_kline(index):
    today = datetime.datetime.today().strftime("%Y-%m-%d")
    return ak.index_zh_a_hist(symbol=index, period="daily")

def update_index_daily_kline():
    """update bj50, sh, sz, index Kline data, insert to daily_kline table"""
    df = pd.DataFrame()
    frames = []
    for _, index in index_dict.items():
        logger.info(f"getting {index} index kline data.")
        # 东方财富网，可能封IP，日期|开盘|收盘|最高|最低|成交量|成交额|振幅|涨跌幅|涨跌额|换手率
        tmp = safe_index_kline(index)
        tmp['ts_code'] = index
        frames.append(tmp)
        time.sleep(random.uniform(5, 10))  # 随机休眠时间
    
    df = pd.concat(frames, axis=0, ignore_index=True, copy=False)
    df = df[['日期', 'ts_code', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率']].rename(columns={
        '日期': 'trade_date',
        '开盘': 'open_raw',
        '收盘': 'close_raw',
        '最高': 'high_raw',
        '最低': 'low_raw',
        '成交量': 'volumn_raw',
        '成交额': 'amount_raw',
        '振幅': 'amplitude_raw',
        '涨跌幅': 'pct_change_raw',
        '涨跌额': 'change_raw',
        '换手率': 'turnover_raw'})
    df['is_st'] = False
    logger.info(f"update index kline: \n{df}")
    postgres.upsert("daily_kline", df.to_dict('records'), pk_cols=['trade_date', 'ts_code'])




if __name__=="__main__":
    # # 更新交易日期表
    # update_trade_date_data()

    # # 更新stock_list表
    # update_stock_list_data()

    # # 更新大盘指数日K数据，按日期更新或按大盘代码全部更新
    # update_index_daily_kline()
    
    # TODO: 尚未调试
    # 更新全部股票的日K表，按日期更新或按股票名全部更新
    os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'
    print(requests.get('https://httpbin.org/ip').json())
    update_stocks_daily_kline()