"""control_switch.games.swsh.lair.upstream：选首发、路线、换不换、研究员换不换。

用 src/control_switch/games/swsh/data/ 里真实的数据和基准 seed 3076008315599927110（extra 为 0）。
首领是 tapu-lele，路线是 ((1, 0), (2, 1), (3, 2))，路上的事件手写在 EVENTS 里（不读 lair_event_LUT.json，
那个文件每跑一局就会变）。队伍是「选的首发 + 三个队友」：
  首发选界面第 0 只：pangoro、maractus、galvantula、cofagrigus
  首发选界面第 2 只：maractus、cofagrigus、galvantula、pangoro
期望值取自搬迁前 swsh.lair.upstream 的运行结果。
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from control_switch.games.swsh.lair import upstream
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.plan import Path as Route

BOSS = "tapu-lele"
ROUTE: Route = ((1, 0), (2, 1), (3, 2))
EVENTS = {
    "0-0>1-0": ["scientist"],
    "1-0>2-1": ["backpacker"],
    "2-1": ["berry"],
    "2-1>3-2": ["scientist", "backpacker"],
}
# 上面的事件排出来的先后：研究员、抓、背包客、抓、研究员、背包客、抓
WalkerFactory = Callable[..., upstream.Walker]
SCHEDULE = ["scientist", "catch", "backpacker", "catch", "scientist", "backpacker", "catch"]


def team_of(lair: Lair, starter: int) -> list[str]:
    """选了界面上第 starter 只之后的队伍：自己在第一个。"""
    return [lair.candidates()[starter], *lair.teammates(starter)]


@pytest.fixture(scope="module")
def scorer(fixed_data: GameData) -> upstream.Scorer:
    """首领是 tapu-lele 的 Scorer，算过的结果缓存着，整个文件共用。"""
    return upstream.Scorer(fixed_data, BOSS)


@pytest.fixture
def make_walker(lair0: Lair, fixed_data: GameData) -> WalkerFactory:
    """返回一个函数：按首发下标和事件建 Walker，每次都是从头开始的新的。"""

    def factory(starter: int = 0, events: dict[str, list[str]] | None = None) -> upstream.Walker:
        return upstream.Walker(
            lair0,
            fixed_data,
            BOSS,
            ROUTE,
            team_of(lair0, starter),
            EVENTS if events is None else events,
        )

    return factory


# ---- Scorer ----


def test_scorer_rentals_are_all_rental_pokemon(scorer: upstream.Scorer) -> None:
    """Scorer：rentals 是租借宝可梦的全部 226 只，boss 是传进去的首领。"""
    assert len(scorer.rentals) == 226
    assert scorer.boss == BOSS


def test_scorer_matchup_without_teammates(scorer: upstream.Scorer) -> None:
    """Scorer.matchup：rhydon 单独对 tapu-lele。"""
    assert scorer.matchup("rhydon", BOSS) == pytest.approx(15.608202790985501)


def test_scorer_matchup_with_teammates(scorer: upstream.Scorer) -> None:
    """Scorer.matchup：带三个具体的队友，分数比单独的低。"""
    result = scorer.matchup("rhydon", BOSS, ("starmie", "scyther", "chansey"))
    assert result == pytest.approx(3.980923155884079)


def test_scorer_matchup_ditto_attacker(scorer: upstream.Scorer) -> None:
    """Scorer.matchup：自己是百变怪时先变成对手。"""
    assert scorer.matchup("ditto", BOSS) == pytest.approx(14.081122383484857)


def test_scorer_matchup_ditto_defender(scorer: upstream.Scorer) -> None:
    """Scorer.matchup：对手是百变怪时，对手变成自己。"""
    assert scorer.matchup("rhydon", "ditto") == pytest.approx(22.33322141344429)


def test_scorer_matchup_is_cached(scorer: upstream.Scorer) -> None:
    """Scorer.matchup：同样的参数第二次算，直接用缓存里的值，结果一样。"""
    assert scorer.matchup("rhydon", BOSS) == scorer.matchup("rhydon", BOSS)


def test_scorer_average_matchup(scorer: upstream.Scorer) -> None:
    """Scorer.average_matchup：rhydon 对 tapu-lele，队友按全部租借宝可梦的平均。"""
    assert scorer.average_matchup("rhydon", BOSS) == pytest.approx(4.142522617426305)


def test_scorer_average_matchup_ditto_attacker(scorer: upstream.Scorer) -> None:
    """Scorer.average_matchup：自己是百变怪时先变成对手。"""
    assert scorer.average_matchup("ditto", BOSS) == pytest.approx(3.547680584776616)


def test_scorer_average_matchup_ditto_defender(scorer: upstream.Scorer) -> None:
    """Scorer.average_matchup：对手是百变怪时，对手变成自己。"""
    assert scorer.average_matchup("rhydon", "ditto") == pytest.approx(8.113624641188673)


def test_scorer_starter_score_is_average_matchup_against_boss(
    scorer: upstream.Scorer, lair0: Lair
) -> None:
    """Scorer.starter_score：选宝可梦界面三只的首发分，等于各自对首领的 average_matchup。"""
    scores = [scorer.starter_score(name) for name in lair0.candidates()[:3]]
    assert scores == pytest.approx([3.6403823807694753, 2.82147919829738, 3.081226759853311])
    assert scores[0] == scorer.average_matchup("pangoro", BOSS)


def test_scorer_route_score_weights_stages_one_two_three(scorer: upstream.Scorer) -> None:
    """Scorer.route_score：三关对手的分按 1、2、3 的权重加起来。"""
    assert scorer.route_score(["swoobat", "fraxure", "beartic"]) == pytest.approx(16.42741140417926)


def test_scorer_route_score_depends_on_order(scorer: upstream.Scorer) -> None:
    """Scorer.route_score：对手的顺序倒过来，分数不一样（权重不同）。"""
    assert scorer.route_score(["beartic", "fraxure", "swoobat"]) == pytest.approx(
        16.420495341790577
    )


def test_scorer_route_score_needs_exactly_three_opponents(scorer: upstream.Scorer) -> None:
    """Scorer.route_score：对手不是三个时抛 ValueError（zip 要求一样长）。"""
    with pytest.raises(ValueError):
        scorer.route_score(["swoobat", "fraxure"])


def test_scorer_team_score_counts_own_fully_and_teammates_half(scorer: upstream.Scorer) -> None:
    """Scorer.team_score：自己的相性算满，三个队友打五折。"""
    team = ["pangoro", "maractus", "galvantula", "cofagrigus"]
    assert scorer.team_score(team) == pytest.approx(8.585583058900703)
    expected = scorer.average_matchup("pangoro", BOSS) + 0.5 * sum(
        scorer.average_matchup(name, BOSS) for name in team[1:]
    )
    assert scorer.team_score(team) == pytest.approx(expected)


def test_scorer_team_score_changes_when_own_pokemon_changes(scorer: upstream.Scorer) -> None:
    """Scorer.team_score：换了自己那只（第一个），分数变。"""
    assert scorer.team_score(["glalie", "rhydon", "ditto", "starmie"]) == pytest.approx(
        8.54533599240588
    )


# ---- schedule_of ----


def test_schedule_of_lists_events_in_order_with_catch_before_each_node() -> None:
    """schedule_of：每个节点（起点除外）前面一次 catch，路上的事件按先后排，树果不算。"""
    assert upstream.schedule_of(ROUTE, EVENTS) == SCHEDULE


def test_schedule_of_without_events_is_three_catches() -> None:
    """schedule_of：路上没有事件时只有三次 catch。"""
    assert upstream.schedule_of(ROUTE, {}) == ["catch", "catch", "catch"]


def test_schedule_of_ignores_berry() -> None:
    """schedule_of：只有树果的路线，排出来还是三次 catch。"""
    assert upstream.schedule_of(ROUTE, {"2-1": ["berry"]}) == ["catch", "catch", "catch"]


def test_schedule_of_other_path_puts_events_at_their_positions() -> None:
    """schedule_of：另一条路线 ((1,1),(2,3),(3,3))，起点的背包客在最前面，最后一段路的研究员在最后。"""
    path: Route = ((1, 1), (2, 3), (3, 3))
    events = {"3-3>4-0": ["scientist"], "0-0": ["backpacker"]}
    assert upstream.schedule_of(path, events) == [
        "backpacker",
        "catch",
        "catch",
        "catch",
        "scientist",
    ]


# ---- Walker ----


def test_walker_initial_state(make_walker: WalkerFactory) -> None:
    """Walker：开始时路线上三关的对手、事件先后、队伍，还没抓到过。"""
    walker = make_walker()
    assert walker.opponents == ["swoobat", "tauros", "torkoal"]
    assert walker.schedule == SCHEDULE
    assert (walker.index, walker.caught) == (0, 0)
    assert walker.team == ["pangoro", "maractus", "galvantula", "cofagrigus"]


def test_walker_without_events_reads_table_for_map_type_and_layout(
    tmp_path: Path, lair0: Lair
) -> None:
    """Walker：events 不给时按 seed 算出的地图类型（2x2）和布局（4）取 lair_event_LUT.json 里的事件。

    用临时目录里一份写好的表，不读仓库里会变的那份。
    """
    directory = tmp_path / "swsh"
    shutil.copytree(GameConfig.data_dir, directory)
    table = {"2x2": {"4": {"0-0>1-0": ["backpacker"], "2-1>3-2": ["scientist"]}}}
    (directory / "lair_event_LUT.json").write_text(json.dumps(table), encoding="utf-8")

    class TmpConfig(GameConfig):
        data_dir = directory

    data = GameData(TmpConfig())
    walker = upstream.Walker(lair0, data, BOSS, ROUTE, team_of(lair0, 0))
    assert walker.schedule == ["backpacker", "catch", "catch", "scientist", "catch"]


def test_walker_copy_is_independent_of_original(make_walker: WalkerFactory) -> None:
    """Walker.copy：改副本的队伍、随机数、已用过的宝可梦、进度，原来的都不变。"""
    walker = make_walker()
    before = (walker.rng.s0, walker.rng.s1)
    used = set(walker.used)
    other = walker.copy()
    other.team[0] = "X"
    other.used.add((1, 1))
    other.rng.next_u32()
    other.catch(True)
    assert walker.team == ["pangoro", "maractus", "galvantula", "cofagrigus"]
    assert (walker.rng.s0, walker.rng.s1) == before
    assert walker.used == used
    assert (walker.index, walker.caught) == (0, 0)


def test_walker_copy_has_same_state(make_walker: WalkerFactory) -> None:
    """Walker.copy：刚复制出来的副本，随机数和队伍和原来一样，往后推出的结果也一样。"""
    walker = make_walker()
    other = walker.copy()
    assert (other.rng.s0, other.rng.s1) == (walker.rng.s0, walker.rng.s1)
    assert other.team == walker.team
    walker.scientist(True)
    other.scientist(True)
    assert other.team == walker.team


def test_walker_next_event_follows_schedule_then_none(make_walker: WalkerFactory) -> None:
    """Walker.next_event：先是 schedule 里的第一件事，走完所有事件之后是 None。"""
    walker = make_walker()
    assert walker.next_event() == "scientist"
    walker.replay([False] * 10)
    assert walker.next_event() is None


def test_walker_left_shrinks_as_pokemon_are_caught(make_walker: WalkerFactory) -> None:
    """Walker.left：抓完现在这几只之后还要打的对手：开始是三个，抓一只剩两个，抓到第三只剩一个（最后一关的）。"""
    walker = make_walker()
    assert walker.left() == ["swoobat", "tauros", "torkoal"]
    walker.side_events(lambda w: False)
    walker.catch(False)
    assert walker.left() == ["tauros", "torkoal"]
    walker.side_events(lambda w: False)
    walker.catch(False)
    assert walker.left() == ["torkoal"]


def test_walker_catch_with_take_replaces_own_pokemon(make_walker: WalkerFactory) -> None:
    """Walker.catch：自己换（take 为 True），新抓到的 swoobat 成为自己，三个队友不变，往下走一件事。"""
    walker = make_walker()
    walker.side_events(lambda w: False)
    walker.catch(True)
    assert walker.team == ["swoobat", "maractus", "galvantula", "emolga"]
    assert (walker.index, walker.caught) == (2, 1)
    assert walker.next_event() == "backpacker"


def test_walker_catch_without_take_gives_it_to_a_teammate(make_walker: WalkerFactory) -> None:
    """Walker.catch：自己不换（take 为 False），按 seed 推出队友 1 换上 swoobat，自己不变。"""
    walker = make_walker()
    walker.side_events(lambda w: False)
    walker.catch(False)
    assert walker.team == ["pangoro", "swoobat", "galvantula", "emolga"]
    assert (walker.index, walker.caught) == (2, 1)


def test_walker_offer_returns_scientist_pokemon_without_changing_state(
    make_walker,
) -> None:
    """Walker.offer：现在遇到研究员的话自己换会拿到 sandslash；队伍、进度、随机数都不变。"""
    walker = make_walker()
    fresh = make_walker()
    assert walker.offer() == "sandslash"
    assert walker.team == fresh.team
    assert walker.index == 0
    assert (walker.rng.s0, walker.rng.s1) == (fresh.rng.s0, fresh.rng.s1)
    assert walker.used == fresh.used


def test_walker_scientist_with_take_gives_own_the_offered_pokemon(
    make_walker,
) -> None:
    """Walker.scientist：自己换，自己变成 sandslash（和 offer 说的一样），队友不变，推到下一件事 catch。"""
    walker = make_walker()
    walker.scientist(True)
    assert walker.team == ["sandslash", "maractus", "galvantula", "cofagrigus"]
    assert (walker.index, walker.next_event()) == (1, "catch")


def test_walker_scientist_without_take_gives_a_teammate_the_pokemon(
    make_walker,
) -> None:
    """Walker.scientist：自己不换，按 seed 推出队友 2 换成 emolga，自己不变。"""
    walker = make_walker()
    walker.scientist(False)
    assert walker.team == ["pangoro", "maractus", "galvantula", "emolga"]
    assert (walker.index, walker.next_event()) == (1, "catch")


def test_walker_scientist_marks_given_pokemon_as_used(make_walker: WalkerFactory) -> None:
    """Walker.scientist：研究员给出的宝可梦记进已用过的，数量加 1。"""
    walker = make_walker()
    before = len(walker.used)
    walker.scientist(True)
    assert len(walker.used) == before + 1


def test_walker_backpacker_advances_index_and_uses_random_numbers(
    make_walker,
) -> None:
    """Walker.backpacker：只往下走一件事，队伍不变，但随机数状态变了。"""
    walker = make_walker()
    walker.side_events(lambda w: False)
    walker.catch(False)
    team = list(walker.team)
    state = (walker.rng.s0, walker.rng.s1)
    walker.backpacker()
    assert (walker.index, walker.next_event()) == (3, "catch")
    assert walker.team == team
    assert (walker.rng.s0, walker.rng.s1) != state


def test_walker_replay_with_no_choices_stays_at_first_decision(make_walker: WalkerFactory) -> None:
    """Walker.replay：没有做过任何决定，停在第一个要做决定的地方（研究员）。"""
    walker = make_walker()
    walker.replay([])
    assert (walker.index, walker.next_event()) == (0, "scientist")
    assert walker.team == ["pangoro", "maractus", "galvantula", "cofagrigus"]


def test_walker_replay_one_choice_applies_scientist_then_stops_at_catch(
    make_walker,
) -> None:
    """Walker.replay：做过一个决定（研究员换），推到下一个要决定的地方（抓到）停下。"""
    walker = make_walker()
    walker.replay([True])
    assert walker.team == ["sandslash", "maractus", "galvantula", "cofagrigus"]
    assert (walker.index, walker.next_event()) == (1, "catch")


def test_walker_replay_two_choices_runs_through_backpacker_without_a_choice(
    make_walker,
) -> None:
    """Walker.replay：决定了研究员不换、抓到换，之后遇到的背包客不用决定，直接推过去，停在下一个 catch 前。"""
    walker = make_walker()
    walker.replay([False, True])
    assert walker.team == ["swoobat", "maractus", "galvantula", "emolga"]
    assert (walker.index, walker.next_event(), walker.caught) == (3, "catch", 1)


def test_walker_replay_all_choices_ends_the_route(make_walker: WalkerFactory) -> None:
    """Walker.replay：把所有决定都推完（5 个：研究员、抓、抓、研究员、抓），事件走完，next_event 是 None。"""
    walker = make_walker()
    walker.replay([False, True, False, False, True])
    assert walker.team == ["torkoal", "seadra", "galvantula", "tauros"]
    assert (walker.index, walker.next_event(), walker.caught) == (7, None, 3)


def test_walker_replay_ignores_extra_choices(make_walker: WalkerFactory) -> None:
    """Walker.replay：决定比事件多时，事件走完就停，多出来的不用。"""
    walker = make_walker()
    walker.replay([False] * 10)
    assert (walker.index, walker.next_event(), walker.caught) == (7, None, 3)


def test_walker_side_events_stops_before_first_catch(make_walker: WalkerFactory) -> None:
    """Walker.side_events：从开头推研究员，到下一次抓到为止；decide 返回 True 时自己换。"""
    walker = make_walker()
    walker.side_events(lambda w: True)
    assert walker.team == ["sandslash", "maractus", "galvantula", "cofagrigus"]
    assert (walker.index, walker.next_event()) == (1, "catch")


def test_walker_side_events_decide_false_gives_teammate_the_pokemon(
    make_walker,
) -> None:
    """Walker.side_events：decide 返回 False 时研究员给队友。"""
    walker = make_walker()
    walker.side_events(lambda w: False)
    assert walker.team == ["pangoro", "maractus", "galvantula", "emolga"]


def test_walker_side_events_passes_walker_to_decide(make_walker: WalkerFactory) -> None:
    """Walker.side_events：遇到研究员时调用 decide，传进去的是这个 Walker，调用一次。"""
    walker = make_walker()
    seen: list[upstream.Walker] = []

    def decide(w: upstream.Walker) -> bool:
        seen.append(w)
        return False

    walker.side_events(decide)
    assert seen == [walker]


def test_walker_side_events_skips_backpacker_and_stops_at_catch(
    make_walker,
) -> None:
    """Walker.side_events：停在 catch 前，不处理 catch；背包客照推，不问 decide。"""
    walker = make_walker()
    walker.side_events(lambda w: False)
    walker.catch(False)
    assert walker.next_event() == "backpacker"
    walker.side_events(lambda w: pytest.fail("背包客不该问 decide"))
    assert (walker.index, walker.next_event()) == (3, "catch")


# ---- decide_scientist、decide_catch、best_path、plan_swaps ----


def test_decide_scientist_false_when_team_score_not_higher(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_scientist：首发选界面第 0 只的队伍，换成 sandslash 后队伍分不更高，不换。"""
    assert upstream.decide_scientist(scorer, make_walker(0)) is False


