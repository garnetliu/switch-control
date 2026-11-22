"""control_switch.games.swsh.lair.lair、next_columns、xoroshiro：seed 算出的租借、遭遇、地图和队友。

seed 用 game_config.py 注释里的超梦基准图 3076008315599927110，extra 取 0 和 1 各算一次。
期望值取自搬迁前 swsh.lair.lair 和 libs.xoroshiro 的运行结果。
GameConfig.lair_caught 是手写的已抓名单，以后会改，所以测试里用子类把名单和
lair_first_draw_top 都固定下来，不跟着名单变。
"""

import pytest

from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.lair import MAP_TYPES, Lair
from control_switch.games.swsh.lair.next_columns import next_columns
from control_switch.games.swsh.lair.xoroshiro import Xoroshiro

SEED = 3076008315599927110


@pytest.fixture
def lair1(fixed_data: GameData) -> Lair:
    """基准 seed，extra 是 1。"""
    return Lair(fixed_data, SEED, 1)


def test_candidates_with_extra_0(lair0: Lair) -> None:
    """candidates：extra 为 0 时 6 只租借候选，选宝可梦界面显示前 3 只。"""
    assert lair0.candidates() == [
        "pangoro",
        "galvantula",
        "maractus",
        "cofagrigus",
        "alcremie",
        "absol",
    ]


def test_candidates_with_extra_1(lair1: Lair) -> None:
    """candidates：extra 为 1 时多取了一个随机数，6 只候选全变了。"""
    assert lair1.candidates() == [
        "galvantula",
        "maractus",
        "cofagrigus",
        "nidoqueen",
        "absol",
        "talonflame",
    ]


def test_encounters_with_extra_0(lair0: Lair) -> None:
    """encounters：extra 为 0 时三层的遭遇是 2、4、4 只。"""
    assert lair0.encounters() == {
        "1": ["swoobat", "fraxure"],
        "2": ["beartic", "tauros", "barbaracle", "obstagoon"],
        "3": ["bouffalant", "sneasel", "torkoal", "hitmontop"],
    }


def test_encounters_with_extra_1(lair1: Lair) -> None:
    """encounters：extra 为 1 时三层的遭遇。"""
    assert lair1.encounters() == {
        "1": ["weezing-galar", "beartic"],
        "2": ["tauros", "barbaracle", "obstagoon", "bouffalant"],
        "3": ["sneasel", "torkoal", "hitmontop", "garbodor"],
    }


def test_map_type_with_extra_0(lair0: Lair) -> None:
    """map_type：extra 为 0 时是 2x2。"""
    assert lair0.map_type() == "2x2"


def test_map_type_with_extra_1(lair1: Lair) -> None:
    """map_type：extra 为 1 时是 2x3。"""
    assert lair1.map_type() == "2x3"


def test_layout_with_extra_0(lair0: Lair) -> None:
    """layout：extra 为 0 时路上事件的布局编号是 4。"""
    assert lair0.layout() == 4


def test_layout_with_extra_1(lair1: Lair) -> None:
    """layout：extra 为 1 时路上事件的布局编号是 9。"""
    assert lair1.layout() == 9


def test_boss_with_extra_0(lair0: Lair) -> None:
    """boss：extra 为 0 时选「不指定」的首领是 moltres。"""
    assert lair0.boss() == "moltres"


def test_boss_with_extra_1(lair1: Lair) -> None:
    """boss：extra 为 1 时首领仍是 moltres（第一次抽数在 extra 之前）。"""
    assert lair1.boss() == "moltres"


@pytest.mark.parametrize(
    ("starter", "expected"),
    [
        (0, ["maractus", "galvantula", "cofagrigus"]),
        (1, ["maractus", "cofagrigus", "pangoro"]),
        (2, ["cofagrigus", "galvantula", "pangoro"]),
    ],
)
def test_teammates_with_extra_0(lair0: Lair, starter: int, expected: list[str]) -> None:
    """teammates：extra 为 0，自己选界面上第 0、1、2 只时，三个队友依次拿到的宝可梦。"""
    assert lair0.teammates(starter) == expected


