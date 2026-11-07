"""日志：同时输出到终端和文件。只用标准库，系统自带的 Python 3.9 也能跑。

日志文件在项目根目录的 logs/ 下，文件名是「名字-年月日-时分秒.log」，
例如 find-20261104-153000.log。start 的日志放进 logs/start/ 目录，每局一个文件。
每次运行都是新文件，不会覆盖以前的。名字由 init_log 指定；没调用过 init_log 就直接 log 的话，
用脚本文件名。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

_logger: logging.Logger | None = None
# 上次 take_warnings 之后记过的 WARNING 和 ERROR，用来写进每局的战报
_warnings: list[str] = []
# 最后一次日志的时间和内容，通知的看门狗用
_last_time = time.time()
_last_message = ""
# 当前的日志文件，通知里带路径用
_path: Path | None = None
_formatter = logging.Formatter("%(asctime)s | %(levelname)s: %(message)s", "%H:%M:%S")


def init_log(name: str | None = None, subdir: bool = False, force: bool = False) -> None:
    """创建日志文件，文件名是「名字-年月日-时分秒.log」。

    name: 文件名的前缀，不传就用脚本文件名。
    subdir: 日志放进 logs/<名字>/ 目录里，文件名不带前缀。
    force: 已经有日志文件时先关掉再新建一个，用来每局输出一个日志文件。
    没 force 时，已经创建过就什么都不做，所以要在第一次 log 之前调用才有效。
    """
    global _logger, _path
    prefix = name or Path(sys.argv[0]).stem or "control-switch"
    if _logger is not None and not force:
        return
    if _logger is None:
        logger = logging.getLogger("control-switch")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        stream = logging.StreamHandler()
        stream.setFormatter(_formatter)
        logger.addHandler(stream)
        _logger = logger
    # 只换文件，终端输出保留
    for handler in list(_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            _logger.removeHandler(handler)
            handler.close()
    log_dir = Path(__file__).parent.parent / "logs"
    if subdir:
        log_dir = log_dir / prefix
        file_name = f"{time.strftime('%Y%m%d-%H%M%S')}.log"
    else:
        file_name = f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / file_name
    _path = path
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_formatter)
    _logger.addHandler(handler)


def log(message: str, level: str = "INFO") -> None:
    """记一条日志。

    message: 日志内容。
    level: DEBUG、INFO、WARNING、ERROR 之一，大小写都行。
    还没调用过 init_log 时，会先用脚本文件名调用一次。
    """
    global _last_time, _last_message
    init_log()
    assert _logger is not None
    _logger.log(logging.getLevelName(level.upper()), message)
    _last_time = time.time()
    _last_message = message
    if level.upper() in ("WARNING", "ERROR"):
        _warnings.append(message)


def take_warnings() -> list[str]:
    """上次调用之后记过的 WARNING 和 ERROR，取出后清空。"""
    taken = list(_warnings)
    _warnings.clear()
    return taken


def last_log() -> tuple[float, str]:
    """最后一次日志的时间和内容。"""
    return _last_time, _last_message


def log_path() -> Path | None:
    """当前的日志文件；还没创建时返回 None。"""
    return _path
