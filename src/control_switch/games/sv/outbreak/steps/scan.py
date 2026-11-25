"""scan：存档，读身边的宝可梦，有要找的闪光就截图、推送并结束。"""

import logging
import time

from control_switch.flow import capture
from control_switch.games.sv.actions import save_game

from ..session import OutbreakSession


def scan(sw: OutbreakSession) -> str:
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
    sw.config.shiny_dir.mkdir(parents=True, exist_ok=True)
    path = sw.config.shiny_dir / f"shiny-{time.strftime('%Y%m%d-%H%M%S')}-sv-outbreak.jpg"
    capture(sw, "闪光").save(str(path))
    sw.notifier.send_everyone("大量出现刷到闪光，已经存档，等你来抓\n" + "\n".join(lines), [path])
    return "done"
