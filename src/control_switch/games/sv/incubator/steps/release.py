"""放生：孵完一盒之后，查闪光、换亲代、放生、换回野餐队伍、存档。"""

import logging

from control_switch.flow import capture, press_until, restart, wait_until
from control_switch.games.sv import actions
from control_switch.games.sv import verify as sv_verify

from .. import verify
from ..actions import box_move_cursor, box_turn, read_mon, read_name
from ..session import IncubatorSession
from ..types import Cursor, Mon, TeamType


def release(sw: IncubatorSession) -> str:
    """孵蛋队伍孵完之后：

    1. 队伍里除了带队的还有宝可梦，先放进放蛋的盒子。
    2. 放蛋的盒子里一只都没有：换回野餐队伍，存档，去拿蛋。
    3. 有：读亲代，亲代不是 6V 就找同种、「最棒」比亲代多的；再看有没有闪光。
       - 没有闪光，也不用换亲代：重启游戏回档，回到 initialize 重新判断。
       - 否则：要换亲代就换，有闪光就放到留东西的盒子，其余的都放生，换回野餐队伍，存档，去拿蛋。
    """
    config = sw.config

    box_turn(sw, sw.boxes.egg)
    slots = _occupied(sw)
    if not slots:
        logging.info("放蛋的盒子里没有宝可梦，换回野餐队伍去拿蛋")
        return _finish(sw)
    mons = _read_box(sw, slots)

    better = None
    if sw.parent_best < 6:
        candidates = [
            (slot, mon) for slot, mon in mons if mon.best > sw.parent_best and not mon.shiny
        ]
        if candidates:
            better = max(candidates, key=lambda item: item[1].best)

    shinies = [(slot, mon) for slot, mon in mons if mon.shiny]

    if better is None and not shinies:
        logging.info("没有闪光，也没有比亲代好的，重启游戏回档")
        restart(sw)
        # restart 在黑屏时就返回了，看画面等游戏加载完回到野外，再等一会儿让人能动
        wait_until(
            sw, lambda s: sv_verify.is_overworld(s, config), "重启之后回到野外", timeout=120.0
        )
        return TeamType.FETCH

    if better is not None:
        logging.info(f"换亲代：{better[1].name}，「最棒」{better[1].best} 项")
        _move_between_boxes(sw, sw.boxes.egg, better[0], sw.boxes.anchor, ("slots", 0, 1))
        sw.parent_best = better[1].best
    keep_slots = _empty_slots(sw, sw.boxes.keep)
    for slot, mon in shinies:
        logging.info(f"闪光{mon.name}放到盒子 {sw.boxes.keep}")
        _move_between_boxes(sw, sw.boxes.egg, slot, sw.boxes.keep, keep_slots.pop(0))
    # 剩下的都放生：换亲代时换下来的旧亲代就在原来那一格
    box_turn(sw, sw.boxes.egg)
    shiny_slots = {slot for slot, _ in shinies}
    for slot, _ in mons:
        if slot in shiny_slots and (better is None or slot != better[0]):
            continue
        box_move_cursor(sw, *slot)
        _release_one(sw)
    return _finish(sw)


def _finish(sw: IncubatorSession) -> str:
    """换回野餐队伍，退回野外存档，返回去拿蛋。"""
    _to_picnic_team(sw)
    sw.team_type = TeamType.FETCH
    actions.exit_to_overworld(sw)
    actions.save_game(sw)
    return TeamType.FETCH


# ---- 读盒子 ----


def _occupied(sw: IncubatorSession) -> list[Cursor]:
    """当前盒子里哪些格子有宝可梦：光标先移到盒子名上（不挡住格子），截一张图看。"""
    box_move_cursor(sw, "other", 0, 0)
    return verify.box_occupied(capture(sw, "盒子里有宝可梦的格子"), sw.config)


def _read_box(
    sw: IncubatorSession, slots: list[Cursor]
) -> list[tuple[Cursor, Mon]]:
    """读当前盒子里 slots 这些格子的宝可梦，返回（格子，宝可梦）；read_best 是 False 时不读「最棒」的项数。"""
    mons: list[tuple[Cursor, Mon]] = []
    for slot in slots:
        box_move_cursor(sw, *slot)
        mon = read_mon(sw, sw.parent_best < 6)
        logging.info(f"第 {slot[1]} 行第 {slot[2]} 列：{mon}")
        mons.append((slot, mon))
    return mons


