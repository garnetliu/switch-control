"""initialize：读亲代的「最棒」项数，检查队伍第 4–6 格。"""

import logging

from control_switch.log import new_log

from .. import screens
from ..box import (
    describe_cursor,
    ensure_judge,
    exit_to_overworld,
    move_cursor,
    open_box,
    read_name,
)
from ..screens import Cursor
from ..session import EggSession
from .party import EGG_SLOTS, STORE_PARENT, party_state


def _read_parent(sw: EggSession, state: str) -> None:
    """读亲代有几项最棒：野餐的队伍在队伍第 2 格，孵蛋的队伍在 flame_box 第 1 行第 2 列。"""
    config = sw.config
    where: Cursor = STORE_PARENT if state in ("hatch", "to_picnic_mid") else ("party", 1)
    move_cursor(sw, where)
    name = read_name(sw)
    if config.parent_name not in name:
        raise RuntimeError(
            f"{describe_cursor(where)}是「{name}」，不是亲代「{config.parent_name}」"
        )
    image = ensure_judge(sw)
    sw.parent_best = screens.panel_best_count(image, config)
    logging.info(f"亲代{name}，{sw.parent_best} 项最棒")


def initialize(sw: EggSession) -> str:
    """读亲代，看队伍里有没有蛋。"""
    sw.frames.clear()
    new_log(sw, "start")
    # 开始时可能停在菜单或盒子里，先退回野外
    exit_to_overworld(sw)
    open_box(sw)
    state = party_state(sw)
    _read_parent(sw, state)
    if state != "hatch":
        # 野餐的队伍里没有蛋，直接去找盒子里的蛋（hatch_load 会补完换到一半的队伍）
        exit_to_overworld(sw)
        return "hatch_load"
    eggs = 0
    hatched = 0
    for slot in EGG_SLOTS:
        move_cursor(sw, ("party", slot))
        name = read_name(sw)
        if screens.is_egg_name(name):
            eggs += 1
        elif name:
            hatched += 1
    exit_to_overworld(sw)
    if hatched:
        # 上次孵出来还没看过的，先去看
        logging.info(f"队伍第 2–6 格有 {hatched} 只孵出来的，先去看")
        return "check"
    if eggs:
        sw.eggs_in_box = 0
        sw.eggs_in_party = eggs
        return "hatch_walk"
    # 盒子里可能还有上次没孵的蛋，先去找；一个都没有时 hatch_load 会去开野餐
    return "hatch_load"
