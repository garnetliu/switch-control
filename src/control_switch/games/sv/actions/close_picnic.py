"""收起野餐，回到野外：按 Y 直到出确认框，按 A 直到回到野外，最后再等一会儿。"""

import logging
import time

from control_switch.flow import press_until
from control_switch.games.sv import screens
from control_switch.games.sv.session import SvSession


def close_picnic(sw: SvSession) -> None:
    """收起野餐，回到野外：按 Y 直到出确认框，按 A 直到回到野外，最后再等一会儿。"""
    config = sw.config
    logging.info("收起野餐")
    press_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: screens.is_prompt(s, config),
        "结束野餐的确认",
        timeout=config.picnic.leave_prompt_timeout,
    )
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_overworld(s, config),
        "回到野外",
        timeout=config.picnic.leave_overworld_timeout,
    )
    time.sleep(config.picnic.leave_final_wait)
