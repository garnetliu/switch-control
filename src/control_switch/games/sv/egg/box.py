"""盒子和队伍里的操作：开关盒子、移光标、读宝可梦、装一列、卸一列、交换、放生。

照 PokemonAutomation 的 PokemonSV_BoxRoutines、PokemonSV_BoxRelease 和 EggAutonomous 里换队伍的几段。
盒子有三个相邻的：左边的盒子放野餐队伍和带队的宝可梦，当前的盒子放蛋，右边的盒子放留下的。
"""

import logging
import time
from typing import NamedTuple

from control_switch.flow import act_until, capture, wait_for
from control_switch.games.sv import actions

from . import screens
from .screens import Cursor
from .session import EggSession

# 盒子里的一格：("party", 队伍第几行, 0) 或 ("slots", 行, 列)。队伍第 0 行是带队的
Slot = tuple[str, int, int]


class Mon(NamedTuple):
    """盒子里读到的一只宝可梦。"""

    name: str
    # 「最棒」的项数；游戏里评定功能没解锁读不到，是 None
    best: int | None
    shiny: bool


# ---- 进出盒子 ----


def open_box(sw: EggSession) -> None:
    """从野外打开盒子（主菜单第 2 项），再把盒子转到放蛋的那个。

    第一次打开时开着的是放亲代和带队宝可梦的盒子，放蛋的是它后面那个，记在 sw.egg_box。
    """
    config = sw.config
    deadline = time.monotonic() + config.open_box_timeout
    while True:
        image = capture(sw, "开盒子")
        if screens.box_cursor(image, config) is not None or screens.box_title(image, config):
            break
        if screens.is_overworld(image, config):
            actions.open_menu(sw)
        elif screens.is_main_menu(image, config):
            actions.menu_to_row(sw, config.menu_box_row)
        else:
            time.sleep(config.wait.interval)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.open_box_timeout} 秒，还是没打开盒子")
    time.sleep(config.box_open_wait)
    if sw.egg_box is None:
        number = _read_title(sw)
        if number is None:
            raise RuntimeError("读不出盒子编号，不知道哪个是放蛋的盒子，不敢往下做")
        sw.egg_box = number % config.box_count + 1
        logging.info(f"开始时是盒子 {number}，蛋放在盒子 {sw.egg_box}")
    _turn_to_egg_box(sw)


def _read_title(sw: EggSession) -> int | None:
    """读盒子编号，连续两次一样才算；读不出返回 None。"""
    config = sw.config
    previous: int | None = None
    for _ in range(config.box_title_tries):
        title = screens.box_title(capture(sw, "盒子编号"), config)
        if title is not None and title == previous:
            return title
        previous = title
        time.sleep(config.read_gap)
    return None


def _turn_to_egg_box(sw: EggSession) -> None:
    """用 L、R 把盒子转到放蛋的那个（sw.egg_box），往近的方向转。读不出盒子编号抛 RuntimeError，转了 box_rounds 轮还没到也抛。"""
    config = sw.config
    egg_box = sw.egg_box
    assert egg_box is not None
    for _ in range(config.box_rounds):
        number = _read_title(sw)
        if number is None:
            raise RuntimeError("读不出盒子编号，不知道开着的是不是放蛋的盒子，不敢往下做")
        if number == egg_box:
            return
        forward = (egg_box - number) % config.box_count
        backward = config.box_count - forward
        button, count = ("R", forward) if forward <= backward else ("L", backward)
        logging.info(f"现在是盒子 {number}，转到盒子 {egg_box}")
        for _ in range(count):
            sw.click(button, config.box_turn_wait)
    raise RuntimeError(f"转了 {config.box_rounds} 轮，还是没转到盒子 {egg_box}")


def exit_to_overworld(sw: EggSession) -> None:
    """按 B 退出盒子或菜单，直到回到野外；在野餐里就先收起野餐。"""
    config = sw.config
    presses = 0
    while True:
        image = capture(sw, "退出到野外")
        if screens.is_overworld(image, config):
            return
        if screens.is_picnic(image, config):
            actions.close_picnic(sw)
            continue
        if presses >= config.exit_presses:
            raise RuntimeError(f"按了 {config.exit_presses} 次 B，还是回不到野外")
        sw.click("B", config.exit_wait)
        presses += 1


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


