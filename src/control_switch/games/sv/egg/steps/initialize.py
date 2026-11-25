"""开始：换新日志文件，退回野外，读野餐队伍里的亲代，存档。"""

import logging

from control_switch.games.sv import actions
from control_switch.log import new_log

from .. import box
from ..session import EggSession


def initialize(sw: EggSession) -> str:
    """换新日志文件，退回野外，打开盒子读野餐队伍里的亲代（不是百变怪的那只），存一次档，返回下一步 "fetch"。

    记下亲代是野餐队伍的第几只、名字、「最棒」的项数，孵出来的和它比。游戏里评定功能没解锁时
    读不到「最棒」的项数，不换亲代，只记一条日志。
    """
    # 每一局一个日志文件：新的一局从这里开始，换一个新文件
    new_log(sw, "start")
    # 上一局没出错，截图丢掉
    sw.frames.clear()
    box.exit_to_overworld(sw)
    box.open_box(sw)
    party = box.read_party(sw)
    box.exit_to_overworld(sw)

    parent = next(
        ((index, mon) for index, mon in enumerate(party) if mon.name != sw.config.ditto_name), None
    )
    if parent is None:
        raise RuntimeError(f"队伍里只有{sw.config.ditto_name}，找不到亲代：{party}")
    sw.parent_index, mon = parent
    sw.parent_name = mon.name
    sw.judge_unlocked = mon.best is not None
    sw.parent_best = mon.best or 0
    logging.info(f"亲代是野餐队伍的第 {sw.parent_index + 1} 只，{sw.parent_name}")
    if sw.judge_unlocked:
        logging.info(f"亲代有 {sw.parent_best} 项「最棒」")
    else:
        logging.warning("游戏里的评定功能没解锁，读不到「最棒」的项数，孵出来的不换亲代")
    actions.save_game(sw)
    return "fetch"
