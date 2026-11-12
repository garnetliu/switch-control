"""游戏数据：data/ 里新代码用到的数据文件。"""

import json
import pickle
from typing import Any

import cv2

from type import Boss, Move, Pokemon

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
        self._misc_icons_cache: dict[str, Any] | None = None
        self._boss_data_cache: dict[str, dict] | None = None
        self._rental_objects_cache: dict[str, Pokemon] | None = None
        self._boss_objects_cache: dict[str, Pokemon] | None = None
        self._pokemon_sprites_cache: list[tuple[str, Any]] | None = None

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
                pokemon["id_num"]: name for name, pokemon in self.rental_pokemon().items()
            }
            self._rental_name_ids_cache = rental_name_ids
        return rental_name_ids

    def _form_name_ids(self) -> dict[tuple[int, int], str]:
        """数据文件里没有 species/form，用 lair_pokemon 的招式反推形态对应的 name_id。"""
        form_name_ids = self._form_name_ids_cache
        if form_name_ids is None:
            rental_moves = {
                frozenset(move["id_num"] for move in pokemon["moves"] if move["id_num"]): name
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
        """路线图上的属性图标模板：{属性: 单通道黑白图}，和截图一样是原始大小。

        图在 data/type_icons/属性名.png。还没在真机上抠到的属性，先用老图标缩小得到的临时图，
        抠到之后用 save_type_icon 换掉。
        """
        type_icons = self._type_icons_cache
        if type_icons is None:
            type_icons = {
                path.stem: cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                for path in sorted((self._directory / "type_icons").glob("*.png"))
            }
            self._type_icons_cache = type_icons
        return type_icons

    def collected_type_icons(self) -> set[str]:
        """已经换成真机抠图的属性，名单在 data/type_icons/collected.json。"""
        path = self._directory / "type_icons" / "collected.json"
        return set(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else set()

    def save_type_icon(self, type_id: str, icon: Any) -> None:
        """把真机上抠到的属性图标存下来，换掉原来的那一张，并记进已收集的名单。"""
        directory = self._directory / "type_icons"
        cv2.imwrite(str(directory / f"{type_id}.png"), icon)
        collected = sorted(self.collected_type_icons() | {type_id})
        (directory / "collected.json").write_text(
            json.dumps(collected, indent=2) + "\n", encoding="utf-8"
        )
        self.type_icons()[type_id] = icon

    def pokemon_sprites(self) -> list[tuple[str, Any]]:
        """租借宝可梦的精灵图：(name_id, 图)，用来认队伍栏。"""
        sprites = self._pokemon_sprites_cache
        if sprites is None:
            sprites = pickle.loads((self._directory / "pokemon_sprites.pickle").read_bytes())
            self._pokemon_sprites_cache = sprites
        return sprites

    def misc_icons(self) -> dict[str, Any]:
        """战斗界面用的图标模板：{名字: BGR 图}。"""
        misc_icons = self._misc_icons_cache
        if misc_icons is None:
            misc_icons = {
                path.stem: cv2.imread(str(path))
                for path in (self._directory / "misc_icons").glob("*.png")
            }
            self._misc_icons_cache = misc_icons
        return misc_icons

    def pokemon_data(self, name_id: str) -> dict:
        """按 name_id 取完整数据，先在租借表里找，再找首领表。"""
        rental = self.rental_pokemon()
        if name_id in rental:
            return rental[name_id]
        boss_data = self._boss_data_cache
        if boss_data is None:
            boss_data = self._load("boss_pokemon.json")
            self._boss_data_cache = boss_data
        return boss_data[name_id]

    def rental_pokemon_objects(self) -> dict[str, Pokemon]:
        """租借宝可梦，name_id 到 Pokemon 对象。"""
        pokemon = self._rental_objects_cache
        if pokemon is None:
            pokemon = {
                name_id: self._pokemon(raw) for name_id, raw in self.rental_pokemon().items()
            }
            self._rental_objects_cache = pokemon
        return pokemon

    def boss_pokemon_objects(self) -> dict[str, Pokemon]:
        """首领宝可梦，name_id 到 Pokemon 对象。"""
        pokemon = self._boss_objects_cache
        if pokemon is None:
            raw = self._load("boss_pokemon.json")
            pokemon = {name_id: self._pokemon(data) for name_id, data in raw.items()}
            self._boss_objects_cache = pokemon
        return pokemon

    def pokemon_object(self, name_id: str) -> Pokemon:
        """按 name_id 取 Pokemon 对象，先在租借表里找，再找首领表。"""
        rental = self.rental_pokemon_objects()
        if name_id in rental:
            return rental[name_id]
        return self.boss_pokemon_objects()[name_id]

    @staticmethod
    def _pokemon(raw: dict) -> Pokemon:
        return Pokemon(
            id_num=raw["id_num"],
            name_id=raw["name_id"],
            names=raw["names"],
            ability_name_id=raw["ability_name_id"],
            abilities=raw["abilities"],
            type_ids=raw["type_ids"],
            types=raw["types"],
            base_stats=GameData._as_tuple(raw["base_stats"]),
            moves=tuple(GameData._move(move) for move in raw["moves"]),
            max_moves=tuple(GameData._move(move) for move in raw["max_moves"]),
            level=raw["level"],
            ivs=GameData._as_tuple(raw["ivs"]),
            evs=GameData._as_tuple(raw["evs"]),
            nature=GameData._as_tuple(raw["nature"]),
        )

    @staticmethod
    def _move(raw: dict) -> Move:
        return Move(
            id_num=raw["id_num"],
            name_id=raw["name_id"],
            names=raw["names"],
            type_id=raw["type_id"],
            category=raw["category"],
            base_power=raw["base_power"],
            accuracy=raw["accuracy"],
            pp=raw["PP"],
            effect=raw["effect"],
            probability=raw["probability"],
            is_spread=raw["is_spread"],
            correction_factor=raw["correction_factor"],
        )

    @staticmethod
    def _as_tuple(value: Any) -> tuple:
        return tuple(value["py/tuple"]) if isinstance(value, dict) else tuple(value)

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
