"""一局冒险的运行状态，用 YAML 保存快照，用于 keep path 和断线后恢复。"""

import os
from typing import Any, Literal, TypedDict

from ruamel.yaml import YAML

from config.paths import GAME_STATE_FILE


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


class GameState:
    def __init__(self, boss: str):
        self._yaml = YAML()
        self.boss = boss
        # keep path
        self.lock_path = False
        self.seed: int | None = None
        # 地图：type（2x3 / 3x2 / 2x2）、每层节点（col + type）、选中的路线、当前走到第几个
        self.maps: Maps | None = None
        # 选的租借宝可梦在三个候选里的下标
        self.lock_pokemon_index: int | None = None
        # 锁定图的每局胜负
        self.lock_results: list[bool] = []
        # 极巨矿数量，读取和减少的逻辑以后做
        self.dynite_ore = 0
        # 队伍名字和 hp，第一个是自己
        self.team: list[tuple[str, float]] = []
        # 当前所在的步骤
        self.step = ""

    def save(self) -> None:
        """把整个状态写进 YAML；先写临时文件再替换。"""
        GAME_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = GAME_STATE_FILE.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as file:
            file.write("# 一局冒险的运行状态，机器写入\n")
            self._yaml.dump(self._to_dict(), file)
        os.replace(temp, GAME_STATE_FILE)

    def load(self) -> None:
        """从 YAML 读回快照；文件不存在时保持默认值。"""
        if not GAME_STATE_FILE.exists():
            return
        with GAME_STATE_FILE.open(encoding="utf-8") as file:
            state = self._yaml.load(file)
        if state:
            self._from_dict(state)

    def _to_dict(self) -> dict[str, Any]:
        """当前状态的快照，set 存成排序后的数组。"""
        return {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in vars(self).items()
        }

    def _from_dict(self, state: dict[str, Any]) -> None:
        """把快照写回当前对象，只覆盖类里已有的属性；set 还原成 set。"""
        for key, value in state.items():
            if hasattr(self, key):
                current = getattr(self, key)
                setattr(self, key, set(value) if isinstance(current, set) else value)
