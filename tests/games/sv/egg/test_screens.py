"""control_switch.games.sv.egg.screens：孵蛋用的画面判断，用 tests/images/sv/egg/ 里的 1080p 真机截图测。

函数只看传进来的 ImageChecker，不按键、不截图。
没有合适截图、这里没测的：has_a_hint（要有野餐中宝可梦站在跟前的截图）、find_hand 和
is_plate_label_yellow（要有做三明治时手和盘子标签的截图）、panel_stats、panel_name、box_title
（只是读文字，不是判断）。
"""

from pathlib import Path
from typing import Any

import pytest

from control_switch.games.sv.egg import screens
from control_switch.vision import ImageChecker

IMAGE_DIR = Path(__file__).resolve().parents[3] / "images" / "sv" / "egg"
_cache: dict[str, ImageChecker] = {}


def load(name: str) -> ImageChecker:
    """读真机截图，同一张图只解码一次。"""
    if name not in _cache:
        _cache[name] = ImageChecker((IMAGE_DIR / name).read_bytes())
    return _cache[name]


def test_recipe_list_screen_reads_numbers_and_selected_cell() -> None:
    """食谱-17.jpg：食谱列表的画面，6 格的编号是 15、16、17、18、20、21，选中的是第 2 格（17）。"""
    image = load("食谱-17.jpg")
    assert screens.is_recipe_list(image) is True
    assert screens.recipe_numbers(image) == [15, 16, 17, 18, 20, 21]
    assert screens.selected_recipe_cell(image) == 2


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg", "桌子菜单.jpg", "选三明治签.jpg"])
def test_recipe_list_is_false_and_no_selection_off_the_recipe_list(name: str) -> None:
    """野外、野餐、桌子菜单、选签子的画面：不是食谱列表，没有选中的格子（-1）。"""
    image = load(name)
    assert screens.is_recipe_list(image) is False
    assert screens.selected_recipe_cell(image) == -1


def test_table_menu_arrow_true_on_table_menu() -> None:
    """is_table_menu_arrow：桌子菜单.jpg（选中第一项「做料理」）是 True。"""
    assert screens.is_table_menu_arrow(load("桌子菜单.jpg")) is True


@pytest.mark.parametrize("name", ["野餐.jpg", "野外.jpg", "食谱-17.jpg"])
def test_table_menu_arrow_false_elsewhere(name: str) -> None:
    """is_table_menu_arrow：野餐、野外、食谱的画面是 False。"""
    assert screens.is_table_menu_arrow(load(name)) is False


def test_pick_arrow_true_on_skewer_pick_screen() -> None:
    """is_pick_arrow：选三明治签子的界面是 True。"""
    assert screens.is_pick_arrow(load("选三明治签.jpg")) is True


@pytest.mark.parametrize("name", ["食谱-17.jpg", "野餐.jpg", "桌子菜单.jpg", "三明治效果.jpg"])
def test_pick_arrow_false_elsewhere(name: str) -> None:
    """is_pick_arrow：食谱、野餐、桌子菜单、做三明治的画面是 False。"""
    assert screens.is_pick_arrow(load(name)) is False


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-打开.jpg", ("slots", 0, 0)),
        ("盒子-拿着蛋.jpg", ("slots", 1, 0)),
        ("盒子-空格.jpg", ("slots", 3, 0)),
        ("盒子-爱吃豚-3V.jpg", ("party", 3, 0)),
        ("盒子-爱吃豚-4V.jpg", ("party", 5, 0)),
        ("盒子-百变怪-6V.jpg", ("party", 1, 0)),
    ],
)
def test_box_cursor_finds_cursor_on_1080p_screenshots(name: str, expected: tuple[Any, ...]) -> None:
    """box_cursor：1080p 真机截图上认出光标所在的格子，队伍是 ("party", 行, 0)，盒子是 ("slots", 行, 列)
    （采集卡是 1080p，要能用）。
    """
    assert screens.box_cursor(load(name)) == expected


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg"])
def test_box_cursor_is_none_when_not_in_box(name: str) -> None:
    """box_cursor：不是盒子的画面返回 None。"""
    assert screens.box_cursor(load(name)) is None