def test_decide_scientist_true_when_team_score_higher(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_scientist：首发选界面第 2 只的队伍，换成 sandslash 后队伍分更高，换。"""
    assert upstream.decide_scientist(scorer, make_walker(2)) is True


def test_decide_scientist_does_not_change_walker(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_scientist：只是判断，Walker 的队伍和进度不变。"""
    walker = make_walker(2)
    upstream.decide_scientist(scorer, walker)
    assert walker.team == ["maractus", "cofagrigus", "galvantula", "pangoro"]
    assert walker.index == 0


def test_decide_scientist_false_when_offered_pokemon_is_not_a_rental(
    make_walker: WalkerFactory,
) -> None:
    """decide_scientist：研究员给的不在 scorer.rentals 里时不换。"""
    walker = make_walker(2)
    small = upstream.Scorer(walker.data, BOSS)
    small.rentals = [name for name in small.rentals if name != "sandslash"]
    assert upstream.decide_scientist(small, walker) is False


def test_decide_catch_keeps_when_not_swapping_is_better(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_catch：首发选界面第 0 只，推到第一次抓到：换 6.967、不换 7.706，不换。"""
    walker = make_walker(0)
    walker.side_events(lambda w: False)
    take, scores = upstream.decide_catch(scorer, walker)
    assert take is False
    assert scores["换"] == pytest.approx(6.967185833641581)
    assert scores["不换"] == pytest.approx(7.705870355211514)


def test_decide_catch_swaps_when_swapping_is_better(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_catch：首发选界面第 2 只，推到第一次抓到：换 7.420、不换 7.147，换。"""
    walker = make_walker(2)
    walker.side_events(lambda w: False)
    take, scores = upstream.decide_catch(scorer, walker)
    assert take is True
    assert scores["换"] == pytest.approx(7.420420152770807)
    assert scores["不换"] == pytest.approx(7.14671473429535)


def test_decide_catch_does_not_change_walker(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """decide_catch：两种走法都在副本上推，Walker 本身的队伍和进度不变。"""
    walker = make_walker(2)
    walker.side_events(lambda w: False)
    team, index = list(walker.team), walker.index
    upstream.decide_catch(scorer, walker)
    assert (walker.team, walker.index, walker.caught) == (team, index, 0)


def test_best_path_returns_highest_route_score(scorer: upstream.Scorer, lair0: Lair) -> None:
    """best_path：2x2 地图上所有路线里路线分最高的是 (1,1)、(2,2)、(3,1)，分数 20.356。"""
    path, score = upstream.best_path(scorer, lair0.encounters(), lair0.map_type())
    assert path == ((1, 1), (2, 2), (3, 1))
    assert score == pytest.approx(20.355610916828724)


def test_plan_swaps_starter_zero_never_swaps(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """plan_swaps：首发选界面第 0 只，三关都不换。"""
    assert upstream.plan_swaps(scorer, make_walker(0)) == [False, False, False]


def test_plan_swaps_starter_two_swaps_every_time(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """plan_swaps：首发选界面第 2 只，三关都换。"""
    assert upstream.plan_swaps(scorer, make_walker(2)) == [True, True, True]


def test_plan_swaps_without_events_can_differ(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """plan_swaps：路上没有研究员时，首发选界面第 2 只的结果是 [换, 换, 不换]。"""
    assert upstream.plan_swaps(scorer, make_walker(2, {})) == [True, True, False]


def test_plan_swaps_does_not_change_walker(
    scorer: upstream.Scorer, make_walker: WalkerFactory
) -> None:
    """plan_swaps：在副本上推，传进去的 Walker 队伍和进度不变。"""
    walker = make_walker(2)
    upstream.plan_swaps(scorer, walker)
    assert (walker.index, walker.caught) == (0, 0)
    assert walker.team == ["maractus", "cofagrigus", "galvantula", "pangoro"]
