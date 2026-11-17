"""找极巨大冒险里首发分加路线分最高的 seed：python src/find_lair_seed.py [--workers 4]。

只做计算，不连 Switch。先算出理论上的最高分，再不停地试随机 seed，每找到一个更高分的就打印出来，
一直保留见过的最高分；找到理论最高分或者按 Ctrl-C 时停下，打印最后的结果。

- 首发分：和 join._assign_new_starter 一样，选宝可梦界面的 3 只里（租借评分³ × 首领相性²）开 5 次方
  最高的那只。
- 路线分：和 join._assign_route 一样，这张图上得分最高的那条路线的得分。
- 地图类型由 seed 算出来，见 docs/实测-地图类型由seed决定.md。

约 2% 的 seed 在真机上开头会多用掉 1 个随机数（见 Lair.__init__），那种 seed 写进游戏后租借和路线
都和这里算的不一样。留存的 138 张图里，这种 seed 开头的 draw(27) 抽到的都是 26 或 27，抽到 0 到 25 的
132 张没有一张是这样的（见 docs/实测-地图类型由seed决定.md），所以这里不要开头抽到 26、27 的 seed。
"""

import argparse
import multiprocessing
import time

import numpy as np

from libs.xoroshiro import Xoroshiro
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.next_columns import next_columns

CONFIG = GameConfig()
DATA = GameData(CONFIG)
BOSS = CONFIG.boss
ROWS = DATA.lair_rows()
SIZE = len(ROWS)
MATCHUPS = DATA.boss_matchups()
RENTAL_SCORES = DATA.rental_scores()
# 地图类型：Lair._picks 里 draw(9) 前面那一次 draw(2) 的值
MAP_TYPES = {0: "2x3", 1: "2x2", 2: "3x2"}
# 路线上第一、二、三关的权重，和 join._assign_route 一样
WEIGHTS = (1.0, 1.1, 1.2)
# 一批试多少个 seed；还没有找到任何结果时先用小的一批，免得第一批全都要完整算
BATCH = 500_000
FIRST_BATCH = 50_000
# 开头的 draw(27) 抽到这个值以上的 seed 不要
FIRST_DRAW_RISKY = 26
# 每次抽取只看洗牌后的前 ORDER 张，前 ORDER 张都不能用（首领或者已经抽过）的 seed 不要了
ORDER = 3
# 每次抽取最多用 MT 的前 OUTPUTS 个随机数
OUTPUTS = 16


def starter_score(name: str) -> float:
    return (RENTAL_SCORES[name] ** 3 * MATCHUPS[name][BOSS] ** 2) ** (1 / 5)


def _row_name(row: list) -> str | None:
    """遭遇表里一行的 name_id，首领那些行不会被抽到，返回 None。"""
    return None if row[2] else DATA.name_id(row[0], row[1])


NAMES = [_row_name(row) for row in ROWS]
FLAGGED = np.array([row[2] for row in ROWS], dtype=bool)
# 同一只宝可梦（species 和 form 一样）在表里第一次出现的下标，用来判断抽没抽过
_first: dict[tuple[int, int], int] = {}
CANON = np.array([_first.setdefault((row[0], row[1]), index) for index, row in enumerate(ROWS)])
STARTER = np.array([starter_score(name) if name else 0.0 for name in NAMES])
MATCH = np.array([MATCHUPS[name][BOSS] if name else 0.0 for name in NAMES])
EXTRA_NEXT = np.array([row[4] != row[5] for row in ROWS], dtype=bool)


def _paths(map_type: str) -> list[tuple[int, int, int]]:
    """这种地图上所有路线经过的三列，顺序和 join._assign_route 一样。"""
    paths = [[(0, 0)]]
    for row in (1, 2, 3):
        paths = [[*path, (row, col)] for path in paths for col in next_columns(map_type, *path[-1])]
    return [(path[1][1], path[2][1], path[3][1]) for path in paths]


PATHS = {map_type: _paths(map_type) for map_type in MAP_TYPES.values()}


