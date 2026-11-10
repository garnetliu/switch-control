"""菜单光标：找到目标选项，把光标移过去。"""

import logging
from collections.abc import Callable

from libs import ImageChecker
from libs.switch import Switch
from tools.text import levenshtein
from tools.wait import act_until
from type import Rect


def move_menu_option(
    sw: Switch,
    image: ImageChecker,
    target: int | str,
    move: Callable[[], None],
    what: str,
    area: Rect | None = None,
) -> int:
    """把菜单光标移到目标项，返回下标。

    target 是序号或文字；文字按编辑距离和菜单里的选项比。
    move 是移一格的操作，比如按 DDOWN 或 DUP。
    area 是找菜单的搜索范围，默认是对话菜单的范围。
    """
    if area is None:
        area = sw.config.rects.menu_search
    found = image.find_menu(area)
    if found is None:
        raise RuntimeError(f"{what}里找不到菜单")
    _, options = found
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
        image = act_until(
            sw,
            move,
            lambda screen, before=current: screen.selected(rects) not in (before, -1),
            f"{what}的光标移一格",
        )
    raise RuntimeError(f"{what}的光标移了 {len(rects)} 次，还是没到第 {index + 1} 项")