def _wait_cursor_change(sw: EggSession, current: Cursor | None) -> Cursor | None:
    """等光标变化，最多 cursor_wait 秒；没变返回原来的。光标在格子外面时返回 None。"""
    config = sw.config
    deadline = time.monotonic() + config.cursor_wait
    while True:
        cursor = screens.box_cursor(capture(sw, "盒子的光标"), config)
        if cursor != current:
            return cursor
        if time.monotonic() >= deadline:
            return cursor
        time.sleep(config.wait.interval)


def move_cursor(sw: EggSession, place: str, row: int, col: int) -> None:
    """盒子画面里把光标移到队伍或盒子的某一格，最多按 cursor_max_presses 下。place 是 "party" 或 "slots"。"""
    config = sw.config
    target: Cursor = (place, row, col)
    # 光标可能停在格子外面（盒子名、「一览」「搜寻」），认不出格子时按 DUP 回来
    image = act_until(
        sw,
        lambda: sw.click("DUP", 0),
        lambda s: screens.box_cursor(s, config) is not None,
        "盒子的光标",
        interval=config.cursor_wait,
    )
    current = screens.box_cursor(image, config)
    for _ in range(config.cursor_max_presses):
        if current == target:
            time.sleep(config.cursor_settle_wait)
            return
        if current is None:
            sw.click("DUP", 0)
            current = _wait_cursor_change(sw, None)
            continue
        sw.click(_next_button(current, target), 0)
        current = _wait_cursor_change(sw, current)
    if current == target:
        time.sleep(config.cursor_settle_wait)
        return
    raise RuntimeError(
        f"光标按了 {config.cursor_max_presses} 下，还是没到 {target}，现在在 {current}"
    )


def slot_has_pokemon(sw: EggSession) -> bool:
    """光标所在的格子里有没有宝可梦（右边的面板上有没有名字栏）。"""
    config = sw.config
    return screens.panel_present(capture(sw, "格子里有没有宝可梦"), config)


# ---- 读宝可梦 ----


def _read_name(sw: EggSession) -> str:
    """读面板上的名字，连续两帧一样才算，最多读 read_tries 次。"""
    config = sw.config
    previous = screens.panel_name(capture(sw, "面板的名字"), config)
    for _ in range(config.read_tries):
        time.sleep(config.read_gap)
        name = screens.panel_name(capture(sw, "面板的名字"), config)
        if name == previous:
            return name
        previous = name
    return previous


def _read_shiny(sw: EggSession) -> bool:
    """面板上有没有闪光的星星：连续两帧里任何一帧有就算。"""
    config = sw.config
    first = screens.panel_shiny(capture(sw, "闪光的星星"), config)
    time.sleep(config.read_gap)
    second = screens.panel_shiny(capture(sw, "闪光的星星"), config)
    return first or second


def _read_best(sw: EggSession) -> int | None:
    """切到评定页读「最棒」的项数；按 PLUS 切了 judge_tries 次也不是评定页，说明评定功能没解锁，返回 None。"""
    config = sw.config
    for _ in range(config.judge_tries):
        texts = screens.panel_stats(capture(sw, "评定页"), config)
        if (
            sum(any(word in text for word in config.judge_words) for text in texts)
            >= config.judge_min
        ):
            return sum("最棒" in text for text in texts)
        sw.click("PLUS", config.judge_wait)
    return None


def read_mon(sw: EggSession) -> Mon:
    """读光标所在格子里的宝可梦：名字、「最棒」的项数、是不是闪光。"""
    name = _read_name(sw)
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
    act_until(
        sw,
        lambda: sw.click(button, 0),
        lambda s: screens.is_box_selecting(s, config),
        "盒子的选择模式",
        interval=config.hold_retry,
    )


def _drop(sw: EggSession) -> None:
    """拿着宝可梦时按 A 放下，直到退出选择模式。"""
    config = sw.config
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_box_selecting(s, config),
        "放下宝可梦",
        interval=config.hold_retry,
    )


def _cancel(sw: EggSession) -> None:
    """按 B 取消选择，直到退出选择模式。"""
    config = sw.config
    act_until(
        sw,
        lambda: sw.click("B", 0),
        lambda s: not screens.is_box_selecting(s, config),
        "取消选择",
        interval=config.hold_retry,
    )


