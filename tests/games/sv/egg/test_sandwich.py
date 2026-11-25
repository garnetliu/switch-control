"""steps.fetch 里做三明治的部分：进食谱列表、选食谱、移动手（照上游 PokemonSV_SandwichRoutines.cpp）。

进食谱列表：_sandwich_state 换成按脚本返回的假函数（"picnic" 回到了野餐、"menu" 桌子菜单的箭头、
"recipes" 食谱列表的箭头、"dialog" 对话、"unknown" 30 秒没识别到），每看一次假时钟走几秒。
选食谱：用一个食谱列表的画面模型（两列、每页 6 个、按 DDOWN 往下、DRIGHT 往右），
screens.recipe_numbers、screens.selected_recipe_cell、screens.is_pick_arrow 读它。
移动手：screens.find_hand(image, 种类, 范围) 换成按脚本返回手的位置的假函数，位置是占画面宽高的比例。
所有框都是 Rect：((左, 上), (右, 下))。
"""

import importlib
from collections.abc import Callable, Sequence
from types import ModuleType
from typing import Any

import pytest

fetch_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.steps.fetch")


def scripted(
    stage: Any, states: Sequence[str], seconds: float = 1.0, repeat_last: bool = False
) -> Callable[..., str]:
    """按顺序返回 states 里的状态，每次让假时钟走 seconds 秒；用完了：repeat_last 为真就一直返回最后一个，否则报错。"""
    queue = list(states)

    def look(*args: Any, **kwargs: Any) -> str:
        stage.advance(seconds)
        if len(queue) > 1 or (queue and not repeat_last):
            return queue.pop(0)
        assert queue and repeat_last, "看得太多次，脚本用完了"
        return queue[0]

    return look


def enter(stage: Any, states: list[str], **kwargs: Any) -> bool:
    """用假的 _sandwich_state 跑一遍 _enter_sandwich_recipe_list。"""
    stage.replace(fetch_module, "_sandwich_state", scripted(stage, states, **kwargs))
    return fetch_module._enter_sandwich_recipe_list(stage.sw)


def test_enter_recipe_list_presses_a_first_then_returns_true_when_list_arrow_appears(
    stage: Any,
) -> None:
    """进食谱列表：先按一下 A 打开桌子的菜单；看到食谱列表的箭头就返回 True，只按了这一下 A。"""
    assert enter(stage, ["recipes"]) is True
    assert stage.clicks() == ["A"]


def test_enter_recipe_list_presses_a_on_menu_arrow(stage: Any) -> None:
    """桌子菜单的箭头（选中「做三明治」）：按 A 进食谱列表，列表出来就返回 True。"""
    assert enter(stage, ["menu", "recipes"]) is True
    assert stage.clicks() == ["A", "A"]


def test_enter_recipe_list_presses_a_on_dialog_before_menu_opened(stage: Any) -> None:
    """菜单还没打开过时看到对话：按 A 往下翻，之后出现菜单箭头、列表箭头，返回 True。"""
    assert enter(stage, ["dialog", "menu", "recipes"]) is True
    assert stage.clicks() == ["A", "A", "A"]


def test_enter_recipe_list_walks_forward_and_presses_a_when_back_at_picnic(stage: Any) -> None:
    """看到的是野餐画面（第一下 A 被游戏吞了）：左摇杆往前推 0.8 秒走到桌子前，再按 A，然后接着看。"""
    assert enter(stage, ["picnic", "recipes"]) is True
    assert stage.log == [
        ("click", "A"),
        ("stick", "LEFT", 0.0, 1.0, 0.8),
        ("click", "A"),
    ]


def test_enter_recipe_list_returns_false_when_dialog_appears_after_menu_opened(
    stage: Any,
) -> None:
    """打开了桌子菜单、按 A 选「做三明治」之后出了对话（没有材料）：返回 False，不再按键。"""
    assert enter(stage, ["menu", "dialog"]) is False
    assert stage.clicks() == ["A", "A"]