@pytest.mark.parametrize(
    ("starter", "expected"),
    [
        (0, ["maractus", "nidoqueen", "talonflame"]),
        (1, ["nidoqueen", "galvantula", "talonflame"]),
        (2, ["maractus", "galvantula", "talonflame"]),
    ],
)
def test_teammates_with_extra_1(lair1: Lair, starter: int, expected: list[str]) -> None:
    """teammates：extra 为 1，自己选界面上第 0、1、2 只时，三个队友依次拿到的宝可梦。"""
    assert lair1.teammates(starter) == expected


def test_results_are_the_same_when_called_again(lair0: Lair) -> None:
    """同一个 Lair 对象里各个方法重复调用，结果一样（算过的缓存起来）。"""
    first = (lair0.candidates(), lair0.encounters(), lair0.map_type(), lair0.layout())
    second = (lair0.candidates(), lair0.encounters(), lair0.map_type(), lair0.layout())
    assert first == second


def test_fate_catch_without_swapping_lets_a_teammate_take_it(lair0: Lair) -> None:
    """fate：catch 事件、自己不换，队友 2 换上新抓到的。"""
    assert lair0.fate(["catch"], "moltres", [False]) == [2]


def test_fate_catch_with_swapping_means_no_teammate_takes_it(lair0: Lair) -> None:
    """fate：catch 事件、自己换了，结果是 None。"""
    assert lair0.fate(["catch"], "moltres", [True]) == [None]


def test_fate_scientist_gives_a_teammate_a_new_pokemon(lair0: Lair) -> None:
    """fate：scientist 事件，队友 2 换成 emolga。"""
    assert lair0.fate(["scientist"], "moltres", []) == [(2, "emolga")]


def test_fate_scientist_after_catch_without_swapping(lair0: Lair) -> None:
    """fate：先抓到一只自己不换，再遇到研究员，后面的随机数不一样，队友 2 换成 slowbro。"""
    result = lair0.fate(["catch", "scientist", "catch"], "moltres", [False, False])
    assert result == [2, (2, "slowbro"), None]


def test_fate_scientist_after_catch_with_swapping(lair0: Lair) -> None:
    """fate：先抓到一只自己换了，再遇到研究员，队友 1 换成 oranguru。"""
    result = lair0.fate(["catch", "scientist", "catch"], "moltres", [True, False])
    assert result == [None, (1, "oranguru"), None]


def test_fate_scientist_nobody_wants_returns_none(lair1: Lair) -> None:
    """fate：scientist 事件，没有队友想要时结果是 None（extra 为 1 的一种走法）。"""
    result = lair1.fate(["catch", "scientist", "catch"], "moltres", [False, False])
    assert result == [2, None, None]


def test_fate_backpacker_returns_none_but_uses_random_numbers(lair0: Lair) -> None:
    """fate：backpacker 事件的结果是 None，但会用掉 3 个随机数：后面研究员的结果和不遇到背包客时不同。"""
    assert lair0.fate(["backpacker"], "moltres", []) == [None]
    assert lair0.fate(["scientist"], "moltres", []) == [(2, "emolga")]
    assert lair0.fate(["backpacker", "scientist"], "moltres", []) == [None, (1, "oranguru")]


def test_fate_backpacker_after_catch_with_and_without_swapping(lair0: Lair) -> None:
    """fate：抓到一只之后遇到背包客再遇到一只，自己换不换会改变后面那只由谁拿走。"""
    swapped = lair0.fate(["backpacker", "catch"], "moltres", [True])
    kept = lair0.fate(["backpacker", "catch"], "moltres", [False])
    assert swapped == [None, None]
    assert kept == [None, 0]


def test_fate_with_empty_schedule_is_empty(lair0: Lair) -> None:
    """fate：没有事件时返回空列表。"""
    assert lair0.fate([], "moltres", []) == []


