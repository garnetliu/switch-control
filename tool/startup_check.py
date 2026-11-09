import time

from lib import switch_v1 as switch
from tool.check_image import ImageChecker

# 画面下方的对话框
DIALOG_RECT = ((0.17, 0.79), (0.83, 0.98))
# 在科学家面前按 A，对话框里出现的第一句话
DIALOG_TEXT = "您现在要出发挑战极巨大冒险吗"


def check_startup(max_b: int = 30) -> bool:
    """按 A 进入对话，然后一直按 B 退出，直到回到初始状态。

    能回到初始状态（对话框区域没有文字）返回 True；按 A 后对话框里没有 DIALOG_TEXT，
    或者按了 max_b 次 B 对话框仍在，返回 False。使用全局连接，需要先调用 switch.connect。
    """
    sw = switch.get()
    sw.click("A")
    time.sleep(1)
    if not ImageChecker(sw.pixel_peek()).has_text(DIALOG_RECT, DIALOG_TEXT):
        return False
    for _ in range(max_b):
        sw.click("B")
        if not ImageChecker(sw.pixel_peek()).read_text(DIALOG_RECT):
            return True
    return False
