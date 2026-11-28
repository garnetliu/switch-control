"""放生：孵蛋全部结束后，在放蛋的盒子里从左上角开始一格一格看，不是闪光就放生，闪光推送之后放到右边的盒子。"""

import logging
import time

from control_switch.flow import capture
from control_switch.games.sv import actions

from .. import box
from ..session import EggSession


def release(sw: EggSession) -> str:
    """打开盒子，从左上角开始一格一格看：不是闪光就放生；闪光推送，放到右边盒子的第一个空格。看完返回 "fetch"。

    偶数行从左到右、奇数行从右到左，少按几下方向键。
    """
    config = sw.config
    box.open_box(sw)

    for agg in range(config.max_eggs):
        actions.menu_to_option(sw)

    for row in range(config.box_rows):
        columns = range(config.box_columns)
        for col in columns if row % 2 == 0 else reversed(columns):
            box.move_cursor(sw, "slots", row, col)
            if not box.slot_has_pokemon(sw):
                continue
            mon = box.read_mon(sw)
            if mon.shiny:
                logging.info(f"第 {row} 行第 {col} 列是闪光{mon.name}")
                _send_shiny(sw, mon)
                box.move_to_next_box(sw, ("slots", row, col))
            else:
                box.release_one(sw)
    actions.exit_to_overworld(sw)
    return "fetch"


def _send_shiny(sw: EggSession, mon: box.Mon) -> None:
    """闪光：存一张截图，推送给所有人。"""
    directory = sw.config.shiny_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}-shiny-{mon.name}.jpg"
    capture(sw, "闪光").save(str(path))
    sw.notifier.send_everyone(f"孵出闪光{mon.name}了！", [path])
