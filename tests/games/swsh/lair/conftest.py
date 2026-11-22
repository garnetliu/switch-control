"""极巨大冒险测试共用的 fixture：固定了手写名单和打分参数的配置、数据、基准 seed 的 Lair。

GameConfig 里的已抓名单（lair_caught）、第一次抽数的上限和各项打分参数以后会改，
测试里用子类把它们固定成现在的值，期望值就不会跟着配置变。
"""

import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.lair import Lair

# 超梦基准图的 seed，见 game_config.py 里 boss_faint_half 的注释
SEED = 3076008315599927110


class FixedConfig(GameConfig):
    """已抓名单（还能遇到的神兽 21 只）、第一次抽数的上限、打分和极巨化轮换的参数都固定。"""

    lair_caught = (
        "tapu-fini",
        "xerneas",
        "tapu-koko",
        "solgaleo",
        "mewtwo",
        "tapu-bulu",
        "tornadus-incarnate",
        "tapu-lele",
    )
    lair_first_draw_top = 20
    dynamax_turns = 3
    dynamax_wait = 3
    dynamax_hp = 1.9
    stage_sure_damage = 1.0
    stage_likely_damage = 0.6
    stage_own_rate = 1.0
    stage_team_rate = 1.4
    stage_base_rate = 0.05
    stage_max_turns = 10
    stage_weak_turns = 1.58
    boss_kill_attack = 1.0
    boss_turn_rate = 0.68
    boss_turns = 3
    boss_max_turns = 10
    boss_faint_half = 0.8
    boss_faint_power = 4
    boss_hurt_scale = 3.0
    boss_hurt_exponent = 3
    stage_weights = (0.3, 0.2, 0.1)
    no_swap_probability = 1 / 8


@pytest.fixture(scope="session")
def fixed_config() -> FixedConfig:
    """固定了名单和参数的配置。"""
    return FixedConfig()


@pytest.fixture(scope="session")
def fixed_data(fixed_config: FixedConfig) -> GameData:
    """用固定了名单的配置读 data/swsh/，只读。"""
    return GameData(fixed_config)


@pytest.fixture
def lair0(fixed_data: GameData) -> Lair:
    """基准 seed，extra 是 0。"""
    return Lair(fixed_data, SEED, 0)
