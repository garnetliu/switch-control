"""朱紫几个脚本都会用到的操作：存档、开野餐、收野餐、从主菜单进某一项。

每一步按完都看画面，认到了才走下一步，没反应就再按（照 PokemonAutomation 的 save_game_from_overworld、
picnic_from_overworld、leave_picnic）。每一步等完都截一张图记在内存里，出错时会写进日志目录。
"""

import logging
import time
from typing import cast

from control_switch.flow import act_until, capture, wait_for
from control_switch.games.sv import screens
from control_switch.games.sv.config import SvConfig
from control_switch.session import Session


def save_game(sw: Session) -> None:
    """在野外存档，存完回到野外。

    状态：野外按 X 开菜单；菜单按 R 出存档的确认框；确认框按 A；存完的对话按 B，菜单再按 B 回到野外。
    """
    config = cast(SvConfig, sw.config)
    logging.info("存档")
    deadline = time.monotonic() + config.save_timeout
    saved = False
    # 按了「是」之后，存档的过程中菜单还在，不能再按 R；存完的对话一直没出来才重来
    confirmed_at: float | None = None
    while True:
        image = capture(sw, "存档")
        now = time.monotonic()
        if confirmed_at is not None and now - confirmed_at > config.save_confirm_timeout:
            confirmed_at = None
        if screens.is_overworld(image, config):
            if saved:
                return
            sw.click("X", config.save_press_wait)
        elif screens.is_prompt(image, config):
            sw.click("A", config.save_press_wait)
            confirmed_at = now
        elif screens.is_dialog(image, config):
            sw.click("B", config.save_press_wait)
            saved = True
            confirmed_at = None
        elif screens.has_dialog_box(image, config):
            # 字还在一个个出来，等它出完
            time.sleep(config.wait.interval)
        elif screens.is_main_menu(image, config):
            if confirmed_at is None:
                sw.click("B" if saved else "R", config.save_press_wait)
            else:
                time.sleep(config.wait.interval)
        else:
            time.sleep(config.wait.interval)
        if now >= deadline:
            raise TimeoutError(f"等了 {config.save_timeout} 秒，还是没存完档")


def open_menu(sw: Session) -> None:
    """在野外按 X 打开主菜单，认到菜单为止。

    按 X 有时没反应（真机上刚退回野外时按的那次被吞掉过），所以隔 menu_retry 秒没出菜单就再按一次。
    """
    config = cast(SvConfig, sw.config)
    act_until(
        sw,
        lambda: sw.click("X", 0),
        lambda s: screens.is_main_menu(s, config),
        "主菜单",
        interval=config.menu_retry,
    )


def menu_to_row(sw: Session, row: int) -> None:
    """主菜单里把光标移到右边第 row 行（从 0 数），按 A 进去。

    光标可能在左边的队伍栏上（上次是从队伍栏退出来的），先按 DRIGHT 到右边。
    """
    config = cast(SvConfig, sw.config)
    image = capture(sw, "主菜单")
    if screens.menu_row(image, config) == -1:
        image = act_until(
            sw,
            lambda: sw.click("DRIGHT", 0),
            lambda s: screens.menu_row(s, config) != -1,
            "主菜单光标到右边",
            interval=config.menu_move_wait,
        )
    current = screens.menu_row(image, config)
    while current != row:
        button = "DDOWN" if row > current else "DUP"
        before = current
        image = act_until(
            sw,
            lambda button=button: sw.click(button, 0),
            lambda s, before=before: screens.menu_row(s, config) not in (before, -1),
            "主菜单的光标移一格",
            interval=config.menu_move_wait,
        )
        current = screens.menu_row(image, config)
    # A 有时被吞掉（菜单还在），隔一会儿没进去就再按一次
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_main_menu(s, config),
        "进主菜单的这一行",
        interval=config.menu_enter_interval,
    )


def open_picnic(sw: Session) -> None:
    """在野外开野餐，认到野餐的画面、等丢精灵球的动画放完为止。

    状态：野外按 X 开菜单；菜单里把光标移到「野餐」按 A。
    """
    config = cast(SvConfig, sw.config)
    logging.info("开野餐")
    deadline = time.monotonic() + config.picnic_timeout
    while True:
        image = capture(sw, "开野餐")
        if screens.is_picnic(image, config):
            break
        if screens.is_overworld(image, config):
            open_menu(sw)
        elif screens.is_main_menu(image, config):
            menu_to_row(sw, config.menu_picnic_row)
            # 进野餐的动画里画面还像野外，不能再按 X，等野餐的画面出来
            wait_for(
                sw, lambda s: screens.is_picnic(s, config), config.picnic_timeout, "野餐的画面"
            )
            break
        else:
            time.sleep(config.wait.interval)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.picnic_timeout} 秒，还是没开成野餐")
    time.sleep(config.picnic_settle_wait)
    capture(sw, "野餐")


def close_picnic(sw: Session) -> None:
    """收起野餐，回到野外：按 Y 直到出确认框，按 A 直到回到野外，最后再等一会儿。"""
    config = cast(SvConfig, sw.config)
    logging.info("收起野餐")
    act_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: screens.is_prompt(s, config),
        "结束野餐的确认",
        interval=config.leave_prompt_interval,
        timeout=config.leave_prompt_timeout,
    )
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_overworld(s, config),
        "回到野外",
        interval=config.leave_overworld_interval,
        timeout=config.leave_overworld_timeout,
    )
    time.sleep(config.leave_final_wait)
