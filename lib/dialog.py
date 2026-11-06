"""和游戏里的人对话：一页页推进对话、认出菜单。"""

import re
import time
from collections.abc import Callable

from config.layout import DIALOG_RECT, MENU_BOX_RECT, MENU_LAST_ITEM_RECT, POPUP_RECT
from config.timing import DEFAULT_TIMEOUT, POLL_INTERVAL
from lib import switch
from lib.log import log
from lib.wait import capture, save_timeout_frames
from tool.check_image import ImageChecker
from tool.image import read_line, text_lines
from tool.text import similarity
from type.image import Rect

# 两次读到的对话文字相似度至少这么多，就算是同一页
SAME_PAGE = 0.9


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
    和按之前不像了（相似度低于 SAME_PAGE）、并且连续两帧差不多：同一页的文字在不同帧上 OCR 会有
    细小差别（全角半角的问号、右下角闪烁的「▼」被认成字），只看一帧会误以为翻了页，接着在还没
    画出来的菜单上又按一次（真机上因此付过罚款）；要求一字不差又会一直等不到（真机上卡住过）。
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


def press_until(
    done: Callable[[ImageChecker], bool],
    what: str,
    button: str = "A",
    max_presses: int = 100,
    interval: float = 0.5,
) -> ImageChecker:
    """一直按 button，直到 done(截图) 为真，返回那张截图。不认中间出现的是什么对话，也不等翻页。

    按一次之后的 interval 秒里一直看画面，满足了就不再按，免得按在要等的菜单上；没满足就再按。
    按键偶尔会被游戏吞掉（USB 真机上连着好几次没反应），所以不等画面变化，只管接着按。
    按了 max_presses 次还没满足抛 RuntimeError。what: 在等什么，写进报错里。
    """
    for _ in range(max_presses):
        screen = capture()
        if done(screen):
            return screen
        log(f"按 {button}（在等{what}）", "DEBUG")
        switch.get().click(button, 0)
        deadline = time.monotonic() + interval
        while time.monotonic() < deadline:
            screen = capture()
            if done(screen):
                return screen
            time.sleep(POLL_INTERVAL)
    raise RuntimeError(f"按了 {max_presses} 次 {button}，还是没等到{what}")


def menu_last_item(screen: ImageChecker) -> str:
    """对话旁边弹出的菜单的最后一行，没有菜单返回空字符串。

    先看菜单的白色底在不在（不到 1 毫秒），在了才只识别最后那一行（约 0.01 秒）。
    """
    if screen.color_ratio(MENU_BOX_RECT, (0, 0, 220), (180, 30, 255)) < 0.3:
        return ""
    return read_line(screen, MENU_LAST_ITEM_RECT)


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
    """一直截图，直到 done 满足，或者对话框里的文字和 before 不像了、并且连续两帧差不多。

    超时时存下开始等时和最后一帧的截图，报错里写上最后读到的文字。
    """
    deadline = time.monotonic() + timeout
    last = None
    first = None
    while True:
        image = capture()
        first = first or image
        if done(image):
            return image
        text = _page_text(image)
        # 对话框右下角闪烁的「▼」有时会被认成一个字，所以不要求一字不差：
        # 和按之前那页不像了，并且连续两帧差不多，就算翻到了新的一页
        if (
            last is not None
            and similarity(text, before) < SAME_PAGE
            and similarity(text, last) >= SAME_PAGE
        ):
            return image
        last = text
        if time.monotonic() >= deadline:
            save_timeout_frames(first, image)
            raise TimeoutError(
                f"等了 {timeout} 秒，画面一直没有出现：{what}（按之前「{before}」，最后「{text}」）"
            )
        time.sleep(POLL_INTERVAL)


def _page_text(image: ImageChecker) -> str:
    """对话框里的文字，去掉空白和标点，只留下用来比较是不是同一页的部分。"""
    return re.sub(r"[\s\W_]", "", image.read_text(DIALOG_RECT))
