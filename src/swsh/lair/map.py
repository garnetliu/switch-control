from typing import Literal, TypedDict


class MapNode(TypedDict):
    """路线图上的一个节点。"""

    # 这一层里的第几列，从 0 开始
    col: int
    # 节点属性。读地图前先用遭遇宝可梦的第一属性占位，读完后换成图上认出的属性
    type: str
    # seed 决定的、走到这个节点会遇到的宝可梦 name_id
    encounter: str


class Maps(TypedDict):
    """整张路线图，选完初始宝可梦后由 seed 和画面上的地图一起填出来。"""

    # 路线图形状，看第 2 层节点的纵向间距判断；还没读地图时是 None
    type: Literal["2x3", "3x2", "2x2"] | None
    # 按层排列的节点，key 是 "1"、"2"、"3"，每层分别有 2、4、4 个节点
    rows: dict[str, list[MapNode]]
    # 选中的路线，按顺序记录每个节点的 [层, 列]
    route: list[list[int]]
    # 当前走到 route 里的第几个节点，0 是起点
    current_index: int
