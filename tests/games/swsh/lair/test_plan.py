"""control_switch.games.swsh.lair.plan：按这张图实际要打的对手，给首发和路线打分。

用 src/control_switch/games/swsh/data/ 里真实的数据和基准 seed 3076008315599927110（extra 为 0），配置用固定了打分参数的子类。
没有真实数据可用的函数（decide、fight、rotate 等纯计算）直接传数字。
首领是 tapu-lele（kill 分支用 moltres），路线是 ((1, 0), (2, 1), (3, 2))，路上的事件手写在 EVENTS 里。
期望值取自搬迁前 swsh.lair.plan 的运行结果。
"""

import dataclasses
import itertools
from collections.abc import Sequence
from typing import Any, cast

import pytest

from control_switch.games.swsh.lair import plan
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.next_columns import next_columns

BOSS = "tapu-lele"
ROUTE: plan.Path = ((1, 0), (2, 1), (3, 2))
EVENTS = {
    "0-0>1-0": ["scientist"],
    "1-0>2-1": ["backpacker"],
    "2-1": ["berry"],
    "2-1>3-2": ["scientist", "backpacker"],
}
# 最好的路线上三关的对手（2x2 地图，不考虑路上的事件时选出来的）
BEST_OPPONENTS = ("fraxure", "barbaracle", "sneasel")


@pytest.fixture(scope="module")
def planner(fixed_data: GameData, fixed_config: GameConfig) -> plan.Planner:
    """首领是 tapu-lele 的 Planner。"""
    return plan.Planner(fixed_data, fixed_config, BOSS)


# ---- Plan、positions、paths ----


