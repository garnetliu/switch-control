"""control_switch.games.sv.screens：几个脚本共用的画面判断，用 tests/images/sv/egg/ 里的 1080p 真机截图测。

函数只看传进来的 ImageChecker，不按键、不截图。
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from control_switch.games.sv import screens
from control_switch.games.sv.config import SvConfig
from control_switch.vision import ImageChecker

IMAGE_DIR = Path(__file__).resolve().parents[2] / "images" / "sv" / "egg"
_cache: dict[str, ImageChecker] = {}


def load(name: str) -> ImageChecker:
    """读真机截图，同一张图只解码一次。"""
    if name not in _cache:
        _cache[name] = ImageChecker((IMAGE_DIR / name).read_bytes())
    return _cache[name]


Predicate = Callable[[ImageChecker], bool]

OVERWORLD = [
    "野外.jpg",
    "野外-骑着.jpg",
    "野外-野餐结束后.jpg",
    "孵化后回到野外.jpg",
    "零区闸口.jpg",
]
BASKET_TALK = ["篮子-看了一看.jpg", "篮子-已领走蛋.jpg", "篮子-没有蛋.jpg", "篮子-还有蛋.jpg"]
NO_DIALOG = [
    "野外.jpg",
    "野餐.jpg",
    "孵化动画.jpg",
    "食谱-17.jpg",
    "选三明治签.jpg",
    "三明治效果.jpg",
]


def test_images_exist() -> None:
    """测试用的截图都在。"""
    assert (IMAGE_DIR / "野外.jpg").is_file()


@pytest.mark.parametrize("name", BASKET_TALK)
def test_is_dialog_true_on_dialog_with_advance_arrow(name: str) -> None:
    """is_dialog：篮子前的对话（右下角有翻页的小三角，按 A 或 B 往下翻）是 True。"""
    assert screens.is_dialog(load(name)) is True


@pytest.mark.parametrize("name", NO_DIALOG)
def test_is_dialog_false_without_dialog_box(name: str) -> None:
    """is_dialog：野外、野餐、孵化动画、食谱、做三明治的画面没有对话框，是 False。"""
    assert screens.is_dialog(load(name)) is False


@pytest.mark.parametrize(
    "name",
    [*BASKET_TALK, "孵化-哦.jpg", "桌子菜单.jpg", "结束野餐确认.jpg", "篮子-要领走蛋吗.jpg"],
)
def test_has_dialog_box_true_on_screens_with_dialog_box(name: str) -> None:
    """has_dialog_box：下方有对话框的画面（篮子、孵化、桌子菜单、选择框）是 True。"""
    assert screens.has_dialog_box(load(name)) is True


@pytest.mark.parametrize("name", NO_DIALOG)
def test_has_dialog_box_false_without_dialog_box(name: str) -> None:
    """has_dialog_box：没有对话框的画面是 False。"""
    assert screens.has_dialog_box(load(name)) is False


@pytest.mark.parametrize("name", ["篮子-要领走蛋吗.jpg", "结束野餐确认.jpg", "地图-飞翔确认.jpg"])
def test_is_prompt_true_on_choice_box(name: str) -> None:
    """is_prompt：对话框带「是 / 否」选择框（要领走蛋吗、结束野餐、飞翔确认）是 True。"""
    assert screens.is_prompt(load(name)) is True


@pytest.mark.parametrize("name", [*BASKET_TALK, "孵化-哦.jpg", "桌子菜单.jpg", *NO_DIALOG])
def test_is_prompt_false_without_choice_box(name: str) -> None:
    """is_prompt：普通对话、桌子菜单、没有对话框的画面是 False。"""
    assert screens.is_prompt(load(name)) is False


@pytest.mark.parametrize("name", OVERWORLD)
def test_is_overworld_true_on_overworld(name: str) -> None:
    """is_overworld：野外（站着、骑着、野餐结束后、孵化后、零区闸口）右下角有小地图，是 True。"""
    assert screens.is_overworld(load(name)) is True


@pytest.mark.parametrize(
    "name",
    [
        "野餐.jpg",
        "战斗菜单.jpg",
        "孵化动画.jpg",
        "选三明治签.jpg",
        "三明治效果.jpg",
        "食谱-17.jpg",
        "盒子-打开.jpg",
    ],
)
def test_is_overworld_false_off_the_field(name: str) -> None:
    """is_overworld：野餐、战斗、孵化动画、做三明治、食谱、盒子的画面是 False。"""
    assert screens.is_overworld(load(name)) is False


def test_is_picnic_true_on_picnic_screen() -> None:
    """is_picnic：野餐中没有对话的画面是 True。"""
    assert screens.is_picnic(load("野餐.jpg")) is True


@pytest.mark.parametrize("name", [*BASKET_TALK, *OVERWORLD, "选三明治签.jpg", "三明治效果.jpg"])
def test_is_picnic_false_with_dialog_or_off_picnic(name: str) -> None:
    """is_picnic：篮子的对话（野餐中但有对话框）、野外、做三明治的画面是 False。"""
    assert screens.is_picnic(load(name)) is False


def test_menu_row_reads_picnic_row() -> None:
    """menu_row：主菜单-野餐.jpg 光标在第 2 行。"""
    assert screens.menu_row(load("主菜单-野餐.jpg")) == 2


def test_menu_row_reads_box_row() -> None:
    """menu_row：主菜单-盒子-骑着.jpg 光标在第 1 行。"""
    assert screens.menu_row(load("主菜单-盒子-骑着.jpg")) == 1


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg", "盒子-打开.jpg"])
def test_menu_row_is_minus_1_when_not_main_menu(name: str) -> None:
    """menu_row：不是主菜单的画面返回 -1。"""
    assert screens.menu_row(load(name)) == -1


@pytest.mark.parametrize("name", ["主菜单-野餐.jpg", "主菜单-盒子-骑着.jpg"])
def test_is_main_menu_true_on_main_menu(name: str) -> None:
    """is_main_menu：主菜单（光标在右边某一行）是 True。"""
    assert screens.is_main_menu(load(name)) is True


@pytest.mark.parametrize("name", [*OVERWORLD, "野餐.jpg", "盒子-打开.jpg", "食谱-17.jpg"])
def test_is_main_menu_false_elsewhere(name: str) -> None:
    """is_main_menu：野外、野餐、盒子、食谱画面是 False。"""
    assert screens.is_main_menu(load(name)) is False


def test_gradient_arrow_true_on_choice_box_area() -> None:
    """gradient_arrow：选择框的区域（dialog.prompt_area）里有选中的渐变箭头：篮子-要领走蛋吗.jpg 是 True。"""
    area = SvConfig().dialog.prompt_area
    assert screens.gradient_arrow(load("篮子-要领走蛋吗.jpg"), area) is True


def test_gradient_arrow_false_on_dialog_without_choice_box() -> None:
    """gradient_arrow：只有普通对话、没有选择框的画面，选择框的区域里没有箭头，是 False。"""
    assert screens.gradient_arrow(load("篮子-还有蛋.jpg"), SvConfig().dialog.prompt_area) is False
