"""control_switch.games.swsh.lair.game_config：GameConfig.data_dir 指向包里的数据目录。"""

from pathlib import Path

import pytest

from control_switch.config import BaseConfig
from control_switch.games import swsh
from control_switch.games.swsh.lair.game_config import GameConfig

DATA_JSON_FILES = [
    "boss_attack_defense_LUT.json",
    "boss_matchup_LUT.json",
    "boss_pokemon.json",
    "lair_event_LUT.json",
    "lair_pokemon.json",
    "max_move_rate.json",
    "rental_damage_LUT.json",
    "rental_matchup_LUT.json",
    "rental_pokemon_scores.json",
    "rental_pokemon.json",
]


def test_data_dir_is_inside_swsh_package() -> None:
    """data_dir 等于 swsh 包目录下的 data，类型是 Path。"""
    assert isinstance(GameConfig.data_dir, Path)
    assert GameConfig.data_dir == Path(swsh.__file__).parent / "data"


def test_data_dir_exists() -> None:
    """data_dir 是磁盘上存在的目录。"""
    assert GameConfig.data_dir.is_dir()


@pytest.mark.parametrize("name", DATA_JSON_FILES)
def test_data_dir_has_json_file(name: str) -> None:
    """data_dir 里有这个 json 文件。"""
    assert (GameConfig.data_dir / name).is_file()


def test_data_dir_has_type_icons() -> None:
    """data_dir 里有 type_icons 目录。"""
    assert (GameConfig.data_dir / "type_icons").is_dir()


def test_data_dir_not_under_repo_root_data() -> None:
    """data_dir 不在仓库根目录的 data/ 下面。"""
    assert not GameConfig.data_dir.is_relative_to(BaseConfig.root / "data")