def test_enter_recipe_list_raises_runtime_error_when_nothing_recognized(stage: Any) -> None:
    """30 秒没有识别出任何状态：抛 RuntimeError，报错里有「食谱」。"""
    with pytest.raises(RuntimeError, match="食谱"):
        enter(stage, ["unknown"])


def test_enter_recipe_list_raises_timeout_error_after_one_minute(stage: Any) -> None:
    """一直在没打开菜单时看到对话（一直按 A）：超过 1 分钟抛 TimeoutError，报错里有「食谱」。"""
    with pytest.raises(TimeoutError, match="食谱"):
        enter(stage, ["dialog"], seconds=10.0, repeat_last=True)


def test_sandwich_state_reports_list_arrow(stage: Any) -> None:
    """画面上是食谱列表的箭头：_sandwich_state 返回 "recipes"。"""
    stage.set_screens(
        is_picnic=lambda: False,
        is_table_menu_arrow=lambda: False,
        is_recipe_list=lambda: True,
        is_dialog=lambda: False,
    )
    assert fetch_module._sandwich_state(stage.sw) == "recipes"


def test_sandwich_state_reports_unknown_after_thirty_seconds(stage: Any) -> None:
    """四种状态都认不出来：看了 30 秒之后 _sandwich_state 返回 "unknown"。"""
    start = stage.clock.now
    stage.set_screens(
        is_picnic=lambda: False,
        is_table_menu_arrow=lambda: False,
        is_recipe_list=lambda: False,
        is_dialog=lambda: False,
    )
    assert fetch_module._sandwich_state(stage.sw) == "unknown"
    assert 30 <= stage.clock.now - start < 32


class RecipeWorld:
    """食谱列表的画面：recipes 是有的食谱编号（从小到大），两列、每页 3 行 6 个，选中的是页面上第 cell 格。

    按 DDOWN 往下一行（选中格在最下一行时整页往下滚一行），DRIGHT 往右一格，A 进选签子的界面，
    再按 A 进入做三明治（两个画面都不是了）。drop_first_a：第一下 A 被游戏吞掉。
    """

    def __init__(
        self, recipes: list[int], *, arrow: bool = True, drop_first_a: bool = False
    ) -> None:
        self.recipes = recipes
        self.arrow = arrow
        self.drop_first_a = drop_first_a
        self.top = 0
        self.cell = 0
        self.phase = "list"

    def index(self) -> int:
        return self.top * 2 + self.cell

    def numbers(self) -> list[int]:
        window = self.recipes[self.top * 2 : self.top * 2 + 6]
        return window + [0] * (6 - len(window))

    def selected(self) -> int:
        return self.cell if self.phase == "list" and self.arrow else -1

    def pick_arrow(self) -> bool:
        return self.phase == "pick"

    def press(self, button: str) -> None:
        if self.phase == "list":
            if button == "DDOWN" and self.index() + 2 < len(self.recipes):
                if self.cell // 2 < 2:
                    self.cell += 2
                else:
                    self.top += 1
            elif button == "DRIGHT" and self.cell % 2 == 0 and self.index() + 1 < len(self.recipes):
                self.cell += 1
            elif button == "A":
                if self.drop_first_a:
                    self.drop_first_a = False
                else:
                    self.phase = "pick"
        elif self.phase == "pick" and button == "A":
            self.phase = "game"


def select(stage: Any, world: RecipeWorld, target: int) -> bool:
    """用食谱列表的画面模型跑一遍 _select_sandwich_recipe。"""
    stage.on_click = world.press
    stage.set_screens(
        recipe_numbers=world.numbers,
        selected_recipe_cell=world.selected,
        is_pick_arrow=world.pick_arrow,
    )
    return fetch_module._select_sandwich_recipe(stage.sw, target)


