"""调试用：每检查一次截图的某个区域，就把这个区域框出来，存一张图。

环境变量 SAVE_CHECKS=1 打开这个功能；打开后只在 config/debug.py 的 SAVE_CHECK_STEPS 里那几步存，
lib.wait.capture 截的图就是 SavingImageChecker，见 should_save。
"""

import os
import sys
import time

import cv2
import numpy as np

from config.debug import SAVE_CHECK_STEPS
from config.paths import CHECK_DIR
from tool.check_image import ImageChecker
from type.image import Rect

# 现在在跑哪一步，main.py 每开始一步就调用 set_step
_step = ""


def set_step(step: str) -> None:
    """记下现在在跑哪一步，决定这一步的截图要不要存检查区域。"""
    global _step
    _step = step


def current_step() -> str:
    """返回 main.py 当前正在执行的步骤名。"""
    return _step


def should_save() -> bool:
    """这一步要不要存检查区域：环境变量 SAVE_CHECKS=1，并且这一步在 SAVE_CHECK_STEPS 里。"""
    return os.environ.get("SAVE_CHECKS") == "1" and _step in SAVE_CHECK_STEPS


class SavingImageChecker(ImageChecker):
    """和 ImageChecker 一样，只是每次裁剪区域（也就是每次检查）时，在整张截图上画出这个区域，存进 CHECK_DIR。

    文件名是「时分秒-毫秒-哪一步-在检查什么」，在检查什么取调用栈上最近的两个函数名，例如
    read_text-_den_state。ImageChecker 的检查方法和 tool/image.py 的函数都通过 _crop 裁剪区域。
    """

    def _crop(self, img: np.ndarray, rect: Rect) -> np.ndarray:  # type: ignore[override]
        height, width = self._bgr.shape[:2]
        (left, top), (right, bottom) = rect
        marked = self._bgr.copy()
        cv2.rectangle(
            marked,
            (round(left * width), round(top * height)),
            (round(right * width), round(bottom * height)),
            (0, 0, 255),
            3,
        )
        caller = sys._getframe(1)
        callers = f"{caller.f_code.co_name}-{caller.f_back.f_code.co_name if caller.f_back else ''}"
        now = time.time()
        stamp = f"{time.strftime('%H%M%S', time.localtime(now))}-{int(now * 1000) % 1000:03d}"
        CHECK_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(CHECK_DIR / f"{stamp}-{_step}-{callers}.jpg"), marked)
        return ImageChecker._crop(img, rect)