def theoretical_best() -> tuple[float, str, list[str]]:
    """理论最高分：(合计, 首发, 路线上的三只)。

    首发和路线上的三只不能重复。路线上的三只放在哪一列都行，所以取首领相性最高的三只，
    相性越高的放在越后面的关卡。
    """
    names = [name for name in NAMES if name]
    best = (0.0, "", [])
    for starter in names:
        others = sorted(
            (name for name in names if name != starter), key=lambda n: MATCHUPS[n][BOSS]
        )
        route = others[-3:]
        total = starter_score(starter) + sum(
            weight * MATCHUPS[name][BOSS] for weight, name in zip(WEIGHTS, route, strict=True)
        )
        if total > best[0]:
            best = (total, starter, route)
    return best


def evaluate(seed: int) -> dict:
    """按程序的算法完整算一个 seed：租借、首发、地图类型、路线和得分。"""
    lair = Lair(DATA, seed)
    candidates, encounters = lair.candidates(), lair.encounters()
    scores = [starter_score(name) for name in candidates[:3]]
    starter = scores.index(max(scores))
    rng = Xoroshiro(seed)
    rng.draw(27)
    for _ in range(4):
        rng.next_u32()
    for threshold in (2, 1, 0):
        rng.draw(2)
        if threshold:
            rng.next_u32()
    map_type = MAP_TYPES[rng.draw(2)]
    route_scores = [
        sum(
            weight * MATCHUPS[encounters[str(row)][col]][BOSS]
            for weight, row, col in zip(WEIGHTS, (1, 2, 3), path, strict=True)
        )
        for path in PATHS[map_type]
    ]
    path = PATHS[map_type][route_scores.index(max(route_scores))]
    return {
        "seed": seed,
        "candidates": candidates,
        "starter": starter,
        "starter_score": scores[starter],
        "map_type": map_type,
        "encounters": encounters,
        "route": [encounters[str(row)][col] for row, col in zip((1, 2, 3), path, strict=True)],
        "route_score": max(route_scores),
        "total": scores[starter] + max(route_scores),
    }


# 下面是一批 seed 一起算的版本，算法和 Xoroshiro、Lair._picks 一样，用来快速筛掉分数不够的

U = np.uint64
MASK32 = U(0xFFFFFFFF)
MATCH_MAX = float(MATCH.max())


class _Rng:
    """一批 Xoroshiro。"""

    def __init__(self, s0: np.ndarray, s1: np.ndarray | None = None):
        self.s0 = s0.copy()
        self.s1 = np.full(len(s0), 0x82A2B175229D6A5B, dtype=U) if s1 is None else s1.copy()

    def take(self, keep: np.ndarray) -> "_Rng":
        return _Rng(self.s0[keep], self.s1[keep])

    def next(self, only: np.ndarray | None = None) -> np.ndarray:
        """每个都取一个随机数；给了 only 就只有 only 是 True 的往前走。"""
        s0, s1 = self.s0, self.s1
        result = (s0 + s1) & MASK32
        mixed = s1 ^ s0
        new0 = ((s0 << U(24)) | (s0 >> U(40))) ^ mixed ^ (mixed << U(16))
        new1 = (mixed << U(37)) | (mixed >> U(27))
        if only is None:
            self.s0, self.s1 = new0, new1
        else:
            self.s0, self.s1 = np.where(only, new0, s0), np.where(only, new1, s1)
        return result

    def draw(self, top: int) -> np.ndarray:
        mask = U((1 << top.bit_length()) - 1)
        todo = np.ones(len(self.s0), dtype=bool)
        result = np.zeros(len(self.s0), dtype=np.int64)
        while todo.any():
            value = self.next(todo) & mask
            done = todo & (value <= U(top))
            result[done] = value[done]
            todo &= ~done
        return result


