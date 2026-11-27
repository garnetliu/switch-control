"""在野外开野餐，认到野餐的画面、等丢精灵球的动画放完为止。"""

import logging
import time

from control_switch.flow import capture, wait_until
from control_switch.games.sv import verify
from control_switch.games.sv.session import SvSession

from .menu_to_row import menu_to_row
from .open_menu import open_menu


def open_picnic(sw: SvSession) -> None:
    """在野外开野餐，认到野餐的画面、等丢精灵球的动画放完为止。

    状态：野外按 X 开菜单；菜单里把光标移到「野餐」按 A。
    """
    config = sw.config
    logging.info("开野餐")
    # 开野餐最多等几秒，认出之后再等几秒（丢精灵球的动画期间人不能动）
    timeout = 120.0
    deadline = time.monotonic() + timeout
    while True:
        image = capture(sw, "开野餐")
        if verify.is_picnic(image, config):
            break
        if verify.is_overworld(image, config):
            open_menu(sw)
        elif verify.is_main_menu(image, config):
            menu_to_row(sw, config.menu.picnic_row)
            # 进野餐的动画里画面还像野外，不能再按 X，等野餐的画面出来
            wait_until(
                sw,
                lambda s: verify.is_picnic(s, config),
                "野餐的画面",
                timeout=timeout,
            )
            break
        else:
            time.sleep(config.wait.interval)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，还是没开成野餐")
    time.sleep(8.0)
    capture(sw, "野餐")
