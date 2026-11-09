"""一局冒险的运行状态快照。"""

from typing import Literal, TypedDict


class MapNode(TypedDict):
    """路线图上的一个节点。"""

    col: int
    type: str


class Maps(TypedDict):
    """整张路线图。"""

    type: Literal["2x3", "3x2", "2x2"]
    rows: dict[str, list[MapNode]]
    route: list[list[int]]
    current_index: int


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