def test_select_recipe_presses_a_twice_when_target_is_selected_on_first_page(stage: Any) -> None:
    """食谱 1 在第一页、已经选中：按 A 进选签子的界面，再按 A 开始做，返回 True，没按过方向键。"""
    assert select(stage, RecipeWorld(list(range(1, 41))), 1) is True
    assert stage.clicks() == ["A", "A"]


def test_select_recipe_moves_right_when_target_is_in_right_column(stage: Any) -> None:
    """食谱 2 在第一页右边一格：按 DRIGHT 一下，再按 A、A，返回 True。"""
    assert select(stage, RecipeWorld(list(range(1, 41))), 2) is True
    assert stage.clicks() == ["DRIGHT", "A", "A"]


def test_select_recipe_moves_down_when_target_is_below_on_same_page(stage: Any) -> None:
    """食谱 3 在第一页左边第二行：按 DDOWN 一下，再按 A、A，返回 True。"""
    assert select(stage, RecipeWorld(list(range(1, 41))), 3) is True
    assert stage.clicks() == ["DDOWN", "A", "A"]


def test_select_recipe_scrolls_down_list_until_target_is_on_page(stage: Any) -> None:
    """食谱 17（列表里第 9 行左边）：一直按 DDOWN 往下翻，8 下之后目标在选中格上，按 A、A，返回 True。"""
    assert select(stage, RecipeWorld(list(range(1, 41))), 17) is True
    assert stage.clicks() == ["DDOWN"] * 8 + ["A", "A"]


def test_select_recipe_moves_right_after_scrolling_when_target_is_in_right_column(
    stage: Any,
) -> None:
    """食谱 18（右边一列）：往下翻 8 下之后按一下 DRIGHT，再按 A、A，返回 True。"""
    assert select(stage, RecipeWorld(list(range(1, 41))), 18) is True
    assert stage.clicks() == ["DDOWN"] * 8 + ["DRIGHT", "A", "A"]


def test_select_recipe_presses_a_again_when_first_a_was_dropped(stage: Any) -> None:
    """选中目标后按的第一下 A 被游戏吞了（画面还在食谱列表）：再按一下 A；进选签子的界面后再按一下 A；一共 3 下 A。"""
    world = RecipeWorld(list(range(1, 41)), drop_first_a=True)
    assert select(stage, world, 1) is True
    assert stage.clicks() == ["A", "A", "A"]


def test_select_recipe_returns_false_without_pressing_a_when_ingredients_are_missing(
    stage: Any,
) -> None:
    """没有材料：列表里 16 和 18 之间没有 17（页面编号范围包住了 17 但没有它）：返回 False，没按过 A。"""
    recipes = [number for number in range(1, 41) if number != 17]
    assert select(stage, RecipeWorld(recipes), 17) is False
    assert "A" not in stage.clicks()


def test_select_recipe_returns_false_after_100_down_presses_when_list_ends_before_target(
    stage: Any,
) -> None:
    """食谱不在（整个列表只有 1 到 10，翻到底也没有 17）：一共按 100 次 DDOWN 之后返回 False，没按过 A。"""
    assert select(stage, RecipeWorld(list(range(1, 11))), 17) is False
    assert stage.clicks() == ["DDOWN"] * 100


def test_select_recipe_presses_down_when_no_number_is_recognized(stage: Any) -> None:
    """页面上一个编号都认不出来（全是 0）：当作目标在下面，按 DDOWN；100 次之后返回 False。"""
    world = RecipeWorld([])
    assert select(stage, world, 17) is False
    assert stage.clicks() == ["DDOWN"] * 100


def test_select_recipe_raises_runtime_error_when_selection_arrow_is_not_seen(stage: Any) -> None:
    """目标在这一页，但 10 秒都看不到选中的箭头：抛 RuntimeError，报错里有「箭头」。"""
    world = RecipeWorld(list(range(1, 41)), arrow=False)
    start = stage.clock.now
    with pytest.raises(RuntimeError, match="箭头"):
        select(stage, world, 1)
    assert stage.clock.now - start >= 10


