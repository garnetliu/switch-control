"""control_switch.games.swsh.scoring：评分公式。

宝可梦用 src/control_switch/games/swsh/data/ 里真实的数据，个体值固定 31。期望值取自搬迁前 swsh.scoring 的运行结果。
常用的组合：自己 rhydon，对手首领 tapu-lele，队友 starmie、scyther、chansey。
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from control_switch.games.swsh import scoring
from control_switch.games.swsh.field import Field
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.pokemon import Pokemon

MonFactory = Callable[[str], Pokemon]

# rhydon 的四个招式：drill-run、smack-down、smart-strike、scary-face
RHYDON_DAMAGE_TO_LELE = (
    0.45270001726188186,
    0.30305823008170624,
    0.5582715102228701,
    0.009296482412060303,
)
RHYDON_MAX_DAMAGE_TO_LELE = (
    0.7656398404234916,
    0.5921717365453221,
    0.9437561855076912,
    0.009296482412060303,
)


@pytest.fixture
def mates(mon: MonFactory) -> list[Pokemon]:
    """三个队友。"""
    return [mon("starmie"), mon("scyther"), mon("chansey")]


def test_weighted_score_is_geometric_mean_weighted_by_counts() -> None:
    """weighted_score：2 的 1 次方乘 0.5 的 3 次方再开 4 次方根。"""
    assert scoring.weighted_score(2.0, 1, 0.5, 3) == pytest.approx(0.7071067811865476)


def test_weighted_score_with_equal_weights_is_plain_geometric_mean() -> None:
    """两项权重一样时就是普通的几何平均。"""
    assert scoring.weighted_score(4.0, 2, 1.0, 2) == pytest.approx(2.0)


def test_type_multiplier_multiplies_both_defender_types() -> None:
    """type_multiplier：火打草冰双属性是 2 乘 2。"""
    assert scoring.type_multiplier("fire", ["grass", "ice"]) == 4.0


def test_type_multiplier_immunity_gives_zero() -> None:
    """type_multiplier：地面打飞行没有效果，倍率 0。"""
    assert scoring.type_multiplier("ground", ["flying"]) == 0.0


def test_type_multiplier_mixed_immunity_still_zero() -> None:
    """type_multiplier：格斗打幽灵加一般，有一个免疫整体就是 0。"""
    assert scoring.type_multiplier("fighting", ["ghost", "normal"]) == 0.0


def test_type_multiplier_resisted_and_super_effective_cancel_out() -> None:
    """type_multiplier：水打地面加岩石是 2 乘 2。"""
    assert scoring.type_multiplier("water", ["ground", "rock"]) == 4.0


def test_damage_of_each_move_against_boss(mon: MonFactory) -> None:
    """damage：rhydon 四个招式打 tapu-lele，以对手最大 HP 为 1。"""
    attacker, boss, field = mon("rhydon"), mon("tapu-lele"), Field()
    values = [scoring.damage(attacker, index, boss, field) for index in range(4)]
    assert values == pytest.approx(RHYDON_DAMAGE_TO_LELE)


def test_damage_uses_max_move_when_attacker_dynamaxed(mon: MonFactory) -> None:
    """damage：自己极巨化时按极巨招式算，伤害更高。"""
    attacker = replace(mon("rhydon"), dynamax=True)
    boss, field = mon("tapu-lele"), Field()
    values = [scoring.damage(attacker, index, boss, field) for index in range(4)]
    assert values == pytest.approx(RHYDON_MAX_DAMAGE_TO_LELE)


def test_damage_multiple_targets_only_changes_spread_moves(mon: MonFactory) -> None:
    """damage：multiple_targets 为 True 时，rhydon 没有范围招式，伤害不变。"""
    attacker, boss, field = mon("rhydon"), mon("tapu-lele"), Field()
    values = [scoring.damage(attacker, index, boss, field, True) for index in range(4)]
    assert values == pytest.approx(RHYDON_DAMAGE_TO_LELE)


def test_damage_burn_halves_physical_move(mon: MonFactory) -> None:
    """damage：烧伤时物理招式的伤害减半（drill-run 是物理招式）。"""
    attacker, boss = replace(mon("rhydon"), status="burn"), mon("tapu-lele")
    assert scoring.damage(attacker, 0, boss, Field()) == pytest.approx(0.22635000863094093)


def test_average_damage_over_all_pairs(mon: MonFactory) -> None:
    """average_damage：两个进攻方、两个防守方，对四个组合各招式的平均取平均。"""
    result = scoring.average_damage(
        [mon("rhydon"), mon("glalie")], [mon("tapu-lele"), mon("mewtwo")], Field()
    )
    assert result == pytest.approx(0.1893376017761284)


def test_average_damage_with_no_pairs_is_zero(mon: MonFactory) -> None:
    """average_damage：没有进攻方时没有组合，结果是 0。"""
    assert scoring.average_damage([], [mon("tapu-lele")], Field()) == 0


def test_average_damage_with_multiple_targets(mon: MonFactory) -> None:
    """average_damage：multiple_targets 传 True，rhydon 对 tapu-lele 没有范围招式，结果不变。"""
    result = scoring.average_damage([mon("rhydon")], [mon("tapu-lele")], Field(), True)
    assert result == pytest.approx(0.33083155999462965)


def test_teammate_damage_of_attack_only_moveset_ranked_by_damage(mon: MonFactory) -> None:
    """teammate_damage：starmie 打 tapu-lele，按实测的出招比例平均。"""
    assert scoring.teammate_damage(mon("starmie"), mon("tapu-lele"), Field()) == pytest.approx(
        0.17308094631421386
    )


def test_teammate_damage_with_status_move_in_set(mon: MonFactory) -> None:
    """teammate_damage：rhydon 有一个变化招式 scary-face，按 TEAMMATE_STATUS 少出进攻招式。"""
    assert scoring.teammate_damage(mon("rhydon"), mon("mewtwo"), Field()) == pytest.approx(
        0.19759096720505256
    )


def test_select_best_move_picks_highest_score(mon: MonFactory, mates: list[Pokemon]) -> None:
    """select_best_move：rhydon 对 tapu-lele，默认的 max_move_probability，选第 2 个招式 smart-strike。"""
    result = scoring.select_best_move(mon("rhydon"), mon("tapu-lele"), Field(), mates)
    assert result[:2] == (2, "smart-strike")
    assert result[2] == pytest.approx(2.9610590148829425)


def test_select_best_move_with_no_max_move_probability(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """select_best_move：max_move_probability 传 0（对手不用极巨招式），分数是 3.248。"""
    result = scoring.select_best_move(mon("rhydon"), mon("tapu-lele"), Field(), mates, 0.0)
    assert result[:2] == (2, "smart-strike")
    assert result[2] == pytest.approx(3.2480022194369726)


def test_select_best_move_with_always_max_move(mon: MonFactory, mates: list[Pokemon]) -> None:
    """select_best_move：max_move_probability 传 1（对手只用极巨招式），分数是 2.5176。"""
    result = scoring.select_best_move(mon("rhydon"), mon("tapu-lele"), Field(), mates, 1.0)
    assert result[:2] == (2, "smart-strike")
    assert result[2] == pytest.approx(2.5175647237396115)


def test_select_best_move_dynamaxed_returns_max_move_name(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """select_best_move：自己极巨化时返回极巨招式的序号和名字。"""
    attacker = replace(mon("rhydon"), dynamax=True)
    result = scoring.select_best_move(attacker, mon("tapu-lele"), Field(), mates, 0.8)
    assert result[:2] == (2, "max-steelspike")
    assert result[2] == pytest.approx(4.0898862380279155)


def test_select_best_move_skips_moves_without_pp(mon: MonFactory, mates: list[Pokemon]) -> None:
    """select_best_move：smart-strike 没 PP 了，选剩下里最高的 drill-run。"""
    attacker = replace(mon("rhydon"), pp=[1, 1, 0, 1])
    result = scoring.select_best_move(attacker, mon("tapu-lele"), Field(), mates)
    assert result[:2] == (0, "drill-run")
    assert result[2] == pytest.approx(2.6567529020779044)


def test_select_best_move_with_no_pp_left_returns_default(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """select_best_move：四个招式都没 PP，返回 (0, 空名字, -100)。"""
    attacker = replace(mon("rhydon"), pp=[0, 0, 0, 0])
    result = scoring.select_best_move(attacker, mon("tapu-lele"), Field(), mates)
    assert result == (0, "", -100.0)


def test_move_score_of_each_move_with_default_probability(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """move_score：rhydon 四个招式对 tapu-lele，默认的 max_move_probability。"""
    attacker, boss, field = mon("rhydon"), mon("tapu-lele"), Field()
    values = [scoring.move_score(attacker, index, boss, mates, field) for index in range(4)]
    assert values == pytest.approx(
        [2.6567529020779044, 2.2254157172677465, 2.9610590148829425, 1.378657818739229]
    )


def test_move_score_with_different_max_move_probability(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """move_score：max_move_probability 传 0.9，挨打更多，四个分数都比默认的低。"""
    attacker, boss, field = mon("rhydon"), mon("tapu-lele"), Field()
    values = [scoring.move_score(attacker, index, boss, mates, field, 0.9) for index in range(4)]
    assert values == pytest.approx(
        [2.310803483692636, 1.9356329254800453, 2.5754843371618708, 1.1991357148310677]
    )


def test_move_score_dynamaxed_attacker_receives_less_damage(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """move_score：自己极巨化时血量是 DYNAMAX_HP 倍，没有队友时分数比不极巨化的高。"""
    boss, field = mon("tapu-lele"), Field()
    plain = mon("rhydon")
    dynamaxed = replace(plain, dynamax=True)
    plain_values = [scoring.move_score(plain, index, boss, [], field) for index in range(4)]
    dynamax_values = [scoring.move_score(dynamaxed, index, boss, [], field) for index in range(4)]
    assert plain_values == pytest.approx(
        [5.598536899680653, 3.7479183105107543, 6.904138570454514, 0.1149695114569509]
    )
    assert dynamax_values == pytest.approx(
        [17.99045548167943, 13.914426472288554, 22.175705526954406, 0.21844207176820668]
    )


def test_move_score_ignores_attacker_and_defender_in_teammates(mon: MonFactory) -> None:
    """move_score：队友列表里混进了自己和对手，不算队友，结果和没有队友一样。"""
    attacker, boss, field = mon("rhydon"), mon("tapu-lele"), Field()
    with_self = scoring.move_score(attacker, 2, boss, [attacker, boss], field)
    without = scoring.move_score(attacker, 2, boss, [], field)
    assert with_self == pytest.approx(without)


def test_evaluate_matchup_plain(mon: MonFactory) -> None:
    """evaluate_matchup：rhydon 对 tapu-lele，没有队友，满血。"""
    assert scoring.evaluate_matchup(mon("rhydon"), mon("tapu-lele")) == pytest.approx(
        14.53992204870446
    )


def test_evaluate_matchup_with_teammates(mon: MonFactory, mates: list[Pokemon]) -> None:
    """evaluate_matchup：带三个队友，lives 传 3，满血时命数不影响。"""
    result = scoring.evaluate_matchup(mon("rhydon"), mon("tapu-lele"), mates, 3)
    assert result == pytest.approx(3.769326765465644)


def test_evaluate_matchup_lower_hp_lowers_score(mon: MonFactory) -> None:
    """evaluate_matchup：血量一半、一条命，分数是满血的一半。"""
    attacker = replace(mon("rhydon"), hp=0.5)
    assert scoring.evaluate_matchup(attacker, mon("tapu-lele")) == pytest.approx(7.26996102435223)


def test_evaluate_matchup_more_lives_hurt_less(mon: MonFactory) -> None:
    """evaluate_matchup：血量一半时命越多血量的影响越小；1、2、4 条命各一个值。"""
    attacker, boss = replace(mon("rhydon"), hp=0.5), mon("tapu-lele")
    values = [scoring.evaluate_matchup(attacker, boss, (), lives) for lives in (1, 2, 4)]
    assert values == pytest.approx([7.26996102435223, 9.087451280440288, 12.722431792616403])


def test_evaluate_matchup_clamps_lives_to_range(mon: MonFactory) -> None:
    """evaluate_matchup：lives 超过 4 按 4、小于 1 按 1。"""
    attacker, boss = replace(mon("rhydon"), hp=0.5), mon("tapu-lele")
    assert scoring.evaluate_matchup(attacker, boss, (), 9) == pytest.approx(12.722431792616403)
    assert scoring.evaluate_matchup(attacker, boss, (), 0) == pytest.approx(7.26996102435223)


def test_evaluate_matchup_ditto_attacker_transforms_into_boss(mon: MonFactory) -> None:
    """evaluate_matchup：自己是百变怪时先变成对手再算。"""
    assert scoring.evaluate_matchup(mon("ditto"), mon("tapu-lele")) == pytest.approx(
        13.259419861859952
    )


def test_evaluate_matchup_ditto_boss_transforms_into_attacker(mon: MonFactory) -> None:
    """evaluate_matchup：对手是百变怪时，对手变成自己再算。"""
    assert scoring.evaluate_matchup(mon("rhydon"), mon("ditto")) == pytest.approx(
        22.320484466892882
    )


def test_evaluate_average_matchup_averages_over_bosses(
    mon: MonFactory, mates: list[Pokemon]
) -> None:
    """evaluate_average_matchup：对两个对手的相性取平均。"""
    result = scoring.evaluate_average_matchup(
        mon("rhydon"), [mon("tapu-lele"), mon("mewtwo")], mates, 2
    )
    assert result == pytest.approx(2.620860059231769)


def test_evaluate_average_matchup_without_bosses_is_one(mon: MonFactory) -> None:
    """evaluate_average_matchup：没有对手时是 1。"""
    assert scoring.evaluate_average_matchup(mon("rhydon"), []) == 1


def test_evaluate_damage_regular_moves(mon: MonFactory) -> None:
    """evaluate_damage：不极巨化时取普通招式里伤害最高的（smart-strike）。"""
    result = scoring.evaluate_damage(mon("rhydon"), mon("tapu-lele"), False, 1.0)
    assert result == pytest.approx(0.5582715102228701)


def test_evaluate_damage_dynamaxed_uses_max_moves_and_hp_multiple(mon: MonFactory) -> None:
    """evaluate_damage：极巨化时用极巨招式，对手血量是 hp=1.9 倍。"""
    result = scoring.evaluate_damage(mon("rhydon"), mon("tapu-lele"), True, 1.9)
    assert result == pytest.approx(0.49671378184615333)


def test_evaluate_damage_ditto_attacker(mon: MonFactory) -> None:
    """evaluate_damage：自己是百变怪时先变成对手再算。"""
    result = scoring.evaluate_damage(mon("ditto"), mon("tapu-lele"), False, 1.0)
    assert result == pytest.approx(0.387620737274157)


def test_evaluate_damage_ditto_defender(mon: MonFactory) -> None:
    """evaluate_damage：对手是百变怪时，对手变成自己再算。"""
    result = scoring.evaluate_damage(mon("rhydon"), mon("ditto"), False, 1.0)
    assert result == pytest.approx(0.839866928247176)


def test_evaluate_damage_without_pp_is_zero(mon: MonFactory) -> None:
    """evaluate_damage：所有招式都没 PP 时是 0。"""
    attacker = replace(mon("rhydon"), pp=[0, 0, 0, 0])
    assert scoring.evaluate_damage(attacker, mon("tapu-lele"), False, 1.0) == 0.0


def test_evaluate_average_damage_regular(mon: MonFactory) -> None:
    """evaluate_average_damage：rhydon 四个普通招式平均打 tapu-lele。"""
    result = scoring.evaluate_average_damage(mon("rhydon"), mon("tapu-lele"), 1.0)
    assert result == pytest.approx(0.33083155999462965)


def test_evaluate_average_damage_ditto_attacker(mon: MonFactory) -> None:
    """evaluate_average_damage：自己是百变怪时先变成对手再算。"""
    result = scoring.evaluate_average_damage(mon("ditto"), mon("tapu-lele"), 1.0)
    assert result == pytest.approx(0.15622618773132513)


def test_evaluate_average_damage_ditto_defender_with_hp_multiple(mon: MonFactory) -> None:
    """evaluate_average_damage：对手是百变怪、血量倍数 2。"""
    result = scoring.evaluate_average_damage(mon("rhydon"), mon("ditto"), 2.0)
    assert result == pytest.approx(0.18823279638948517)


def test_evaluate_received_averages_regular_and_max_moves(mon: MonFactory) -> None:
    """evaluate_received：boss 的普通招式占 0.7、极巨招式占 0.3，各自取平均。"""
    assert scoring.evaluate_received(mon("rhydon"), mon("tapu-lele")) == pytest.approx(
        0.31977007573236194
    )


def test_evaluate_received_same_result_whether_boss_is_dynamaxed(mon: MonFactory) -> None:
    """evaluate_received：boss 已经极巨化时结果和没极巨化一样，函数里两种都算。

    任务文件写的是「对手极巨化时结果按 DYNAMAX_HP 折算」，但 evaluate_received 里没有用到
    DYNAMAX_HP，这里按实际行为写：boss 的 dynamax 字段不影响结果。
    """
    dynamaxed = replace(mon("tapu-lele"), dynamax=True)
    assert scoring.evaluate_received(mon("rhydon"), dynamaxed) == pytest.approx(0.31977007573236194)


def test_evaluate_received_ditto_transforms_into_boss(mon: MonFactory) -> None:
    """evaluate_received：自己是百变怪时先变成对手再算。"""
    assert scoring.evaluate_received(mon("ditto"), mon("tapu-lele")) == pytest.approx(
        0.2327057652012054
    )


def test_transform_ditto_copies_template_but_keeps_ditto_hp_stat(mon: MonFactory) -> None:
    """transform_ditto：名字和 HP 种族值保留百变怪的，其余能力、招式照抄，每个招式 5 PP。"""
    ditto, template = mon("ditto"), mon("tapu-lele")
    result = scoring.transform_ditto(ditto, template)
    assert result.name_id == "ditto"
    assert result.base_stats == (48, 85, 75, 130, 115, 95)
    assert result.moves == template.moves[:4]
    assert result.pp == [5, 5, 5, 5]
    assert result.type_ids == template.type_ids
    assert result.ability_name_id == template.ability_name_id
    assert result.hp == template.hp


def test_dynamax_hp_matches_config_dynamax_hp() -> None:
    """DYNAMAX_HP 和 GameConfig.dynamax_hp 一样是 1.9。"""
    assert scoring.DYNAMAX_HP == GameConfig.dynamax_hp == 1.9


# ---- damage 里天气、场地、特性的倍率 ----
#
# 用同一个自制的物理招式（威力 80、命中 1.0）：攻击方是 rhydon 改成格斗系、没有特性，
# 防守方是 chansey 改成一般系、没有特性。每种情况算出伤害，除以没有任何加成（晴朗、无场地、
# 普通招式）时的伤害，得到倍率。倍率就是游戏里的规则，这里逐条核对 damage 实现的这些倍率。

Changes = dict[str, Any]


def custom_damage(
    mon: MonFactory,
    move: Changes | None = None,
    attacker: Changes | None = None,
    defender: Changes | None = None,
    field: Field | None = None,
) -> float:
    """自制招式对 chansey 的伤害，move、attacker、defender 是要改的字段。"""
    base_move = replace(
        mon("rhydon").moves[0],
        name_id="test-move",
        type_id="normal",
        category="physical",
        base_power=80.0,
        accuracy=1.0,
        is_spread=False,
        correction_factor=1.0,
    )
    use = replace(base_move, **(move or {}))
    own = replace(
        mon("rhydon"),
        **{
            "moves": (use,),
            "type_ids": ["fighting"],
            "ability_name_id": "none",
            **(attacker or {}),
        },
    )
    target = replace(
        mon("chansey"),
        **{"type_ids": ["normal"], "ability_name_id": "none", **(defender or {})},
    )
    return scoring.damage(own, 0, target, field or Field())


def multiplier(
    mon: MonFactory,
    move: Changes | None = None,
    attacker: Changes | None = None,
    defender: Changes | None = None,
    field: Field | None = None,
) -> float:
    """这种情况的伤害，除以同一类别、同一威力的普通招式在晴朗无场地时的伤害。"""
    category = (move or {}).get("category", "physical")
    plain = custom_damage(mon, {"category": category})
    return custom_damage(mon, move, attacker, defender, field) / plain


@pytest.mark.parametrize(
    ("move", "weather", "expected"),
    [
        ({"name_id": "solar-beam", "type_id": "grass"}, "sunlight", 2.0),
        ({"name_id": "thunder", "type_id": "electric"}, "sunlight", 0.5 / 0.7),
        ({"name_id": "hurricane", "type_id": "flying"}, "sunlight", 0.5 / 0.7),
        ({"name_id": "weather-ball"}, "sunlight", 3.0),
        ({"type_id": "fire"}, "sunlight", 1.5),
        ({"type_id": "water"}, "sunlight", 0.5),
        ({"name_id": "solar-beam", "type_id": "grass"}, "rain", 0.5),
        ({"name_id": "thunder", "type_id": "electric"}, "rain", 1 / 0.7),
        ({"name_id": "weather-ball"}, "rain", 3.0),
        ({"type_id": "water"}, "rain", 1.5),
        ({"type_id": "fire"}, "rain", 0.5),
        ({"name_id": "solar-beam", "type_id": "grass"}, "hail", 0.5),
        ({"name_id": "blizzard", "type_id": "ice"}, "hail", 1 / 0.7),
        ({"name_id": "weather-ball"}, "hail", 2.0),
        ({"name_id": "solar-beam", "type_id": "grass"}, "sandstorm", 0.5),
        ({"name_id": "weather-ball"}, "sandstorm", 2.0),
    ],
    ids=[
        "sunlight-solar-beam",
        "sunlight-thunder",
        "sunlight-hurricane",
        "sunlight-weather-ball",
        "sunlight-fire",
        "sunlight-water",
        "rain-solar-beam",
        "rain-thunder",
        "rain-weather-ball",
        "rain-water",
        "rain-fire",
        "hail-solar-beam",
        "hail-blizzard",
        "hail-weather-ball",
        "sandstorm-solar-beam",
        "sandstorm-weather-ball",
    ],
)
def test_damage_weather_multiplier(
    mon: MonFactory, move: Changes, weather: str, expected: float
) -> None:
    """damage：各种天气对各种招式的倍率（日照火招 1.5、水招 0.5，下雨反过来，日光束、雷、飓风、暴风雪、天气球的变化）。"""
    assert multiplier(mon, move, field=Field(weather=weather)) == pytest.approx(expected)


def test_damage_weather_ball_without_weather_is_normal_type(mon: MonFactory) -> None:
    """damage：晴朗时天气球按一般系算，数据里写的属性（火）不起作用。"""
    fire_ball = custom_damage(mon, {"name_id": "weather-ball", "type_id": "fire"})
    normal_ball = custom_damage(mon, {"name_id": "weather-ball", "type_id": "normal"})
    assert fire_ball == pytest.approx(normal_ball)


@pytest.mark.parametrize(
    ("move", "attacker", "terrain", "expected"),
    [
        ({"type_id": "electric"}, None, "electric", 1.3),
        ({"type_id": "grass"}, None, "grassy", 1.3),
        ({"type_id": "psychic"}, None, "psychic", 1.3),
        ({"name_id": "terrain-pulse"}, None, "electric", 1.95),
        ({"name_id": "expanding-force", "type_id": "psychic"}, None, "psychic", 1.95),
        ({"type_id": "dragon"}, None, "misty", 0.5),
        ({"name_id": "terrain-pulse"}, None, "misty", 1.5),
        ({"name_id": "rising-voltage", "type_id": "electric"}, None, "electric", 2.6),
        (
            {"type_id": "electric"},
            {"type_ids": ["flying"], "ability_name_id": "levitate"},
            "electric",
            1.0,
        ),
    ],
    ids=[
        "electric-terrain-electric-move",
        "grassy-terrain-grass-move",
        "psychic-terrain-psychic-move",
        "electric-terrain-terrain-pulse",
        "psychic-terrain-expanding-force",
        "misty-terrain-dragon-move",
        "misty-terrain-terrain-pulse",
        "electric-terrain-rising-voltage",
        "electric-terrain-levitating-attacker-gets-no-boost",
    ],
)
def test_damage_terrain_multiplier(
    mon: MonFactory, move: Changes, attacker: Changes | None, terrain: str, expected: float
) -> None:
    """damage：各种场地对各种招式的倍率，飘浮的飞行系攻击方不在地面上，吃不到场地加成。"""
    result = multiplier(mon, move, attacker=attacker, field=Field(terrain=terrain))
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("ability", "expected"),
    [("aerilate", 1.2), ("refrigerate", 1.2), ("galvanize", 1.2), ("pixilate", 1.2)],
)
def test_damage_skin_abilities_turn_normal_moves_into_typed_moves(
    mon: MonFactory, ability: str, expected: float
) -> None:
    """damage：-皮肤类特性把一般系招式变成飞行、冰、电、妖精系，威力 1.2 倍（对一般系对手属性相克都是 1）。"""
    result = multiplier(mon, attacker={"ability_name_id": ability})
    assert result == pytest.approx(expected)


def test_damage_normalize_turns_other_moves_into_normal(mon: MonFactory) -> None:
    """damage：适应性（normalize）把火系招式变成一般系，威力 1.2 倍。"""
    result = multiplier(mon, {"type_id": "fire"}, attacker={"ability_name_id": "normalize"})
    assert result == pytest.approx(1.2)


def test_damage_fairy_aura_on_attacker_boosts_fairy_moves(mon: MonFactory) -> None:
    """damage：攻击方有妖精气场时妖精系招式 1.33 倍。"""
    result = multiplier(mon, {"type_id": "fairy"}, attacker={"ability_name_id": "fairy-aura"})
    assert result == pytest.approx(1.33)


def test_damage_dark_aura_on_defender_boosts_dark_moves(mon: MonFactory) -> None:
    """damage：防守方有暗黑气场时恶系招式也是 1.33 倍。"""
    result = multiplier(mon, {"type_id": "dark"}, defender={"ability_name_id": "dark-aura"})
    assert result == pytest.approx(1.33)


@pytest.mark.parametrize(
    ("move", "defender_ability", "expected"),
    [
        ({"type_id": "ground"}, "levitate", 0.0),
        ({"name_id": "thousand-arrows", "type_id": "ground"}, "levitate", 1.0),
        ({"type_id": "water"}, "water-absorb", -1.0),
        ({"type_id": "water"}, "storm-drain", -1.0),
        ({"type_id": "water"}, "dry-skin", -1.0),
        ({"type_id": "fire"}, "flash-fire", -1.0),
        ({"type_id": "fire"}, "fluffy", 2.0),
        ({"type_id": "fire"}, "dry-skin", 2.0),
        ({"type_id": "fire"}, "thick-fat", 0.5),
        ({"type_id": "fire"}, "heatproof", 0.5),
        ({"type_id": "grass"}, "sap-sipper", -1.0),
        ({"type_id": "electric"}, "volt-absorb", -1.0),
        ({"type_id": "electric"}, "lightning-rod", -1.0),
        ({"type_id": "electric"}, "motor-drive", -1.0),
        ({"type_id": "ice"}, "thick-fat", 0.5),
    ],
)
def test_damage_defender_ability_multiplier(
    mon: MonFactory, move: Changes, defender_ability: str, expected: float
) -> None:
    """damage：防守方的特性对招式属性的倍率：免疫 0、吸收变成 -1（打过去反而回血）、2 倍、一半。"""
    result = multiplier(mon, move, defender={"ability_name_id": defender_ability})
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("attacker_ability", "move", "defender_ability"),
    [
        ("mold-breaker", {"type_id": "ground"}, "levitate"),
        ("turboblaze", {"type_id": "water"}, "water-absorb"),
        ("teravolt", {"type_id": "electric"}, "volt-absorb"),
    ],
)
def test_damage_mold_breaker_family_ignores_defender_ability(
    mon: MonFactory, attacker_ability: str, move: Changes, defender_ability: str
) -> None:
    """damage：破格类特性（mold-breaker、turboblaze、teravolt）无视防守方的免疫、吸收特性，倍率是 1。"""
    result = multiplier(
        mon,
        move,
        attacker={"ability_name_id": attacker_ability},
        defender={"ability_name_id": defender_ability},
    )
    assert result == pytest.approx(1.0)


def test_damage_thousand_arrows_ignores_flying_type_immunity(mon: MonFactory) -> None:
    """damage：千箭齐发（thousand-arrows）打飞行系不受「地面打飞行没效果」影响，倍率 1。"""
    move = {"name_id": "thousand-arrows", "type_id": "ground"}
    assert multiplier(mon, move, defender={"type_ids": ["flying"]}) == pytest.approx(1.0)
    assert multiplier(mon, {"type_id": "ground"}, defender={"type_ids": ["flying"]}) == 0.0


def test_damage_iron_fist_boosts_punching_moves_only(mon: MonFactory) -> None:
    """damage：铁拳（iron-fist）让拳类招式 1.2 倍，别的招式不变。"""
    attacker = {"ability_name_id": "iron-fist"}
    assert multiplier(mon, {"name_id": "mach-punch"}, attacker=attacker) == pytest.approx(1.2)
    assert multiplier(mon, attacker=attacker) == pytest.approx(1.0)


def test_damage_strong_jaw_boosts_biting_moves(mon: MonFactory) -> None:
    """damage：强壮之颚（strong-jaw）让咬类招式 1.5 倍。"""
    result = multiplier(mon, {"name_id": "crunch"}, attacker={"ability_name_id": "strong-jaw"})
    assert result == pytest.approx(1.5)


def test_damage_burn_halves_physical_but_not_special(mon: MonFactory) -> None:
    """damage：烧伤时物理招式减半，特殊招式不变。"""
    assert multiplier(mon, attacker={"status": "burn"}) == pytest.approx(0.5)
    assert multiplier(mon, {"category": "special"}, attacker={"status": "burn"}) == pytest.approx(
        1.0
    )


def test_damage_accuracy_scales_damage(mon: MonFactory) -> None:
    """damage：命中 0.5 的招式伤害是命中 1.0 的一半。"""
    half = custom_damage(mon, {"accuracy": 0.5})
    assert half / custom_damage(mon) == pytest.approx(0.5)


def test_damage_spread_move_with_multiple_targets_is_three_quarters(mon: MonFactory) -> None:
    """damage：范围招式打多个目标时 0.75 倍，单体招式不受影响。"""
    spread = replace(mon("rhydon").moves[0], is_spread=True)
    own = replace(mon("rhydon"), moves=(spread,))
    target = mon("chansey")
    single = scoring.damage(own, 0, target, Field(), False)
    several = scoring.damage(own, 0, target, Field(), True)
    assert several / single == pytest.approx(0.75)


def test_damage_body_press_uses_attackers_defense(mon: MonFactory) -> None:
    """damage：身体压制（body-press）按自己的防御算，不是攻击。"""
    pressed = custom_damage(mon, {"name_id": "body-press", "type_id": "fighting"})
    plain = custom_damage(mon, {"type_id": "fighting"})
    assert pressed == pytest.approx(1.741472350230415)
    assert plain == pytest.approx(1.8656013824884796)


def test_damage_foul_play_uses_defenders_attack(mon: MonFactory) -> None:
    """damage：欺诈（foul-play）按对手的攻击算。"""
    foul = custom_damage(mon, {"name_id": "foul-play", "type_id": "dark"})
    plain = custom_damage(mon, {"type_id": "dark"})
    assert foul == pytest.approx(0.10307142857142856)
    assert plain == pytest.approx(0.6218671274961598)


@pytest.mark.parametrize("name_id", ["psyshock", "psystrike"])
def test_damage_psyshock_and_psystrike_hit_defense_not_special_defense(
    mon: MonFactory, name_id: str
) -> None:
    """damage：精神冲击、精神击破是特殊招式，但打的是对手的防御，比普通特殊招式伤害高。"""
    special = custom_damage(mon, {"name_id": name_id, "type_id": "psychic", "category": "special"})
    plain = custom_damage(mon, {"type_id": "psychic", "category": "special"})
    assert special == pytest.approx(0.26857680491551456)
    assert plain == pytest.approx(0.05527018633540373)


def test_damage_sandstorm_raises_rock_types_special_defense(mon: MonFactory) -> None:
    """damage：沙暴时岩石系对手的特防是 1.5 倍，特殊招式伤害变小。"""
    rock = {"type_ids": ["rock"]}
    clear = custom_damage(mon, {"category": "special"}, defender=rock)
    sandstorm = custom_damage(
        mon, {"category": "special"}, defender=rock, field=Field(weather="sandstorm")
    )
    assert clear == pytest.approx(0.027635093167701866)
    assert sandstorm == pytest.approx(0.01915752242926156)
