"""control_switch.games.registry：按「游戏/脚本」的名字找到脚本。"""

import pytest

from control_switch.games.registry import SCRIPTS, load_script
from control_switch.session import Session


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak"])
def test_load_script_returns_module_with_steps_and_start(name: str) -> None:
    """load_script：返回的模块有 STEPS、START，START 是 STEPS 里的一步。"""
    script = load_script(name)
    assert isinstance(script.STEPS, dict)
    assert script.START in script.STEPS


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak"])
def test_load_script_has_session_subclass_and_no_connect(name: str) -> None:
    """load_script：返回的模块有 SESSION，它是 Session 的子类（不是 Session 本身）；没有 connect。"""
    script = load_script(name)
    assert isinstance(script.SESSION, type)
    assert issubclass(script.SESSION, Session)
    assert script.SESSION is not Session
    assert not hasattr(script, "connect")


def test_scripts_table_has_both_game_scripts() -> None:
    """SCRIPTS 里有 swsh/lair 和 sv/outbreak 两个名字。"""
    assert set(SCRIPTS) == {"swsh/lair", "sv/outbreak"}


def test_swsh_lair_start_is_initialize_and_steps_are_callable() -> None:
    """swsh/lair 从 initialize 开始，每一步都是能调用的函数。"""
    script = load_script("swsh/lair")
    assert script.START == "initialize"
    assert set(script.STEPS) == {
        "initialize",
        "join",
        "path",
        "battle",
        "catch",
        "select_pokemon",
    }
    assert all(callable(step) for step in script.STEPS.values())


def test_load_script_unknown_name_exits_listing_available_names() -> None:
    """load_script：不认识的名字抛 SystemExit，报错里列出所有可以用的名字。"""
    with pytest.raises(SystemExit) as error:
        load_script("没有/这个")
    message = str(error.value)
    assert "没有/这个" in message
    assert "swsh/lair" in message
    assert "sv/outbreak" in message
