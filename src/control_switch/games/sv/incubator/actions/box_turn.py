from control_switch.games.sv import verify as sv_verify

from ..session import IncubatorSession


def box_turn(sw: IncubatorSession, target: int) -> None:
    """换到编号是 target 的盒子：往近的那边按 L 或 R，一次换一个，每按一下读一次盒子编号，按键被吞了就再按。"""
    count = sw.config.box_count
    current = sv_verify.box_title(sw)
    while current != target:
        # 往右要换几个；最后一个盒子往右是第一个
        right = (target - current) % count
        sw.click("R" if right <= count - right else "L", 0)
        current = sv_verify.box_title(sw)
