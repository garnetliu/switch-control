"""检查冒险路上当前是哪个分支。"""

import logging

from control_switch.flow import (
    act_until,
    press_until,
    wait_for,
)
from control_switch.types import Rect
from control_switch.vision import ImageChecker
from control_switch.vision.text import contains
from swsh.lair import upstream
from swsh.lair.lair import Lair
from swsh.lair.next_columns import next_columns
from swsh.lair.steps.battle import Messages
from swsh.lair.steps.catch import walker_now
from swsh.lair.switch import LairSwitch

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
    maps = sw.game.maps
    if maps.get("layout") is None and sw.game.seed is not None:
        # 旧的存档里没有布局编号（锁定的图沿用存档），按 seed 补上
        maps["layout"] = Lair(sw.data, sw.game.seed).layout()
    # 这一段从哪个节点出发；选岔路之前遇到的事件记在这个节点上，之后遇到的记在走的那段路上
    start = maps["route"][maps["current_index"]]
    before: list[str] = []
    after: list[str] = []
    forked = False
    # 路上黑色面板上的字（谁换上了刚抓的那只、遇到了谁、谁和研究员换了）也写进日志
    rects = sw.config.rects
    messages = Messages((rects.black_center_line1, rects.black_center_line2), "路上的文字")

    def found(screen: ImageChecker, active: tuple[str, ...]) -> bool:
        messages.read(screen)
        return _match_state(sw, screen, active) is not None

    while True:
        image = wait_for(
            sw,
            lambda screen, active=states: found(screen, active),
            sw.config.timeout,
            "路线上的界面",
        )
        state = _match_state(sw, image, states)
        assert state is not None

        if state == "battle":
            # 战斗
            _record_events(sw, start, forked, before, after)
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
            _save_map(sw, image)
            _handle_fork(sw)
            forked = True
        else:
            logging.warning("未知的路线分支状态: %s", state)
        if state in ("backpacker", "scientist", "berry"):
            (after if forked else before).append(state)
        # 同一分支一次 path 调用只处理一次，处理完就不再认它
        states = tuple(other for other in states if other != state)


def _save_map(sw: LairSwitch, image: ImageChecker) -> None:
    """每种地图类型、每个布局编号，在每个岔路口存一张路线图，以后认图上的研究员、背包客、树果图标用。"""
    maps = sw.game.maps
    index = maps["current_index"]
    picture = sw.config.log_dir / "maps" / f"{maps['type']}-{maps.get('layout')}-{index}.jpg"
    if maps.get("layout") is None or picture.exists():
        return
    picture.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(picture))


def _record_events(
    sw: LairSwitch, start: list[int], forked: bool, before: list[str], after: list[str]
) -> None:
    """把这一段路上遇到的事件记进表里（GameData.lair_events），什么都没遇到也记，表示走过了。"""
    maps = sw.game.maps
    layout = maps.get("layout")
    if maps["type"] is None or layout is None:
        return
    row, col = start
    sw.data.record_lair_events(maps["type"], layout, f"{row}-{col}", before)
    if forked:
        next_row, next_col = maps["route"][maps["current_index"]]
        position = f"{row}-{col}>{next_row}-{next_col}"
        sw.data.record_lair_events(maps["type"], layout, position, after)
    if before or after:
        logging.info(f"路上的事件：选岔路之前 {before}，之后 {after}")


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
    press_until(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_center_line1, "树果"),
        "树果的对话结束",
        timeout=sw.config.timeout,
    )


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
    items = [image.read_text(rect).strip() for rect in sw.config.rects.backpacker_items]
    logging.info(f"背包客的道具: {items}")
    sw.click("A", 0)
    wait_for(
        sw,
        lambda screen: not _backpacker_shown(sw, screen),
        sw.config.timeout,
        "背包客的道具面板消失",
    )


def _handle_scientist(sw: LairSwitch) -> None:
    """研究员问要不要换租借宝可梦：按 seed 算出它实际会给哪只（upstream.Walker.offer），
    换成那只后队伍分更高就换（upstream.decide_scientist），决定记进 game.choices。

    按 A 之前核对画面上「希望交换成…」里的名字，和算的不一样（路上有没记录的事件，随机数错位了）就不换。
    路线上没记着这个研究员的，按不换，也不记决定。
    """
    found = walker_now(sw)
    give = None
    take = False
    if found is not None:
        scorer, walker = found
        if walker.next_event() == "scientist":
            give = walker.offer()
            take = upstream.decide_scientist(scorer, walker)
        else:
            logging.warning("路线上没记着这个研究员，按不换（后面按 seed 推的队伍会错位）")
            found = None

    image = wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.black_center_line1, "希望交换成"),
        sw.config.timeout,
        "研究员问换不换",
    )
    offered = image.read_text(sw.config.rects.black_center_line1) + image.read_text(
        sw.config.rects.black_center_line2
    )
    if take and give is not None:
        name = sw.data.pokemon_object(give).name(sw.config.language)
        if not contains(offered, name):
            logging.warning(f"按 seed 算研究员给的是 {name}，画面上是「{offered}」，对不上，不换")
            take = False
    own = sw.game.team[0][0]
    logging.info(
        f"研究员：给的是 {give}（画面上「{offered}」），{'换' if take else '不换'}，现在是 {own}"
    )
    sw.click("A" if take else "B", 0)
    wait_for(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_center_line1, "希望交换成"),
        sw.config.timeout,
        "研究员问话消失",
    )
    if found is not None:
        sw.game.choices.append(take)
    if take and give is not None:
        sw.game.team[0] = (give, 1.0)
    sw.game.save()


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
