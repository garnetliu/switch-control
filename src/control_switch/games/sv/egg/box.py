"""盒子和队伍里的操作：开关盒子、移光标、读宝可梦、装一列、卸一列、交换、放生。

照 PokemonAutomation 的 PokemonSV_BoxRoutines、PokemonSV_BoxRelease 和 EggAutonomous 里换队伍的几段。
盒子有三个相邻的：左边的盒子放野餐队伍和带队的宝可梦，当前的盒子放蛋，右边的盒子放留下的。
"""

import logging
from collections.abc import Callable
from typing import NamedTuple, TypeVar

from control_switch.flow import capture, press_until, wait_until
from control_switch.games.sv import actions
from control_switch.games.sv import screens as sv_screens
from control_switch.vision import ImageChecker

from . import screens
from .screens import Cursor
from .session import EggSession

# 盒子里的一格：("party", 队伍第几行, 0) 或 ("slots", 行, 列)。队伍第 0 行是带队的
Slot = tuple[str, int, int]

T = TypeVar("T")


class Mon(NamedTuple):
    """盒子里读到的一只宝可梦。"""

    name: str
    # 「最棒」的项数；游戏里评定功能没解锁读不到，是 None
    best: int | None
    shiny: bool


# ---- 进出盒子 ----


def open_box(sw: EggSession) -> None:
    """从野外打开盒子。

    第一次打开时开着的是放亲代和带队宝可梦的盒子，放蛋的是它后面那个，记在 sw.egg_box，往右转一个盒子。
    之后再打开，游戏停在上次看的盒子，就是放蛋的盒子。
    """
    config = sw.config
    actions.open_box(sw)
    if sw.egg_box is None:
        number = read_title(sw)
        sw.egg_box = number % config.box_count + 1
        logging.info(f"开始时是盒子 {number}，蛋放在盒子 {sw.egg_box}")
        turn_box(sw, "R")


def _read_stable(sw: EggSession, read: Callable[[ImageChecker], T | None], what: str) -> T:
    """一直截图读，直到连着 stable_frames 帧读到一样的、不是 None 的结果，返回它。"""
    values: list[T | None] = []

    def stable(image: ImageChecker) -> bool:
        values.append(read(image))
        last = values[-sw.config.stable_frames:]
        return (
                len(last) == sw.config.stable_frames
                and last[0] is not None
                and all(value == last[0] for value in last)
        )

    wait_until(sw, stable, sw.config.wait.timeout, what)
    value = values[-1]
    assert value is not None
    return value


def read_title(sw: EggSession) -> int:
    """读盒子编号，连着几帧一样才算。"""
    return _read_stable(sw, lambda s: sv_screens.box_title(s, sw.config), "盒子编号")


# ---- 光标 ----


def _next_button(current: Cursor, target: Cursor) -> str:
    """往目标靠近要按的方向键：先换列（队伍和盒子之间、盒子里左右），再上下。"""
    current_place, current_row, current_col = current
    target_place, target_row, target_col = target
    if current_place == "party":
        if target_place == "slots":
            # 队伍第 6 格往右是盒子下面的「搜寻」按钮，不是盒子，要先往上一格（真机上出过）
            return "DUP" if current_row >= 5 else "DRIGHT"
        return "DDOWN" if target_row > current_row else "DUP"
    if target_place == "party":
        return "DLEFT"
    if target_col != current_col:
        return "DRIGHT" if target_col > current_col else "DLEFT"
    return "DDOWN" if target_row > current_row else "DUP"


def move_cursor(sw: EggSession, place: str, row: int, col: int) -> None:
    """盒子画面里把光标移到队伍或盒子的某一格，最多按 cursor_max_presses 下。place 是 "party" 或 "slots"。

    每按一下方向键都看光标动了没有，没动就再按；光标在格子外面（盒子名、「一览」「搜寻」）时按 DUP 回来。
    """
    config = sw.config
    target: Cursor = (place, row, col)
    current = screens.box_cursor(capture(sw, "盒子的光标"), config)
    for _ in range(config.cursor_max_presses):
        if current == target:
            return
        button = "DUP" if current is None else _next_button(current, target)
        image = press_until(
            sw,
            lambda key=button: sw.click(key, 0),
            lambda s, last=current: screens.box_cursor(s, config) != last,
            config.wait.timeout,
            "盒子的光标移一格",
            interval=sw.config.wait.press_interval,
        )
        current = screens.box_cursor(image, config)
    if current != target:
        raise RuntimeError(
            f"光标按了 {config.cursor_max_presses} 下，还是没到 {target}，现在在 {current}"
        )