def test_plan_holds_fields_and_is_frozen() -> None:
    """Plan：保存首发下标、路线、对手、队友、分数、换不换，是不可改的。"""
    result = plan.Plan(
        0,
        ((1, 0), (2, 0), (3, 0)),
        ("a", "b", "c"),
        ("x", "y", "z"),
        0.1,
        0.2,
        0.3,
        (True, False, True),
    )
    assert result.starter == 0
    assert result.swaps == (True, False, True)
    assert (result.total, result.stage, result.boss) == (0.1, 0.2, 0.3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cast(Any, result).total = 1.0


def test_positions_alternate_nodes_and_roads_from_start_to_boss() -> None:
    """positions：从起点到首领，节点和节点之间的路交替。"""
    assert plan.positions(ROUTE) == [
        "0-0",
        "0-0>1-0",
        "1-0",
        "1-0>2-1",
        "2-1",
        "2-1>3-2",
        "3-2",
        "3-2>4-0",
    ]


def test_paths_of_2x3_map() -> None:
    """paths：2x3 地图一共 13 条路线，从起点走到第 3 层。"""
    result = plan.paths("2x3")
    assert len(result) == 13
    assert result[0] == ((1, 0), (2, 0), (3, 0))
    assert result[-1] == ((1, 1), (2, 3), (3, 3))
    assert ((1, 1), (2, 2), (3, 3)) in result


def test_paths_of_3x2_map() -> None:
    """paths：3x2 地图一共 11 条路线。"""
    result = plan.paths("3x2")
    assert len(result) == 11
    assert result[0] == ((1, 0), (2, 0), (3, 0))
    assert result[-1] == ((1, 1), (2, 3), (3, 3))
    assert ((1, 0), (2, 2), (3, 1)) in result


def test_paths_of_2x2_map() -> None:
    """paths：2x2 地图一共 11 条路线。"""
    result = plan.paths("2x2")
    assert len(result) == 11
    assert result[0] == ((1, 0), (2, 0), (3, 0))
    assert result[-1] == ((1, 1), (2, 3), (3, 3))
    assert ((1, 0), (2, 1), (3, 3)) in result


@pytest.mark.parametrize("map_type", ["2x3", "3x2", "2x2"])
def test_paths_follow_next_columns_and_have_no_duplicates(map_type: str) -> None:
    """paths：每条路线的每一步都是上一个节点能走到的列，没有重复的路线。"""
    result = plan.paths(map_type)
    assert len(set(result)) == len(result)
    for path in result:
        nodes = [(0, 0), *path]
        for (row, col), (_, next_col) in itertools.pairwise(nodes):
            assert next_col in next_columns(map_type, row, col)


# ---- fate ----


def test_fate_without_swapping_lets_teammates_take_pokemon_and_scientist_changes(
    lair0: Lair,
) -> None:
    """fate：三关都不换。抓到的由队友 0、2、2 换上；研究员在第一只之前把队友 2 换成 emolga，
    在第二只之后把队友 0 换成 seadra。
    """
    result = plan.fate(lair0, ROUTE, EVENTS, BOSS, [False, False, False])
    assert result == plan.Fate(takers=(0, 2, 2), changes=((-1, 2, "emolga"), (1, 0, "seadra")))


def test_fate_with_swapping_means_nobody_takes_caught_pokemon(lair0: Lair) -> None:
    """fate：三关都换。抓到的没人换上（None），研究员给的变成 boltund 给队友 1。"""
    result = plan.fate(lair0, ROUTE, EVENTS, BOSS, [True, True, True])
    assert result == plan.Fate(
        takers=(None, None, None), changes=((-1, 2, "emolga"), (1, 1, "boltund"))
    )


def test_fate_without_events_has_only_takers(lair0: Lair) -> None:
    """fate：路上没有事件时 changes 是空的，只有抓到的由谁换上。"""
    result = plan.fate(lair0, ROUTE, {}, BOSS, [False, False, False])
    assert result == plan.Fate(takers=(2, 0, None), changes=())


# ---- rotate、own_hurt ----


def test_rotate_while_dynamax_remaining_counts_down(fixed_config: GameConfig) -> None:
    """rotate：极巨化还剩 2 个回合（left > 0）：这个回合极巨化，left 减 1，wait 不变。"""
    assert plan.rotate(2, 5, fixed_config) == (True, 1, 5)
    assert plan.rotate(1, 3, fixed_config) == (True, 0, 3)


def test_rotate_starts_dynamax_when_wait_is_zero(fixed_config: GameConfig) -> None:
    """rotate：没有剩余的极巨化回合、wait 是 0：轮到自己极巨化，left 变成 dynamax_turns - 1，wait 变成 dynamax_wait。"""
    assert plan.rotate(0, 0, fixed_config) == (True, 2, 3)


def test_rotate_waits_when_not_yet_its_turn(fixed_config: GameConfig) -> None:
    """rotate：没有剩余的极巨化回合、wait 大于 0：这个回合不极巨化，wait 减 1。"""
    assert plan.rotate(0, 2, fixed_config) == (False, 0, 1)


@pytest.mark.parametrize(
    ("wait", "expected"),
    [
        (0, 0.5263157894736842),
        (1, 0.6842105263157895),
        (2, 0.8421052631578948),
        (3, 1.0),
        (5, 1.0),
    ],
)
def test_own_hurt_by_dynamaxed_share_of_first_turns(
    fixed_config: GameConfig, wait: int, expected: float
) -> None:
    """own_hurt：前 3 个回合里极巨化的回合越多，挨打的倍数越小（极巨化时血量是 1.9 倍）。"""
    assert plan.own_hurt(wait, fixed_config) == pytest.approx(expected)


# ---- fight ----


def test_fight_sure_damage_finishes_in_one_turn(fixed_config: GameConfig) -> None:
    """fight：这个回合伤害不低于 1：打完，预测 1 回合，轮换也按 1 回合，极巨化的轮换走到 wait 3。"""
    assert plan.fight([1.2, 1.5], 0, fixed_config) == (1.0, 1, 3)


def test_fight_first_turn_uses_dynamax_damage_when_it_is_own_turn(fixed_config: GameConfig) -> None:
    """fight：wait 为 0 时第 1 个回合轮到自己极巨化，用极巨招式的伤害（1.5 够打完）。"""
    assert plan.fight([0.5, 1.5], 0, fixed_config) == (1.0, 1, 3)


def test_fight_first_turn_uses_normal_damage_when_waiting(fixed_config: GameConfig) -> None:
    """fight：wait 为 1 时第 1 个回合不极巨化，普通伤害 0.5 打不完，第 2 个回合极巨化 1.5 打完，共 2 回合。"""
    assert plan.fight([0.5, 1.5], 1, fixed_config) == (2.0, 2, 3)


def test_fight_likely_damage_not_finished_counts_one_and_a_half_turns(
    fixed_config: GameConfig,
) -> None:
    """fight：伤害 0.7（不低于 0.6）、队友没有输出，这个回合没打完：算一回合半，轮换多走一个回合。"""
    assert plan.fight([0.7, 0.9], 2, fixed_config) == (1.5, 2, 0)


def test_fight_likely_damage_finished_by_team_counts_one_and_a_half_turns_but_one_rotation(
    fixed_config: GameConfig,
) -> None:
    """fight：伤害 0.7 加上队友的输出这个回合就打完：还是算一回合半，轮换只走一个回合。"""
    assert plan.fight([0.7, 0.9], 2, fixed_config, 0.3) == (1.5, 1, 1)


def test_fight_weak_damage_knocked_out_in_first_turn_uses_weak_turns(
    fixed_config: GameConfig,
) -> None:
    """fight：伤害低，但队友合计很高，第 1 个回合对手就掉完：算 stage_weak_turns（1.58）个回合，轮换按 2 个回合。"""
    assert plan.fight([0.3, 0.3], 5, fixed_config, 0.6) == (1.58, 2, 3)


def test_fight_weak_damage_knocked_out_later_adds_fraction_and_half_turn(
    fixed_config: GameConfig,
) -> None:
    """fight：伤害低，第 2 个回合对手掉完：回合数 = 整回合数 + 最后一个回合用掉的比例 + 半个回合。"""
    assert plan.fight([0.3, 0.5], 0, fixed_config) == (pytest.approx(2.318181818181818), 2, 3)


def test_fight_weak_damage_is_capped_at_max_turns(fixed_config: GameConfig) -> None:
    """fight：伤害是 0、队友也没有输出，打到 stage_max_turns（10）回合还没掉完：预测 10.5 回合。"""
    assert plan.fight([0.0, 0.0], 0, fixed_config) == (10.5, 10, 2)


def test_fight_team_damage_speeds_up_the_fight(fixed_config: GameConfig) -> None:
    """fight：同样的伤害，加上队友的输出，打得更快。"""
    alone = plan.fight([0.3, 0.5], 0, fixed_config)[0]
    with_team = plan.fight([0.3, 0.5], 0, fixed_config, 0.1)[0]
    assert with_team == pytest.approx(1.9492753623188404)
    assert with_team < alone


# ---- faint_chance、combine ----


@pytest.mark.parametrize(
    ("damage", "expected"),
    [
        (0.0, 0.0),
        (0.4, 0.058823529411764705),
        (0.8, 0.5),
        (1.6, 0.9411764705882353),
        (2.0, 0.9750390015600623),
    ],
)
def test_faint_chance_is_half_at_boss_faint_half(
    fixed_config: GameConfig, damage: float, expected: float
) -> None:
    """faint_chance：damage 到 boss_faint_half（0.8）时是一半，一半时只有 6%，两倍时 94%，是 0 时没有机会。"""
    assert plan.faint_chance(damage, fixed_config) == pytest.approx(expected)


def test_combine_is_weighted_geometric_mean(fixed_config: GameConfig) -> None:
    """combine：三关的分权重合计 0.6、首领 0.4：0.5 和 0.5 合起来是 0.5。"""
    assert plan.combine(0.5, 0.5, fixed_config) == pytest.approx(0.5)


def test_combine_perfect_scores_give_one(fixed_config: GameConfig) -> None:
    """combine：三关和首领都是 1 分时总分是 1。"""
    assert plan.combine(1, 1, fixed_config) == pytest.approx(1.0)


def test_combine_weights_stage_by_point_six(fixed_config: GameConfig) -> None:
    """combine：三关 0.25、首领 0.9：0.25 的 0.6 次方乘 0.9 的 0.4 次方。"""
    assert plan.combine(0.25, 0.9, fixed_config) == pytest.approx(0.41731213044030924)


# ---- decide ----


def stage_score(after: Sequence[str]) -> tuple[float, int]:
    """假的三关分：每一关上场的是 b 加 0.1；等待回合数固定 2。"""
    return 0.5 + 0.1 * sum(1 for member in after if member == "b"), 2


def boss_score(own: str, wait: int, members: Sequence[str]) -> float:
    """假的首领分：自己是 b 加 0.05，每个队友是 x 加 0.01。"""
    return 0.2 + 0.05 * (own == "b") + 0.01 * sum(1 for member in members if member == "x")


def test_decide_picks_swap_combination_with_highest_total(fixed_config: GameConfig) -> None:
    """decide：没给 fate，两只抓到的 b、x，换第一只、不换第二只总分最高：(0.470, 三关 0.7, 首领 0.259, (True, False))。"""
    result = plan.decide("a", ["m1", "m2", "m3"], ["b", "x"], stage_score, boss_score, fixed_config)
    assert result[:3] == pytest.approx((0.47012242469397786, 0.7, 0.25875000000000004))
    assert result[3] == (True, False)


def test_decide_with_first_true_only_tries_swapping_first(fixed_config: GameConfig) -> None:
    """decide：first 指定第一只换，结果就是只在换第一只的组合里选。"""
    result = plan.decide(
        "a", ["m1", "m2", "m3"], ["b", "x"], stage_score, boss_score, fixed_config, first=True
    )
    assert result[3] == (True, False)
    assert result[0] == pytest.approx(0.47012242469397786)


def test_decide_with_first_false_only_tries_not_swapping_first(fixed_config: GameConfig) -> None:
    """decide：first 指定第一只不换，结果只在不换第一只的组合里选，总分比自由选低。"""
    result = plan.decide(
        "a", ["m1", "m2", "m3"], ["b", "x"], stage_score, boss_score, fixed_config, first=False
    )
    assert result[3] == (False, False)
    assert result[0] == pytest.approx(0.35255964180344196)
    assert result[1] == pytest.approx(0.5)
    assert result[2] == pytest.approx(0.2087500000000001)


def test_decide_without_fate_averages_over_who_takes_the_unswapped_pokemon(
    fixed_config: GameConfig,
) -> None:
    """decide：没给 fate，自己不换的那只，没人换、队友 0、1、2 各换一次，首领分按这四种情况取期望。"""
    seen: list[tuple[str, int, list[str]]] = []

    def recording_boss(own: str, wait: int, members: Sequence[str]) -> float:
        seen.append((own, wait, list(members)))
        return 0.3

    result = plan.decide(
        "a", ["m1", "m2", "m3"], ["b"], lambda after: (0.5, 0), recording_boss, fixed_config
    )
    assert seen == [
        ("a", 0, ["m1", "m2", "m3"]),
        ("a", 0, ["b", "m2", "m3"]),
        ("a", 0, ["m1", "b", "m3"]),
        ("a", 0, ["m1", "m2", "b"]),
        ("b", 0, ["m1", "m2", "m3"]),
    ]
    assert result[3] == (False,)
    assert result[2] == pytest.approx(0.30000000000000004)
    assert result[0] == pytest.approx(0.40759655480296136)


def test_decide_with_fate_uses_determined_teammates(fixed_config: GameConfig) -> None:
    """decide：给了 fate，首领战的队友是确定的：抓到的被队友 0 换上、研究员把队友 2 换成 z、队友 1 换成 w，不取期望。"""
    seen: list[tuple[str, int, list[str]]] = []

    def recording_boss(own: str, wait: int, members: Sequence[str]) -> float:
        seen.append((own, wait, list(members)))
        return 0.3

    def fate(swaps: tuple[bool, ...]) -> plan.Fate[str]:
        return plan.Fate(takers=(0, 1), changes=((-1, 2, "z"), (0, 1, "w")))

    result = plan.decide(
        "a", ["m1", "m2", "m3"], ["b", "x"], stage_score, recording_boss, fixed_config, fate=fate
    )
    # 四种换法各算一次；两只都不换时队友是 [b, x, z] 还是别的，由 fate 的 takers 和 changes 定
    assert ("a", 2, ["b", "x", "z"]) in seen
    assert len(seen) == 4
    assert result[0] == pytest.approx(0.49877804185215613)
    assert result[3] == (True, False)


def test_decide_with_fate_ignores_taker_when_own_swapped(fixed_config: GameConfig) -> None:
    """decide：给了 fate，自己换了的那一只，队友不会再换上它（takers 里写了也不用）。"""
    seen: list[list[str]] = []

    def recording_boss(own: str, wait: int, members: Sequence[str]) -> float:
        seen.append(list(members))
        return 0.3

    def fate(swaps: tuple[bool, ...]) -> plan.Fate[str]:
        return plan.Fate(takers=(0,), changes=())

    plan.decide(
        "a",
        ["m1", "m2", "m3"],
        ["b"],
        lambda after: (0.5, 0),
        recording_boss,
        fixed_config,
        fate=fate,
    )
    assert seen == [["b", "m2", "m3"], ["m1", "m2", "m3"]]


def test_decide_with_fate_total_and_boss(fixed_config: GameConfig) -> None:
    """decide：给了 fate 时，只有 takers 里的第 0 只被队友 1 换上，其余不变，结果的总分、首领分。"""

    def fate(swaps: tuple[bool, ...]) -> plan.Fate[str]:
        return plan.Fate(takers=(1, None), changes=())

    result = plan.decide(
        "a", ["m1", "m2", "m3"], ["b", "x"], stage_score, boss_score, fixed_config, fate=fate
    )
    assert result[:3] == pytest.approx((0.4636975779962094, 0.7, 0.25))
    assert result[3] == (True, False)


def test_decide_tie_prefers_fewer_swaps(fixed_config: GameConfig) -> None:
    """decide：每种换法总分都一样时取换得少的，即全不换。"""
    result = plan.decide(
        "a",
        ["m1", "m2", "m3"],
        ["b", "x"],
        lambda after: (0.5, 0),
        lambda o, w, m: 0.4,
        fixed_config,
    )
    assert result[3] == (False, False)
    assert result[0] == pytest.approx(0.45730505192732634)


def test_decide_with_no_catches_returns_empty_swaps(fixed_config: GameConfig) -> None:
    """decide：没有要抓的了：换法是空的，总分按现在的算。"""
    result = plan.decide(
        "a", ["m1", "m2", "m3"], [], lambda after: (0.5, 0), lambda o, w, m: 0.4, fixed_config
    )
    assert result[3] == ()
    assert result[0] == pytest.approx(0.4573050519273263)


# ---- Planner ----


def test_planner_stages(planner: plan.Planner) -> None:
    """Planner.stages：rhydon、glalie、ditto 依次打三关，队友 starmie、scyther、chansey：三关的分和首领战前的 wait。"""
    score, wait = planner.stages(
        ["rhydon", "glalie", "ditto"],
        ["swoobat", "tauros", "torkoal"],
        ["starmie", "scyther", "chansey"],
    )
    assert score == pytest.approx(0.3893841733834897)
    assert wait == 3


def test_planner_stages_with_average_placeholders(planner: plan.Planner) -> None:
    """Planner.stages：用 AVERAGE（全部租借宝可梦的平均）代替具体的宝可梦也能算。"""
    score, wait = planner.stages(
        [plan.AVERAGE] * 3, ["swoobat", "tauros", "torkoal"], [plan.AVERAGE] * 3
    )
    assert score == pytest.approx(0.42166456880656866)
    assert wait == 3


@pytest.mark.parametrize(
    ("wait", "expected"),
    [
        (0, (0.2257789917482515, 0.22577899174825147)),
        (1, (0.13355777756527995, 0.19503858702059432)),
        (2, (0.13355777756527995, 0.16429818229293713)),
        (3, (0.13355777756527995, 0.13355777756527995)),
        (4, (0.13355777756527995, 0.13355777756527995)),
    ],
)
def test_planner_boss_attack_uses_dynamax_attack_on_dynamax_turns(
    planner: plan.Planner, wait: int, expected: tuple[float, float]
) -> None:
    """Planner.boss_attack：rhydon 打首领，(第 1 回合的, 前 3 个回合平均的)；wait 越小，前几个回合里极巨化的越多。"""
    assert planner.boss_attack("rhydon", wait) == pytest.approx(expected)


def test_planner_boss_one_turn_kill_branch(fixed_data: GameData, fixed_config: GameConfig) -> None:
    """Planner.boss：四只的进攻合计不低于 boss_kill_attack（1.0）算能一回合打死，首领分只看进攻合计：
    boss_turn_rate × 合计，最高 1。首领 moltres，自己 relicanth，队友 tyrantrum、两只 lycanroc。
    """
    moltres = plan.Planner(fixed_data, fixed_config, "moltres")
    first, _ = moltres.boss_attack("relicanth", 0)
    assert first == pytest.approx(0.4707005747617363)
    score = moltres.boss("relicanth", 0, ["tyrantrum", "lycanroc-midday", "lycanroc-midnight"])
    assert score == pytest.approx(0.9379600093907705)


def test_planner_boss_slow_branch_with_faint_penalty(planner: plan.Planner) -> None:
    """Planner.boss：进攻合计不到 1，预测打几个回合，再按预计倒下几只扣分。"""
    score = planner.boss("rhydon", 0, ["starmie", "scyther", "chansey"])
    assert score == pytest.approx(0.033351293263258024)


def test_planner_boss_with_average_placeholders(planner: plan.Planner) -> None:
    """Planner.boss：自己和三个队友都用 AVERAGE。"""
    assert planner.boss(plan.AVERAGE, 3, [plan.AVERAGE] * 3) == pytest.approx(0.019214311331304027)


def test_planner_boss_is_higher_for_stronger_attackers(planner: plan.Planner) -> None:
    """Planner.boss：rhydon 的队伍比 starmie 的队伍分高。"""
    strong = planner.boss("rhydon", 0, ["starmie", "scyther", "chansey"])
    weak = planner.boss("starmie", 0, ["starmie", "scyther", "chansey"])
    assert strong == pytest.approx(0.033351293263258024)
    assert weak == pytest.approx(0.013928093228524672)
    assert strong > weak


def test_planner_score_without_fate(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.score：首发选界面第 0 只（pangoro），没有 fate：总分、三关的分、首领分、三关换不换。"""
    opponents = BEST_OPPONENTS
    total, stage, boss, swaps = planner.score("pangoro", lair0.teammates(0), opponents)
    assert (total, stage, boss) == pytest.approx(
        (0.22800162506700664, 0.5967574271208885, 0.0538453379118802)
    )
    assert swaps == (False, False, False)


def test_planner_score_with_average_teammate(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.score：队友里有一个 AVERAGE（研究员换上来的未知宝可梦）时，分数比具体的队友低。"""
    teammates = [plan.AVERAGE, *lair0.teammates(0)[1:]]
    result = planner.score("pangoro", teammates, BEST_OPPONENTS)
    assert result[:3] == pytest.approx(
        (0.2144305840250311, 0.5460781701956445, 0.05276362165535009)
    )


def test_planner_score_with_fate(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.score：给 fate（三关都没有队友换上抓到的）：首领分按确定的队友算。"""
    result = planner.score(
        "pangoro",
        lair0.teammates(0),
        BEST_OPPONENTS,
        lambda swaps: plan.Fate((None, None, None), ()),
    )
    assert result[:3] == pytest.approx(
        (0.21760698447367222, 0.5967574271208885, 0.04791652641153534)
    )
    assert result[3] == (False, False, False)


def test_planner_score_starter_two_swaps_last_stage(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.score：首发选界面第 2 只（maractus）：三关换不换是 (不换, 不换, 换)。"""
    result = planner.score("maractus", lair0.teammates(2), BEST_OPPONENTS)
    assert result[:3] == pytest.approx(
        (0.20588313154990115, 0.5396749479869024, 0.048512485502588035)
    )
    assert result[3] == (False, False, True)


def test_planner_best_without_events(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.best：基准 seed、2x2 地图，不给事件：选首发 0、路线 (1,1)(2,2)(3,1)，三关都不换。"""
    best = planner.best(
        lair0.candidates()[:3], lair0.encounters(), lair0.map_type(), lair0.teammates
    )
    assert best.starter == 0
    assert best.path == ((1, 1), (2, 2), (3, 1))
    assert best.opponents == BEST_OPPONENTS
    assert best.teammates == ("maractus", "galvantula", "cofagrigus")
    assert (best.total, best.stage, best.boss) == pytest.approx(
        (0.22800162506700664, 0.5967574271208885, 0.0538453379118802)
    )
    assert best.swaps == (False, False, False)


def test_planner_best_restricted_to_one_starter(planner: plan.Planner, lair0: Lair) -> None:
    """Planner.best：starters 只给第 2 只时只在它里面选，换不换是 (不换, 不换, 换)。"""
    best = planner.best(
        lair0.candidates()[:3],
        lair0.encounters(),
        lair0.map_type(),
        lair0.teammates,
        starters=(2,),
    )
    assert best.starter == 2
    assert best.path == ((1, 1), (2, 2), (3, 1))
    assert best.teammates == ("cofagrigus", "galvantula", "pangoro")
    assert best.total == pytest.approx(0.20588313154990115)
    assert best.swaps == (False, False, True)


def test_planner_best_with_scientist_on_road_changes_choice(
    planner: plan.Planner, lair0: Lair
) -> None:
    """Planner.best：第一段路 0-0>1-1 上有研究员，走 (1,1) 的路线要把一个队友换成 AVERAGE 取平均，最好的路线变成 (1,1)(2,3)(3,1)。"""
    best = planner.best(
        lair0.candidates()[:3],
        lair0.encounters(),
        lair0.map_type(),
        lair0.teammates,
        events={"0-0>1-1": ["scientist"]},
    )
    assert best.path == ((1, 1), (2, 3), (3, 1))
    assert best.opponents == ("fraxure", "obstagoon", "sneasel")
    assert best.total == pytest.approx(0.21914370179763862)
    assert best.swaps == (False, False, False)


def test_planner_best_with_fate_uses_determined_teammates(
    planner: plan.Planner, lair0: Lair
) -> None:
    """Planner.best：给 fate（按基准 seed 推出队友怎么变）时，不再用 AVERAGE，选出的路线是 (1,0)(2,1)(3,1)。"""

    def fate(path: plan.Path, swaps: tuple[bool, ...]) -> plan.Fate[str]:
        return plan.fate(lair0, path, EVENTS, BOSS, swaps)

    best = planner.best(
        lair0.candidates()[:3],
        lair0.encounters(),
        lair0.map_type(),
        lair0.teammates,
        events=EVENTS,
        fate=fate,
    )
    assert best.starter == 0
    assert best.path == ((1, 0), (2, 1), (3, 1))
    assert best.opponents == ("swoobat", "tauros", "sneasel")
    assert (best.total, best.stage, best.boss) == pytest.approx(
        (0.20398796880594006, 0.6272741253582329, 0.03782904028736648)
    )
    assert best.swaps == (False, False, False)
