"""队伍的两种组法和换位置。"""

import logging

from ..box import (
    describe_cursor,
    move_cursor,
    pick_up,
    put_down,
    read_name,
    select_box,
)
from ..screens import Cursor
from ..session import EggSession

# 队伍的两种组法（照 PokemonAutomation EggAutonomous 的文档）：
# 野餐收蛋时只有能配对的两只：第 1 格百变怪，第 2 格亲代；
# 孵蛋时第 1 格火焰之躯，第 2–6 格放蛋。不在队伍里的放在 flame_box 第 1 行：
# 野餐时火焰之躯在第 1 列；孵蛋时百变怪在第 1 列、亲代在第 2 列
EGG_SLOTS = (1, 2, 3, 4, 5)
PARENT_SLOT = 1
LEAD_SLOT = 0
STORE_LEAD: Cursor = ("box", 0, 0)
STORE_PARENT: Cursor = ("box", 0, 1)


def slot_name(sw: EggSession, cursor: Cursor) -> str:
    move_cursor(sw, cursor)
    return read_name(sw)


def party_state(sw: EggSession) -> str:
    """看队伍第 1、2 格和 flame_box 第 1 行第 1、2 列四个位置的名字，认出现在是哪种组法。盒子要已经打开。

    picnic：（百变怪，亲代，火焰之躯，空）；hatch：（火焰之躯，蛋或空，百变怪，亲代）；
    to_hatch_mid：换到一半（火焰之躯，亲代，百变怪，空），还差把亲代放进盒子；
    to_picnic_mid：换到一半（百变怪，蛋或空，火焰之躯，亲代），还差把亲代放回队伍。
    认不出抛 RuntimeError。读完光标停在 flame_box。
    """
    config = sw.config
    lead = slot_name(sw, ("party", LEAD_SLOT))
    second = slot_name(sw, ("party", PARENT_SLOT))
    select_box(sw, config.flame_box)
    stored_lead = slot_name(sw, STORE_LEAD)
    stored_parent = slot_name(sw, STORE_PARENT)
    flame, ditto, parent = config.flame_name, config.ditto_name, config.parent_name
    if ditto in lead and parent in second and flame in stored_lead and not stored_parent:
        return "picnic"
    if flame in lead and ditto in stored_lead and parent in stored_parent:
        return "hatch"
    if flame in lead and parent in second and ditto in stored_lead and not stored_parent:
        return "to_hatch_mid"
    if ditto in lead and flame in stored_lead and parent in stored_parent:
        return "to_picnic_mid"
    raise RuntimeError(
        "队伍认不出是哪种组法："
        f"队伍第 1 格「{lead}」，队伍第 2 格「{second}」，"
        f"盒子 {config.flame_box} 第 1 行第 1 列「{stored_lead}」，第 2 列「{stored_parent}」"
    )


def swap(sw: EggSession, first: Cursor, second: Cursor) -> None:
    """first 和 second 交换：从有宝可梦的那一格拿起，放到另一格。

    在空格上按 Y 也会进入替换模式（画面变紫），看起来像拿着东西，其实什么都没拿（真机上出过），
    所以先确认拿起的那一格不是空的。两格都空抛 RuntimeError。
    """
    move_cursor(sw, first)
    if not read_name(sw):
        first, second = second, first
        move_cursor(sw, first)
        if not read_name(sw):
            raise RuntimeError(
                f"{describe_cursor(first)}和{describe_cursor(second)}都是空的，没东西可换"
            )
    pick_up(sw)
    move_cursor(sw, second)
    put_down(sw)


def _swap_lead(sw: EggSession) -> None:
    """队伍第 1 格和 flame_box 第 1 行第 1 列交换。"""
    select_box(sw, sw.config.flame_box)
    swap(sw, STORE_LEAD, ("party", LEAD_SLOT))


def _swap_parent(sw: EggSession) -> None:
    """队伍第 2 格和 flame_box 第 1 行第 2 列交换。"""
    select_box(sw, sw.config.flame_box)
    swap(sw, STORE_PARENT, ("party", PARENT_SLOT))


def to_picnic_party(sw: EggSession) -> None:
    """换成野餐的队伍：火焰之躯和盒子里的百变怪交换，亲代放回队伍第 2 格。

    盒子要已经打开，队伍第 2–6 格要已经空了（孵出来的都看完了）。按实际位置补完剩下的搬动。
    最后盒子停在 egg_boxes[0]，篮子里的蛋从这个盒子开始放。
    """
    config = sw.config
    state = party_state(sw)
    if state == "hatch":
        _swap_lead(sw)
        _swap_parent(sw)
    elif state == "to_picnic_mid":
        _swap_parent(sw)
    elif state == "to_hatch_mid":
        _swap_lead(sw)
    if state != "picnic":
        if party_state(sw) != "picnic":
            raise RuntimeError("换完之后队伍第 2 格不是亲代")
        logging.info("换成野餐的队伍：百变怪和亲代")
    select_box(sw, config.egg_boxes[0])


def to_hatch_party(sw: EggSession) -> None:
    """换成孵蛋的队伍：盒子里的火焰之躯和百变怪交换，亲代放进盒子。盒子要已经打开。"""
    state = party_state(sw)
    if state == "hatch":
        return
    if state == "to_picnic_mid":
        _swap_parent(sw)
        state = "picnic"
    if state == "picnic":
        _swap_lead(sw)
    _swap_parent(sw)
    if party_state(sw) != "hatch":
        raise RuntimeError("换完之后亲代没有放进盒子")
    logging.info("换成孵蛋的队伍：火焰之躯")
