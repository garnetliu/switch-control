"""control_switch.games.swsh.pokemon：Pokemon、Move、Match。

宝可梦用 src/control_switch/games/swsh/data/ 里真实的 rhydon（钻角犀兽，65 级，努力值全 0，性格系数全 1）。
期望值取自搬迁前 swsh.pokemon 的运行结果。
"""

from collections.abc import Callable
from dataclasses import replace

from control_switch.games.swsh.pokemon import LANGUAGE, Match, Pokemon

MonFactory = Callable[[str], Pokemon]


def test_language_default_is_simplified_chinese() -> None:
    """LANGUAGE 是 zh-Hans。"""
    assert LANGUAGE == "zh-Hans"


def test_pokemon_individual_values_are_fixed_to_31(mon: MonFactory) -> None:
    """pokemon_object 取出的宝可梦个体值全是 31，不是 json 里的 15。"""
    assert mon("rhydon").ivs == (31, 31, 31, 31, 31, 31)


def test_pokemon_stats_from_level_ivs_evs_and_nature(mon: MonFactory) -> None:
    """Pokemon.stats：rhydon 的能力值是 HP 231、攻击 194、防御 181、特攻 83、特防 83、速度 77。"""
    assert mon("rhydon").stats == (231, 194, 181, 83, 83, 77)


def test_pokemon_stats_for_another_species(mon: MonFactory) -> None:
    """Pokemon.stats：glalie（65 级）的六项能力值是 199、129、129、129、129、129。"""
    assert mon("glalie").stats == (199, 129, 129, 129, 129, 129)


def test_pokemon_pp_defaults_to_each_move_pp(mon: MonFactory) -> None:
    """Pokemon.pp：不传时等于各招式的 PP。"""
    pokemon = mon("rhydon")
    assert pokemon.pp == [10, 15, 10, 10]
    assert pokemon.pp == [move.pp for move in pokemon.moves]


def test_pokemon_replace_copies_pp_list(mon: MonFactory) -> None:
    """dataclasses.replace 复制宝可梦后，改副本的 PP 不影响原来的。"""
    original = mon("rhydon")
    copy = replace(original)
    copy.pp[0] -= 3
    assert copy.pp == [7, 15, 10, 10]
    assert original.pp == [10, 15, 10, 10]


def test_pokemon_explicit_pp_is_kept_but_copied(mon: MonFactory) -> None:
    """Pokemon.pp：传了就用传的值（复制一份），改传进去的列表不影响宝可梦。"""
    pp = [1, 2, 3, 4]
    pokemon = replace(mon("rhydon"), pp=pp)
    pp[0] = 99
    assert pokemon.pp == [1, 2, 3, 4]


def test_pokemon_name_in_known_language(mon: MonFactory) -> None:
    """Pokemon.name：默认语言返回中文名，指定 en 返回英文名。"""
    pokemon = mon("rhydon")
    assert pokemon.name() == "钻角犀兽"
    assert pokemon.name("en") == "Rhydon"


def test_pokemon_name_in_unknown_language_returns_name_id(mon: MonFactory) -> None:
    """Pokemon.name：没有这种语言的名字时返回 name_id。"""
    assert mon("rhydon").name("xx") == "rhydon"


def test_pokemon_ability_in_known_language(mon: MonFactory) -> None:
    """Pokemon.ability：默认语言返回中文特性名，指定 en 返回英文名。"""
    pokemon = mon("rhydon")
    assert pokemon.ability() == "坚硬脑袋"
    assert pokemon.ability("en") == "Rock Head"


def test_pokemon_ability_in_unknown_language_returns_ability_name_id(mon: MonFactory) -> None:
    """Pokemon.ability：没有这种语言的名字时返回 ability_name_id。"""
    assert mon("rhydon").ability("xx") == "rock-head"


def test_move_power_applies_correction_factor(mon: MonFactory) -> None:
    """Move.power：威力乘修正系数，ivysaur 的 solar-beam 是 120 乘 0.5。"""
    move = next(move for move in mon("ivysaur").moves if move.name_id == "solar-beam")
    assert (move.base_power, move.correction_factor) == (120, 0.5)
    assert move.power == 60.0


def test_move_power_without_correction_equals_base_power(mon: MonFactory) -> None:
    """Move.power：修正系数是 1 时等于基础威力，rhydon 的 drill-run 是 80。"""
    move = mon("rhydon").moves[0]
    assert move.name_id == "drill-run"
    assert move.power == 80.0


def test_move_name_in_known_language(mon: MonFactory) -> None:
    """Move.name：默认语言返回中文招式名，指定 en 返回英文名。"""
    move = mon("rhydon").moves[0]
    assert move.name() == "直冲钻"
    assert move.name("en") == "Drill Run"


def test_move_name_in_unknown_language_returns_name_id(mon: MonFactory) -> None:
    """Move.name：没有这种语言的名字时返回 name_id。"""
    assert mon("rhydon").moves[0].name("xx") == "drill-run"


def test_match_is_poor_when_distance_equals_third_of_length_is_false(mon: MonFactory) -> None:
    """Match.is_poor：6 个字、编辑距离 2（刚好等于三分之一）不算匹配得差。"""
    assert Match(mon("rhydon"), 2, "钻角犀兽钻角").is_poor is False


def test_match_is_poor_when_distance_exceeds_third_of_length(mon: MonFactory) -> None:
    """Match.is_poor：6 个字、编辑距离 3（超过三分之一）算匹配得差。"""
    assert Match(mon("rhydon"), 3, "钻角犀兽钻角").is_poor is True


def test_match_is_poor_with_exact_match_is_false(mon: MonFactory) -> None:
    """Match.is_poor：编辑距离 0 不算差。"""
    assert Match(mon("rhydon"), 0, "钻角犀兽").is_poor is False
