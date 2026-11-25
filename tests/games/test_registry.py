"""control_switch.games.registry：按「游戏/脚本」的名字找到脚本。"""

import pytest

from control_switch.games.registry import SCRIPTS, load_script
from control_switch.session import Session


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak", "sv/egg"])
def test_load_script_returns_module_with_steps_and_start(name: str) -> None:
    """load_script：返回的模块有 STEPS、START，START 是 STEPS 里的一步。"""
    script = load_script(name)
    assert isinstance(script.STEPS, dict)
    assert script.START in script.STEPS


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak", "sv/egg"])
def test_load_script_has_session_subclass_and_no_connect(name: str) -> None:
    """load_script：返回的模块有 SESSION，它是 Session 的子类（不是 Session 本身）；没有 connect。"""
    script = load_script(name)
    assert isinstance(script.SESSION, type)
    assert issubclass(script.SESSION, Session)
    assert script.SESSION is not Session
    assert not hasattr(script, "connect")


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak", "sv/egg"])
def test_load_script_requires_is_frozenset_of_known_devices(name: str) -> None:
    """load_script：返回的模块有 REQUIRES，是 frozenset，是 {"screen", "controller", "memory"} 的子集。"""
    requires = load_script(name).REQUIRES
    assert isinstance(requires, frozenset)
    assert requires <= {"screen", "controller", "memory"}


@pytest.mark.parametrize("name", ["swsh/lair", "sv/outbreak", "sv/egg"])
def test_load_script_has_non_empty_title_ids(name: str) -> None:
    """load_script：返回的模块有 TITLE_IDS，不为空。"""
    assert len(load_script(name).TITLE_IDS) > 0


def test_scripts_table_has_all_game_scripts() -> None:
    """SCRIPTS 里有 swsh/lair、sv/outbreak、sv/egg 三个名字。"""
    assert set(SCRIPTS) == {"swsh/lair", "sv/outbreak", "sv/egg"}


def test_sv_egg_loads_with_initialize_start_and_session_class() -> None:
    """sv/egg 能加载：START 是 initialize，SESSION 是 EggSession，TITLE_IDS 和 sv/outbreak 一样。"""
    script = load_script("sv/egg")
    assert script.START == "initialize"
    assert script.SESSION.__name__ == "EggSession"
    assert script.TITLE_IDS == load_script("sv/outbreak").TITLE_IDS


def test_sv_egg_requires_screen_and_controller_but_not_memory() -> None:
    """sv/egg 的 REQUIRES 正好是 {"screen", "controller"}，没有 memory。"""
    requires = load_script("sv/egg").REQUIRES
    assert requires == frozenset({"screen", "controller"})
    assert "memory" not in requires


def test_sv_egg_steps_are_the_three_documented_steps() -> None:
    """sv/egg 的 STEPS 正好是 initialize、fetch、hatch 三步（任务 14：旧的 8 步改成 3 步），每一步都能调用。"""
    script = load_script("sv/egg")
    assert set(script.STEPS) == {"initialize", "fetch", "hatch"}
    assert all(callable(step) for step in script.STEPS.values())


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
    assert "sv/egg" in message
