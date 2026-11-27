"""在野外打开盒子，认到盒子的画面为止。"""

import logging

from control_switch.flow import wait_until
from control_switch.games.sv import screens
from control_switch.games.sv.session import SvSession

from .menu_to_row import menu_to_row
from .open_menu import open_menu


def open_box(sw: SvSession) -> None:
    """在野外打开盒子：按 X 开主菜单，把光标移到「盒子」按 A，等到盒子画面（读得出盒子编号）。"""
    config = sw.config
    logging.info("开盒子")
    open_menu(sw)
    menu_to_row(sw, config.box.menu_row)
    wait_until(
        sw,
        lambda s: screens.box_title(s, config) is not None,
        "盒子画面",
        timeout=config.box.open_timeout,
    )
