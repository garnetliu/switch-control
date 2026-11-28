"""孵蛋刷闪几个文件共用的类型。"""

from enum import StrEnum
from typing import NamedTuple


class TeamType(StrEnum):
    """队伍是孵蛋队伍还是拿蛋用的野餐队伍，值和步骤名一样。"""

    HATCH = "hatch"
    FETCH = "fetch"


class Mon(NamedTuple):
    """盒子里读到的一只宝可梦。"""

    name: str
    # 「最棒」的项数；游戏里评定功能没解锁读不到是-1
    best: int
    shiny: bool


class Boxes(NamedTuple):
    """用到的三个相邻的盒子编号。"""

    # 锚点：放亲代和带队宝可梦的盒子
    anchor: int
    # 放蛋的盒子，在锚点后面
    egg: int
    # 放留下来的（闪光）的盒子，在放蛋的盒子后面
    keep: int


# 盒子里光标的位置：("party", 队伍第几行, 0) 或 ("slots", 行, 列)
Cursor = tuple[str, int, int]
