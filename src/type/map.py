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