# ---- 移动手 ----

Rect = tuple[tuple[float, float], tuple[float, float]]


def flat(rect: Rect) -> tuple[float, float, float, float]:
    """((左, 上), (右, 下)) 变成 (左, 上, 右, 下)，方便用 pytest.approx 比较。"""
    return (rect[0][0], rect[0][1], rect[1][0], rect[1][1])


def around(x: float, y: float, half_width: float = 0.03, half_height: float = 0.03) -> Rect:
    """以 (x, y) 为中心的目标框。"""
    return ((x - half_width, y - half_height), (x + half_width, y + half_height))


def watch_hand(
    stage: Any, locations: Sequence[tuple[float, float] | None]
) -> list[tuple[str, Rect]]:
    """screens.find_hand 换成按顺序返回 locations 的假函数（用完后一直返回最后一个）；返回它每次被问到的 (种类, 范围)。"""
    asked: list[tuple[str, Rect]] = []
    queue = list(locations)

    def find_hand(image: Any, kind: str, area: Rect, *args: Any, **kwargs: Any) -> Any:
        asked.append((kind, area))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    stage.replace(
        importlib.import_module("control_switch.games.sv.egg.screens"), "find_hand", find_hand
    )
    return asked


START: Rect = ((0.44, 0.455), (0.552, 0.634))


def move(stage: Any, kind: str, pressing_a: bool, end: Rect, start: Rect = START) -> Rect:
    return fetch_module._move_sandwich_hand(stage.sw, kind, pressing_a, start, end)


def test_move_hand_pushes_full_stick_toward_far_target(stage: Any) -> None:
    """推多大按距离算：手在 (0.2, 0.5)，目标中心在 (0.6, 0.5)，差 0.4 个画面宽（按 16:9 算 6.4 格），
    超过 4 格就满推：左摇杆 x 是 1.0，y 是 0。第二次看到手已经在目标框里，结束。
    """
    watch_hand(stage, [(0.2, 0.5), (0.6, 0.5)])
    move(stage, "free", False, around(0.6, 0.5))
    sticks = [entry for entry in stage.log if entry[0] == "stick"]
    assert len(sticks) == 1
    assert sticks[0][1] == "LEFT"
    assert sticks[0][2:4] == (1.0, 0.0)


def test_move_hand_pushes_proportionally_when_target_is_near(stage: Any) -> None:
    """推多大按距离算：手在 (0.5, 0.5)，目标在右边 0.1 个画面宽（1.6 格）：推 1.6 × 0.25 = 0.4，x 是 0.4。"""
    watch_hand(stage, [(0.5, 0.5), (0.6, 0.5)])
    move(stage, "free", False, around(0.6, 0.5))
    stick = next(entry for entry in stage.log if entry[0] == "stick")
    assert stick[2] == pytest.approx(0.4, abs=0.002)
    assert stick[3] == pytest.approx(0.0, abs=0.002)


def test_move_hand_pushes_down_with_negative_y_when_target_is_below(stage: Any) -> None:
    """目标在手的下方（屏幕 y 变大）：左摇杆 y 是负数。手在 (0.5, 0.3)，目标在下面 0.2 个画面高（1.8 格）：y 是 -0.45。"""
    watch_hand(stage, [(0.5, 0.3), (0.5, 0.5)])
    move(stage, "free", False, around(0.5, 0.5))
    stick = next(entry for entry in stage.log if entry[0] == "stick")
    assert stick[2] == pytest.approx(0.0, abs=0.002)
    assert stick[3] == pytest.approx(-0.45, abs=0.002)


