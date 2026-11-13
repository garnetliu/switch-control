"""检查冒险路上当前是哪个分支。"""

import logging

from libs import ImageChecker
from swsh.lair.next_columns import next_columns
from swsh.lair.score import rental_boss_score
from swsh.lair.switch import LairSwitch
from tools import (
    act_until,
    keep_image,
    press_until,
    wait_for,
)
from tools.text import contains
from type import Rect

# 每个分支在底部文字里要认的关键词
_KEYWORDS = {
    "battle": "出现了",
    "backpacker": "遇到了背包客",
    "scientist": "遇到了研究员",
    "berry": "树果",
    "fork": "要走哪条路",
}


def path(sw: LairSwitch) -> str:
    """一直处理路线上的分支，直到进入战斗，返回 "battle"。

    每个分支一次调用最多处理一次，处理完就从 states 里删掉：
    backpacker 出现「遇到了背包客」、scientist 出现「遇到了研究员」、
    berry 出现「树果」、fork 出现「要走哪条路」、battle 出现「出现了」。
    """

    states = ("battle", "backpacker", "scientist", "berry", "fork")
    while True:
        image = wait_for(
            sw,
            lambda screen, active=states: _match_state(sw, screen, active) is not None,
            sw.config.timeout,
            "路线上的界面",
        )
        state = _match_state(sw, image, states)
        assert state is not None
        keep_image(sw, image, f"路线上的界面-{_KEYWORDS[state]}")

        if state == "battle":
            # 战斗
            return state
        elif state == "backpacker":
            # 背包客
            _handle_backpacker(sw)
        elif state == "scientist":
            # 研究员
            _handle_scientist(sw)
        elif state == "berry":
            # 树果
            _handle_berry(sw)
        elif state == "fork":
            # 分岔路
            _handle_fork(sw)
        else:
            logging.warning("未知的路线分支状态: %s", state)
        # 同一分支一次 path 调用只处理一次，处理完就不再认它
        states = tuple(other for other in states if other != state)


def _match_state(sw: LairSwitch, image: ImageChecker, states: tuple[str, ...]) -> str | None:
    """先读黑色中间面板的第一行，按 states 的顺序比背包客、研究员、树果、岔路口的关键词；
    都没有，再读黑色占满面板的第一行，看是不是「×××出现了」。
    """
    rects = sw.config.rects
    found = image.read_text(rects.black_center_line1)
    for state in [s for s in states if s != "battle"]:
        if contains(found, _KEYWORDS[state]):
            return state
    if "battle" in states and contains(
        image.read_text(rects.black_full_line1), _KEYWORDS["battle"]
    ):
        return "battle"
    return None


def _handle_berry(sw: LairSwitch) -> None:
    """按 A 推进树果对话，直到文字框里不再有「树果」。"""
    image = press_until(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_center_line1, "树果"),
        "树果的对话结束",
        timeout=sw.config.timeout,
    )
    keep_image(sw, image, "树果的对话结束")


def _handle_fork(sw: LairSwitch) -> None:
    """把岔路口光标移到计划路线上的下一个节点，按 A 确认。"""
    maps = sw.game.maps
    index = maps["current_index"]
    if index + 1 >= len(maps["route"]):
        raise RuntimeError("路线规划里没有下一个节点")
    # route 里下一项是 [层号, 列号]，光标要移到这一层的这一列
    row, col = maps["route"][index + 1]
    # 岔路口只能选当前节点连着的几列
    current_row, current_col = maps["route"][index]
    columns = next_columns(maps["type"], current_row, current_col)
    if col not in columns:
        raise RuntimeError(f"路线目标第 {row} 层第 {col + 1} 列不在当前节点能走到的 {columns} 里")
    rects = sw.config.rects.path_cursors[maps["type"]][(current_row, current_col)]
    _move_fork_cursor(sw, dict(zip(columns, rects)), col)
    sw.click("A", 0)
    maps["current_index"] = index + 1
    sw.game.save()


