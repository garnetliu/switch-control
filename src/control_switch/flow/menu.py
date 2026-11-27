"""菜单：认出菜单的选项，把光标移到目标选项。"""

import logging
from collections.abc import Callable

from control_switch.flow.screen import press_until
from control_switch.session import Session
from control_switch.types import Rect
from control_switch.vision import ImageChecker
from control_switch.vision.text import levenshtein


def menu_last_item(
    screen: ImageChecker,
    area: Rect,
    index: int = -1,
    dialog: Rect | None = None,
) -> str:
    """读 area 里的菜单第 index 项的文本，默认最后一项；没有菜单返回空字符串。

    菜单只跟着对话出现时传 dialog（对话文字的范围）：那里没有文字就当作没有菜单。
    """
    if dialog is not None and not screen.read_text(dialog):
        return ""
    found = screen.find_menu(area)
    if found is None:
        return ""
    _, options = found
    return options[index][0] if -len(options) <= index < len(options) else ""


def move_menu_option(
    sw: Session,
    image: ImageChecker,
    target: int | str,
    move: Callable[[], None],
    what: str,
    area: Rect,
) -> int:
    """把菜单光标移到目标项，返回下标。

    target 是序号或文字；文字按编辑距离和菜单里的选项比。
    move 是移一格的操作，比如按 DDOWN 或 DUP。
    area 是找菜单的搜索范围。
    """
    found = image.find_menu(area)
    if found is None:
        raise RuntimeError(f"{what}里找不到菜单")
    _, options = found
    # 光标的箭头有时会被单独认成一行字「>」（真机上三项的传说菜单出现过），不是选项，去掉
    options = [(text, rect) for text, rect in options if text.strip(" >＞›》〉")]
    texts = [text for text, _ in options]
    rects = [rect for _, rect in options]

    label = None
    if isinstance(target, str):
        index = next(
            (i for i, text in enumerate(texts) if levenshtein(text, target) <= len(target) / 3),
            None,
        )
        if index is None:
            raise RuntimeError(f"{what}里找不到「{target}」，读到的选项: {texts}")
        label = texts[index]
    else:
        index = target

    for _ in range(len(rects)):
        current = image.selected(rects)
        if current == index:
            if label is not None:
                logging.info(f"{what}选中了「{label}」")
            return index
        image = press_until(
            sw,
            move,
            lambda screen, before=current: screen.selected(rects) not in (before, -1),
            f"{what}的光标移一格",
        )
    raise RuntimeError(f"{what}的光标移了 {len(rects)} 次，还是没到第 {index + 1} 项")