def slot_has_pokemon(sw: EggSession) -> bool:
    """光标所在的格子里有没有宝可梦（右边的面板上有没有名字栏），连着几帧一样才算（光标刚到时面板还没换）。"""
    config = sw.config
    return _read_stable(sw, lambda s: screens.panel_present(s, config), "格子里有没有宝可梦")


# ---- 读宝可梦 ----


def read_name(sw: EggSession) -> str:
    """读面板上的名字，连着几帧一样、不是空的才算。"""
    config = sw.config
    return _read_stable(sw, lambda s: screens.panel_name(s, config) or None, "面板的名字")


def _read_shiny(sw: EggSession) -> bool:
    """面板上有没有闪光的星星，连着几帧一样才算。"""
    config = sw.config
    return _read_stable(sw, lambda s: screens.panel_shiny(s, config), "闪光的星星")


def _read_best(sw: EggSession) -> int | None:
    """切到评定页读「最棒」的项数：不在评定页就按 PLUS 切过去。

    按了 judge_timeout 秒还切不到评定页，说明游戏里评定功能没解锁，返回 None。
    """
    config = sw.config
    image = capture(sw, "评定页")
    if not screens.is_judge_page(image, config):
        try:
            image = press_until(
                sw,
                lambda: sw.click("PLUS", 0),
                lambda s: screens.is_judge_page(s, config),
                config.judge_timeout,
                "评定页",
                interval=sw.config.wait.press_interval,
            )
        except TimeoutError:
            return None
    return sum("最棒" in text for text in screens.panel_stats(image, config))


def read_ability(sw: EggSession) -> str:
    """读光标所在格子里宝可梦的特性：面板不在能力页就按 PLUS 切过去。"""
    config = sw.config
    image = capture(sw, "面板的特性")
    if not screens.is_stats_page(image, config):
        image = press_until(
            sw,
            lambda: sw.click("PLUS", 0),
            lambda s: screens.is_stats_page(s, config),
            config.wait.timeout,
            "面板的能力页",
            interval=sw.config.wait.press_interval,
        )
    return screens.panel_ability(image, config)


def count_box_eggs(sw: EggSession) -> int:
    """当前盒子里有几个蛋：每一格和蛋的图片比。

    光标停着的格子里的蛋被压扁了，和图片比不出来，这一格看右边面板上的名字是不是「蛋」。
    """
    config = sw.config
    image = capture(sw, "盒子里的蛋")
    eggs = screens.box_eggs(image, config)
    cursor = screens.box_cursor(image, config)
    if (
            cursor is not None
            and cursor[0] == "slots"
            and (cursor[1], cursor[2]) not in eggs
            and screens.panel_name(image, config).startswith("蛋")
    ):
        return len(eggs) + 1
    return len(eggs)


def read_mon(sw: EggSession) -> Mon:
    """读光标所在格子里的宝可梦：名字、「最棒」的项数、是不是闪光。"""
    name = read_name(sw)
    shiny = _read_shiny(sw)
    best = None if name.startswith("蛋") else _read_best(sw)
    return Mon(name, best, shiny)


def read_party(sw: EggSession) -> list[Mon]:
    """队伍里所有的宝可梦，从上到下。"""
    config = sw.config
    mons: list[Mon] = []
    for row in range(config.party_rows):
        move_cursor(sw, "party", row, 0)
        if not slot_has_pokemon(sw):
            break
        mons.append(read_mon(sw))
    return mons


def count_party_eggs(sw: EggSession) -> int:
    """队伍里除了带队的，有几个蛋；有不是蛋的宝可梦抛 RuntimeError。光标要先移到队伍里。"""
    config = sw.config
    image = capture(sw, "队伍里的蛋")
    slots = [screens.party_slot(image, row, config) for row in range(1, config.party_rows)]
    if "mon" in slots:
        raise RuntimeError(f"队伍里除了带队的，还有不是蛋的宝可梦：{slots}")
    return slots.count("egg")


# ---- 拿起、放下 ----


def _hold(sw: EggSession, button: str) -> None:
    """按 button（MINUS 或 Y）直到进了选择模式；没反应就隔一会儿再按。"""
    config = sw.config
    press_until(
        sw,
        lambda: sw.click(button, 0),
        lambda s: screens.is_box_selecting(s, config),
        sw.config.wait.timeout,
        "盒子的选择模式",
        interval=sw.config.wait.press_interval,
    )


def _drop(sw: EggSession) -> None:
    """拿着宝可梦时按 A 放下，直到退出选择模式。"""
    config = sw.config
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_box_selecting(s, config),
        sw.config.wait.timeout,
        "放下宝可梦",
        interval=sw.config.wait.press_interval,
    )


