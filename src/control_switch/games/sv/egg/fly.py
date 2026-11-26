"""飞到零区闸口：人就在零区，按 Y 打开地图，一直按 A 直到画面变黑，等回到野外。"""

import logging
import time

from control_switch.flow import press_until, wait_until
from control_switch.vision import ImageChecker

from . import screens
from .config import EggConfig
from .session import EggSession


def is_map(image: ImageChecker, config: EggConfig) -> bool:
    """地图画面：左上角有「地图」两个字。"""
    return image.has_text(config.map_title, config.map_title_text)


def fly_to_gate(sw: EggSession) -> None:
    """按 Y 直到打开地图，一直按 A（飞翔、是）直到画面变黑，再等回到野外，回到之后再等 fly_settle_wait 秒。"""
    config = sw.config
    press_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: is_map(s, config),
        config.wait.timeout,
        "地图",
        interval=sw.config.wait.press_interval,
    )
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: s.is_black(),
        config.wait.timeout,
        "飞走的黑屏",
        interval=sw.config.wait.press_interval,
    )
    wait_until(sw, lambda s: screens.is_overworld(s, config), config.fly_timeout, "飞到零区闸口")
    # 刚认出野外画面时人还动不了，马上按键会被吃掉
    time.sleep(1)
    logging.info(f"飞到了{config.gate_name}")
