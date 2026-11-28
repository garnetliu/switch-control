import logging
from functools import cache
from importlib.resources import files

import cv2
import numpy as np

from control_switch.flow import capture, press_until
from control_switch.games.sv import actions
from control_switch.games.sv import verify as sv_verify
from control_switch.log import new_log
from control_switch.vision import ImageChecker

from .. import verify
from ..actions import box_move_cursor, box_turn, read_mon, read_name
from ..config import IncubatorConfig
from ..session import IncubatorSession
from ..types import Boxes, Mon, TeamType


def initialize(sw: IncubatorSession) -> str:
    new_log(sw, "start")
    actions.exit_to_overworld(sw)
    actions.open_box(sw)
    sw.team_type, sw.boxes, sw.parent_best = _box_read_team(sw)

    box_turn(sw, sw.boxes.egg)
    box_eggs, sw.eggs_in_party = _box_count_eggs(sw)
    sw.eggs = box_eggs + sw.eggs_in_party
    logging.info(
        f"放蛋的是盒子 {sw.boxes.egg}，盒子和队伍一共 {sw.eggs} 个蛋，队伍里 {sw.eggs_in_party} 个"
    )
    # 队伍是什么就去做什么：拿蛋队伍去 fetch，孵蛋队伍去 hatch；孵蛋队伍但没有蛋了，去 release
    if sw.team_type == TeamType.HATCH and sw.eggs == 0:
        return "release"
    return sw.team_type


def _box_read_team(sw: IncubatorSession) -> tuple[TeamType, Boxes, int]:
    """看队伍是什么队伍，找到锚点盒子（放亲代和带队宝可梦的盒子），返回（队伍，三个盒子的编号，亲代「最棒」的项数）。

    三个盒子是锚点、后面一个放蛋、再后面一个放留下来的。

    队伍里有百变怪是拿蛋用的野餐队伍，锚点盒子第一格是带队的火焰之躯；
    没有百变怪是孵蛋队伍，锚点盒子第一格是从野餐队伍换下来的百变怪。
    从当前开着的盒子开始看第一格，不是就按 L 看前一个盒子，最多看 3 个，都不是抛 RuntimeError。
    """
    config = sw.config
    mons: list[Mon] = []
    for row in range(2):
        box_move_cursor(sw, "party", row, 0)
        if not verify.slot_has_pokemon(sw):
            break
        mons.append(read_mon(sw))

    team = TeamType.FETCH if any(mon.name == config.ditto_name for mon in mons) else TeamType.HATCH
    box_move_cursor(sw, "slots", 0, 0)
    count = config.box_count
    current = sv_verify.box_title(sw)
    for index in range(3):
        if index > 0:
            # 前一个盒子；第一个盒子往前是最后一个
            current = (current - 2) % count + 1
            box_turn(sw, current)
        if verify.slot_has_pokemon(sw) and _is_anchor(sw, team):
            boxes = Boxes(current, current % count + 1, (current + 1) % count + 1)
            logging.info(f"队伍是 {team}，盒子是 {boxes}")

            if team == TeamType.HATCH:
                mon = read_mon(sw)
                return team, boxes, mon.best
            else:
                return team, boxes, mons[1].best
    raise RuntimeError(f"队伍是 {team}，往前看了 3 个盒子，第一格都不对，找不到锚点盒子")


def _is_anchor(sw: IncubatorSession, team: TeamType) -> bool:
    """光标在盒子第一格时，这个盒子是不是锚点：拿蛋队伍看是不是火焰之躯，孵蛋队伍看是不是百变怪。"""
    if team == TeamType.FETCH:
        return "火焰之躯" in _read_ability(sw)
    return read_name(sw) == sw.config.ditto_name


def _read_ability(sw: IncubatorSession) -> str:
    """读光标所在格子里宝可梦的特性：面板不在能力页就按 PLUS 切过去。"""
    image = capture(sw, "面板的特性")
    if not verify.is_stats_page(image):
        image = press_until(sw, lambda: sw.click("PLUS", 0), verify.is_stats_page, "面板的能力页")
    return verify.panel_ability(image)


def _box_count_eggs(sw: IncubatorSession) -> tuple[int, int]:
    """数当前盒子和队伍里的蛋，返回（盒子里的蛋数，队伍里的蛋数）。

    先把光标移到盒子名上，格子和队伍都不会被光标挡住。
    """
    config = sw.config
    box_move_cursor(sw, "other", 0, 0)
    image = capture(sw, "盒子和队伍里的蛋")
    return len(_box_eggs(image, config)), _party_eggs(image, config)


@cache
def _egg_template() -> np.ndarray:
    """盒子格子里蛋的模板：格子缩成 120×120 时蛋身中间的一块。"""
    path = files("control_switch.games.sv") / "data" / "box_egg.png"
    template = cv2.imread(str(path))
    if template is None:
        raise RuntimeError(f"读不到蛋的模板 {path}")
    return template


def _box_eggs(image: ImageChecker, config: IncubatorConfig) -> list[tuple[int, int]]:
    """盒子里哪些格子是蛋，返回 (行, 列)：每一格缩成 120×120 和蛋的模板比，匹配度超过 0.9 的是蛋。

    光标停着的那一格里的蛋会被压扁，比不出来，调用前先把光标移到格子外面。
    """
    template = _egg_template()
    eggs = []
    for row in range(config.box_rows):
        for col in range(config.box_columns):
            # 第 0 行第 0 列的格子，相邻两格横向隔 0.0656、纵向隔 0.1167
            left, top = 0.234 + 0.0656 * col, 0.183 + 0.1167 * row
            cell = cv2.resize(image.crop(((left, top), (left + 0.0625, top + 0.111))), (120, 120))
            if float(cv2.matchTemplate(cell, template, cv2.TM_CCOEFF_NORMED).max()) > 0.9:
                eggs.append((row, col))
    return eggs


def _party_eggs(image: ImageChecker, config: IncubatorConfig) -> int:
    """盒子画面左边的队伍里有几个蛋：每一行的名字是「蛋」就算一个。"""
    # 第 0 行名字的位置，每往下一行加 0.1167
    return sum(
        image.read_text(((0.03, 0.235 + 0.1167 * row), (0.17, 0.29 + 0.1167 * row))).startswith(
            "蛋"
        )
        for row in range(config.party_rows)
    )
