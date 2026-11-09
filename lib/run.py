"""一局极巨大冒险的状态：选的宝可梦、队友、路线图。

同一时间只有一局：用 start 开新的一局，用 get 取当前这一局。
状态用 save 写进状态文件，用 load 读出来。keep path（重置游戏回到同一个种子）时，
下一局拿它来核对画面、沿用上一局的结果。
"""

import json
import os
import time
from dataclasses import replace
from typing import Any, ClassVar

from config.paths import STATE_FILE
from lib import data
from typedefs.battle import Field
from typedefs.path import BossNode, TypeMatch
from typedefs.pokemon import Pokemon

# 路线图有 5 层：起点、第 1 层 2 个、第 2 层 4 个、第 3 层 4 个、首领
START_ROW, FIRST_ROW, SECOND_ROW, THIRD_ROW, BOSS_ROW = range(5)


class Run:
    # 第 2 层四个节点在屏幕上的纵向间距（像素）对应的路线形状，数值是别人量出来的标准值
    PATH_TYPES: ClassVar[dict[int, str]] = {135: "2x2", 180: "2x3", 65: "3x2"}

    # 每种路线形状里，第 1、2 层的每个节点能走到下一层的哪几列：{(层, 列): (下一层的列, ...)}
    LINKS: ClassVar[dict[str, dict[tuple[int, int], tuple[int, ...]]]] = {
        "2x3": {
            (FIRST_ROW, 0): (0, 1),
            (FIRST_ROW, 1): (1, 2, 3),
            (SECOND_ROW, 0): (0, 1, 2),
            (SECOND_ROW, 1): (0, 1, 2),
            (SECOND_ROW, 2): (2, 3),
            (SECOND_ROW, 3): (2, 3),
        },
        "3x2": {
            (FIRST_ROW, 0): (0, 1, 2),
            (FIRST_ROW, 1): (2, 3),
            (SECOND_ROW, 0): (0, 1),
            (SECOND_ROW, 1): (0, 1),
            (SECOND_ROW, 2): (0, 1),
            (SECOND_ROW, 3): (1, 2, 3),
        },
        "2x2": {
            (FIRST_ROW, 0): (0, 1),
            (FIRST_ROW, 1): (2, 3),
            (SECOND_ROW, 0): (0, 1),
            (SECOND_ROW, 1): (1, 2, 3),
            (SECOND_ROW, 2): (1, 2, 3),
            (SECOND_ROW, 3): (1, 2, 3),
        },
    }

    def __init__(self, boss: str):
        """boss: 要找的传说宝可梦的 name_id，例如 "xerneas"。不在数据里抛 ValueError。"""
        if boss not in data.boss_pokemon():
            raise ValueError(f"不认识的传说宝可梦: {boss}")
        self.boss = boss
        # 自己的宝可梦，还没选就是 None
        self.pokemon: Pokemon | None = None
        # 三个队友
        self.team: list[Pokemon] = []
        # 已经出现过的宝可梦，之后不会再作为对手出现
        self.encountered: set[str] = set()
        self.path_type: str | None = None
        # seed 对应的普通遭遇宝可梦，按路线图层和列排列
        self.path_opponents: dict[int, list[str]] = {}
        self.target_path: list[BossNode] = []
        # 现在走到目标路线上的第几个节点，0 是起点
        self.current_index = 0
        # 还剩几条命，濒死 4 次这一局就结束了
        self.lives = 4
        # 已经抓到几只
        self.num_caught = 0
        # 抓到的宝可梦，按抓的顺序
        self.caught: list[str] = []
        # 出发时的自己和队友（_member 的结果），由 record_start 记下。keep path 时下一局沿用的是出发时的队伍，
        # 不是一局结束时的（中途会抓到、会被研究员换掉）
        self.start_members: list[dict[str, Any]] = []
        # 扔完球之后各种球还剩几个：{球名: 个数}，读不出的不记
        self.balls: dict[str, int] = {}
        # 下面这些只用来写每局结束时的战报
        # 本次启动的第几局
        self.round = 0
        # 目标路线的得分
        self.path_score: float | None = None
        # 每场对战倒下了几次：{节点序号: 次数}
        self.battle_faints: dict[int, int] = {}
        # 每只抓到的宝可梦闪光框占比的最高值：(资料页上的名字, 最高值)，按查的顺序
        self.shiny_peaks: list[tuple[str, float]] = []
        # 这一局存下的战果截图
        self.screenshots: list[str] = []
        # 在哪个节点从研究员那里换来了哪只：{节点序号: name_id}
        self.scientist: dict[int, str] = {}
        # 每个节点遇到的对手：{节点序号: name_id}
        self.opponents: dict[int, str] = {}
        # 下面是当前这场对战的状态，每场开始时用 start_battle 重置
        # 对手，还没认出来是 None
        self.opponent: Pokemon | None = None
        # 极巨化还剩几回合：-1 这场还没有人极巨化，0 这场已经极巨化过了
        self.dynamax_turns = -1
        self.field = Field()
        # 下一局要不要沿用这一局的结果（keep path），由一局结束时的步骤决定
        self.keep_path = False
        # 这一局的冒险 seed，用来判断下一局是不是同一张图
        self.seed: int | None = None
        # 锁定这张图之后每一局是赢是输，用来判断要不要解锁
        self.lock_results: list[bool] = []
        # 这一局开始的时间（time.time()）
        self.started = time.time()
        # 三只可选的租借宝可梦，顺序和屏幕上一致；选中的是第几个
        self.candidates: list[str] = []
        # 租借界面出现过的所有候选，包括选走后补入的宝可梦
        self.rental_pool: list[str] = []
        self.selection: int | None = None
        # keep path 时上一局的状态（to_dict 的结果），用来校验画面、沿用结果；没有就是 None
        self.plan: dict[str, Any] | None = None
        self.rows: list[list[BossNode | None]] = [
            [BossNode("START", START_ROW, 0)],
            [None] * 2,
            [None] * 4,
            [None] * 4,
            [BossNode(boss, BOSS_ROW, 0)],
        ]

    @property
    def start_node(self) -> BossNode:
        node = self.rows[START_ROW][0]
        assert node is not None
        return node

    def start_battle(self) -> None:
        """开始一场新的对战：对手还没认出来，没有人极巨化过，场地恢复正常。"""
        self.opponent = None
        self.dynamax_turns = -1
        self.field = Field()
        if self.pokemon is not None:
            self.pokemon.dynamax = False

    @property
    def current_node(self) -> BossNode:
        """现在所在的节点。"""
        return self.target_path[self.current_index]

    def next_fork_offset(self) -> int:
        """下一个岔路口要把光标往右移几格：下一个目标节点在当前节点的后继里排第几。

        已经走到目标路线的终点抛 IndexError。
        """
        if self.current_index + 1 >= len(self.target_path):
            raise IndexError("已经走到目标路线的终点，没有岔路可选")
        return self.current_node.downstream.index(self.target_path[self.current_index + 1])

    def advance(self) -> None:
        """走到目标路线上的下一个节点。已经走到终点抛 IndexError。"""
        if self.current_index + 1 >= len(self.target_path):
            raise IndexError("已经走到目标路线的终点")
        self.current_index += 1

    def row_type_sets(self, row: int) -> list[set[str]] | None:
        """这一层每一列可能是哪些属性：seed 里这一层遇到的宝可梦的属性。

        读路线图时用来核对认出来的标签，岔路口认标签时用来放宽匹配。数据不全时返回 None。
        """
        names = self.path_opponents.get(row, [])
        rentals = data.rental_pokemon()
        if len(names) != 4 or any(name not in rentals for name in names):
            return None
        return [set(rentals[name].type_ids) for name in names]

    def update_paths(self, row: int, matches: list[TypeMatch]) -> None:
        """记下某一层读到的各节点属性。

        读完第 2 层时，用节点的纵向间距判断路线形状；读完第 3 层时，连好所有节点。
        """
        self.rows[row] = [
            BossNode(match.type_id, row, col, match) for col, match in enumerate(matches)
        ]
        if row == SECOND_ROW:
            ys = [match.location[1] for match in matches]
            spread = max(ys) - min(ys)
            closest = min(self.PATH_TYPES, key=lambda standard: abs(standard - spread))
            self.path_type = self.PATH_TYPES[closest]
        if row == THIRD_ROW:
            self._link_nodes()

    def record_start(self) -> None:
        """记下出发时的自己和队友。"""
        assert self.pokemon is not None
        self.start_members = [_member(member) for member in [self.pokemon, *self.team]]

    def path_name(self) -> str:
        """目标路线中间三个节点的属性，例如 "fairy-water-normal"。"""
        return "-".join(node.name for node in self.target_path[1:-1])

    def to_dict(self) -> dict[str, Any]:
        """这一局的状态，只含能写进 JSON 的值。宝可梦只记 name_id 和血量。"""
        start = self.start_members or (
            [_member(member) for member in [self.pokemon, *self.team]] if self.pokemon else []
        )
        rows = {
            str(row): [
                [node.match.type_id, node.match.score, list(node.match.location)]
                for node in self.rows[row]
            ]
            for row in (FIRST_ROW, SECOND_ROW, THIRD_ROW)
            if all(node is not None and node.match is not None for node in self.rows[row])
        }
        return {
            "boss": self.boss,
            "seed": self.seed,
            "keep_path": self.keep_path,
            "lock_results": self.lock_results,
            "candidates": self.candidates,
            "rental_pool": self.rental_pool,
            "selection": self.selection,
            # 出发时的队伍，没记下（还没出发）就是现在的
            "pokemon": start[0] if start else None,
            "team": start[1:],
            "encountered": sorted(self.encountered),
            "caught": self.caught,
            "rows": rows,
            "path_opponents": {str(row): names for row, names in self.path_opponents.items()},
            "target_path": [[node.row, node.col] for node in self.target_path],
            "path_score": self.path_score,
            "scientist": {str(index): name_id for index, name_id in self.scientist.items()},
            "opponents": {str(index): name_id for index, name_id in self.opponents.items()},
            "plan": self.plan,
        }

    def restore_team(self, state: dict[str, Any], full_hp: bool) -> None:
        """从 to_dict 的结果还原自己的宝可梦和队友。full_hp 为 True 时血量都记为满。"""
        pokemon = state["pokemon"]
        self.pokemon = _restore_member(pokemon, full_hp) if pokemon is not None else None
        self.team = [_restore_member(raw, full_hp) for raw in state["team"]]
        self.encountered.update(raw["name_id"] for raw in [state["pokemon"], *state["team"]] if raw)

    def restore_paths(self, state: dict[str, Any]) -> None:
        """从 to_dict 的结果还原路线图和目标路线，路线形状和节点连接照读到时的方式重新算。"""
        for row, matches in sorted(state["rows"].items()):
            self.update_paths(
                int(row), [TypeMatch(type_id, score, tuple(loc)) for type_id, score, loc in matches]
            )
        self.target_path = [self.rows[row][col] for row, col in state["target_path"]]
        self.path_score = state.get("path_score")

    def paths(self, truncate: bool = False) -> list[list[BossNode]]:
        """从起点到首领的所有路线。truncate 为 True 时去掉起点和首领，只留中间三个节点。"""
        paths = self.start_node.all_paths()
        return [path[1:-1] for path in paths] if truncate else paths

    def _link_nodes(self) -> None:
        if self.path_type is None:
            raise RuntimeError("还没读第 2 层，不知道路线形状")
        first, second, third = (self.rows[row] for row in (FIRST_ROW, SECOND_ROW, THIRD_ROW))
        boss = self.rows[BOSS_ROW][0]
        assert boss is not None
        self.start_node.downstream = list(first)
        layers = {FIRST_ROW: (first, second), SECOND_ROW: (second, third)}
        for (row, col), next_cols in self.LINKS[self.path_type].items():
            this_row, next_row = layers[row]
            this_row[col].downstream = [next_row[next_col] for next_col in next_cols]
        for node in third:
            node.downstream = [boss]


