"""存截图：判定成功时的截图和长期留着的截图。"""

import logging
import os
import time
from pathlib import Path

import cv2

from libs import ImageChecker, Switch
from type import Rect


def _save_image(image: ImageChecker, path: Path, *rects: Rect) -> None:
    """把截图存到 path，rects 里的范围画成红框；不传 rects 就是原图。"""
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
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), marked)


def save_check(sw: Switch, image: ImageChecker, name: str, *rects: Rect) -> None:
    """判定成功时把截图存进 check_dir，判定用的范围画成红框。

    环境变量 SAVE_CHECKS 写要存的步骤名字，用逗号分开，比如 SAVE_CHECKS=join,battle；
    现在的步骤（sw.game.step）在里面才存，没设置就都不存。文件名是「时分秒-毫秒-name」。
    """
    steps = [step.strip() for step in os.environ.get("SAVE_CHECKS", "").split(",")]
    if not sw.game.step or sw.game.step not in steps:
        return
    now = time.time()
    stamp = f"{time.strftime('%H%M%S', time.localtime(now))}-{int(now * 1000) % 1000:03d}"
    name = name.replace("/", "_")
    _save_image(image, sw.config.check_dir / f"{stamp}-{name}.jpg", *rects)


def keep_image(sw: Switch, image: ImageChecker, name: str) -> None:
    """每种画面长期留一张：原图存到 keep_dir/name.jpg，不看环境变量，已经有同名的就不存。

    keep_dir 这个目录 initialize 清空 logs 时不删。
    """
    path = sw.config.keep_dir / f"{name.replace('/', '_')}.jpg"
    if path.exists():
        return
    _save_image(image, path)
    logging.info(f"留下一张「{name}」的画面: {path}")
