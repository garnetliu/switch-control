"""大量出现刷闪的步骤。

人站在大量出现的范围里，菜单的光标停在「野餐」上。先把击败数改满，然后循环：
开野餐再收起，刷新身边的宝可梦；存档，读内存里身边的宝可梦；有闪光就停下并推送。
"""

import logging
import time

from sv.actions import close_picnic, open_picnic, save_game
from sv.blocks import OUTBREAK_ACTIVE, OUTBREAK_KO, OUTBREAK_TOTAL
from tools import capture, enter_game, restart_to_title
from tools.log import new_log

from .switch import OutbreakSwitch


def initialize(sw: OutbreakSwitch) -> str:
    """确认前台是朱/紫，找到存档块表。前台不是朱/紫抛 RuntimeError。"""
    new_log(sw, "start")
    title_id = sw.title_id().upper()
    if title_id not in sw.config.game_title_ids:
        raise RuntimeError(f"前台不是朱/紫（Title ID {title_id}）")
    sw.blocks.locate()
    return "knockout" if sw.config.knockout else "refresh"


def knockout(sw: OutbreakSwitch) -> str:
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


def _fill_knockouts(sw: OutbreakSwitch, region: str, index: int) -> None:
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


def refresh(sw: OutbreakSwitch) -> str:
    """开野餐再收起，身边的宝可梦会重新生成。"""
    # 新的一轮从这里开始，上一轮没出错，截图丢掉
    sw.frames.clear()
    open_picnic(sw)
    close_picnic(sw)
    time.sleep(sw.config.spawn_wait)
    return "scan"


def scan(sw: OutbreakSwitch) -> str:
    """存档，读身边的宝可梦。有要找的闪光就截图、推送并结束，没有就回去刷新。"""
    save_game(sw)
    pokemon = sw.blocks.read_overworld()
    logging.info(
        f"身边 {len(pokemon)} 只："
        + "、".join(("闪光" if p["shiny"] else "") + p["name"] for p in pokemon)
    )
    targets = sw.config.targets
    found = [p for p in pokemon if p["shiny"] and (not targets or p["name"] in targets)]
    if not found:
        return "refresh"
    lines = [
        f"闪光{p['name']}（形态 {p['form']}，{p['nature']}，个体 {'/'.join(map(str, p['ivs']))}）"
        for p in found
    ]
    logging.info("找到了：" + "；".join(lines))
    sw.config.catch_dir.mkdir(parents=True, exist_ok=True)
    path = sw.config.catch_dir / f"shiny-{time.strftime('%Y%m%d-%H%M%S')}-sv-outbreak.jpg"
    capture(sw, "闪光").save(str(path))
    sw.notifier.send_everyone("大量出现刷到闪光，已经存档，等你来抓\n" + "\n".join(lines), [path])
    return "done"