_current: Run | None = None
# 本次启动开了几局
_rounds = 0


def start(boss: str, plan: dict[str, Any] | None = None) -> Run:
    """开新的一局，替换掉之前那一局。boss 不在数据里抛 ValueError。

    plan: keep path 时上一局的状态（load 的结果），这一局用它校验画面、沿用结果。
    """
    global _current, _rounds
    _rounds += 1
    _current = Run(boss)
    _current.round = _rounds
    if plan is not None:
        # 上一局自己的 plan 用不到了，不带过来，免得状态文件一层层套下去
        _current.plan = {**plan, "plan": None, "seed": None}
        # 上一局的 seed 拿来和这局比较，比较完这一局会用自己的
        _current.seed = plan.get("seed")
        # 沿用锁定的图，这一局一开始就是锁定的：中途出错停下时状态文件里也还是锁定，
        # 下次启动接着刷同一张图（真机上中途崩溃过一次，锁就丢了）
        _current.keep_path = True
        _current.lock_results = list(plan.get("lock_results", []))
    return _current


def get() -> Run:
    """取当前这一局。还没调用 start 会抛 RuntimeError。"""
    if _current is None:
        raise RuntimeError("还没有开始一局")
    return _current


def save() -> None:
    """把当前这一局写进状态文件。先写临时文件再替换，写到一半退出也不会留下半个文件。"""
    STATE_FILE.parent.mkdir(exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(get().to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, STATE_FILE)


def clear() -> None:
    """删掉状态文件，下一局从头开始：不沿用任何结果，keep path 的锁定也清掉。"""
    STATE_FILE.unlink(missing_ok=True)


def load() -> dict[str, Any] | None:
    """读状态文件，没有就返回 None。"""
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _member(pokemon: Pokemon) -> dict[str, Any]:
    return {"name_id": pokemon.name_id, "hp": pokemon.hp}


def _restore_member(raw: dict[str, Any], full_hp: bool) -> Pokemon:
    """_member 的反向：数据里那只宝可梦的副本，血量按记下的，full_hp 为 True 时记为满。"""
    return replace(data.rental_pokemon()[raw["name_id"]], hp=1.0 if full_hp else raw["hp"])
