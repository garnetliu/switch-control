"""control_switch.games.sv.egg.box：队伍和盒子之间的操作（照上游 PokemonSV_BoxRoutines 和 EggAutonomous）。

光标移动（box.move_cursor）、读格子里的宝可梦（box.slot_has_pokemon）都要看画面，这里换成假函数，
只测它们被调用的顺序和按键：
- 装一列、卸一列：光标到那一列，按 MINUS 进选择模式，按 DDOWN 把一整列选上，按 A 拿起，光标到目标，按 A 放下。
- 交换两格：光标到第一格，按 Y 拿起，光标到第二格，按 A 放下。
选择模式用假的 is_box_selecting 表示：MINUS 进入，A 第一下拿起整列，第二下放下并退出，Y 拿起一只，B 取消。
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

box_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.box")


class SelectionWorld:
    """盒子里的选择模式：MINUS 进入（没拿起），Y 进入（拿起一只），A 拿起或放下，B 取消。"""

    def __init__(self) -> None:
        self.selecting = False
        self.held = False

    def press(self, button: str) -> None:
        if button == "MINUS" and not self.selecting:
            self.selecting = True
            self.held = False
        elif button == "Y":
            self.selecting = True
            self.held = True
        elif button == "A" and self.selecting:
            if self.held:
                self.selecting = False
                self.held = False
            else:
                self.held = True
        elif button == "B":
            self.selecting = False
            self.held = False


def collapse(entries: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """去掉连着的重复项（同一个键连按、等画面时重按都算一次）。"""
    result: list[tuple[Any, ...]] = []
    for entry in entries:
        if not result or result[-1] != entry:
            result.append(entry)
    return result


@pytest.fixture
def world(stage: Any) -> SelectionWorld:
    """选择模式的画面模型，按键让它变化，box 里的 is_box_selecting 读它。"""
    selection = SelectionWorld()
    stage.on_click = selection.press
    stage.set_screens(is_box_selecting=lambda: selection.selecting)
    return selection


def cursor_stub(stage: Any, fail_on: set[int] | None = None) -> list[int]:
    """box.move_cursor 换成记 ("cursor", 位置, 行, 列) 的假函数；第 n 次调用（从 1 数）在 fail_on 里就抛 RuntimeError。

    返回的列表里记着调用次数（只有一项，随着调用增加）。
    """
    count = [0]

    def move(place: str, row: int, col: int) -> None:
        count[0] += 1
        if fail_on and count[0] in fail_on:
            raise RuntimeError("光标没移到")
        stage.log.append(("cursor", place, row, col))

    def fake(sw: Any, place: str, row: int, col: int) -> None:
        move(place, row, col)

    stage.replace(box_module, "move_cursor", fake)
    return count


def keys_and_cursor(stage: Any) -> list[tuple[Any, ...]]:
    """log 里的光标移动和选择模式用到的键，连着重复的去掉。"""
    wanted = {"MINUS", "Y", "A", "B", "DDOWN"}
    return collapse(
        [
            entry
            for entry in stage.log
            if entry[0] == "cursor" or (entry[0] == "click" and entry[1] in wanted)
        ]
    )


def test_load_column_moves_cursor_holds_column_then_drops_it_in_party(
    stage: Any, world: SelectionWorld
) -> None:
    """装一列（第 3 列）：光标到盒子第 0 行第 3 列，按 MINUS，按 DDOWN 选整列，按 A 拿起，光标到队伍第 1 行，按 A 放下。"""
    cursor_stub(stage)
    box_module.load_column(stage.sw, 3)
    assert keys_and_cursor(stage) == [
        ("cursor", "slots", 0, 3),
        ("click", "MINUS"),
        ("click", "DDOWN"),
        ("click", "A"),
        ("cursor", "party", 1, 0),
        ("click", "A"),
    ]
    assert not world.selecting


def test_load_column_presses_down_enough_times_to_select_whole_column(
    stage: Any, world: SelectionWorld
) -> None:
    """装一列：一列最多 5 只，选整列至少按 5 下 DDOWN（上游按 15 下，防止游戏吞键）。"""
    cursor_stub(stage)
    box_module.load_column(stage.sw, 0)
    assert stage.clicks().count("DDOWN") >= 5


def test_unload_column_moves_cursor_holds_party_column_then_drops_it_in_box(
    stage: Any, world: SelectionWorld
) -> None:
    """卸一列（到第 2 列）：光标到队伍第 1 行，按 MINUS，按 DDOWN 选上，按 A 拿起，光标到盒子第 0 行第 2 列，按 A 放下。"""
    cursor_stub(stage)
    box_module.unload_column(stage.sw, 2)
    assert keys_and_cursor(stage) == [
        ("cursor", "party", 1, 0),
        ("click", "MINUS"),
        ("click", "DDOWN"),
        ("click", "A"),
        ("cursor", "slots", 0, 2),
        ("click", "A"),
    ]
    assert not world.selecting
    assert stage.clicks().count("DDOWN") >= 5


def test_load_column_cancels_and_retries_when_cursor_cannot_reach_party(
    stage: Any, world: SelectionWorld
) -> None:
    """装一列：把整列拿起之后光标移不到队伍（A 可能被游戏吞了）：按 B 取消，从头再来一遍，第二次成功就结束。"""
    cursor_stub(stage, fail_on={2})
    box_module.load_column(stage.sw, 1)
    assert keys_and_cursor(stage) == [
        ("cursor", "slots", 0, 1),
        ("click", "MINUS"),
        ("click", "DDOWN"),
        ("click", "A"),
        ("click", "B"),
        ("cursor", "slots", 0, 1),
        ("click", "MINUS"),
        ("click", "DDOWN"),
        ("click", "A"),
        ("cursor", "party", 1, 0),
        ("click", "A"),
    ]
    assert not world.selecting


def test_load_column_raises_runtime_error_after_ten_failed_attempts(
    stage: Any, world: SelectionWorld
) -> None:
    """装一列：光标连续 10 次移不到队伍：抛 RuntimeError，一共试了 10 次。"""
    count = cursor_stub(stage, fail_on={2 * n for n in range(1, 30)})
    with pytest.raises(RuntimeError):
        box_module.load_column(stage.sw, 1)
    assert count[0] == 20


def test_unload_column_raises_runtime_error_after_ten_failed_attempts(
    stage: Any, world: SelectionWorld
) -> None:
    """卸一列：光标连续 10 次移不到盒子：抛 RuntimeError，一共试了 10 次。"""
    count = cursor_stub(stage, fail_on={2 * n for n in range(1, 30)})
    with pytest.raises(RuntimeError):
        box_module.unload_column(stage.sw, 1)
    assert count[0] == 20


def test_swap_slots_picks_up_source_then_drops_on_target(stage: Any, world: SelectionWorld) -> None:
    """交换两格：光标到第一格，按 Y 拿起，光标到第二格，按 A 放下。"""
    cursor_stub(stage)
    stage.stub(box_module, "slot_has_pokemon", True)
    box_module.swap_slots(stage.sw, ("slots", 0, 0), ("party", 0, 0))
    assert keys_and_cursor(stage) == [
        ("cursor", "slots", 0, 0),
        ("click", "Y"),
        ("cursor", "party", 0, 0),
        ("click", "A"),
    ]
    assert not world.selecting


def test_swap_slots_raises_runtime_error_without_pressing_y_when_source_is_empty(
    stage: Any, world: SelectionWorld
) -> None:
    """交换两格：第一格是空的：抛 RuntimeError，没有按过 Y。"""
    cursor_stub(stage)
    stage.stub(box_module, "slot_has_pokemon", False)
    with pytest.raises(RuntimeError):
        box_module.swap_slots(stage.sw, ("slots", 0, 0), ("party", 0, 0))
    assert "Y" not in stage.clicks()


def test_to_left_box_presses_l_and_to_right_box_presses_r(stage: Any) -> None:
    """换盒子：往左一个盒子按 L，往右一个盒子按 R，都只按一下（看不到画面，上游也是盲按）。"""
    box_module.to_left_box(stage.sw)
    box_module.to_right_box(stage.sw)
    assert stage.clicks() == ["L", "R"]


def test_to_hatch_party_swaps_leads_unloads_rest_loads_first_egg_column_and_returns_egg_count(
    stage: Any,
) -> None:
    """野餐队伍换成孵蛋队伍：开盒子，到左边盒子，盒子第 0 格（带队的）和队伍第 0 只交换，
    队伍里其余的卸到第 1 列，回到中间盒子，把第 0 列装进队伍，光标到队伍第 0 只，数蛋，退出盒子。
    返回数到的蛋数（5）。
    """
    stage.stub(box_module, "open_box")
    stage.stub(box_module, "to_left_box")
    stage.stub(box_module, "to_right_box")
    stage.stub(box_module, "swap_slots")
    stage.stub(box_module, "unload_column")
    stage.stub(box_module, "load_column")
    stage.stub(box_module, "move_cursor")
    stage.stub(box_module, "count_party_eggs", 5)
    stage.stub(box_module, "exit_to_overworld")
    assert box_module.to_hatch_party(stage.sw) == 5
    assert stage.log == [
        ("open_box",),
        ("to_left_box",),
        ("swap_slots", ("slots", 0, 0), ("party", 0, 0)),
        ("unload_column", 1),
        ("to_right_box",),
        ("load_column", 0),
        ("move_cursor", "party", 0, 0),
        ("count_party_eggs",),
        ("exit_to_overworld",),
    ]


def test_to_picnic_party_swaps_leads_and_loads_second_column(stage: Any) -> None:
    """孵蛋队伍换回野餐队伍（已经在盒子里、当前是中间盒子）：到左边盒子，队伍第 0 只和盒子第 0 格交换，
    第 1 列装进队伍，回到中间盒子。不开盒子也不退出盒子。
    """
    stage.stub(box_module, "to_left_box")
    stage.stub(box_module, "to_right_box")
    stage.stub(box_module, "swap_slots")
    stage.stub(box_module, "load_column")
    box_module.to_picnic_party(stage.sw)
    assert stage.log == [
        ("to_left_box",),
        ("swap_slots", ("party", 0, 0), ("slots", 0, 0)),
        ("load_column", 1),
        ("to_right_box",),
    ]


def test_release_box_visits_all_thirty_slots_in_z_shape_and_releases_each(stage: Any) -> None:
    """放生整盒：5 行 × 6 列，偶数行从左到右、奇数行从右到左，每格光标移过去再放生。"""
    stage.stub(box_module, "move_cursor")
    stage.stub(box_module, "release_one")
    box_module.release_box(stage.sw)
    expected: list[tuple[Any, ...]] = []
    for row in range(5):
        columns = range(6) if row % 2 == 0 else range(5, -1, -1)
        for col in columns:
            expected += [("move_cursor", "slots", row, col), ("release_one",)]
    assert stage.log == expected


# ---- 开盒子：转到放蛋的盒子 ----


def test_open_box_raises_runtime_error_when_box_number_cannot_be_read(stage: Any) -> None:
    """盒子编号一直读不出来（_read_title 返回 None）：不知道开着的是不是放蛋的盒子，后面要装蛋、放生整盒，
    不能当作转好了：open_box 抛 RuntimeError，不是正常返回。
    """
    stage.set_screens(box_cursor=lambda: ("slots", 0, 0))
    stage.replace(box_module, "_read_title", lambda sw: None)
    with pytest.raises(RuntimeError):
        box_module.open_box(stage.sw)


def test_open_box_returns_without_turning_when_already_on_egg_box(stage: Any) -> None:
    """盒子编号读出来就是放蛋的盒子（sw.egg_box）：不按 L、R，正常返回。"""
    stage.set_screens(box_cursor=lambda: ("slots", 0, 0))
    stage.sw.egg_box = 3
    stage.replace(box_module, "_read_title", lambda sw: 3)
    box_module.open_box(stage.sw)
    assert "L" not in stage.clicks()
    assert "R" not in stage.clicks()


def test_open_box_first_time_takes_next_box_as_egg_box_and_turns_right_once(stage: Any) -> None:
    """第一次开盒子，开着的是盒子 29：放蛋的记成盒子 30，按一下 R 转过去。"""
    stage.set_screens(box_cursor=lambda: ("slots", 0, 0))
    titles = iter([29, 29, 30])
    stage.replace(box_module, "_read_title", lambda sw: next(titles))
    box_module.open_box(stage.sw)
    assert stage.sw.egg_box == 30
    assert stage.clicks().count("R") == 1
    assert "L" not in stage.clicks()


def test_open_box_first_time_on_last_box_wraps_egg_box_to_first(stage: Any) -> None:
    """第一次开盒子，开着的是最后一个盒子 32：放蛋的是盒子 1。"""
    stage.set_screens(box_cursor=lambda: ("slots", 0, 0))
    titles = iter([32, 32, 1])
    stage.replace(box_module, "_read_title", lambda sw: next(titles))
    box_module.open_box(stage.sw)
    assert stage.sw.egg_box == 1


# ---- 放生 ----


class ReleaseWorld:
    """放生的画面：按 A 出操作菜单（光标已经在「放生」上），按 A 进确认框（光标在「否」，按 DUP 到「是」），
    选「是」按 A 之后是「再见」的对话，再按 A 对话消失。格子之后空不空由 emptied 决定。
    """

    def __init__(self, stage: Any, emptied: bool) -> None:
        self.stage = stage
        self.phase = "idle"
        self.up = False
        self.emptied = emptied
        self.released = False
        stage.on_click = self.press
        stage.set_screens(
            has_dialog_box=lambda: self.phase in ("menu", "confirm", "bye"),
            is_prompt=lambda: self.phase == "confirm",
            operation_row=lambda: stage.sw.config.release_row if self.phase == "menu" else -1,
        )
        stage.replace(box_module, "_read_name", lambda sw: "烛光灵")
        stage.replace(
            box_module, "slot_has_pokemon", lambda sw: not (self.released and self.emptied)
        )

    def press(self, button: str) -> None:
        if button == "DUP" and self.phase == "confirm":
            self.up = True
        elif button == "A":
            if self.phase == "idle":
                self.phase = "menu"
            elif self.phase == "menu":
                self.phase = "confirm"
            elif self.phase == "confirm":
                self.phase = "bye" if self.up else "menu"
                self.released = self.up
            elif self.phase == "bye":
                self.phase = "idle"


def test_release_one_returns_normally_when_slot_is_empty_afterwards(stage: Any) -> None:
    """放生：走完菜单、确认框（选「是」）、再见的对话，格子空了：正常返回，按键里有选「是」的 DUP。"""
    world = ReleaseWorld(stage, emptied=True)
    box_module.release_one(stage.sw)
    assert world.released
    assert "DUP" in stage.clicks()


def test_release_one_does_not_return_as_success_when_slot_still_has_pokemon(stage: Any) -> None:
    """放生流程走完了，格子里还有宝可梦（没放生成功，比如确认框里的 DUP 被吞，选成了「否」）：
    release_one 要抛错（RuntimeError 或 TimeoutError）或者重试到格子空，不能当作成功返回。
    """
    ReleaseWorld(stage, emptied=False)
    with pytest.raises((RuntimeError, TimeoutError)):
        box_module.release_one(stage.sw)
