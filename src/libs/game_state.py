"""一局冒险的运行状态，用 YAML 保存快照，用于 keep path 和断线后恢复。"""

import os
import time

from ruamel.yaml import YAML

from type import GameStateSnapshot, Maps

from .game_config import GameConfig


class GameState:
    def __init__(self, config: GameConfig):
        self._config = config
        self._yaml = YAML()
        state = self._load()
        if state is None:
            state = GameStateSnapshot(
                boss=self._config.boss,
                lock_path=False,
                seed=None,
                rental_pool=[],
                candidates=[],
                maps=None,
                lock_pokemon_index=None,
                lock_results=[],
                dynite_ore=0,
                team=[],
                num_caught=0,
                caught=[],
                faints=[],
                route_score=0.0,
                balls={},
                step="",
                started=0.0,
            )
        self.boss = state.get("boss", self._config.boss)  # boss 可能在 config 里没设置
        # keep path
        self.lock_path = state.get("lock_path", False)
        self.seed: int | None = state.get("seed")
        # seed 对应的 6 只租借候选；初始界面从里面连续取 3 只，通常是前 3 只
        self.rental_pool: list[str] = state.get("rental_pool", [])
        # 选初始界面从内存读到的 3 只，顺序和屏幕上一致
        self.candidates: list[str] = state.get("candidates", [])
        # 地图：type（2x3 / 3x2 / 2x2）、每层节点（col + type）、选中的路线、当前走到第几个
        self.maps: Maps | None = state.get("maps")
        # 选的租借宝可梦在三个候选里的下标
        self.lock_pokemon_index: int | None = state.get("lock_pokemon_index")
        # 刷这只 boss 以来每一局的胜负，换 boss 才清掉；长度就是战报里的第几轮
        self.lock_results: list[bool] = state.get("lock_results", [])
        # 极巨矿数量，读取和减少的逻辑以后做
        self.dynite_ore = state.get("dynite_ore", 0)
        # 队伍名字和 hp，第一个是自己
        self.team: list[tuple[str, float]] = [tuple(item) for item in state.get("team", [])]
        # 已抓到的数量和顺序
        self.num_caught: int = state.get("num_caught", 0)
        self.caught: list[str] = state.get("caught", [])
        # 这一局每一关倒下了几次，每打完一关加一项，没倒下是 0
        self.faints: list[int] = state.get("faints", [])
        # 这一局路线规划的得分
        self.route_score: float = state.get("route_score", 0.0)
        # 各种球还剩几个：{球名: 数量}
        self.balls: dict[str, int] = state.get("balls", {})
        # 当前所在的步骤
        self.step = state.get("step", "")
        # 这一局开始的时间（time.time()），join 一开始记下
        self.started: float = state.get("started", 0.0)

    @property
    def lives(self) -> int:
        """还剩几条命：4 减去这一局已经打完的各关倒下的次数。"""
        return 4 - sum(self.faints)

    def clear(self, seed: int | None = None, boss: str | None = None) -> None:
        """清空快照，用新的 boss 和 seed 重新初始化并写回文件。

        这一局的开始时间保留；每局的胜负记录不换 boss 就一直保留，换了 boss 才清掉。
        """
        started = self.started
        results = self.lock_results if boss is None or boss == self.boss else []
        self._config.game_state_file.unlink(missing_ok=True)
        self.__init__(self._config)
        self.started = started
        self.lock_results = results
        self.boss = boss if boss else self._config.boss
        self.seed = seed if seed else self.seed
        self.save()

    def new_run(self) -> None:
        """开始新的一局：只清掉这一局的状态，路线、初始宝可梦、球数这些跨局的保留，记下开始时间。"""
        self.num_caught = 0
        self.caught = []
        self.faints = []
        self.team = []
        if self.maps is not None:
            self.maps["current_index"] = 0
        self.started = time.time()
        self.save()

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
            rental_pool=self.rental_pool,
            candidates=self.candidates,
            maps=self.maps,
            lock_pokemon_index=self.lock_pokemon_index,
            lock_results=self.lock_results,
            dynite_ore=self.dynite_ore,
            team=self.team,
            num_caught=self.num_caught,
            caught=self.caught,
            faints=self.faints,
            route_score=self.route_score,
            balls=self.balls,
            step=self.step,
            started=self.started,
        )
