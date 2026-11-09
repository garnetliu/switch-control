"""日志：配置输出到终端和文件。"""

import logging
import sys
import time
from pathlib import Path

from libs import Switch

_formatter = logging.Formatter("%(asctime)s | %(levelname)s: %(message)s", "%H:%M:%S")


class _RootOnly(logging.Filter):
    """只保留直接调用 logging.debug/info/warning 的记录，挡掉第三方库的日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "root"


def _get_logger() -> logging.Logger:
    """取根 logger，第一次调用时加上终端输出。"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in logger.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(_formatter)
        stream.addFilter(_RootOnly())
        logger.addHandler(stream)
    return logger


def init_log(sw: Switch, name: str | None = None) -> None:
    """初始化日志：终端输出，并创建第一个日志文件。已经初始化过就不做。"""
    logger = _get_logger()
    if not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
        new_log(sw, name)


def new_log(sw: Switch, name: str | None = None) -> None:
    """换一个新的日志文件，之后的日志写进去。"""
    logger = _get_logger()
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()
    prefix = name or Path(sys.argv[0]).stem or "control-switch"
    sw.config.log_dir.mkdir(parents=True, exist_ok=True)
    path = sw.config.log_dir / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_formatter)
    handler.addFilter(_RootOnly())
    logger.addHandler(handler)