def _hold_column(sw: EggSession) -> None:
    """光标在一列的最上面，把一整列拿起来：按减号进选择模式，往下按够多下选满一列，按 A 拿起。"""
    config = sw.config
    _hold(sw, "MINUS")
    # 多按几下，防止游戏吞键；已经选到底了再按没有影响
    for _ in range(config.column_downs):
        sw.click("DDOWN", config.column_down_wait)
    time.sleep(config.hold_settle_wait)
    # 这一下 A 拿没拿起来看不出来，只能直接往下走
    sw.click("A", config.hold_press_wait)


def _move_column(sw: EggSession, source: Slot, target: Slot) -> None:
    """把 source 那一列拿起来放到 target：光标移不过去时（A 可能被吞了）按 B 取消再来，连着 10 次失败抛 RuntimeError。"""
    config = sw.config
    for _ in range(config.column_attempts):
        move_cursor(sw, *source)
        _hold_column(sw)
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


def to_left_box(sw: EggSession) -> None:
    """往左转一个盒子。看不到画面，只能按一下。"""
    sw.click("L", sw.config.box_turn_wait)


def to_right_box(sw: EggSession) -> None:
    """往右转一个盒子。看不到画面，只能按一下。"""
    sw.click("R", sw.config.box_turn_wait)


# ---- 换队伍 ----


def to_hatch_party(sw: EggSession) -> int:
    """从野外把野餐队伍换成孵蛋队伍：带队的熔岩虫在左边盒子第一格，队伍第一格是野餐队伍的第一只。

    打开盒子，到左边的盒子，带队的和队伍第一只交换，队伍里其余的卸到左边盒子第 1 列，
    回到放蛋的盒子，把第 0 列的蛋装进队伍，数队伍里的蛋，退出盒子。返回蛋数。
    """
    open_box(sw)
    to_left_box(sw)
    swap_slots(sw, ("slots", 0, 0), ("party", 0, 0))
    unload_column(sw, 1)
    to_right_box(sw)
    load_column(sw, 0)
    move_cursor(sw, "party", 0, 0)
    eggs = count_party_eggs(sw)
    exit_to_overworld(sw)
    return eggs


def to_picnic_party(sw: EggSession) -> None:
    """在盒子里（当前是放蛋的盒子）把孵蛋队伍换回野餐队伍：队伍第一格和左边盒子第一格交换，第 1 列装进队伍。"""
    to_left_box(sw)
    swap_slots(sw, ("party", 0, 0), ("slots", 0, 0))
    load_column(sw, 1)
    to_right_box(sw)


# ---- 放生 ----


def release_one(sw: EggSession) -> None:
    """放生光标所在格子里的宝可梦，格子是空的就什么都不做。

    按 A 出操作菜单，把光标移到「放生」按 A，确认框里选「是」，然后一直按 A 过「再见」的对话。
    """
    config = sw.config
    if not slot_has_pokemon(sw):
        return
    name = _read_name(sw)
    # 按 A 出操作菜单（底下有「要拿……怎么办？」的对话框），没出来就再按
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.has_dialog_box(s, config),
        "盒子的操作菜单",
        interval=config.operation_interval,
    )
    # 菜单刚出来时按键会被吞，等一会儿；往下移到「放生」，每按一下读一次选中的是哪行，所以不按固定次数
    time.sleep(config.operation_settle_wait)
    for _ in range(config.operation_rows * 2):
        row = screens.operation_row(capture(sw, "操作菜单选中的一项"), config)
        if row == config.release_row:
            break
        sw.click("DDOWN" if row < config.release_row else "DUP", config.release_down_wait)
    else:
        raise RuntimeError("操作菜单的光标移不到「放生」")
    sw.click("A", config.release_confirm_wait)
    wait_for(sw, lambda s: screens.is_prompt(s, config), config.wait.timeout, "放生确认")
    # 确认框的光标默认在「否」，往上一格选「是」
    sw.click("DUP", config.release_down_wait)
    sw.click("A", config.release_confirm_wait)
    wait_for(sw, lambda s: screens.has_dialog_box(s, config), config.wait.timeout, "放生后的对话")
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.has_dialog_box(s, config),
        "放生后的盒子",
        interval=config.dialog_retry,
    )
    time.sleep(config.release_check_wait)
    if slot_has_pokemon(sw):
        raise RuntimeError(f"放生{name}之后格子里还有宝可梦，没放生成功")
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
