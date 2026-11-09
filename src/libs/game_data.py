"""游戏数据：data/ 里新代码用到的数据文件。"""

import json
import pickle
from typing import Any

from type import Boss

from .game_config import GameConfig


class GameData:
    """加载 data/ 里的数据文件。"""

    def __init__(self, config: GameConfig):
        self._config = config
        self._directory = config.data_dir
        self._boss_pokemon: dict[str, Boss] | None = None
        self._lair_rows_cache: list[list] | None = None
        self._rental_pokemon_cache: dict[str, dict] | None = None
        self._rental_name_ids_cache: dict[int, str] | None = None
        self._form_name_ids_cache: dict[tuple[int, int], str] | None = None
        self._boss_matchups_cache: dict[str, dict[str, float]] | None = None
        self._rental_scores_cache: dict[str, float] | None = None
        self._type_icons_cache: dict[str, Any] | None = None

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

    def lair_rows(self) -> list[list]:
        """极巨大冒险的遭遇表。"""
        lair_rows = self._lair_rows_cache
        if lair_rows is None:
            lair_rows = self._load("lair_pokemon.json")["rows"]
            self._lair_rows_cache = lair_rows
        return lair_rows

    def name_id(self, species: int, form: int) -> str:
        """把游戏里的 species/form 转成项目数据里的 name_id。"""
        name_id = self._form_name_ids().get((species, form))
        if name_id is None and form == 0:
            name_id = self._rental_name_ids().get(species)
        if name_id is None or name_id not in self.boss_matchups():
            raise ValueError(f"没有 species={species}, form={form} 对应的首领相性数据")
        return name_id

    def rental_pokemon(self) -> dict[str, dict]:
        """租借宝可梦，name_id 到完整数据。"""
        rental_pokemon = self._rental_pokemon_cache
        if rental_pokemon is None:
            rental_pokemon = self._load("rental_pokemon.json")
            self._rental_pokemon_cache = rental_pokemon
        return rental_pokemon

    def _rental_name_ids(self) -> dict[int, str]:
        rental_name_ids = self._rental_name_ids_cache
        if rental_name_ids is None:
            rental_name_ids = {
                pokemon["id_num"]: name
                for name, pokemon in self.rental_pokemon().items()
            }
            self._rental_name_ids_cache = rental_name_ids
        return rental_name_ids

    def _form_name_ids(self) -> dict[tuple[int, int], str]:
        """数据文件里没有 species/form，用 lair_pokemon 的招式反推形态对应的 name_id。"""
        form_name_ids = self._form_name_ids_cache
        if form_name_ids is None:
            rental_moves = {
                frozenset(
                    move["id_num"] for move in pokemon["moves"] if move["id_num"]
                ): name
                for name, pokemon in self.rental_pokemon().items()
            }
            form_name_ids = {}
            for row in self.lair_rows():
                species, form = row[:2]
                moves = frozenset(move for move in row[6:10] if move)
                name = rental_moves.get(moves)
                if not row[2] and form and name is not None:
                    form_name_ids[(species, form)] = name
            self._form_name_ids_cache = form_name_ids
        return form_name_ids

    def type_icons(self) -> dict[str, Any]:
        """路线图上的属性图标模板：{属性: 单通道图}。"""
        type_icons = self._type_icons_cache
        if type_icons is None:
            type_icons = pickle.loads(
                (self._directory / "type_icons.pickle").read_bytes()
            )
            self._type_icons_cache = type_icons
        return type_icons

    def boss_matchups(self) -> dict[str, dict[str, float]]:
        """租借宝可梦对每个传说的相性：{租借宝可梦: {传说: 分数}}。"""
        boss_matchups = self._boss_matchups_cache
        if boss_matchups is None:
            boss_matchups = self._load("boss_matchup_LUT.json")
            self._boss_matchups_cache = boss_matchups
        return boss_matchups

    def rental_scores(self) -> dict[str, float]:
        """租借宝可梦对其他租借宝可梦的平均相性：{租借宝可梦: 分数}。"""
        rental_scores = self._rental_scores_cache
        if rental_scores is None:
            rental_scores = self._load("rental_pokemon_scores.json")
            self._rental_scores_cache = rental_scores
        return rental_scores

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((self._directory / name).read_text(encoding="utf-8"))