@pytest.mark.parametrize(
    "name",
    [
        "盒子-21-蛋和宝可梦.jpg",
        "盒子-22-蛋和宝可梦.jpg",
        "盒子-23-两个蛋.jpg",
        "盒子-打开.jpg",
        "盒子-拿着蛋.jpg",
        "盒子-爱吃豚-3V.jpg",
        "盒子-百变怪-6V.jpg",
    ],
)
def test_panel_present_true_when_cursor_is_on_a_pokemon(name: str) -> None:
    """panel_present：光标在有宝可梦（或蛋）的格子上，右边有面板（顶上的名字栏是黄色），是 True。"""
    assert screens.panel_present(load(name)) is True


@pytest.mark.parametrize("name", ["盒子-空格.jpg", "野外.jpg", "野餐.jpg"])
def test_panel_present_false_on_empty_slot_or_off_the_box(name: str) -> None:
    """panel_present：光标在空格上（没有面板）、不是盒子的画面是 False。"""
    assert screens.panel_present(load(name)) is False


def test_panel_shiny_true_on_shiny_panel() -> None:
    """panel_shiny：盒子-22-蛋和宝可梦.jpg 右边面板有闪光的星星，是 True。"""
    assert screens.panel_shiny(load("盒子-22-蛋和宝可梦.jpg")) is True


@pytest.mark.parametrize(
    "name",
    [
        "盒子-21-蛋和宝可梦.jpg",
        "盒子-23-两个蛋.jpg",
        "盒子-打开.jpg",
        "盒子-爱吃豚-3V.jpg",
        "盒子-爱吃豚-4V.jpg",
        "盒子-百变怪-6V.jpg",
    ],
)
def test_panel_shiny_false_on_non_shiny_panels(name: str) -> None:
    """panel_shiny：不是闪光的面板是 False。"""
    assert screens.panel_shiny(load(name)) is False


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-百变怪-6V.jpg", ["mon", "mon", "mon", "egg", "egg", "empty"]),
        ("盒子-21-蛋和宝可梦.jpg", ["mon", "mon", "mon", "empty", "empty", "empty"]),
    ],
)
def test_party_slot_tells_mon_egg_and_empty(name: str, expected: list[str]) -> None:
    """party_slot：队伍 6 行里每一行是什么："mon"（宝可梦）、"egg"（蛋）、"empty"（空格）。"""
    image = load(name)
    assert [screens.party_slot(image, row) for row in range(6)] == expected


def test_operation_row_reads_selected_release() -> None:
    """operation_row：盒子里按 A 出来的操作菜单（移动、查看能力、携带持有物、标记、放生、取消），
    盒子-菜单选中放生.jpg 选中的是第 4 行（放生）。
    """
    assert screens.operation_row(load("盒子-菜单选中放生.jpg")) == 4


def test_operation_row_reads_selected_move() -> None:
    """operation_row：盒子-操作菜单.jpg 选中的是第 0 行（移动）。"""
    assert screens.operation_row(load("盒子-操作菜单.jpg")) == 0


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg"])
def test_operation_row_is_minus_1_without_operation_menu(name: str) -> None:
    """operation_row：没有操作菜单的画面返回 -1。"""
    assert screens.operation_row(load(name)) == -1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-操作菜单.jpg", False),
        ("盒子-拿着蛋.jpg", True),
        ("盒子-打开.jpg", False),
        ("盒子-爱吃豚-3V.jpg", False),
    ],
)
def test_is_box_selecting_follows_bottom_bar(name: str, expected: bool) -> None:
    """is_box_selecting：选择模式（拿着东西）时底栏中间的按键提示没了，只剩右边的「返回」：
    盒子-拿着蛋.jpg 是 True，正常浏览的盒子画面是 False。
    """
    assert screens.is_box_selecting(load(name)) is expected
