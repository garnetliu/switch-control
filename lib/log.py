"""日志：同时输出到终端和文件。只用标准库，系统自带的 Python 3.9 也能跑。

日志文件在项目根目录的 logs/ 下，文件名是「名字-年月日-时分秒.log」，
例如 find-20261104-153000.log。每次运行都是新文件，不会覆盖以前的。
名字由 init_log 指定；没调用过 init_log 就直接 log 的话，用脚本文件名。
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

_logger: logging.Logger | None = None


def init_log(name: str | None = None) -> None:
    """创建日志文件，文件名是「name-年月日-时分秒.log」。

    name: 文件名的前缀，不传就用脚本文件名。
    已经创建过就什么都不做，所以要在第一次 log 之前调用才有效。
    """
    global _logger
    if _logger is not None:
        return
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    prefix = name or Path(sys.argv[0]).stem or "control-switch"
    path = log_dir / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.log"

    logger = logging.getLogger("control-switch")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)s: %(message)s", "%H:%M:%S")
    for handler in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    _logger = logger


def log(message: str, level: str = "INFO") -> None:
    """记一条日志。

    message: 日志内容。
    level: DEBUG、INFO、WARNING、ERROR 之一，大小写都行。
    还没调用过 init_log 时，会先用脚本文件名调用一次。
    """
    init_log()
    assert _logger is not None
    _logger.log(logging.getLevelName(level.upper()), message)
