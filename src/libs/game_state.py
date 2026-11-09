"""一局冒险的运行状态，用 YAML 保存快照，用于 keep path 和断线后恢复。"""

import os

from ruamel.yaml import YAML

from type import GameStateSnapshot, Maps


class GameState:
    def __init__(self, config):
        self._config = config
        self._yaml = YAML()
        state = self._load()
        if state is None:
            state = GameStateSnapshot(
                boss=self._config.boss,
                lock_path=False,
                seed=None,
                maps=None,
                lock_pokemon_index=None,
                lock_results=[],
                dynite_ore=0,
                team=[],
                step="",
            )
        self.boss = state.get("boss", self._config.boss)  # boss 可能在 config 里没设置
        # keep path
        self.lock_path = state.get("lock_path", False)
        self.seed: int | None = state.get("seed")
        # 地图：type（2x3 / 3x2 / 2x2）、每层节点（col + type）、选中的路线、当前走到第几个
        self.maps: Maps | None = state.get("maps")
        # 选的租借宝可梦在三个候选里的下标
        self.lock_pokemon_index: int | None = state.get("lock_pokemon_index")
        # 锁定图的每局胜负
        self.lock_results: list[bool] = state.get("lock_results", [])
        # 极巨矿数量，读取和减少的逻辑以后做
        self.dynite_ore = state.get("dynite_ore", 0)
        # 队伍名字和 hp，第一个是自己
        self.team: list[tuple[str, float]] = [
            tuple(item) for item in state.get("team", [])
        ]
        # 当前所在的步骤
        self.step = state.get("step", "")

    def clear(self) -> None:
        """清空这一局的状态和保存的快照。"""
        self._config.game_state_file.unlink(missing_ok=True)
        self.__init__(self._config)

    def set_seed(self, seed: int, boss: str | None = None) -> None:
        """设置这一局的 seed。seed 或 boss 和已保存的不一样时先清空状态。"""
        boss = self.boss if boss is None else boss
        if self.seed != seed or self.boss != boss:
            self.clear()
        self.seed = seed
        self.boss = boss

    def save(self) -> None:
        """把整个状态写进 YAML；先写临时文件再替换。"""
        self._config.game_state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self._config.game_state_file.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as file:
            file.write("# 一局冒险的运行状态，机器写入\n")
            self._yaml.dump(self._to_dict(), file)
        os.replace(temp, self._config.game_state_file)

    def _load(self) -> GameStateSnapshot | None:
        """读 YAML 快照并返回；文件不存在时返回 None。"""
        if not self._config.game_state_file.exists():
            return None
        with self._config.game_state_file.open(encoding="utf-8") as file:
            state = self._yaml.load(file)
        return state if state else None

    def _to_dict(self) -> GameStateSnapshot:
        """当前状态的结构化快照。"""
        return GameStateSnapshot(
            boss=self.boss,
            lock_path=self.lock_path,
            seed=self.seed,
            maps=self.maps,
            lock_pokemon_index=self.lock_pokemon_index,
            lock_results=self.lock_results,
            dynite_ore=self.dynite_ore,
            team=self.team,
            step=self.step,
        )