def _empty_slots(sw: IncubatorSession, box: int) -> list[Cursor]:
    """编号是 box 的盒子里所有的空格，从左上角开始。"""
    config = sw.config
    box_turn(sw, box)
    occupied = set(_occupied(sw))
    empty: list[Cursor] = []
    for row in range(config.box_rows):
        for col in range(config.box_columns):
            slot: Cursor = ("slots", row, col)
            if slot not in occupied:
                empty.append(slot)
    return empty


# ---- 拿起、放下 ----


def _hold(sw: IncubatorSession, button: str) -> None:
    """按 button（MINUS 或 Y）直到进了选择模式。"""
    press_until(sw, lambda: sw.click(button, 0), verify.is_box_selecting, "盒子的选择模式")


def _drop(sw: IncubatorSession) -> None:
    """拿着宝可梦时按 A 放下，直到退出选择模式。"""
    press_until(
        sw, lambda: sw.click("A", 0), lambda s: not verify.is_box_selecting(s), "放下宝可梦"
    )


def _move_between_boxes(
    sw: IncubatorSession, source_box: int, source: Cursor, target_box: int, target: Cursor
) -> None:
    """把 source_box 盒子 source 那一格的宝可梦按 Y 拿起来，换到 target_box 盒子放到 target；target 有宝可梦就交换。"""
    box_turn(sw, source_box)
    box_move_cursor(sw, *source)
    _hold(sw, "Y")
    box_turn(sw, target_box)
    box_move_cursor(sw, *target)
    _drop(sw)


def _move_column(sw: IncubatorSession, source: Cursor, target: Cursor) -> None:
    """光标移到一列最上面的 source，按减号、按 DDOWN 选到这一列最下面、按 A 拿起，放到 target。"""
    config = sw.config
    place, _, col = source
    bottom = config.party_rows - 1 if place == "party" else config.box_rows - 1
    box_move_cursor(sw, *source)
    _hold(sw, "MINUS")
    press_until(
        sw,
        lambda: sw.click("DDOWN", 0),
        lambda s: verify.box_cursor(s, config) == (place, bottom, col),
        "选到一列的最下面",
    )
    sw.click("A", 0)
    box_move_cursor(sw, *target)
    _drop(sw)


def _to_picnic_team(sw: IncubatorSession) -> None:
    """换回野餐队伍：带队的和锚点盒子第 0 行第 0 列（百变怪）交换，锚点盒子第 1 列（亲代）装进队伍。"""
    box_turn(sw, sw.boxes.anchor)
    box_move_cursor(sw, "party", 0, 0)
    _hold(sw, "Y")
    box_move_cursor(sw, "slots", 0, 0)
    _drop(sw)
    _move_column(sw, ("slots", 0, 1), ("party", 1, 0))


# ---- 放生 ----


def _choose_operation(sw: IncubatorSession, target: int) -> None:
    """按 A 出操作菜单，把光标移到第 target 行（移动、查看能力、携带持有物、标记、放生、取消）。"""
    config = sw.config
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: sv_verify.has_dialog_box(s, config),
        "盒子的操作菜单",
    )
    image = wait_until(sw, lambda s: verify.operation_row(s) != -1, "操作菜单选中的一项")
    current = verify.operation_row(image)
    while current != target:
        button = "DDOWN" if current < target else "DUP"
        image = press_until(
            sw,
            lambda key=button: sw.click(key, 0),
            lambda s, last=current: verify.operation_row(s) not in (last, -1),
            "操作菜单的光标移一格",
        )
        current = verify.operation_row(image)


def _release_one(sw: IncubatorSession) -> None:
    """放生光标所在格子里的宝可梦：操作菜单选「放生」（第 4 行），确认框选「是」，按 A 过「再见」的对话。"""
    config = sw.config
    name = read_name(sw)
    _choose_operation(sw, 4)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: sv_verify.is_prompt(s, config),
        "放生确认",
        interval=0.5,
    )
    # 确认框的光标默认在「否」，往上一格选「是」
    press_until(
        sw,
        lambda: sw.click("DUP", 0),
        lambda s: sv_verify.gradient_arrow(s, ((0.7161, 0.5713), (0.7625, 0.6639)), config),
        "放生确认选中「是」",
    )
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not sv_verify.is_prompt(s, config),
        "放生后的对话",
    )
    wait_until(sw, lambda s: sv_verify.is_dialog(s, config), f"放生{name}的对话")
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not sv_verify.has_dialog_box(s, config),
        "放生后的盒子",
    )
    if verify.slot_has_pokemon(sw):
        raise RuntimeError(f"放生{name}之后格子里还有宝可梦")
    logging.info(f"放生了{name}")
