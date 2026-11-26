"""启动时的检查：确认按键真的送到了画面上的这台 Switch。"""

import logging

from control_switch.device import DeviceCheckError
from control_switch.session import Session

from .restart import home_shown
from .screen import capture, wait_until


def check_controller_reaches_screen(sw: Session) -> None:
    """按一下 HOME，画面变了再按一下，画面回到原来的状态。任何一步等超时抛 DeviceCheckError。"""
    was_home = home_shown(sw, capture(sw, "按键检查：现在是不是 HOME 菜单"))
    logging.info("检查按键：按 HOME")
    _press_and_wait(sw, not was_home, "第一次")
    _press_and_wait(sw, was_home, "第二次")
    logging.info("按键检查通过")


def _press_and_wait(sw: Session, want_home: bool, which: str) -> None:
    sw.click("HOME", 0)
    try:
        wait_until(
            sw,
            lambda screen: home_shown(sw, screen) == want_home,
            sw.config.check.timeout,
            f"按键检查：{which}按 HOME 后画面变化",
        )
    except TimeoutError as error:
        raise DeviceCheckError(
            f"按键：{which}按了 HOME，画面没有变化。可能是按键没有送到，或者取图和按键接的不是同一台 Switch"
        ) from error
