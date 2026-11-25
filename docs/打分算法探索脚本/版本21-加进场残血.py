"""路线分 = 每场预测倒下相加，每场的预测里加上「进场时队伍最低血量」，残血按 seed 推的队伍一场一场推下去。

倒下模型（泊松回归，拟合时去掉 3076、12873、9960 三张图）：
  M1：E[倒下] = exp(β0 + β1·首领 + β2·log m + β3·log 进场最低血量)
  M2：E[倒下] = exp(β0 + β1·首领 + β2·log r + β3·log(血量 ÷ d) + β4·log 进场最低血量)
  （进场最低血量下限 0.05；不加残血的 M1、M2 一起算，作对比）
残血怎么推：开局四只都是满血；每一场四只各掉「连续回合 (对手战斗血量 ÷ d) × 这只一回合平均掉的血」；
掉到 0 以下算倒下，回来是满血；新换上来的（抓到的、研究员给的）是满血。
先拿日志里的实际进场血量核对一下推得准不准，再排 3076、12873 两组和 9960。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本21-加进场残血.py
逐场表用 版本20-逐场取数.py 生成的（环境变量 FIGHTS_JSON 指定位置）。
"""

import importlib.util
import io
import json
import math
import os
import statistics
import sys
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path, argv=None):
    saved = sys.argv
    sys.argv = [path] + (argv or [])
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
    module = importlib.util.module_from_spec(spec)
    with redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    sys.argv = saved
    return module


v13 = load("v13", "版本13-按实际上场算路线分.py", ["--no-skip"])
fetch = load("fetch", "版本20-逐场取数.py")

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

EXCLUDE = {"3076008315599927110", "12873702124229926581", "9960686445389280169"}
rows = json.load(open(fetch.OUT, encoding="utf-8"))


def x(r, kind, low):
    b = 1.0 if r["stage"] == 3 else 0.0
    hp = math.log(max(0.05, low))
    if kind == "M1":
        return [1, b, math.log(r["m"]), hp]
    if kind == "M1 不加残血":
        return [1, b, math.log(r["m"])]
    if kind == "M2":
        return [1, b, math.log(r["r"]), math.log(r["hp_ratio"]), hp]
    return [1, b, math.log(r["r"]), math.log(r["hp_ratio"])]


def fit(kind):
    train = [r for r in rows if r["seed"] not in EXCLUDE]
    a = np.array([x(r, kind, min(r["hp"])) for r in train])
    y = np.array([r["faints"] for r in train], dtype=float)
    beta = np.zeros(a.shape[1])
    beta[0] = math.log(y.mean())
    for _ in range(100):
        mu = np.exp(a @ beta)
        step = np.linalg.solve((a * mu[:, None]).T @ a, a.T @ (y - mu))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


KINDS = ["M1 不加残血", "M1", "M2 不加残血", "M2"]
BETAS = {kind: fit(kind) for kind in KINDS}
for kind, beta in BETAS.items():
    print(f"{kind}：系数 {np.round(beta, 3).tolist()}")


def step_hp(hp, team, feat):
    """打完这一场以后每只的血量（name → 比例）。"""
    turns = feat["hp_ratio"]
    out = dict(hp)
    for name, per_turn in zip(team, feat["r_members"], strict=True):
        left = hp.get(name, 1.0) - turns * per_turn
        out[name] = left if left > 0 else 1.0
    return out


# 1. 推的残血准不准：拿日志里同一局连续的场核对（用日志里的实际队伍，只推一场）
pairs = []
by_file = {}
for r in rows:
    by_file.setdefault(r["file"], []).append(r)
for fights in by_file.values():
    fights.sort(key=lambda r: r["stage"])
    for a, b in zip(fights, fights[1:]):
        if b["stage"] != a["stage"] + 1 or a["faints"]:
            continue
        hp = dict(zip(a["team"], a["hp"], strict=True))
        after = step_hp(hp, a["team"], a)
        for name, real in zip(b["team"], b["hp"], strict=True):
            if name in a["team"]:
                pairs.append((after[name], real))
err = [p - r for p, r in pairs]
print(
    f"\n残血推算（上一场没人倒下的，{len(pairs)} 只）：推的 − 实际 中位 {statistics.median(err):+.3f}，"
    f"绝对误差中位 {statistics.median(abs(e) for e in err):.3f}，相关 {np.corrcoef([p for p, _ in pairs], [r for _, r in pairs])[0, 1]:.2f}"
)


# 2. 排路线
def route_faints(data, boss, fighters, opponents, boss_team, kind):
    beta = BETAS[kind]
    hp = {}
    total = 0.0
    for index, (team, opponent) in enumerate(
        [*zip(fighters, opponents, strict=True), (boss_team, boss)]
    ):
        feat = fetch.features(list(team), opponent, boss)
        low = min(hp.get(name, 1.0) for name in team)
        row = dict(feat, stage=3 if index == 3 else index)
        total += math.exp(float(np.dot(x(row, kind, low), beta)))
        hp = step_hp(hp, team, feat)
    return total


PAIRS = {
    12873702124229926581: [
        ("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), ("不换", "不换", "换"), "好，22 局 3 次"),
        ("力壮鸡", ("托戈德玛尔", "双剑鞘", "魔墙人偶"), ("不换", "换", "不换"), "差，10 局 9 次"),
    ],
    3076008315599927110: [
        ("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), ("不换", "不换", "不换"), "好，6 局 4 次"),
        ("流氓熊猫", ("心蝙蝠", "肯泰罗", "狃拉"), ("不换", "不换", "不换"), "差，9 局 13 次"),
    ],
}
EXPECTED = {
    9960686445389280169: ("古空棘鱼", ("钻角犀兽", "三地鼠", "托戈德玛尔"), ("换", "不换", "不换"))
}

for boss, seed, _ in v13.CHECKS[:3]:
    config = GameConfig()
    config.lair_first_draw_top = v13.TOP[boss]
    data = GameData(config)
    fetch.data = data
    fetch.cache.clear()
    lair = Lair(data, seed)
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")
    candidates = lair.candidates()[:3]
    plans = []
    for starter in range(3):
        for path in upstream.paths(lair.map_type()):
            walker = upstream.Walker(
                lair, data, boss, path, [candidates[starter], *lair.teammates(starter)]
            )
            for catches, scientists, fighters, boss_team in v13.outcomes(walker):
                key = (zh(candidates[starter]), tuple(zh(o) for o in walker.opponents), catches)
                plans.append((key, scientists, fighters, walker.opponents, boss_team))
    print(f"\n== {seed}（{boss}），{len(plans)} 个方案")
    for kind in KINDS:
        scored = sorted(
            ((route_faints(data, boss, f, o, b, kind), key, sci) for key, sci, f, o, b in plans),
            key=lambda item: item[0],
        )
        best = scored[0]
        line = f"  {kind}：第 1 {best[1][0]}；{' → '.join(best[1][1])}；{'、'.join(best[1][2])}（{best[0]:.3f}）"
        for starter, path, swaps, note in PAIRS.get(seed, []):
            for rank, (value, key, _) in enumerate(scored, 1):
                if key == (starter, path, swaps):
                    line += f"；{note}的 {value:.3f}（第 {rank}）"
                    break
        if seed in EXPECTED:
            rank = next(rank for rank, (_, key, _) in enumerate(scored, 1) if key == EXPECTED[seed])
            line += f"；实测最好的第 {rank}"
        print(line)
