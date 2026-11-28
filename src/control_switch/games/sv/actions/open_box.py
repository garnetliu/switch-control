"""在野外打开盒子，认到盒子的画面为止。"""

import logging

from control_switch.games.sv import verify
from control_switch.games.sv.session import SvSession

from .main_menu_open import main_menu_open
from .main_menu_to_row import main_menu_to_row


def open_box(sw: SvSession) -> None:
    """在野外打开盒子：按 X 开主菜单，把光标移到「盒子」按 A，等到盒子画面（连着几帧读到一样的盒子编号）。"""
    logging.info("开盒子")
    main_menu_open(sw)
    # 主菜单里「盒子」是第 1 行（从 0 数）；打开盒子最多等 30 秒
    main_menu_to_row(sw, 1)
    verify.box_title(sw)
