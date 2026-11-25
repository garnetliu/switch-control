"""hatch_load：在盒子里找蛋，三个一组放进队伍。"""

from .. import screens
from ..box import (
    exit_to_overworld,
    open_box,
    read_name,
    select_box,
    stable_egg_cells,
)
from ..session import EggSession
from .party import EGG_SLOTS, slot_name, swap, to_hatch_party


def hatch_load(sw: EggSession) -> str:
    """按 egg_boxes 的顺序，在盒子画面里找蛋，放进队伍第 2–6 格里的空格。"""
    sw.frames.clear()
    config = sw.config
    open_box(sw)
    to_hatch_party(sw)
    # 队伍第 2–6 格里可能还留着蛋（上次没孵完），只往空格里放
    waiting = 0
    free: list[int] = []
    for slot in EGG_SLOTS:
        name = slot_name(sw, ("party", slot))
        if screens.is_egg_name(name):
            waiting += 1
        elif not name:
            free.append(slot)
        else:
            raise RuntimeError(f"拿蛋前队伍第 {slot + 1} 格是「{name}」，应该是空的或者蛋")
    free = free[: config.eggs_per_load]
    taken = 0
    for number in config.egg_boxes:
        if taken >= len(free):
            break
        select_box(sw, number)
        for row, col in stable_egg_cells(sw):
            if taken >= len(free):
                break
            name = slot_name(sw, ("box", row, col))
            if not screens.is_egg_name(name):
                raise RuntimeError(
                    f"盒子 {number} 第 {row + 1} 行第 {col + 1} 列不是蛋，读到「{name}」"
                )
            slot = free[taken]
            swap(sw, ("box", row, col), ("party", slot))
            name = read_name(sw)
            if not screens.is_egg_name(name):
                raise RuntimeError(f"蛋放进队伍第 {slot + 1} 格之后，那一格是「{name}」")
            taken += 1
    if not taken + waiting:
        select_box(sw, config.egg_boxes[0])
        exit_to_overworld(sw)
        return "picnic"
    sw.eggs_in_party = taken + waiting
    exit_to_overworld(sw)
    return "hatch_walk"
