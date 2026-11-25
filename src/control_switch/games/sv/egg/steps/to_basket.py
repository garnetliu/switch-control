"""to_basket：走到篮子前。"""

import time

from ..session import EggSession
from .common import push


def to_basket(sw: EggSession) -> str:
    """收回坐骑，走到篮子前。"""
    sw.frames.clear()
    config = sw.config
    sw.click("PLUS", config.unride_wait)
    for action, seconds in config.basket_route:
        if action == "btn:L":
            sw.click("L", seconds)
        else:
            push(sw, "LEFT", action, seconds)
            time.sleep(config.basket_step_wait)
    sw.eggs_in_box = 0
    return "collect"
