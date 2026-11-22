"""游戏数据：data/swsh/ 里的数据文件。"""

import json
import logging
from typing import Any

import cv2

from swsh.pokemon import Move, Pokemon

from .boss import Boss
from .game_config import GameConfig


class GameData:
    """加载 data/swsh/ 里的数据文件。"""

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
        self._rental_matchups_cache: dict[str, dict[str, float]] | None = None
        self._rental_damages_cache: dict[str, dict[str, list[float]]] | None = None
        self._boss_attack_defense_cache: dict[str, dict[str, list[float]]] | None = None
        self._max_move_rate_cache: dict[str, float] | None = None
        self._type_icons_cache: dict[str, Any] | None = None
        self._boss_data_cache: dict[str, dict] | None = None
        self._lair_events_cache: dict[str, dict[str, dict[str, list[str]]]] | None = None
        self._rental_objects_cache: dict[str, Pokemon] | None = None
        self._boss_objects_cache: dict[str, Pokemon] | None = None

    def first_draw_top(self) -> int:
        """一局开头第一次抽数的上限：还没抓到的神兽只数 − 1，见 GameConfig.lair_caught。"""
        top = self._config.lair_first_draw_top
        return len(self.lair_legends()) - 1 if top is None else top

    def lair_legends(self) -> list[str]:
        """这个存档现在还能遇到的神兽（name_id），按遭遇表的顺序：去掉遇不到的和已经抓到的。"""
        by_id = {boss.id_num: name_id for name_id, boss in self.boss_pokemon().items()}
        # 遭遇表里基格尔德写的是 718，首领数据里是 50% 形态的编号
        by_id[718] = "zygarde-50"
        config = self._config
        gone = {*config.lair_other_version, *config.lair_caught}
        if not config.lair_ultra_beasts_unlocked:
            gone.update(config.lair_ultra_beasts)
        names = [by_id[row[0]] for row in self.lair_rows() if row[2]]
        return [name for name in names if name not in gone]

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

        图在 data/swsh/type_icons/属性名.png，都是从真机截图上抠下来的。
        """
        type_icons = self._type_icons_cache
        if type_icons is None:
            type_icons = {
                path.stem: cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                for path in sorted((self._directory / "type_icons").glob("*.png"))
            }
            self._type_icons_cache = type_icons
        return type_icons

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
            # 数据文件里的个体值统一写的 15（上游的默认值）。极巨大冒险里每只有 4 项保底 31，
            # 日志里读到的每一项的中位数是 31，按 31 算
            ivs=(31,) * 6,
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

    def rental_matchups(self) -> dict[str, dict[str, float]]:
        """租借宝可梦两两之间的相性：{进攻的: {防守的: 分数}}。"""
        rental_matchups = self._rental_matchups_cache
        if rental_matchups is None:
            rental_matchups = self._load("rental_matchup_LUT.json")
            self._rental_matchups_cache = rental_matchups
        return rental_matchups

    def rental_damages(self) -> dict[str, dict[str, list[float]]]:
        """租借宝可梦两两之间一回合的伤害：{进攻的: {防守的: [普通, 极巨, 平均]}}，
        进攻的打掉防守方多少比例的血量：没极巨化、极巨化了各用伤害最高的招式，
        平均是普通招式每个用的机会一样（估队友用）。

        用 src/make_lair_damage.py 生成，算法见 scoring.evaluate_damage。
        """
        rental_damages = self._rental_damages_cache
        if rental_damages is None:
            rental_damages = self._load("rental_damage_LUT.json")
            self._rental_damages_cache = rental_damages
        return rental_damages

    def boss_attack_defense(self) -> dict[str, dict[str, list[float]]]:
        """租借宝可梦对每个传说的进攻和挨打：{租借宝可梦: {传说: [普通进攻, 极巨进攻, 挨打]}}。

        进攻是自己最好的招式一回合打掉首领血量的比例，没极巨化和极巨化了各一个；
        挨打是首领平均一回合打掉它血量的比例。
        用 src/make_lair_damage.py 生成。
        """
        table = self._boss_attack_defense_cache
        if table is None:
            table = self._load("boss_attack_defense_LUT.json")
            self._boss_attack_defense_cache = table
        return table

    def max_move_rate(self, name: str) -> float:
        """对手 name 用极巨招式的比例，日志实测（docs/实测-队友出招和对手出手.md）。

        出手不到 10 次的对手没有单独的数，路上的对手用路上的合计，首领用首领的合计。
        """
        rates = self._max_move_rate_cache
        if rates is None:
            rates = self._load("max_move_rate.json")
            self._max_move_rate_cache = rates
        if name in rates:
            return rates[name]
        return rates["首领" if name in self.boss_pokemon() else "路上"]

    def lair_events(self, map_type: str | None, layout: int | None) -> dict[str, list[str]]:
        """这种地图类型、这个布局编号的图，路上已经知道的事件：{位置: [事件]}。

        位置是节点 "层-列"（走到这个节点、打完之后、选岔路之前遇到的；起点是 "0-0"）
        或者一段路 "层-列>层-列"（选完岔路之后、到下一个节点之前遇到的）。
        事件是 scientist（研究员）、backpacker（背包客）、berry（树果）；空列表是走过、什么都没有。
        表里没有的位置是还没走过，不知道。表在 lair_event_LUT.json 里，程序每走一段就记一次。
        """
        if map_type is None or layout is None:
            return {}
        return self._lair_event_table().get(map_type, {}).get(str(layout), {})

    def record_lair_events(
        self, map_type: str, layout: int, position: str, events: list[str]
    ) -> None:
        """记下这种地图类型、这个布局编号的图上，position 这个位置遇到的事件，写进文件。"""
        table = self._lair_event_table()
        known = table.setdefault(map_type, {}).setdefault(str(layout), {})
        if known.get(position) == events:
            return
        if position in known:
            logging.warning(
                f"路上的事件和以前记的不一样：{map_type} 布局 {layout} 位置 {position}，"
                f"以前是 {known[position]}，这次是 {events}，按这次的记"
            )
        known[position] = events
        path = self._directory / "lair_event_LUT.json"
        path.write_text(
            json.dumps(table, indent=4, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def _lair_event_table(self) -> dict[str, dict[str, dict[str, list[str]]]]:
        table = self._lair_events_cache
        if table is None:
            path = self._directory / "lair_event_LUT.json"
            table = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            self._lair_events_cache = table
        return table

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((self._directory / name).read_text(encoding="utf-8"))
