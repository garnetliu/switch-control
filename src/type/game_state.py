from typing import TypedDict

from .map import Maps


class GameStateSnapshot(TypedDict):
    """写进 YAML 的一局状态。"""

    boss: str
    lock_path: bool
    seed: int | None
    rental_pool: list[str]
    candidates: list[str]
    maps: Maps | None
    lock_pokemon_index: int | None
    lock_results: list[bool]
    path_results: list[bool]
    dynite_ore: int
    team: list[tuple[str, float]]
    num_caught: int
    caught: list[str]
    faints: list[int]
    route_score: float
    balls: dict[str, int]
    step: str
    started: float
