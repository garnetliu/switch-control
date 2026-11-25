"""picnic：开野餐。"""

import logging
import time

from control_switch.flow import wait_for

from .. import screens
from ..box import (
    exit_to_overworld,
    menu_to_row,
    open_box,
    open_menu,
    set_riding,
)
from ..fly import fly_to_gate
from ..session import EggSession
from .common import leave_gate
from .party import to_picnic_party


def picnic(sw: EggSession) -> str:
    """没骑坐骑，转镜头，开野餐。"""
    sw.frames.clear()
    config = sw.config
    open_box(sw)
    to_picnic_party(sw)
    exit_to_overworld(sw)
    # 照 PokemonAutomation picnic_at_zero_gate：飞到零区闸口，背对观测站往外走一段再开野餐
    fly_to_gate(sw)
    set_riding(sw, False)
    leave_gate(sw, config.picnic_walk)
    open_menu(sw)
    menu_to_row(sw, 2)
    wait_for(sw, lambda s: screens.is_picnic(s, config), config.picnic_timeout, "野餐画面")
    # 刚开野餐时人在丢精灵球，这段动画里不能动
    time.sleep(config.picnic_settle_wait)
    sw.picnics += 1
    logging.info(f"开了第 {sw.picnics} 次野餐")
    return "sandwich"
