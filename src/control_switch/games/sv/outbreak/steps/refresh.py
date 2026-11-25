"""refresh：开野餐再收起，身边的宝可梦重新生成。"""

import time

from control_switch.games.sv.actions import close_picnic, open_picnic

from ..session import OutbreakSession


def refresh(sw: OutbreakSession) -> str:
    """开野餐再收起，身边的宝可梦会重新生成。"""
    # 新的一轮从这里开始，上一轮没出错，截图丢掉
    sw.frames.clear()
    open_picnic(sw)
    close_picnic(sw)
    time.sleep(sw.config.spawn_wait)
    return "scan"
