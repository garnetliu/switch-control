"""和极巨大冒险的科学家说话：打开开场对话，有中途退出的罚款就先付掉。"""

import re

from config.layout import DIALOG_RECT, ORE_RECT, YES_NO_RECTS
from config.timing import DEFAULT_TIMEOUT
from lib import switch
from lib.dialog import advance_until
from lib.log import log
from lib.wait import wait_for
from tool.check_image import ImageChecker

# 在科学家面前按 A 之后的开场白
START_TEXT = "您现在要出发挑战极巨大冒险吗"
# 有中途退出的记录时，按 A 之后先说的是这个，接着要求付极矿石作为罚款
PENALTY_TEXT = "中途退出的记录"
# 罚款对话最后一页的问话，同时弹出「是 / 否」
PENALTY_QUESTION = "可以吗"


def open_start_dialog() -> ImageChecker:
    """在科学家面前按 A，直到出现开场白，返回那时的截图。

    开始时游戏要停在科学家面前、没有对话框。使用全局连接，需要先调用 switch.connect。
    有中途退出的记录时，科学家会先要求付极矿石作为罚款，这里照付，日志里写明付之前有多少，
    付完对话结束，再按一次 A 打开开场白。
    """
    image = _press_a_at_scientist()
    if image.has_text(DIALOG_RECT, PENALTY_TEXT):
        _pay_penalty()
        image = _press_a_at_scientist()
        if not image.has_text(DIALOG_RECT, START_TEXT):
            raise RuntimeError("付完罚款再说话，出现的还不是开场白")
    return image


def _press_a_at_scientist() -> ImageChecker:
    """按 A，等出现开场白或者罚款的对话。"""
    switch.get().click("A", 0)
    return wait_for(
        lambda screen: (
            screen.has_text(DIALOG_RECT, START_TEXT) or screen.has_text(DIALOG_RECT, PENALTY_TEXT)
        ),
        DEFAULT_TIMEOUT,
        "科学家的开场白或罚款对话",
    )


def _pay_penalty() -> None:
    """罚款对话：推进到「是 / 否」，确认光标在「是」上再按 A，然后把对话推进完。"""
    image = advance_until(_yes_no_shown, "付罚款的是 / 否")
    log(f"科学家要求付罚款：{image.read_text(DIALOG_RECT)}；现有 {_ore(image)}", "WARNING")
    if image.selected(list(YES_NO_RECTS)) != 0:
        raise RuntimeError("付罚款的菜单上光标不在「是」上")
    switch.get().click("A", 0)
    # 付完之后还有一句话，推进到对话框消失
    advance_until(lambda screen: not screen.read_text(DIALOG_RECT), "罚款对话结束")
    log("罚款已付")


def _yes_no_shown(screen: ImageChecker) -> bool:
    """罚款的「是 / 否」菜单弹出来了：对话问「可以吗」，并且两行里有一行明显变暗（选中）。"""
    return screen.selected(list(YES_NO_RECTS)) >= 0 and screen.has_text(
        DIALOG_RECT, PENALTY_QUESTION
    )


def _ore(image: ImageChecker) -> str:
    """画面右上角显示的极矿石数量，例如「519 个极矿石」，读不出就返回读到的原文。"""
    text = image.read_text(ORE_RECT)
    match = re.search(r"(\d+)\s*$", text)
    return f"{match.group(1)} 个极矿石" if match else f"极矿石（读到「{text}」）"
