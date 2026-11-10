"""日志：配置输出到终端和文件。"""

import logging
import os
import sys
import time
from pathlib import Path

import cv2

from libs import ImageChecker, Switch
from type import Rect

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
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
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
    directory = sw.config.log_dir / prefix
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_formatter)
    handler.addFilter(_RootOnly())
    logger.addHandler(handler)


def save_check(sw: Switch, image: ImageChecker, name: str, *rects: Rect) -> None:
    """判定成功时把截图存进 check_dir，判定用的范围画成红框。

    环境变量 SAVE_CHECKS=1 时才存。文件名是「时分秒-毫秒-name」。
    """
    if os.environ.get("SAVE_CHECKS") != "1":
        return
    marked = image.bgr.copy()
    height, width = marked.shape[:2]
    for (left, top), (right, bottom) in rects:
        cv2.rectangle(
            marked,
            (round(left * width), round(top * height)),
            (round(right * width), round(bottom * height)),
            (0, 0, 255),
            3,
        )
    now = time.time()
    stamp = f"{time.strftime('%H%M%S', time.localtime(now))}-{int(now * 1000) % 1000:03d}"
    sw.config.check_dir.mkdir(parents=True, exist_ok=True)
    name = name.replace("/", "_")
    cv2.imwrite(str(sw.config.check_dir / f"{stamp}-{name}.jpg"), marked)