def test_move_hand_pushes_diagonally_with_same_total_strength(stage: Any) -> None:
    """斜着推：手在 (0.3, 0.3)，目标在右下，距离超过 4 格：总的推力是满的，方向按两边的差比例分：
    差 (0.3, 0.3) 按 16:9 算是 (4.8, 2.7)，x = 4.8/5.507 = 0.8716，y = -2.7/5.507 = -0.4903。
    """
    watch_hand(stage, [(0.3, 0.3), (0.6, 0.6)])
    move(stage, "free", False, around(0.6, 0.6))
    stick = next(entry for entry in stage.log if entry[0] == "stick")
    assert stick[2] == pytest.approx(0.8716, abs=0.002)
    assert stick[3] == pytest.approx(-0.4903, abs=0.002)


def test_move_hand_pushes_for_160_milliseconds_each_time(stage: Any) -> None:
    """每次推摇杆推 0.16 秒，一直推到手到了目标框里：手先后在 (0.2, 0.5)、(0.4, 0.5)、(0.6, 0.5)，推了 2 次。"""
    watch_hand(stage, [(0.2, 0.5), (0.4, 0.5), (0.6, 0.5)])
    move(stage, "free", False, around(0.6, 0.5))
    sticks = [entry for entry in stage.log if entry[0] == "stick"]
    assert len(sticks) == 2
    assert all(entry[4] == 0.16 for entry in sticks)


def test_move_hand_arrives_when_hand_center_is_inside_target_box_and_does_not_push(
    stage: Any,
) -> None:
    """手的中心离目标中心在两个方向上都小于目标框宽高的一半：算到了，不推摇杆，直接返回。"""
    watch_hand(stage, [(0.61, 0.51)])
    move(stage, "free", False, around(0.6, 0.5))
    assert [entry for entry in stage.log if entry[0] == "stick"] == []


def test_move_hand_keeps_pushing_when_hand_is_just_outside_target_box(stage: Any) -> None:
    """手的中心离目标中心的横向距离超过目标框宽的一半（0.03）：还没到，要推；这里手在目标左边 0.05。"""
    watch_hand(stage, [(0.55, 0.5), (0.6, 0.5)])
    move(stage, "free", False, around(0.6, 0.5))
    assert len([entry for entry in stage.log if entry[0] == "stick"]) == 1


def test_move_hand_returns_hand_box_around_final_position(stage: Any) -> None:
    """返回手最后所在的框：以手的中心为中心，宽 0.071、高 0.106（上游 hand_location_to_box）。"""
    watch_hand(stage, [(0.61, 0.51)])
    box = move(stage, "free", False, around(0.6, 0.5))
    assert flat(box) == pytest.approx((0.61 - 0.0355, 0.51 - 0.053, 0.61 + 0.0355, 0.51 + 0.053))


def test_move_hand_searches_first_in_start_box_then_in_expanded_box_around_last_position(
    stage: Any,
) -> None:
    """找手的范围：第一次在传进来的起点框里找；之后在上次手所在的框往外扩的范围里找（上游 expand_box：
    左上角往外扩 1.5 倍框的宽高，宽高变成 4 倍）。手在 (0.5, 0.5) 时扩出来的是 (0.358, 0.288) 到 (0.642, 0.712)。
    """
    asked = watch_hand(stage, [(0.5, 0.5), (0.9, 0.9)])
    move(stage, "free", False, around(0.9, 0.9))
    assert asked[0] == ("free", START)
    assert flat(asked[1][1]) == pytest.approx((0.358, 0.288, 0.642, 0.712))


def test_move_hand_holds_a_while_moving_when_pressing_a(stage: Any) -> None:
    """抓着东西移动（pressing_a）：先按住 A，到了目标之后松开 A；推摇杆都在按住 A 的期间。"""
    watch_hand(stage, [(0.2, 0.5), (0.6, 0.5)])
    move(stage, "grabbing", True, around(0.6, 0.5))
    kinds = [entry[0] for entry in stage.log]
    assert stage.log[0] == ("press", "A")
    assert stage.log[-1] == ("release", "A")
    assert "stick" in kinds[1:-1]