def _mt_outputs(seed: np.ndarray) -> list[np.ndarray]:
    """每个 MT 种子的前 OUTPUTS 个随机数的低 9 位。"""
    need: dict[int, np.ndarray] = {}
    state = seed.copy()
    for index in range(397 + OUTPUTS):
        if index:
            state = (U(1812433253) * (state ^ (state >> U(30))) + U(index)) & MASK32
        if index <= OUTPUTS or index >= 397:
            need[index] = state
    outputs = []
    for index in range(OUTPUTS):
        y = (need[index] & U(0x80000000)) | (need[index + 1] & U(0x7FFFFFFF))
        value = need[index + 397] ^ (y >> U(1)) ^ np.where(y & U(1), U(0x9908B0DF), U(0))
        value ^= value >> U(11)
        value ^= (value << U(7)) & U(0x9D2C5680)
        value ^= (value << U(15)) & U(0xEFC60000)
        value ^= value >> U(18)
        outputs.append((value & U(0x1FF)).astype(np.int64))
    return outputs


def _pick(seed: np.ndarray, used: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """一次抽取：返回 (抽到的行的下标, 这个结果能不能用)。

    和 Lair._picks 里的 pick 一样洗牌，但只算洗牌后的前 ORDER 张，取里面第一张不是首领、
    也没抽过的。前 ORDER 张都不行的不往下算，标成不能用。
    """
    outputs = _mt_outputs(seed)
    count = len(seed)
    cursor = np.zeros(count, dtype=np.int64)
    valid = np.ones(count, dtype=bool)
    # 洗牌时换过位置的格子：(位置, 现在放的是哪一行)，后记的盖掉先记的
    moved: list[tuple[np.ndarray, np.ndarray]] = []

    def at(position: np.ndarray) -> np.ndarray:
        value = position.copy()
        for where, row in moved:
            value = np.where(position == where, row, value)
        return value

    order = []
    for index in range(ORDER):
        offset = np.zeros(count, dtype=np.int64)
        done = np.zeros(count, dtype=bool)
        for number, output in enumerate(outputs):
            hit = ~done & (cursor <= number) & (output <= SIZE - 1 - index)
            offset = np.where(hit, output, offset)
            cursor = np.where(hit, number + 1, cursor)
            done |= hit
        valid &= done
        here = np.full(count, index, dtype=np.int64)
        other = here + offset
        here_row, other_row = at(here), at(other)
        moved.append((here, other_row))
        moved.append((other, here_row))
        order.append(other_row)

    chosen = np.full(count, -1, dtype=np.int64)
    for row in order:
        usable = ~FLAGGED[row]
        for previous in used:
            usable &= CANON[row] != previous
        take = (chosen < 0) & usable
        chosen[take] = row[take]
    valid &= chosen >= 0
    return np.maximum(chosen, 0), valid


def scan(seeds: np.ndarray, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """一批 seed 里合计高过 floor 的那些：(seed, 合计)。

    顺序和 Lair._picks 一样。每算完一段就估一下合计的上限（没算到的关卡按相性最高的算），
    上限到不了 floor 的 seed 不往下算。
    """
    rng = _Rng(seeds)
    # 开头抽到 26、27 的 seed 在真机上可能多用掉 1 个随机数，不要
    valid = rng.draw(27) < FIRST_DRAW_RISKY
    used: list[np.ndarray] = []
    layers: list[list[np.ndarray]] = []
    starter = np.zeros(len(seeds))
    kind = np.zeros(len(seeds), dtype=np.int64)

    def pick() -> np.ndarray:
        nonlocal valid
        row, usable = _pick(rng.next(), used)
        used.append(CANON[row])
        valid &= usable
        return row

    def prune() -> None:
        """只留下结果能用、合计上限高过 floor 的 seed。"""
        nonlocal seeds, rng, used, layers, valid, starter, kind
        bound = starter.copy()
        for index, weight in enumerate(WEIGHTS):
            done = index < len(layers)
            bound += weight * (np.maximum.reduce(layers[index]) if done else MATCH_MAX)
        keep = valid & (bound > floor)
        seeds, rng, starter, kind = seeds[keep], rng.take(keep), starter[keep], kind[keep]
        used = [rows[keep] for rows in used]
        layers = [[match[keep] for match in layer] for layer in layers]
        valid = np.ones(len(seeds), dtype=bool)

    for _ in range(3):
        starter = np.maximum(starter, STARTER[pick()])
    prune()
    pick()
    rng.draw(2)
    pick()
    rng.draw(2)
    pick()
    rng.draw(2)
    kind = rng.draw(2)
    rng.draw(9)
    for size in (2, 4, 4):
        layer = []
        for _ in range(size):
            row = pick()
            layer.append(MATCH[row])
            rng.next(EXTRA_NEXT[row])
        layers.append(layer)
        prune()

    route = np.zeros(len(seeds))
    for value, map_type in MAP_TYPES.items():
        best = np.zeros(len(seeds))
        for path in PATHS[map_type]:
            score = sum(
                weight * layer[col]
                for weight, layer, col in zip(WEIGHTS, layers, path, strict=True)
            )
            best = np.maximum(best, score)
        route = np.where(kind == value, best, route)
    total = starter + route
    keep = total > floor
    return seeds[keep], total[keep]


def _scan_batch(floor: float) -> tuple[int, int | None]:
    """试一批随机 seed，返回 (试了多少个, 这一批里合计最高并且高过 floor 的 seed，没有是 None)。"""
    size = BATCH if floor > 0 else FIRST_BATCH
    seeds = np.random.default_rng().integers(0, 2**64, size=size, dtype=np.uint64)
    found, totals = scan(seeds, floor)
    if not len(found):
        return size, None
    return size, int(found[totals.argmax()])


def _describe(result: dict) -> str:
    def name(name_id: str) -> str:
        return DATA.pokemon_object(name_id).name(CONFIG.language)

    candidates = result["candidates"]
    lines = [
        f"seed {result['seed']}",
        f"  合计 {result['total']:.3f} = 首发 {result['starter_score']:.3f} + 路线 {result['route_score']:.3f}",
        f"  首发 {name(candidates[result['starter']])}（第 {result['starter'] + 1} 位）",
        f"  选宝可梦界面的 3 只：{'、'.join(name(n) for n in candidates[:3])}",
        f"  地图 {result['map_type']}，路线 {' → '.join(name(n) for n in result['route'])}",
    ]
    for row, encounters in result["encounters"].items():
        lines.append(f"  第 {row} 层：{'、'.join(name(n) for n in encounters)}")
    return "\n".join(lines)


def main(workers: int) -> None:
    top, top_starter, top_route = theoretical_best()
    print(
        f"首领 {BOSS}，理论最高分 {top:.3f}：首发 {top_starter}，路线 {' → '.join(top_route)}",
        flush=True,
    )
    best: dict | None = None
    tried = 0
    started = reported = time.time()
    with multiprocessing.Pool(workers) as pool:
        pending: list = []
        try:
            while best is None or best["total"] < top - 1e-9:
                floor = best["total"] if best else 0.0
                while len(pending) < workers:
                    pending.append(pool.apply_async(_scan_batch, (floor,)))
                time.sleep(0.05)
                for task in [task for task in pending if task.ready()]:
                    pending.remove(task)
                    size, seed = task.get()
                    tried += size
                    if seed is None:
                        continue
                    result = evaluate(seed)
                    if best is None or result["total"] > best["total"] + 1e-9:
                        best = result
                        minutes = (time.time() - started) / 60
                        print(
                            f"\n试了 {tried / 1e6:.1f} 百万个，{minutes:.1f} 分钟，新的最高分：",
                            flush=True,
                        )
                        print(_describe(best), flush=True)
                if time.time() - reported > 60:
                    reported = time.time()
                    total = f"{best['total']:.3f}" if best else "还没有"
                    print(f"试了 {tried / 1e6:.0f} 百万个，目前最高分 {total}", flush=True)
        except KeyboardInterrupt:
            pool.terminate()
    print(f"\n停止。一共试了 {tried / 1e6:.1f} 百万个，最高分的 seed：")
    print(_describe(best) if best else "还没有找到")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="找极巨大冒险里首发分加路线分最高的 seed")
    parser.add_argument("--workers", type=int, default=4, help="同时用几个进程算，默认 4")
    main(parser.parse_args().workers)
