"""control_switch.games.swsh.field：天气和场地的提示文字。"""

import pytest

from control_switch.games.swsh.field import Field


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("脚下的青草消失了", "clear"),
        ("脚下出现了电光", "electric"),
        ("脚下长满了青草", "grassy"),
        ("脚下雾气弥漫", "misty"),
        ("脚下变得奇妙了", "psychic"),
    ],
)
def test_change_recognizes_each_terrain(text: str, value: str) -> None:
    """Field.change：每种场地的提示文字都得到 ("terrain", 对应的场地)。"""
    assert Field.change(text) == ("terrain", value)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("日照复原了", "clear"),
        ("雨停了", "clear"),
        ("沙暴停止了", "clear"),
        ("冰雹停止了", "clear"),
        ("日照变强了", "sunlight"),
        ("开始下雨了", "rain"),
        ("开始刮沙暴了", "sandstorm"),
        ("开始下冰雹了", "hail"),
    ],
)
def test_change_recognizes_each_weather(text: str, value: str) -> None:
    """Field.change：每种天气（包括四种天气结束的提示）都得到 ("weather", 对应的天气)。"""
    assert Field.change(text) == ("weather", value)


def test_change_terrain_clear_takes_priority_over_grass_keyword() -> None:
    """Field.change：「脚下的青草消失了」里也有「青草」，要得到 clear 而不是 grassy。"""
    assert Field.change("脚下的青草消失了") == ("terrain", "clear")


def test_change_unrelated_text_returns_none() -> None:
    """Field.change：和天气、场地无关的战斗文字返回 None。"""
    assert Field.change("夜暮林夕的沙铃仙人掌使出了") is None


def test_change_terrain_text_without_known_keyword_returns_none() -> None:
    """Field.change：带「脚下」但没有认识的场地关键字时返回 None，不会去看天气。"""
    assert Field.change("脚下有点晃，开始下雨了") is None


def test_update_changes_matching_attribute() -> None:
    """Field.update：是场地提示时只改 terrain，天气不动。"""
    field = Field(weather="rain")
    field.update("脚下长满了青草")
    assert (field.weather, field.terrain) == ("rain", "grassy")


def test_update_changes_weather_attribute() -> None:
    """Field.update：是天气提示时只改 weather，场地不动。"""
    field = Field(terrain="misty")
    field.update("开始刮沙暴了")
    assert (field.weather, field.terrain) == ("sandstorm", "misty")


def test_update_with_unrelated_text_keeps_field() -> None:
    """Field.update：不是提示时天气和场地都不变。"""
    field = Field(weather="hail", terrain="electric")
    field.update("使出了十万伏特")
    assert (field.weather, field.terrain) == ("hail", "electric")


def test_update_with_same_value_keeps_value() -> None:
    """Field.update：提示的值和现在一样时，值不变。"""
    field = Field(weather="rain")
    field.update("开始下雨了")
    assert field.weather == "rain"


def test_default_field_is_clear() -> None:
    """Field 默认晴朗、无场地。"""
    field = Field()
    assert (field.weather, field.terrain) == ("clear", "clear")