def test_move_hand_does_not_press_a_when_not_pressing_a(stage: Any) -> None:
    """空手移动（不按 A）：没有按住过 A。"""
    watch_hand(stage, [(0.2, 0.5), (0.6, 0.5)])
    move(stage, "free", False, around(0.6, 0.5))
    assert ("press", "A") not in stage.log


def test_move_hand_recovers_by_moving_to_screen_corner_when_hand_not_found_for_five_seconds(
    stage: Any,
) -> None:
    """找不到手（5 秒内）：手可能在屏幕边上。空手时左摇杆往右下推 4 秒，再往左推 0.8 秒，
    然后在整个屏幕里找手，找到了就接着移动。手在 6 秒后才出现。
    """
    start = stage.clock.now
    asked: list[tuple[str, Rect]] = []

    def find_hand(image: Any, kind: str, area: Rect, *args: Any, **kwargs: Any) -> Any:
        asked.append((kind, area))
        return (0.6, 0.5) if stage.clock.now >= start + 6 else None

    screens = importlib.import_module("control_switch.games.sv.egg.screens")
    stage.replace(screens, "find_hand", find_hand)
    move(stage, "free", False, around(0.6, 0.5))
    sticks = [entry[1:] for entry in stage.log if entry[0] == "stick"]
    assert sticks == [("LEFT", 1.0, -1.0, 4.0), ("LEFT", -1.0, 0.0, 0.8)]
    assert ("free", ((0.0, 0.0), (1.0, 1.0))) in asked


def test_move_hand_does_not_recover_when_hand_shows_up_within_five_seconds(stage: Any) -> None:
    """手 3 秒后出现（不到 5 秒）：不用恢复，没有往角落推过摇杆。"""
    start = stage.clock.now
    screens = importlib.import_module("control_switch.games.sv.egg.screens")

    def find_hand(image: Any, kind: str, area: Rect, *args: Any, **kwargs: Any) -> Any:
        return (0.6, 0.5) if stage.clock.now >= start + 3 else None

    stage.replace(screens, "find_hand", find_hand)
    move(stage, "free", False, around(0.6, 0.5))
    assert [entry for entry in stage.log if entry[0] == "stick"] == []


def test_move_hand_recovers_while_holding_a_when_grabbing(stage: Any) -> None:
    """抓着东西时找不到手：恢复时也一直按着 A（不然东西会掉）：往右下、往左的两次推摇杆都在按住 A 和松开 A 之间。"""
    start = stage.clock.now
    screens = importlib.import_module("control_switch.games.sv.egg.screens")

    def find_hand(image: Any, kind: str, area: Rect, *args: Any, **kwargs: Any) -> Any:
        return (0.6, 0.5) if stage.clock.now >= start + 6 else None

    stage.replace(screens, "find_hand", find_hand)
    move(stage, "grabbing", True, around(0.6, 0.5))
    first = stage.log.index(("press", "A"))
    last = len(stage.log) - 1 - stage.log[::-1].index(("release", "A"))
    sticks = [
        index
        for index, entry in enumerate(stage.log)
        if entry[0] == "stick" and entry[4] in (4.0, 0.8)
    ]
    assert len(sticks) == 2
    assert all(first < index < last for index in sticks)


def test_move_hand_raises_runtime_error_when_hand_is_not_found_after_recovery(
    stage: Any,
) -> None:
    """恢复之后在整个屏幕里还是找不到手：抛 RuntimeError，报错里有「手」。"""
    watch_hand(stage, [None])
    with pytest.raises(RuntimeError, match="手"):
        move(stage, "free", False, around(0.6, 0.5))


def test_move_hand_releases_a_when_it_raises(stage: Any) -> None:
    """抓着东西、找不到手而报错：A 也要松开（不能一直按着）。"""
    watch_hand(stage, [None])
    with pytest.raises(RuntimeError):
        move(stage, "grabbing", True, around(0.6, 0.5))
    assert stage.log[-1] == ("release", "A")
