"""路线图相关的共用类型。"""

from dataclasses import dataclass, field
from typing import NamedTuple


class TypeMatch(NamedTuple):
    """在路线图上认出一个节点的属性。"""

    type_id: str
    # 模板匹配度，0 到 1
    score: float
    # 图标在截取区域里的位置 (x, y)，像素
    location: tuple[int, int]


@dataclass(eq=False)
class BossNode:
    """路线图上的一个节点（一场对战）。"""

    name: str
    row: int
    col: int
    match: TypeMatch | None = None
    downstream: list["BossNode"] = field(default_factory=list)

    def __str__(self) -> str:
        return self.name

    def all_paths(self) -> list[list["BossNode"]]:
        """从这个节点出发到首领的所有路线，每条都包含这个节点。"""
        if not self.downstream:
            return [[self]]
        return [[self, *path] for node in self.downstream for path in node.all_paths()]
