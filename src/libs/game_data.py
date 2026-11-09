"""游戏数据：data/ 里新代码用到的数据文件。"""

import json
from pathlib import Path
from typing import Any

from type import Boss


class GameData:
    """加载 data/ 里的数据文件。"""

    def __init__(self, config, directory: Path | None = None):
        self._config = config
        self._directory = directory or config.data_dir
        self._boss_pokemon: dict[str, Boss] | None = None

    def boss_pokemon(self) -> dict[str, Boss]:
        """传说宝可梦，name_id 到名字。"""
        boss_pokemon = self._boss_pokemon
        if boss_pokemon is None:
            raw = self._load("boss_pokemon.json")
            boss_pokemon = {
                name_id: Boss(pokemon["names"][self._config.language], pokemon["id_num"])
                for name_id, pokemon in raw.items()
            }
            self._boss_pokemon = boss_pokemon
        return boss_pokemon

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((self._directory / name).read_text(encoding="utf-8"))
