"""孵蛋刷闪几个文件共用的类型。"""

from enum import StrEnum


class TeamType(StrEnum):
    """队伍是孵蛋队伍还是拿蛋用的野餐队伍，值和步骤名一样。"""

    HATCH = "hatch"
    FETCH = "fetch"
