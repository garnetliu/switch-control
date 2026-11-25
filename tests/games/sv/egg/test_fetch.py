"""steps.fetch：开野餐、做三明治、走到篮子、查篮子、收野餐、飞回闸口、换成孵蛋队伍，返回 "hatch"。

这个文件测 fetch 本身的顺序，和上游 EggRoutines 里走路的那几段（开野餐前的走位、走到篮子的路线）、
吃完三明治。查篮子在 test_basket.py，进食谱、选食谱、移动手在 test_sandwich.py。

走路、转向这些推摇杆的动作看不了画面，用上游的时间：
stage.log 里的 ("stick", 边, x, y, 秒) 就是上游 pbf_move_left_joystick 的方向和时间（x、y 满推是 1.0）。
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

box_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.box")
fly_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.fly")
actions_module: ModuleType = importlib.import_module("control_switch.games.sv.actions")
fetch_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.steps.fetch")
fetch = fetch_module.fetch


@pytest.fixture
def parts(stage: Any) -> Any:
    """fetch 用到的小函数和 box、fly、actions 里的操作都换成假函数；做三明治成功，收到 30 个蛋，换队伍后队伍里有 5 个蛋。"""
    stage.stub(fetch_module, "_picnic_at_zero_gate")
    stage.stub(fetch_module, "_eat_egg_sandwich", True)
    stage.stub(fetch_module, "_collect_eggs_after_sandwich", 30)
    stage.stub(actions_module, "close_picnic")
    stage.stub(fly_module, "fly_to_gate")
    stage.stub(box_module, "to_hatch_party", 5)
    return stage


def test_fetch_runs_picnic_sandwich_basket_leave_fly_and_party_change_in_order(parts: Any) -> None:
    """正常走完：在零区闸口开野餐、做三明治、走到篮子收蛋、收野餐、飞回闸口、换成孵蛋队伍，按这个顺序。"""
    fetch(parts.sw)
    assert parts.log == [
        ("_picnic_at_zero_gate",),
        ("_eat_egg_sandwich",),
        ("_collect_eggs_after_sandwich",),
        ("close_picnic",),
        ("fly_to_gate",),
        ("to_hatch_party",),
    ]


def test_fetch_returns_hatch_and_records_number_of_eggs_in_party(parts: Any) -> None:
    """正常走完：返回 "hatch"，sw.eggs_in_party 是换队伍时数到的蛋数（5）。"""
    assert fetch(parts.sw) == "hatch"
    assert parts.sw.eggs_in_party == 5


def test_fetch_raises_runtime_error_when_sandwich_cannot_be_made(parts: Any) -> None:
    """没有食谱或者材料不够（做三明治返回 False）：抛 RuntimeError，报错里有「三明治」，后面的收野餐、换队伍都没做。"""
    parts.stub(fetch_module, "_eat_egg_sandwich", False)
    with pytest.raises(RuntimeError, match="三明治"):
        fetch(parts.sw)
    assert parts.log == [("_picnic_at_zero_gate",), ("_eat_egg_sandwich",)]


def test_picnic_at_zero_gate_turns_camera_walks_away_from_station_then_opens_picnic(
    stage: Any,
) -> None:
    """开野餐前的走位（上游 picnic_at_zero_gate）：按 L 把镜头转到人面对的方向，左摇杆往右前方推 0.4 秒让人背对观测站，
    按 L，往前走 1 秒，再开野餐。
    """
    stage.stub(actions_module, "open_picnic")
    fetch_module._picnic_at_zero_gate(stage.sw)
    assert stage.log == [
        ("click", "L"),
        ("stick", "LEFT", 1.0, 0.75, 0.4),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 1.0),
        ("open_picnic",),
    ]


def test_walk_to_basket_follows_upstream_route(stage: Any) -> None:
    """走到篮子前（上游 collect_eggs_after_sandwich 里镜头辅助开关都能用的那一段）：按 PLUS 收起坐骑，
    往前、往左、往前过桌子、往右、往前、转向篮子、往前靠近、后退再往前，中间按 L 转镜头。方向和时间照上游。
    """
    fetch_module._walk_to_basket(stage.sw)
    assert stage.log == [
        ("click", "PLUS"),
        ("stick", "LEFT", 0.0, 1.0, 0.32),
        ("stick", "LEFT", -1.0, 0.0, 0.08),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 0.32),
        ("stick", "LEFT", 1.0, 0.0, 0.08),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 0.64),
        ("stick", "LEFT", 1.0, 0.0, 0.08),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 0.32),
        ("stick", "LEFT", 1.0, 0.0, 0.08),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 0.8),
        ("stick", "LEFT", 0.0, -1.0, 0.2),
        ("stick", "LEFT", 0.0, 1.0, 0.08),
        ("click", "L"),
    ]


@pytest.fixture
def sandwich_parts(stage: Any) -> Any:
    """_eat_egg_sandwich 用到的小函数都换成假函数：进食谱列表、选食谱、做三明治都成功。"""
    stage.stub(fetch_module, "_clear_mons_in_front")
    stage.stub(fetch_module, "_enter_sandwich_recipe_list", True)
    stage.stub(fetch_module, "_select_sandwich_recipe", True)
    stage.stub(fetch_module, "_run_sandwich_maker")
    return stage


def test_eat_egg_sandwich_walks_to_table_clears_mons_enters_list_selects_recipe_17_and_makes_it(
    sandwich_parts: Any,
) -> None:
    """做三明治成功：往前走 0.24 秒到桌子前，等前面的宝可梦让开，进食谱列表，选食谱 17，做三明治，返回 True。"""
    assert fetch_module._eat_egg_sandwich(sandwich_parts.sw) is True
    assert sandwich_parts.log == [
        ("stick", "LEFT", 0.0, 1.0, 0.24),
        ("_clear_mons_in_front",),
        ("_enter_sandwich_recipe_list",),
        ("_select_sandwich_recipe", 17),
        ("_run_sandwich_maker",),
    ]


def test_eat_egg_sandwich_returns_false_when_no_ingredients_for_recipe_list(
    sandwich_parts: Any,
) -> None:
    """进不了食谱列表（没材料，菜单后面出了对话）：返回 False，没选食谱也没做三明治。"""
    sandwich_parts.stub(fetch_module, "_enter_sandwich_recipe_list", False)
    assert fetch_module._eat_egg_sandwich(sandwich_parts.sw) is False
    assert ("_select_sandwich_recipe", 17) not in sandwich_parts.log
    assert ("_run_sandwich_maker",) not in sandwich_parts.log


def test_eat_egg_sandwich_returns_false_when_recipe_is_missing(sandwich_parts: Any) -> None:
    """食谱 17 不在列表里（没解锁或者材料不够）：返回 False，没做三明治。"""
    sandwich_parts.stub(fetch_module, "_select_sandwich_recipe", False)
    assert fetch_module._eat_egg_sandwich(sandwich_parts.sw) is False
    assert ("_run_sandwich_maker",) not in sandwich_parts.log


def test_finish_sandwich_eating_presses_a_until_picnic_appears(stage: Any) -> None:
    """吃完三明治（上游 finish_sandwich_eating）：一直按 A，直到回到野餐的画面，之后不再按。"""
    start = stage.clock.now
    stage.set_screens(is_picnic=lambda: stage.clock.now >= start + 10)
    fetch_module._finish_sandwich_eating(stage.sw)
    assert stage.clicks()
    assert set(stage.clicks()) == {"A"}
    assert len(stage.clicks()) <= 5


def test_finish_sandwich_eating_raises_timeout_error_when_picnic_never_appears(
    stage: Any,
) -> None:
    """吃完三明治：一直回不到野餐的画面：抛 TimeoutError，等了至少 60 秒，按的都是 A。"""
    start = stage.clock.now
    stage.set_screens(is_picnic=lambda: False)
    with pytest.raises(TimeoutError):
        fetch_module._finish_sandwich_eating(stage.sw)
    assert stage.clock.now - start >= 60
    assert set(stage.clicks()) == {"A"}
