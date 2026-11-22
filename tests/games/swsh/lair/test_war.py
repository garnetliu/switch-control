"""control_switch.games.swsh.lair.war：一场对战里的场上状态。

宝可梦用 data/swsh/ 里真实的数据：自己 rhydon，对手 tapu-lele，队友 starmie、scyther、chansey。
期望值取自搬迁前 swsh.lair.war 的运行结果。
"""

from collections.abc import Callable

import pytest

from control_switch.games.swsh import scoring
from control_switch.games.swsh.field import Field
from control_switch.games.swsh.lair.war import War
from control_switch.games.swsh.pokemon import Pokemon

MonFactory = Callable[[str], Pokemon]


@pytest.fixture
def mates(mon: MonFactory) -> list[Pokemon]:
    """三个队友。"""
    return [mon("starmie"), mon("scyther"), mon("chansey")]


@pytest.fixture
def war(mon: MonFactory, mates: list[Pokemon]) -> War:
    """rhydon 对 tapu-lele，带三个队友，这场还没极巨化。"""
    return War(own=mon("rhydon"), opponent=mon("tapu-lele"), teammates=mates)


def test_war_is_a_field_with_clear_weather_and_terrain(war: War) -> None:
    """War 继承 Field：默认晴朗、无场地，打分函数能把它当 Field 用；这场没极巨化、没倒下。"""
    assert isinstance(war, Field)
    assert (war.weather, war.terrain) == ("clear", "clear")
    assert (war.dynamax_turns, war.faints) == (-1, 0)
    assert war.max_move_rate == scoring.MAX_MOVE_PROBABILITY


def test_own_ditto_transforms_into_opponent_on_entry(mon: MonFactory) -> None:
    """自己是百变怪：一上场就变成对手，名字还是 ditto，招式和对手的一样。"""
    opponent = mon("tapu-lele")
    war = War(own=mon("ditto"), opponent=opponent)
    assert war.own.name_id == "ditto"
    assert war.own.moves == opponent.moves[:4]
    assert war.own.base_stats == (48, 85, 75, 130, 115, 95)
    assert war.opponent.name_id == "tapu-lele"


def test_opponent_ditto_transforms_into_own_on_entry(mon: MonFactory) -> None:
    """对手是百变怪：一上场就变成自己，名字还是 ditto，招式和自己的一样。"""
    own = mon("rhydon")
    war = War(own=own, opponent=mon("ditto"))
    assert war.opponent.name_id == "ditto"
    assert war.opponent.moves == own.moves[:4]
    assert war.own.name_id == "rhydon"


def test_both_ditto_only_own_transforms(mon: MonFactory) -> None:
    """双方都是百变怪：只有自己变成对手，对手保持原样。"""
    opponent = mon("ditto")
    war = War(own=mon("ditto"), opponent=opponent)
    assert war.own.moves == opponent.moves[:4]
    assert war.opponent is opponent


def test_dynamax_sets_flag_and_three_turns(war: War) -> None:
    """dynamax：自己极巨化，剩 3 回合。"""
    war.dynamax()
    assert war.own.dynamax is True
    assert war.dynamax_turns == 3


def test_dynamax_ends_at_third_start_turn(war: War) -> None:
    """dynamax 之后第 3 次 start_turn 时极巨化结束：前两次还在，第 3 次结束，剩余回合变成 0。"""
    war.dynamax()
    war.start_turn()
    assert (war.own.dynamax, war.dynamax_turns) == (True, 2)
    war.start_turn()
    assert (war.own.dynamax, war.dynamax_turns) == (True, 1)
    war.start_turn()
    assert (war.own.dynamax, war.dynamax_turns) == (False, 0)


def test_start_turn_without_dynamax_changes_nothing(war: War) -> None:
    """start_turn：没极巨化过时什么都不变，剩余回合还是 -1。"""
    war.start_turn()
    assert (war.own.dynamax, war.dynamax_turns) == (False, -1)


def test_start_turn_after_dynamax_ended_changes_nothing(war: War) -> None:
    """start_turn：极巨化结束之后（剩余回合 0）再调用，不变。"""
    war.dynamax()
    for _ in range(3):
        war.start_turn()
    war.start_turn()
    assert (war.own.dynamax, war.dynamax_turns) == (False, 0)


def test_faint_ends_dynamax(war: War) -> None:
    """faint：自己倒下，极巨化结束，剩余回合变成 0。"""
    war.dynamax()
    war.faint()
    assert (war.own.dynamax, war.dynamax_turns) == (False, 0)


