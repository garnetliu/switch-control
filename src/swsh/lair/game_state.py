"""一局冒险的运行状态，用 YAML 保存快照，用于 keep path 和断线后恢复。"""

import logging
import os
import time

from ruamel.yaml import YAML

from .game_config import GameConfig
from .map import Maps
from .snapshot import GameStateSnapshot


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
                path_results=[],
                dynite_ore=0,
                team=[],
                num_caught=0,
                caught=[],
                faints=[],
                route_score=0.0,
                balls={},
                started=0.0,
            )
        self.boss: str = state.get("boss", self._config.boss)  # boss 可能在 config 里没设置
        # 锁定了这张图（keep path）：select_pokemon 决定锁定时设成 True，解锁或带走闪光时设回 False。
        # join 看到 seed 一样并且锁定了才沿用路线，崩溃或手动重启时 seed 也一样，但不算 keep path
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
        # 锁定这张图以来每一局的胜负，锁定的那一局算第 1 局，用来判断要不要解锁
        self.path_results: list[bool] = state.get("path_results", [])
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
        # 这一局开始的时间（time.time()），join 一开始记下
        self.started: float = state.get("started", 0.0)

    @property
    def lives(self) -> int:
        """还剩几条命：4 减去这一局已经打完的各关倒下的次数。"""
        return 4 - sum(self.faints)

    def start_run(self) -> None:
        """join 开始时调用：记下这一局的开始时间，清掉上一局打到一半的数据（崩溃后重跑也一样）。"""
        self.started = time.time()
        self.num_caught = 0
        self.caught = []
        self.faints = []
        self.team = []
        if self.maps is not None:
            self.maps["current_index"] = 0
        self.save()

    def check_keep(self, boss: str, seed: int) -> bool:
        """读到 boss 和 seed 后调用：判断 keep path 存着的初始宝可梦和路线能不能用。

        锁定了这张图并且 boss、seed 都对得上才沿用，返回 True；有一个对不上（崩溃、手动重启、
        换了 boss 等意外情况）就清掉 keep path 的数据，换了 boss 还要清掉胜负记录，返回 False。
        """
        if self.lock_path and boss == self.boss and seed == self.seed:
            return True
        if boss != self.boss:
            self.lock_results = []
        self.boss = boss
        self.seed = seed
        self.lock_path = False
        self.path_results = []
        self.rental_pool = []
        self.candidates = []
        self.lock_pokemon_index = None
        self.maps = None
        self.route_score = 0.0
        self.save()
        return False

    def finish_run(self, took_shiny: bool) -> tuple[bool, str]:
        """select_pokemon 结束时调用：记下这一局的胜负，算锁定还是解锁，返回 (锁定, 写进战报的锁定情况)。

        带走了闪光不锁定。环境变量 KEEP_PATH 不是 1 时也不锁定（keep path 要重启游戏，
        下次和科学家说话要付极矿石）。
        锁定的图：只看锁定以来的胜负，见 _should_unlock；赢了的局不管用了多久、倒下几次都保持。
        没锁定的图：打赢、倒下次数和用时都在范围内，就锁定这张图。
        """
        config = self._config
        won = self.num_caught == 4
        faints = 4 - self.lives
        minutes: float = (time.time() - self.started) / 60
        self.lock_results.append(won)
        if took_shiny:
            self.lock_path = False
            lock = "带走了闪光，不锁定"
        elif os.environ.get("KEEP_PATH") != "1":
            self.lock_path = False
            lock = "没有开启 KEEP_PATH，不锁定"
        elif self.lock_path:
            self.path_results.append(won)
            self.lock_path = not self._should_unlock()
            rate = self.path_results.count(True) / len(self.path_results) * 100
            lock = (
                f"这张图锁定后打了 {len(self.path_results)} 局，胜率 {rate:.0f}%，"
                f"{'继续锁定' if self.lock_path else '解锁'}"
            )
        else:
            self.lock_path = (
                won and faints <= config.lock_max_faints and minutes <= config.lock_max_minutes
            )
            # 锁定的这一局是按打赢锁的，算这张图的第 1 局
            self.path_results = [True] if self.lock_path else []
            lock = "锁定这张图" if self.lock_path else "不锁定"
        self.save()
        logging.info(f"倒下 {faints} 次，用时 {minutes:.1f} 分钟，{lock}")
        return self.lock_path, lock

    def save(self) -> None:
        """把整个状态写进 YAML；先写临时文件再替换。"""
        self._config.game_state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self._config.game_state_file.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as file:
            file.write("# 一局冒险的运行状态，机器写入\n")
            self._yaml.dump(self._to_dict(), file)
        os.replace(temp, self._config.game_state_file)

    def _should_unlock(self) -> bool:
        """这张锁定的图是不是该扔了。

        打满 lock_window_rounds 局之前只看输的局数，输 lock_early_fails 局就扔；
        打满之后看锁定以来的总胜率，低于 lock_min_win_rate 就扔。
        """
        results = self.path_results
        if len(results) < self._config.lock_window_rounds:
            return results.count(False) >= self._config.lock_early_fails
        return results.count(True) / len(results) < self._config.lock_min_win_rate

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
            path_results=self.path_results,
            dynite_ore=self.dynite_ore,
            team=self.team,
            num_caught=self.num_caught,
            caught=self.caught,
            faints=self.faints,
            route_score=self.route_score,
            balls=self.balls,
            started=self.started,
        )
