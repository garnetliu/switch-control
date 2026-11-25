"""剑盾测试共用的 fixture：读一次 src/control_switch/games/swsh/data/ 的真实数据，每次取宝可梦都给一份复制。"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.pokemon import Pokemon


@pytest.fixture(scope="session")
def data() -> GameData:
    """用默认配置读 src/control_switch/games/swsh/data/ 的数据，整个测试过程只读一次，测试里不要改它。"""
    return GameData(GameConfig())


@pytest.fixture
def mon(data: GameData) -> Callable[[str], Pokemon]:
    """按 name_id 取一只宝可梦的复制，测试里可以随便改（极巨化、PP、血量）。"""

    def factory(name_id: str) -> Pokemon:
        return replace(data.pokemon_object(name_id))

    return factory