def test_faint_without_dynamax_changes_nothing(war: War) -> None:
    """faint：没极巨化时倒下，剩余回合还是 -1（这场还没极巨化过）。"""
    war.faint()
    assert (war.own.dynamax, war.dynamax_turns) == (False, -1)


def test_use_move_spends_one_pp(war: War) -> None:
    """use_move：平时扣 1 点 PP，只扣用的那个招式。"""
    war.use_move(1)
    assert war.own.pp == [10, 14, 10, 10]


def test_use_move_against_pressure_spends_two_pp(mon: MonFactory) -> None:
    """use_move：对手特性是压迫感（absol）时扣 2 点 PP。"""
    opponent = mon("absol")
    assert opponent.ability_name_id == "pressure"
    war = War(own=mon("rhydon"), opponent=opponent)
    war.use_move(0)
    assert war.own.pp == [8, 15, 10, 10]


def test_best_move_without_dynamax_option(war: War) -> None:
    """best_move：画面上没有极巨化按钮时选 smart-strike（序号 2），不极巨化。"""
    index, score, dynamax = war.best_move(False, set())
    assert (index, dynamax) == (2, False)
    assert score == pytest.approx(2.9610590148829425)


def test_best_move_skips_blocked_moves(war: War) -> None:
    """best_move：不选 blocked 里的招式，序号 2 被封住时选序号 0。"""
    index, score, dynamax = war.best_move(False, {2})
    assert (index, dynamax) == (0, False)
    assert score == pytest.approx(2.6567529020779044)


def test_best_move_does_not_change_own_pp(war: War) -> None:
    """best_move：把 blocked 当成没 PP 只在算的时候，自己的 PP 不变。"""
    war.best_move(False, {0, 1, 2, 3})
    assert war.own.pp == [10, 15, 10, 10]


def test_best_move_with_all_moves_blocked_returns_default(war: War) -> None:
    """best_move：四个招式都被封住，返回序号 0、分数 -100，不极巨化。"""
    assert war.best_move(False, {0, 1, 2, 3}) == (0, -100.0, False)


def test_best_move_chooses_dynamax_when_possible_and_better(war: War) -> None:
    """best_move：能极巨化、这场没极巨化过、极巨化的分数更高时，返回要极巨化。"""
    index, score, dynamax = war.best_move(True, set())
    assert (index, dynamax) == (2, True)
    assert score == pytest.approx(4.577594516048346)


def test_best_move_does_not_dynamax_when_button_missing(war: War) -> None:
    """best_move：can_dynamax 为 False 时即使极巨化分数更高也不极巨化。"""
    assert war.best_move(False, set())[2] is False


def test_best_move_does_not_dynamax_when_already_dynamaxed_this_battle(war: War) -> None:
    """best_move：这场已经极巨化过（dynamax_turns 不是 -1）就不再考虑极巨化。"""
    war.dynamax_turns = 0
    index, score, dynamax = war.best_move(True, set())
    assert (index, dynamax) == (2, False)
    assert score == pytest.approx(2.9610590148829425)


def test_best_move_does_not_dynamax_when_not_better(mon: MonFactory) -> None:
    """best_move：极巨化的分数不比普通的高（pyukumuku 打 tapu-lele）时不极巨化。"""
    war = War(own=mon("pyukumuku"), opponent=mon("tapu-lele"))
    index, score, dynamax = war.best_move(True, set())
    assert (index, dynamax) == (2, False)
    assert score == pytest.approx(0.2686677002414139)


def test_best_move_passes_max_move_rate_to_select_best_move(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """best_move：max_move_rate 传到了 select_best_move：设成 0.9 时分数和直接用 0.9 算的一样，比默认的低。"""
    war = War(own=mon("rhydon"), opponent=mon("tapu-lele"), teammates=mates, max_move_rate=0.9)
    index, score, _ = war.best_move(False, set())
    direct = scoring.select_best_move(mon("rhydon"), mon("tapu-lele"), war, mates, 0.9)
    assert (index, score) == (direct[0], direct[2])
    assert score == pytest.approx(2.5754843371618708)


def test_best_move_does_not_modify_own_dynamax_flag(war: War) -> None:
    """best_move：试算极巨化只在复制品上，自己的 dynamax 不变。"""
    war.best_move(True, set())
    assert war.own.dynamax is False
