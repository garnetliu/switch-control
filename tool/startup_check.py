import time

from lib import switch
from tool.check_image import check_image, read_text

# 画面下方的对话框
DIALOG_RECT = ((0.17, 0.79), (0.83, 0.98))


def check_startup(text: str, max_b: int = 30) -> bool:
    """按 A 进入对话，然后一直按 B 退出，直到回到初始状态。

    text: 按 A 之后，对话框里应该出现的文字。
    能回到初始状态（对话框区域没有文字）返回 True；按 A 后对话框里没有 text，
    或者按了 max_b 次 B 对话框仍在，返回 False。使用全局连接，需要先调用 switch.connect。
    """
    sw = switch.get()
    sw.click("A")
    time.sleep(1)
    if not check_image(sw.pixel_peek(), DIALOG_RECT, text):
        return False
    for _ in range(max_b):
        sw.click("B")
        if not read_text(sw.pixel_peek(), DIALOG_RECT):
            return True
    return False
