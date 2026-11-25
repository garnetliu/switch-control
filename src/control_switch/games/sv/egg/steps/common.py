"""几个步骤共用的走路操作：推摇杆、离开零区闸口。"""

from typing import cast

from control_switch.session import Session

from ..config import EggConfig

# 每个方向推满时 (x, y) 是摇杆最大值的几倍，y 正数向上
DIRECTIONS = {"U": (0, 1), "D": (0, -1), "L": (-1, 0), "R": (1, 0)}


def push(sw: Session, side: str, direction: str, seconds: float) -> None:
    x, y = DIRECTIONS[direction]
    stick_max = sw.controller.STICK_MAX
    sw.stick(side, x * stick_max, y * stick_max, seconds)


def leave_gate(sw: Session, walk: float) -> None:
    """在零区闸口的飞行点上：转镜头，往右前方走，让人背对观测站，再转镜头、往前走 walk 秒。"""
    config = cast(EggConfig, sw.config)
    sw.click("L", config.camera_wait)
    sw.stick(
        "LEFT",
        sw.controller.STICK_MAX,
        round(sw.controller.STICK_MAX * config.gate_turn_y),
        config.gate_turn,
    )
    sw.click("L", config.camera_wait)
    push(sw, "LEFT", "U", walk)
