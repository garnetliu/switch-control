"""开始：退回野外，打开盒子看现在是拿蛋还是孵蛋，找到放亲代和带队的盒子，数蛋，存档。"""

import logging
from collections.abc import Callable

from control_switch.games.sv import actions
from control_switch.log import new_log

from .. import box
from ..session import EggSession


def initialize(sw: EggSession) -> str:
    """看队伍和放蛋的盒子判断下一步，返回 "hatch"、"release" 或 "fetch"。

    队伍是亲代和百变怪，或者第 1 只是火焰之躯、后面是蛋或者孵出来的，都不是抛 RuntimeError。
    找到放亲代和带队的盒子（锚点），放蛋的是它后面那个，记在 sw.egg_box；放蛋的盒子和队伍里的蛋数记在 sw.eggs。
    有蛋：孵蛋。没有蛋、队伍超过两只：放生。没有蛋、队伍是亲代和百变怪：拿蛋。
    最后盒子停在放蛋的盒子上，退回野外，存一次档。
    """
    config = sw.config
    # 每一局一个日志文件：新的一局从这里开始，换一个新文件
    new_log(sw, "start")
    actions.exit_to_overworld(sw)
    actions.open_box(sw)
    party = box.read_party(sw)
    if any(mon.name == config.ditto_name for mon in party):
        if len(party) > 2:
            names = "、".join(mon.name for mon in party)
            raise RuntimeError(
                f"野餐队伍里只能有亲代和{config.ditto_name}两只，现在有 {len(party)} 只：{names}"
            )
        parent = next(
            ((index, mon) for index, mon in enumerate(party) if mon.name != config.ditto_name),
            None,
        )
        if parent is None:
            raise RuntimeError(f"队伍里只有{config.ditto_name}，找不到亲代：{party}")
        _find_anchor(sw, _is_picnic_anchor)
        _set_parent(sw, *parent)
    else:
        box.move_cursor(sw, "party", 0, 0)
        if config.flame_body not in box.read_ability(sw):
            names = "、".join(mon.name for mon in party)
            raise RuntimeError(
                f"队伍里没有{config.ditto_name}，第 1 只也不是{config.flame_body}，"
                f"不是野餐队伍也不是孵蛋队伍：{names}"
            )
        _find_anchor(sw, _is_hatch_anchor)
        _set_parent(sw, *_read_hatch_parent(sw))
        others = [mon.name for mon in party[1:] if not mon.name.startswith("蛋")]
        if any(name != sw.parent_name for name in others):
            raise RuntimeError(f"队伍里除了蛋和孵出来的{sw.parent_name}，还有别的：{others}")

    sw.egg_box = box.turn_box(sw, "R")
    sw.eggs = box.count_box_eggs(sw) + sum(mon.name.startswith("蛋") for mon in party)
    if sw.eggs > 0:
        step = "hatch"
        logging.info(f"孵蛋：放蛋的是盒子 {sw.egg_box}，还要孵 {sw.eggs} 个蛋")
    elif len(party) > 2:
        step = "release"
        logging.info(f"放生：放蛋的是盒子 {sw.egg_box}，没有蛋了，队伍里有 {len(party)} 只")
    else:
        step = "fetch"
        logging.info(f"拿蛋：放蛋的是盒子 {sw.egg_box}，没有蛋")
    actions.exit_to_overworld(sw)
    actions.save_game(sw)
    return step


def _find_anchor(sw: EggSession, is_anchor: Callable[[EggSession], bool]) -> int:
    """找放亲代和带队的盒子，停在那个盒子上，返回它的编号。没找到抛 RuntimeError。

    开着的盒子里有蛋，它是放蛋的盒子，只看前一个；没有蛋就看它自己和前面两个
    （刚准备好时开着的就是锚点，孵蛋到一半时开着的是放蛋的或者放闪光的盒子）。
    """
    current = box.read_title(sw)
    if box.count_box_eggs(sw) > 0:
        current = box.turn_box(sw, "L")
        checks = 1
    else:
        checks = 3
    for index in range(checks):
        if index > 0:
            current = box.turn_box(sw, "L")
        if is_anchor(sw):
            logging.info(f"放亲代和带队的是盒子 {current}")
            return current
    raise RuntimeError("找不到放亲代和带队的盒子")


def _is_picnic_anchor(sw: EggSession) -> bool:
    """队伍是野餐队伍时：盒子第 0 行第 0 列是火焰之躯的宝可梦（带队的）。"""
    box.move_cursor(sw, "slots", 0, 0)
    return box.slot_has_pokemon(sw) and sw.config.flame_body in box.read_ability(sw)


def _is_hatch_anchor(sw: EggSession) -> bool:
    """队伍是孵蛋队伍时：盒子第 0 行第 0、1 列是亲代和百变怪（野餐队伍换下来放在这里）。"""
    names = []
    for col in (0, 1):
        box.move_cursor(sw, "slots", 0, col)
        if not box.slot_has_pokemon(sw):
            return False
        names.append(box.read_name(sw))
    return names.count(sw.config.ditto_name) == 1


def _read_hatch_parent(sw: EggSession) -> tuple[int, box.Mon]:
    """在锚点盒子里读亲代：第 0 行第 0、1 列里不是百变怪的那只，返回它在野餐队伍里是第几只和读到的宝可梦。"""
    for col in (0, 1):
        box.move_cursor(sw, "slots", 0, col)
        if box.read_name(sw) != sw.config.ditto_name:
            return col, box.read_mon(sw)
    raise RuntimeError(f"锚点盒子里只有{sw.config.ditto_name}，找不到亲代")


def _set_parent(sw: EggSession, index: int, mon: box.Mon) -> None:
    """记下亲代是野餐队伍的第几只、名字、「最棒」的项数，孵出来的和它比。

    游戏里评定功能没解锁时读不到「最棒」的项数，不换亲代，只记一条日志。
    """
    sw.parent_index = index
    sw.parent_name = mon.name
    sw.judge_unlocked = mon.best is not None
    sw.parent_best = mon.best or 0
    logging.info(f"亲代是野餐队伍的第 {index + 1} 只，{sw.parent_name}")
    if sw.judge_unlocked:
        logging.info(f"亲代有 {sw.parent_best} 项「最棒」")
    else:
        logging.warning("游戏里的评定功能没解锁，读不到「最棒」的项数，孵出来的不换亲代")