def test_fate_dual_type_boss_uses_one_random_number_first(lair0: Lair) -> None:
    """fate：首领是双属性的（moltres）先用掉 1 个随机数，单属性的（mewtwo）不用，同样的研究员结果不同。"""
    assert lair0.fate(["scientist"], "moltres", []) == [(2, "emolga")]
    assert lair0.fate(["scientist"], "mewtwo", []) == [None]


def test_map_types_has_all_three_types() -> None:
    """MAP_TYPES：抽到 0、1、2 分别是 2x3、2x2、3x2。"""
    assert MAP_TYPES == {0: "2x3", 1: "2x2", 2: "3x2"}


@pytest.mark.parametrize("map_type", ["2x3", "2x2", "3x2"])
def test_next_columns_from_start_is_first_two_columns(map_type: str) -> None:
    """next_columns：第 0 层（起点）在三种地图上都固定能走到第 1 层的 0、1 两列。"""
    assert next_columns(map_type, 0, 0) == (0, 1)


@pytest.mark.parametrize(
    ("row", "col", "expected"),
    [(1, 1, (1, 2, 3)), (2, 2, (2, 3))],
)
def test_next_columns_2x3(row: int, col: int, expected: tuple[int, ...]) -> None:
    """next_columns：2x3 地图上两个节点能走到的列。"""
    assert next_columns("2x3", row, col) == expected


@pytest.mark.parametrize(
    ("row", "col", "expected"),
    [(1, 0, (0, 1, 2)), (2, 3, (1, 2, 3))],
)
def test_next_columns_3x2(row: int, col: int, expected: tuple[int, ...]) -> None:
    """next_columns：3x2 地图上两个节点能走到的列。"""
    assert next_columns("3x2", row, col) == expected


@pytest.mark.parametrize(
    ("row", "col", "expected"),
    [(1, 1, (2, 3)), (2, 1, (1, 2, 3))],
)
def test_next_columns_2x2(row: int, col: int, expected: tuple[int, ...]) -> None:
    """next_columns：2x2 地图上两个节点能走到的列。"""
    assert next_columns("2x2", row, col) == expected


def test_xoroshiro_next_u32_sequence_for_fixed_seed() -> None:
    """Xoroshiro：种子 1234，连着取 5 个 32 位随机数。"""
    rng = Xoroshiro(1234)
    assert [rng.next_u32() for _ in range(5)] == [
        580742957,
        4067073325,
        312800087,
        1292967996,
        2332399337,
    ]


def test_xoroshiro_state_after_first_number_from_seed_zero() -> None:
    """Xoroshiro：种子 0 的初始状态，以及取一个数之后 s0、s1 的值。"""
    rng = Xoroshiro(0)
    assert (rng.s0, rng.s1) == (0, 0x82A2B175229D6A5B)
    assert rng.next_u32() == 580741723
    assert (rng.s0, rng.s1) == (0x33D793E848C66A5B, 0x53AD4B7054562EA4)


def test_xoroshiro_draw_stays_within_top_for_fixed_seed() -> None:
    """Xoroshiro.draw：种子 1234，上限依次是 2、3、9、1、0、100 时抽到的数。"""
    rng = Xoroshiro(1234)
    assert [rng.draw(top) for top in (2, 3, 9, 1, 0, 100)] == [1, 1, 7, 0, 0, 17]


def test_xoroshiro_draw_retries_values_above_top() -> None:
    """Xoroshiro.draw：抽到的数超过上限就重抽，所以结果从不超过上限。"""
    rng = Xoroshiro(99)
    values = [rng.draw(5) for _ in range(200)]
    assert max(values) <= 5
    assert set(values) == {0, 1, 2, 3, 4, 5}


def test_xoroshiro_seed_is_truncated_to_64_bits() -> None:
    """Xoroshiro：种子只取低 64 位，-1 变成全 1，2 的 64 次方加 5 等于 5。"""
    assert Xoroshiro(-1).s0 == 0xFFFFFFFFFFFFFFFF
    assert Xoroshiro((1 << 64) | 5).s0 == 5
