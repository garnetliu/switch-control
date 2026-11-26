"""knockout：存档，重启游戏，停在标题画面时把所有大量出现的击败数改满，再进游戏。"""

import logging
import time

from control_switch.flow import enter_game, restart_to_title
from control_switch.games.sv.actions import save_game
from control_switch.games.sv.outbreak.blocks import OUTBREAK_ACTIVE, OUTBREAK_KO, OUTBREAK_TOTAL

from ..session import OutbreakSession


def knockout(sw: OutbreakSession) -> str:
    """把正在发生的大量出现的击败数改满。

    照 PokeViewer.NET 的做法：存档，关掉游戏重开，停在标题画面时改内存里的击败数，再进游戏。
    所有地图上的大量出现都改，不去判断人站在哪一个里面。
    """
    save_game(sw)
    restart_to_title(sw)
    time.sleep(sw.config.title_wait)
    sw.blocks.locate()
    for region, active_key in OUTBREAK_ACTIVE.items():
        active = sw.blocks.read_byte(active_key)
        for index in range(min(active, len(OUTBREAK_KO[region]))):
            _fill_knockouts(sw, region, index)
    enter_game(sw)
    time.sleep(sw.config.enter_wait)
    sw.blocks.locate()
    return "refresh"


def _fill_knockouts(sw: OutbreakSession, region: str, index: int) -> None:
    """把 region 的第 index 个大量出现的击败数改满，已经够了就不动。"""
    name = f"{region}第 {index + 1} 个大量出现"
    ko_key = OUTBREAK_KO[region][index]
    count = sw.blocks.read_int(ko_key)
    total = sw.blocks.read_int(OUTBREAK_TOTAL[region][index])
    if count >= sw.config.knockout_enough:
        logging.info(f"{name}：击败数 {count}/{total}，不用改")
        return
    wanted = min(sw.config.knockout_count, total - 1)
    if wanted < sw.config.knockout_enough:
        logging.info(
            f"{name}：击败数 {count}/{total}，总数太少，改不到 {sw.config.knockout_enough}"
        )
        return
    sw.blocks.write_int(ko_key, wanted)
    written = sw.blocks.read_int(ko_key)
    if written != wanted:
        raise RuntimeError(f"{name}：击败数写成 {wanted}，读回来是 {written}")
    logging.info(f"{name}：击败数 {count} 改成 {wanted}，总数 {total}")