def _cancel(sw: EggSession) -> None:
    """按 B 取消选择，直到退出选择模式。"""
    config = sw.config
    press_until(
        sw,
        lambda: sw.click("B", 0),
        lambda s: not screens.is_box_selecting(s, config),
        sw.config.wait.timeout,
        "取消选择",
        interval=sw.config.wait.press_interval,
    )


def _hold_column(sw: EggSession, source: Slot) -> None:
    """光标在一列的最上面（source），把一整列拿起来：按减号进选择模式，按 DDOWN 直到光标到这一列最下面，按 A 拿起。"""
    config = sw.config
    place, _, col = source
    bottom: Cursor = (
        place,
        config.party_rows - 1 if place == "party" else config.box_rows - 1,
        col,
    )
    _hold(sw, "MINUS")
    press_until(
        sw,
        lambda: sw.click("DDOWN", 0),
        lambda s: screens.box_cursor(s, config) == bottom,
        config.wait.timeout,
        "选到一列的最下面",
        interval=sw.config.wait.press_interval,
    )
    # 这一下 A 拿没拿起来看不出来，后面移光标时移不过去会取消再来
    sw.click("A", 0)


def _move_column(sw: EggSession, source: Slot, target: Slot) -> None:
    """把 source 那一列拿起来放到 target：光标移不过去时（A 可能被吞了）按 B 取消再来，连着 10 次失败抛 RuntimeError。"""
    config = sw.config
    for _ in range(config.column_attempts):
        move_cursor(sw, *source)
        _hold_column(sw, source)
        try:
            move_cursor(sw, *target)
        except RuntimeError:
            logging.warning("拿着一列移不到目标，取消再来")
            _cancel(sw)
            continue
        _drop(sw)
        return
    raise RuntimeError(f"连着 {config.column_attempts} 次都没能把一列移过去")


def load_column(sw: EggSession, column: int) -> None:
    """把盒子第 column 列装进队伍（放在队伍第 1 行起）。"""
    logging.info(f"把盒子第 {column} 列装进队伍")
    _move_column(sw, ("slots", 0, column), ("party", 1, 0))


def unload_column(sw: EggSession, column: int) -> None:
    """把队伍里除了带队的卸到盒子第 column 列。"""
    logging.info(f"把队伍卸到盒子第 {column} 列")
    _move_column(sw, ("party", 1, 0), ("slots", 0, column))


def swap_slots(sw: EggSession, source: Slot, target: Slot) -> None:
    """把 source 那一格的宝可梦和 target 那一格交换：source 是空的抛 RuntimeError。"""
    logging.info(f"交换 {source} 和 {target}")
    move_cursor(sw, *source)
    if not slot_has_pokemon(sw):
        raise RuntimeError(f"要交换的 {source} 是空的")
    _hold(sw, "Y")
    move_cursor(sw, *target)
    _drop(sw)


def turn_box(sw: EggSession, button: str) -> int:
    """按 L 或 R 转一个盒子，一直按到盒子编号变成旁边那个，返回新的编号。"""
    config = sw.config
    current = read_title(sw)
    step = 1 if button == "R" else -1
    target = (current - 1 + step) % config.box_count + 1
    press_until(
        sw,
        lambda: sw.click(button, 0),
        lambda s: sv_screens.box_title(s, config) == target,
        config.wait.timeout,
        f"转到盒子 {target}",
        interval=sw.config.wait.press_interval,
    )
    return target


# ---- 换队伍 ----


def to_hatch_party(sw: EggSession) -> int:
    """从野外把野餐队伍换成孵蛋队伍：带队的熔岩虫在左边盒子第一格，队伍第一格是野餐队伍的第一只。

    打开盒子，到左边的盒子，带队的和队伍第一只交换，队伍里其余的卸到左边盒子第 1 列，
    回到放蛋的盒子，把第 0 列的蛋装进队伍，数队伍里的蛋，退出盒子。返回蛋数。
    """
    open_box(sw)
    turn_box(sw, "L")
    swap_slots(sw, ("slots", 0, 0), ("party", 0, 0))
    unload_column(sw, 1)
    turn_box(sw, "R")
    load_column(sw, 0)
    move_cursor(sw, "party", 0, 0)
    eggs = count_party_eggs(sw)
    actions.exit_to_overworld(sw)
    return eggs