def _move_fork_cursor(sw: LairSwitch, cursors: dict[int, Rect], column: int) -> None:
    """把岔路口光标移到第 column 列。cursors 是能走到的几列的光标区域：{列号: 区域}。

    先用每个光标区域里的白色占比判断当前列，再按 column 在左还是右推左摇杆；
    每次推完都重新读一帧，输入被吞掉时 act_until 会重推。
    """
    columns = sorted(cursors)
    rects = tuple(cursors[c] for c in columns)
    target = columns.index(column)
    image = wait_for(
        sw,
        lambda screen: _path_cursor_index(sw, screen, rects) != -1,
        sw.config.timeout,
        "岔路口光标",
    )
    keep_image(sw, image, "岔路口光标")
    start = _path_cursor_index(sw, image, rects)
    for _ in range(len(rects)):
        current = _path_cursor_index(sw, image, rects)
        if current == target:
            logging.info(f"岔路口光标从第 {columns[start] + 1} 列移到第 {column + 1} 列")
            return
        direction = 1 if target > current else -1
        image = act_until(
            sw,
            lambda step=direction: sw.stick(
                "LEFT", step * sw.config.stick_max, 0, sw.config.stick_tick
            ),
            lambda screen, before=current: (
                _path_cursor_index(sw, screen, rects) not in (before, -1)
            ),
            "岔路口光标移动",
        )
        keep_image(sw, image, "岔路口光标移动")
    raise RuntimeError(f"岔路口光标移了 {len(rects)} 次，还是没到第 {column + 1} 列")


def _path_cursor_index(sw: LairSwitch, image: ImageChecker, rects: tuple[Rect, ...]) -> int:
    """几个光标区域里白色占比最高的序号，没有明显的返回 -1。"""
    ratios = [
        image.color_ratio(rect, sw.config.cursor_white_lower, sw.config.cursor_white_upper)
        for rect in rects
    ]
    best = max(range(len(ratios)), key=ratios.__getitem__)
    return best if ratios[best] > sw.config.cursor_white_ratio else -1


def _handle_backpacker(sw: LairSwitch) -> None:
    """等背包客的蓝色道具面板出来，读一下道具名，拿默认道具，再等面板消失。"""
    # 「遇到了背包客」之后对话自己翻页，道具面板才出来
    image = wait_for(
        sw,
        lambda screen: _backpacker_shown(sw, screen),
        sw.config.timeout,
        "背包客的道具面板",
    )
    keep_image(sw, image, "背包客的道具面板")
    items = [image.read_text(rect).strip() for rect in sw.config.rects.backpacker_items]
    logging.info(f"背包客的道具: {items}")
    sw.click("A", 0)
    image = wait_for(
        sw,
        lambda screen: not _backpacker_shown(sw, screen),
        sw.config.timeout,
        "背包客的道具面板消失",
    )
    keep_image(sw, image, "背包客的道具面板消失")


def _handle_scientist(sw: LairSwitch) -> None:
    """研究员问要不要换租借宝可梦：平均分更高就换。

    平均分排除候选池和这一局路线上的遭遇宝可梦。
    """
    own = sw.game.team[0][0]

    rental_scores = sw.data.rental_scores()
    # 候选池和这一局路线上的宝可梦不会再作为新对手出现，算平均分时排除
    excluded = set(sw.game.rental_pool)
    for nodes in sw.game.maps["rows"].values():
        excluded.update(node["encounter"] for node in nodes)
    names = [name for name in rental_scores if name not in excluded]
    floor = sw.game.maps["current_index"]
    average = sum(rental_boss_score(sw, name, sw.game.boss, floor) for name in names) / len(names)
    own_score = rental_boss_score(sw, own, sw.game.boss, floor)
    take = average > own_score
    logging.info(
        f"研究员：平均分 {average:.2f}，{own} 的分数 {own_score:.2f}，{'换' if take else '不换'}"
    )

    image = wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.black_center_line1, "希望交换成"),
        sw.config.timeout,
        "研究员问换不换",
    )
    keep_image(sw, image, "研究员问换不换")
    sw.click("A" if take else "B", 0)
    image = wait_for(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_center_line1, "希望交换成"),
        sw.config.timeout,
        "研究员问话消失",
    )
    keep_image(sw, image, "研究员问话消失")


def _backpacker_shown(sw: LairSwitch, image: ImageChecker) -> bool:
    """蓝色道具面板正显示着。"""
    return (
        image.color_ratio(
            sw.config.rects.backpacker,
            sw.config.backpacker_lower,
            sw.config.backpacker_upper,
        )
        > sw.config.backpacker_ratio
    )
