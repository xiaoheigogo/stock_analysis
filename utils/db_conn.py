"""
PostgreSQL 轻量级封装
自动连接池 + 上下文管理 + 通用 CRUD
"""
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
from utils.logger import logger
import pandas as pd
import os
from contextlib import contextmanager
from functools import wraps

def _build_where_order(where: dict):
    """
    内部：把 where 字典 拆成
    where_sql, where_vals, order_sql
    支持运算符、IN、排序
    """
    where_sql = sql.SQL('')
    where_vals = []
    order_sql = sql.SQL('')
    # 排序关键字
    order_by = where.pop('__order_by', None)
    order_dir = where.pop('__order', 'ASC').upper()  # ASC/DESC

    if where:  # 还有普通条件
        cond = []
        for k, v in where.items():
            if isinstance(v, tuple) and len(v) == 2:  # 运算符
                op, val = v
                cond.append(sql.SQL("{} {} %s").format(sql.Identifier(k), sql.SQL(op)))
                where_vals.append(val)
            elif isinstance(v, (list, tuple)):  # IN
                placeholders = sql.SQL(', ').join([sql.SQL('%s')] * len(v))
                cond.append(sql.SQL("{} IN ({})").format(sql.Identifier(k), placeholders))
                where_vals.extend(v)
            else:  # 默认 =
                cond.append(sql.SQL("{} = %s").format(sql.Identifier(k)))
                where_vals.append(v)
        where_sql = sql.SQL(' WHERE ') + sql.SQL(' AND ').join(cond)

    if order_by:
        order_sql = sql.SQL(' ORDER BY {} {}').format(
            sql.Identifier(order_by), sql.SQL(order_dir))

    return where_sql, where_vals, order_sql