def to_picnic_party(sw: EggSession) -> None:
    """在盒子里（当前是放蛋的盒子）把孵蛋队伍换回野餐队伍：队伍第一格和左边盒子第一格交换，第 1 列装进队伍。"""
    turn_box(sw, "L")
    swap_slots(sw, ("party", 0, 0), ("slots", 0, 0))
    load_column(sw, 1)
    turn_box(sw, "R")


# ---- 放生 ----


def _choose_operation(sw: EggSession, target: int) -> None:
    """按 A 出操作菜单，把光标移到第 target 行（移动、查看能力、携带持有物、标记、放生、取消）。"""
    config = sw.config
    # 按 A 出操作菜单（底下有「要拿……怎么办？」的对话框），没出来就再按
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.has_dialog_box(s, config),
        sw.config.wait.timeout,
        "盒子的操作菜单",
        interval=sw.config.wait.press_interval,
    )
    # 往下移到「放生」：每按一下看选中的行变了没有，没变（菜单刚出来时按键会被吞）就再按
    image = wait_until(
        sw,
        lambda s: screens.operation_row(s, config) != -1,
        config.wait.timeout,
        "操作菜单选中的一项",
    )
    current = screens.operation_row(image, config)
    while current != target:
        button = "DDOWN" if current < target else "DUP"
        image = press_until(
            sw,
            lambda key=button: sw.click(key, 0),
            lambda s, last=current: screens.operation_row(s, config) not in (last, -1),
            config.wait.timeout,
            "操作菜单的光标移一格",
            interval=sw.config.wait.press_interval,
        )
        current = screens.operation_row(image, config)


def move_to_next_box(sw: EggSession, source: Slot) -> None:
    """把 source 那一格的宝可梦放到右边盒子的第一个空格，再转回来。右边的盒子满了抛 RuntimeError。

    先到右边的盒子找空格，回来在操作菜单里选「移动」拿起来，按 R 转到右边的盒子，移到空格放下。
    """
    config = sw.config
    turn_box(sw, "R")
    target = next(
        (
            ("slots", row, col)
            for row in range(config.box_rows)
            for col in range(config.box_columns)
            if not _is_slot_filled(sw, row, col)
        ),
        None,
    )
    turn_box(sw, "L")
    if target is None:
        raise RuntimeError("右边的盒子满了，放不进去")
    logging.info(f"把 {source} 移到右边盒子的 {target}")
    move_cursor(sw, *source)
    _choose_operation(sw, config.move_row)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_box_selecting(s, config),
        config.wait.timeout,
        "盒子的选择模式",
        interval=sw.config.wait.press_interval,
    )
    turn_box(sw, "R")
    move_cursor(sw, *target)
    _drop(sw)
    turn_box(sw, "L")


def _is_slot_filled(sw: EggSession, row: int, col: int) -> bool:
    """把光标移到盒子第 row 行第 col 列，看里面有没有宝可梦。"""
    move_cursor(sw, "slots", row, col)
    return slot_has_pokemon(sw)


def release_one(sw: EggSession) -> None:
    """放生光标所在格子里的宝可梦，格子是空的就什么都不做。

    按 A 出操作菜单，把光标移到「放生」按 A，确认框里选「是」，然后一直按 A 过「再见」的对话。
    """
    config = sw.config
    if not slot_has_pokemon(sw):
        return
    name = read_name(sw)
    _choose_operation(sw, config.release_row)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_prompt(s, config),
        config.wait.timeout,
        "放生确认",
        interval=0.5
    )
    # 确认框的光标默认在「否」，往上一格选「是」
    press_until(
        sw,
        lambda: sw.click("DUP", 0),
        lambda s: screens.gradient_arrow(s, config.release_yes_area, config),
        config.wait.timeout,
        "放生确认选中「是」",
        interval=sw.config.wait.press_interval,
    )
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_prompt(s, config),
        config.wait.timeout,
        "放生后的对话",
        interval=sw.config.wait.press_interval,
    )
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.has_dialog_box(s, config),
        sw.config.wait.timeout,
        "放生后的盒子",
        interval=sw.config.wait.press_interval,
    )
    wait_until(
        sw,
        lambda s: not screens.panel_present(s, config),
        config.wait.timeout,
        f"放生{name}之后格子空了",
    )
    logging.info(f"放生了{name}")


def release_box(sw: EggSession) -> None:
    """放生当前盒子里的所有宝可梦：5 行 6 列，偶数行从左到右、奇数行从右到左，每格移过去放生。"""
    config = sw.config
    logging.info("放生整个盒子")
    for row in range(config.box_rows):
        columns = range(config.box_columns)
        for col in columns if row % 2 == 0 else reversed(columns):
            move_cursor(sw, "slots", row, col)
            release_one(sw)
