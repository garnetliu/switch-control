"""sandwich：做超级花生酱三明治。"""

import logging
import time
from typing import cast

from control_switch.flow import act_until, capture, wait_for
from control_switch.session import Session
from control_switch.vision import ImageChecker

from .. import screens
from ..config import EggConfig
from ..session import EggSession
from .common import DIRECTIONS, push


def _is_making(image: ImageChecker, config: EggConfig) -> bool:
    """已经在做三明治：底下有「长按以抓起」的提示。"""
    return image.has_text(config.making_hint, config.making_hint_text)


def _reach_table(sw: Session) -> None:
    """走到桌子前按 A，等对话框；前面有宝可梦挡着就吹口哨再试。"""
    config = cast(EggConfig, sw.config)
    for attempt in range(config.table_attempts):
        if attempt:
            sw.click("R", config.whistle_wait)
        push(sw, "LEFT", "U", config.walk_to_table)
        sw.click("A", config.press_wait)
        try:
            wait_for(sw, lambda s: screens.is_dialog(s, config), config.dialog_wait, "桌子的对话")
            return
        except TimeoutError:
            continue
    raise RuntimeError("走到桌子前按 A，一直没有对话框，可能前面有宝可梦挡着")


def _fill(sw: Session) -> None:
    """放 3 片香蕉。"""
    config = cast(EggConfig, sw.config)
    for action, seconds in config.filling_moves:
        if action in DIRECTIONS:
            push(sw, "LEFT", action, seconds)
        elif action == "A+":
            sw.press("A")
            time.sleep(seconds)
        elif action == "A-":
            sw.release("A")
            time.sleep(seconds)
        elif action.startswith("A+") and action[2:] in DIRECTIONS:
            push(sw, "LEFT", action[2:], seconds)
        else:
            raise ValueError(f"不认识的动作：{action}")


def sandwich(sw: EggSession) -> str:
    """做超级花生酱三明治。"""
    sw.frames.clear()
    config = sw.config
    _reach_table(sw)
    # 桌子的菜单第一项是「做料理」，按 A 直到出食谱画面
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: s.has_text(config.recipe_title, "食谱"),
        "食谱画面",
        interval=config.table_interval,
        timeout=config.table_timeout,
    )
    time.sleep(config.recipe_wait)
    for _ in range(config.recipe_downs):
        sw.click("DDOWN", config.recipe_down_wait)
    if not capture(sw, "食谱 17").has_text(config.recipe_name, config.recipe_name_text):
        raise RuntimeError(f"食谱 17 不是{config.recipe_name_text}，可能没解锁或者材料不够")
    # 进选签子的界面，再按 A 开始做，每一步都认画面
    # 选签子的界面有时一闪而过（按 A 太快会直接开始做），所以等「选签子」或者「已经在做」任一个
    image = act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_pick_screen(s, config) or _is_making(s, config),
        "选签子的界面",
        interval=config.pick_press_interval,
    )
    if not _is_making(image, config):
        act_until(
            sw,
            lambda: sw.click("A", 0),
            lambda s: _is_making(s, config),
            "开始做三明治",
            interval=config.make_press_interval,
        )
    time.sleep(config.start_wait)
    try:
        _fill(sw)
    except BaseException:
        sw.release("A")
        sw.release_stick("LEFT")
        raise
    push(sw, "LEFT", "L", config.bread_left)
    sw.click("A", config.bread_wait)
    sw.click("A", config.skewer_wait)
    deadline = time.monotonic() + config.eat_timeout
    while not screens.is_picnic(capture(sw, "吃三明治"), config):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.eat_timeout} 秒，三明治还没吃完")
        sw.click("A", config.eat_wait)
    sw.sandwich_at = time.monotonic()
    logging.info("三明治做好了")
    return "to_basket"