class Postgres:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_config_from_yaml(self):
        """从config.yaml加载数据库配置"""
        import os
        import yaml

        config_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml'),
            'config.yaml',
            '../config.yaml'
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)

                    # 提取数据库配置
                    db_config = config.get('database', {}).get('postgres', {})
                    if db_config:
                        return {
                            'host': db_config.get('host', 'localhost'),
                            'port': db_config.get('port', 5432),
                            'database': db_config.get('database', 'postgres'),
                            'user': db_config.get('user', 'postgres'),
                            'password': db_config.get('password', '')
                        }
                except Exception as e:
                    logger.warning(f"读取配置文件 {config_path} 失败: {e}")

        return None

    def __init__(self, minconn=1, maxconn=50, **kwargs):
        if hasattr(self, '_pool'):   # 防止重复建池
            return

        # 默认配置
        default_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'postgres',
            'user': 'postgres',
            'password': ''
        }

        # 尝试从config.yaml读取配置
        config_from_yaml = self._load_config_from_yaml()
        if config_from_yaml:
            default_config.update(config_from_yaml)

        # 使用kwargs中的值覆盖默认值
        final_config = default_config.copy()
        for key in ['host', 'port', 'database', 'user', 'password']:
            if kwargs.get(key) is not None:
                final_config[key] = kwargs[key]

        self._params = final_config
        try:
            self._pool = pool.SimpleConnectionPool(minconn, maxconn, **self._params)
            logger.info("PostgreSQL 连接池创建成功")
        except Exception as e:
            logger.error("连接池创建失败", exc_info=True)
            raise

    # ---------- 上下文管理器：自动获取/归还 ----------
    @contextmanager
    def get_cursor(self, dict_cursor=False):
        conn = cur = None
        try:
            conn = self._pool.getconn()
            cur = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)
            yield cur
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error("数据库操作异常", exc_info=True)
            raise
        finally:
            if cur:
                cur.close()
            if conn:
                self._pool.putconn(conn)

    # ---------- 通用查询 ----------
    def select(self, sql, params=None, fetch_one=False):
        with self.get_cursor(dict_cursor=True) as cur:
            cur.execute(sql, params)
            return cur.fetchone() if fetch_one else cur.fetchall()

    # def select_df(self, sql, params=None) -> pd.DataFrame:
    #     return pd.read_sql(sql, con=self._pool.getconn(), params=params)

    def select_df(self, sql, params=None) -> pd.DataFrame:
        with self.get_cursor(dict_cursor=True) as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[desc[0] for desc in cur.description])

    # ---------- 通用增/改/删 ----------
    def execute(self, sql, params=None):
        with self.get_cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def execute_many(self, sql, params_seq):
        with self.get_cursor() as cur:
            cur.executemany(sql, params_seq)
            return cur.rowcount

    # ---------- 返回 list[dict] ----------
    def select_table(self, table: str, cols: list[str] = None, where: dict = None) -> list[dict]:
        if cols is None:
            cols = ['*']
        else:
            cols = [sql.Identifier(c) for c in cols]

        where_sql, where_vals, order_sql = _build_where_order(where or {})

        query = sql.SQL("SELECT {} FROM {}{}{}").format(
            sql.SQL(', ').join(cols),
            sql.Identifier(table),
            where_sql,
            order_sql
        )

        with self.get_cursor(dict_cursor=True) as cur:
            cur.execute(query, where_vals)
            return cur.fetchall()


    # ---------- 返回 DataFrame ----------
    def select_table_df(self, table: str, cols: list[str] = None, where: dict = None) -> pd.DataFrame:
        if cols is None:
            cols = ['*']
        else:
            cols = [sql.Identifier(c) for c in cols]

        where_sql, where_vals, order_sql = _build_where_order(where or {})

        query = sql.SQL("SELECT {} FROM {}{}{}").format(
            sql.SQL(', ').join(cols),
            sql.Identifier(table),
            where_sql,
            order_sql
        )

        return self.select_df(query.as_string(self._pool.getconn()), where_vals)

    # ---------- 建表 ----------
    def create_table(self, table: str, cols_dict: dict, pk=None):
        """
        cols_dict = {'col':'TYPE [NOT NULL]', ...}
        pk = ['col1','col2']
        """
        col_defs = [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in cols_dict.items()]
        pieces = col_defs.copy()
        if pk:
            pieces.append(sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(', ').join(map(sql.Identifier, pk))))
        query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({});").format(
            sql.Identifier(table),
            sql.SQL(', ').join(pieces)
        )
        self.execute(query)
        logger.info(f"表 {table} 创建/已存在")


    # ---------- 便捷 Upsert（PostgreSQL ON CONFLICT） ----------
    def upsert(self, table: str, data: list[dict], pk_cols: list[str]):
        if not data:
            return
        cols = list(data[0].keys())
        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {}").format(
            sql.Identifier(table),
            sql.SQL(', ').join(map(sql.Identifier, cols)),
            sql.SQL(', ').join(map(sql.Identifier, pk_cols)),
            sql.SQL(', ').join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
                for c in cols if c not in pk_cols
            )
        )
        # psycopg2.extras.execute_values 批量高效
        from psycopg2.extras import execute_values
        with self.get_cursor() as cur:
            execute_values(cur, insert_sql.as_string(cur), [tuple(d[c] for c in cols) for d in data])
            logger.info(f"Upsert {table} {len(data)} 条")

    # ---------- 关闭池 ----------
    def close(self):
        if self._pool:
            self._pool.closeall()
            logger.info("连接池已关闭")


# ----------------- 模块级单例 -----------------
import os

# 创建数据库连接实例
# 优先从环境变量读取配置，如果环境变量不存在，则从config.yaml读取
# 检查是否有环境变量设置，如果没有则使用空值让__init__从config.yaml读取
host = os.getenv('POSTGRES_HOST')
port = os.getenv('POSTGRES_PORT')
database = os.getenv('POSTGRES_DB')
user = os.getenv('POSTGRES_USER')
password = os.getenv('POSTGRES_PASSWORD')
minconn = os.getenv('POSTGRES_MINCONN')
maxconn = os.getenv('POSTGRES_MAXCONN')

# 只有环境变量存在时才传递，否则让__init__从config.yaml读取
kwargs = {}
if host is not None:
    kwargs['host'] = host
if port is not None:
    kwargs['port'] = int(port)
if database is not None:
    kwargs['database'] = database
if user is not None:
    kwargs['user'] = user
if password is not None:
    kwargs['password'] = password
if minconn is not None:
    kwargs['minconn'] = int(minconn)
if maxconn is not None:
    kwargs['maxconn'] = int(maxconn)

postgres = Postgres(**kwargs)