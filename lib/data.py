"""游戏数据：data/ 里的数据文件和图片资源。每种数据第一次用到时读取，之后复用。"""

import json
import pickle
from functools import cache
from typing import Any

import numpy as np

from config.game import LANGUAGE
from config.paths import DATA_DIR
from tool.check_image import load_template
from type.pokemon import Move, Pokemon


@cache
def rental_pokemon() -> dict[str, Pokemon]:
    """可以租借的宝可梦，name_id 到宝可梦。冒险里的对手和队友也都是它们。"""
    return _load_pokemon("rental_pokemon.json")


@cache
def boss_pokemon() -> dict[str, Pokemon]:
    """传说宝可梦，name_id 到宝可梦。"""
    return _load_pokemon("boss_pokemon.json")


@cache
def boss_matchups() -> dict[str, dict[str, float]]:
    """租借宝可梦对每个传说的相性：{租借宝可梦: {传说: 分数}}。"""
    return _load_json("boss_matchup_LUT.json")


@cache
def rental_scores() -> dict[str, float]:
    """租借宝可梦对其他租借宝可梦的平均相性：{租借宝可梦: 分数}。"""
    return _load_json("rental_pokemon_scores.json")


@cache
def path_scores() -> dict[str, dict[str, float]]:
    """预先算好的路线评分表：{传说: {属性: 分数}}，分数是该属性的租借宝可梦对这个传说的平均相性。

    只支持 tree_depth 为 1 的表，其他深度抛 ValueError。
    """
    raw = _load_json("path_tree.json")
    if raw["tree_depth"] != 1:
        raise ValueError(f"不支持 tree_depth {raw['tree_depth']}，只支持 1")
    return {boss: node["hash_table"] for boss, node in raw["base_node"]["hash_table"].items()}


@cache
def type_icons() -> dict[str, np.ndarray]:
    """属性图标：属性名到二值化的单通道图，用来在路线图上认出每个节点的属性。"""
    return _load_pickle("type_icons.pickle")


@cache
def pokemon_sprites() -> list[tuple[str, np.ndarray]]:
    """租借宝可梦的精灵图：(name_id, 彩色图)，用来在队伍栏里认出队友。"""
    return _load_pickle("pokemon_sprites.pickle")


@cache
def misc_icons() -> dict[str, np.ndarray]:
    """其他图标：文件名（不含 .png）到彩色图，例如战斗菜单的 fight。"""
    return {path.stem: load_template(path) for path in (DATA_DIR / "misc_icons").glob("*.png")}


@cache
def type_names() -> dict[str, str]:
    """属性到它的中文名，从租借宝可梦的数据里收集，例如 {"fire": "火"}。"""
    names: dict[str, str] = {}
    for rental in rental_pokemon().values():
        for type_id, type_name in zip(rental.type_ids, rental.types):
            names.setdefault(type_id, type_name.get(LANGUAGE, type_id))
    return names


def _load_json(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as file:
        return json.load(file)


def _load_pickle(name: str) -> Any:
    with open(DATA_DIR / name, "rb") as file:
        return pickle.load(file)


def _load_pokemon(name: str) -> dict[str, Pokemon]:
    return {name_id: _pokemon(raw) for name_id, raw in _load_json(name).items()}


def _pokemon(raw: dict[str, Any]) -> Pokemon:
    return Pokemon(
        id_num=raw["id_num"],
        name_id=raw["name_id"],
        names=raw["names"],
        ability_name_id=raw["ability_name_id"],
        abilities=raw["abilities"],
        type_ids=raw["type_ids"],
        types=raw["types"],
        base_stats=_as_tuple(raw["base_stats"]),
        moves=tuple(_move(m) for m in raw["moves"]),
        max_moves=tuple(_move(m) for m in raw["max_moves"]),
        level=raw["level"],
        ivs=_as_tuple(raw["ivs"]),
        evs=_as_tuple(raw["evs"]),
        nature=_as_tuple(raw["nature"]),
    )


def _move(raw: dict[str, Any]) -> Move:
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


def _as_tuple(value: Any) -> tuple:
    """数据文件里的元组是 {"py/tuple": [...]}，列表就是普通列表。"""
    return tuple(value["py/tuple"]) if isinstance(value, dict) else tuple(value)
