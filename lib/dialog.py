"""和游戏里的人对话：一页页推进对话、认出菜单。"""

import re
import time
from collections.abc import Callable

from config.layout import DIALOG_RECT, POPUP_RECT
from config.timing import DEFAULT_TIMEOUT, POLL_INTERVAL
from lib import switch
from lib.log import log
from lib.wait import capture
from tool.check_image import ImageChecker
from tool.image import text_lines
from type.image import Rect


def advance_until(
    done: Callable[[ImageChecker], bool],
    what: str,
    button: str = "A",
    max_presses: int = 10,
    timeout: float = DEFAULT_TIMEOUT,
) -> ImageChecker:
    """按 button 一页页推进对话，直到 done(截图) 为真，返回那张截图。

    每次按之前都先看一眼，已经满足就不再按，所以不会按在要等的菜单上。
    按完之后，要么 done 满足，要么对话翻到了新的一页才按下一次。「翻页」是指对话框里的文字
    和按之前不同、并且连续两帧一样：同一页的文字在不同帧上 OCR 会有细小差别（比如全角半角的
    问号），只看一帧会误以为翻了页，接着在还没画出来的菜单上又按一次（真机上因此付过罚款）。
    按了 max_presses 次还没满足抛 RuntimeError；按完一直不翻页抛 TimeoutError。
    what: 在等什么，写进报错里。
    """
    image = capture()
    for _ in range(max_presses):
        if done(image):
            return image
        before = _page_text(image)
        log(f"对话「{before}」，按 {button}（在等{what}）", "DEBUG")
        switch.get().click(button, 0)
        image = _wait_next_page(done, before, timeout, f"按 {button} 之后对话翻页（在等{what}）")
    if done(image):
        return image
    raise RuntimeError(f"按了 {max_presses} 次 {button}，还是没等到{what}")


def menu_items(image: ImageChecker) -> list[str]:
    """对话旁边弹出的菜单里的选项，从上到下；没有菜单就是空列表。"""
    return [text for text, _ in text_lines(image, POPUP_RECT)]


def menu_selected(image: ImageChecker) -> int:
    """对话旁边弹出的菜单里，当前选中的是第几项（从 0 开始），认不出返回 -1。"""
    lines = text_lines(image, POPUP_RECT)
    return image.selected([rect for _, rect in lines]) if lines else -1


def marker_shown(screen: ImageChecker, rect: Rect) -> bool:
    """rect 里有菜单光标「>」：白色描边加黑色填充。真机上有光标时白 0.15、黑 0.3，没有时都是 0。"""
    white = screen.color_ratio(rect, (0, 0, 220), (180, 40, 255))
    dark = screen.color_ratio(rect, (0, 0, 0), (180, 255, 40))
    return white > 0.08 and dark > 0.15


def _wait_next_page(
    done: Callable[[ImageChecker], bool], before: str, timeout: float, what: str
) -> ImageChecker:
    """一直截图，直到 done 满足，或者对话框里的文字和 before 不同、并且连续两帧一样。"""
    deadline = time.monotonic() + timeout
    last = None
    while True:
        image = capture()
        if done(image):
            return image
        text = _page_text(image)
        if text != before and text == last:
            return image
        last = text
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(POLL_INTERVAL)


def _page_text(image: ImageChecker) -> str:
    """对话框里的文字，去掉空白和标点，只留下用来比较是不是同一页的部分。"""
    return re.sub(r"[\s\W_]", "", image.read_text(DIALOG_RECT))
