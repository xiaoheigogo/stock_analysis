import logging
import colorlog
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).resolve().parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

def get_logger(name: str = 'stock', level: int = logging.INFO) -> logging.Logger:
    """返回全局 logger，支持彩色控制台+文件分割"""
    logger = logging.getLogger(name)
    if logger.hasHandlers():          # 避免重复 addHandler
        return logger

    logger.setLevel(level)

    # 1. 控制台彩色
    console_fmt = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )
    sh = logging.StreamHandler()
    sh.setFormatter(console_fmt)
    logger.addHandler(sh)

    # 2. 文件日志（按天分割，保留 30 天）
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)8s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    from logging.handlers import TimedRotatingFileHandler
    fh = TimedRotatingFileHandler(
        LOG_DIR / "stock.log",
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    fh.setFormatter(file_fmt)
    logger.addHandler(fh)

    return logger

# 全局 logger 实例
logger = get_logger()