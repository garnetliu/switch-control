from typing import TypedDict

from .map import Maps


class GameStateSnapshot(TypedDict):
    """写进 YAML 的一局状态。"""

    boss: str
    lock_path: bool
    seed: int | None
    maps: Maps | None
    lock_pokemon_index: int | None
    lock_results: list[bool]
    dynite_ore: int
    team: list[tuple[str, float]]
    step: str
