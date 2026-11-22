"""在 7 张图（版本 13 的 CHECKS）上比几种路线分：首领权重 2、3、4 的 m 连乘和 ΣL，以及按全部日志拟合的「预测倒下之和」。

预测倒下之和：每一场 E[倒下] = exp(常数 + 首领系数 + k · log m)（泊松回归，系数用 版本20-全部日志逐场校准.py 的
poisson_fit 现拟合，拟合时去掉 3076、12873、9960 三张图的所有局），整条路线相加，越小越好；
相同时看预测回合之和（E[回合] 同样拟合）。首领权重不用手定，来自首领系数。
组合方式和版本 13 一样（首发 × 路线 × 换不换 × 研究员换不换，不算不抓）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本20-路线分对比.py
"""

import importlib.util
import math
import os
import sys
from collections import defaultdict

import numpy as np

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.argv = [sys.argv[0], "--no-skip"]
v13 = load("v13", "版本13-按实际上场算路线分.py")
take = load("take", "版本20-逐场取数.py")
calib = load("calib", "版本20-全部日志逐场校准.py")

TRAIN = calib.train_rows()
FAINT_MODELS = ["m", "m + 限制级首领", "r、血量 ÷ d 分开", "r、血量 ÷ d + 限制级首领", "L = T × r", "L = T × r + 限制级首领"]
BETAS = {kind: calib.poisson_fit(TRAIN, kind) for kind in FAINT_MODELS}
_a = np.array([[1, r["stage"] == 3, math.log(r["hp_ratio"])] for r in TRAIN], dtype=float)
_y = np.array([r["turns"] for r in TRAIN], dtype=float)
TURN_BETA = np.zeros(3)
TURN_BETA[0] = math.log(_y.mean())
for _ in range(100):
    _mu = np.exp(_a @ TURN_BETA)
    TURN_BETA += np.linalg.solve((_a * _mu[:, None]).T @ _a, _a.T @ (_y - _mu))

PAIRS = {
    3076008315599927110: [("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), ("不换", "不换", "不换"), "好：6 局全胜，倒下 0.67"),
                          ("流氓熊猫", ("心蝙蝠", "肯泰罗", "狃拉"), ("不换", "不换", "不换"), "差：9 局 8 胜，倒下 1.44")],
    12873702124229926581: [("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), ("不换", "不换", "换"), "好：日志 22 局，倒下 3"),
                           ("力壮鸡", ("托戈德玛尔", "双剑鞘", "魔墙人偶"), ("不换", "换", "不换"), "差：日志 10 局，倒下 9")],
}


def fight_row(team, opp, boss):
    f = take.features(list(team), opp, boss)
    return {"stage": 3 if opp == boss else 0, "restricted": boss in take.RESTRICTED, "hp": [1.0], **f}


def fight_values(team, opp, boss):
    f = take.features(list(team), opp, boss)
    row = fight_row(team, opp, boss)
    faints = {kind: math.exp(np.dot(calib.design(row, kind), beta)) for kind, beta in BETAS.items()}
    turns = math.exp(TURN_BETA[0] + TURN_BETA[1] * (opp == boss) + TURN_BETA[2] * math.log(f["hp_ratio"]))
    return f["m"], f["L"], faints, turns


def plan(data, boss, lair):
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    candidates = lair.candidates()[:3]
    results = []
    for starter in range(3):
        for path in upstream.paths(lair.map_type()):
            walker = upstream.Walker(lair, data, boss, path, [candidates[starter], *lair.teammates(starter)])
            for catches, scientists, fighters, boss_team in v13.outcomes(walker):
                fights = [fight_values(t, o, boss) for t, o in zip(fighters, walker.opponents, strict=True)]
                bm, bl, bf, bt = fight_values(boss_team, boss, boss)
                rec = {"key": (zh(candidates[starter]), tuple(zh(o) for o in walker.opponents), catches),
                       "scientists": scientists}
                road_logm = sum(math.log(f[0]) for f in fights)
                for w in (2, 3, 4):
                    rec[f"m^{w}"] = math.exp((road_logm + w * math.log(bm)) / (3 + w))
                    rec[f"L×{w}"] = sum(f[1] for f in fights) + w * bl
                for kind in BETAS:
                    rec[f"倒下[{kind}]"] = sum(f[2][kind] for f in fights) + bf[kind]
                rec["回合"] = sum(f[3] for f in fights) + bt
                rec["各场倒下[m]"] = [f[2]["m"] for f in fights] + [bf["m"]]
                rec["各场m"] = [f[0] for f in fights] + [bm]
                rec["路上L"], rec["首领L"] = sum(f[1] for f in fights), bl
                rec["路上logm"], rec["首领logm"] = road_logm, math.log(bm)
                rec["路上倒下m"], rec["首领倒下m"] = sum(f[2]["m"] for f in fights), bf["m"]
                rec["场"] = [*zip(fighters, walker.opponents), (boss_team, boss)]
                results.append(rec)
    return results


SCORES = [("m^2", True), ("m^3", True), ("m^4", True), ("L×2", False), ("L×3", False), ("L×4", False)] + \
         [(f"倒下[{k}]", False) for k in FAINT_MODELS]


def ranked(results, name, higher):
    sign = -1 if higher else 1
    return sorted(results, key=lambda r: (sign * r[name], r["回合"]))


def robustness(pair_rows, rounds=300):
    """按图重抽样（有放回）重新拟合，看 3076、12873 两对是不是都排对；再加一次按图等权拟合。

    pair_rows: {seed: (好那条的逐场 row, 差那条的逐场 row)}。
    """
    print("\n== 稳不稳：按图重抽样 300 次重新拟合，两对都排对的比例（每对单独排对的比例）")
    seeds = sorted({r["seed"] for r in TRAIN})
    by_seed = defaultdict(list)
    for r in TRAIN:
        by_seed[r["seed"]].append(r)
    rng = np.random.default_rng(1)
    samples = [[r for s in rng.choice(seeds, len(seeds)) for r in by_seed[s]] for _ in range(rounds)]

    def total(rows_, kind, beta):
        return sum(math.exp(np.dot(calib.design(r, kind), beta)) for r in rows_)

    for kind in FAINT_MODELS:
        ok = defaultdict(int)
        for smp in samples:
            beta = calib.poisson_fit(smp, kind)
            both = True
            for seed, (good, bad) in pair_rows.items():
                right = total(good, kind, beta) < total(bad, kind, beta)
                ok[seed] += right
                both &= right
            ok["both"] += both
        beta = calib.poisson_fit(TRAIN, kind, weights=calib.seed_weights(TRAIN))
        weighted = "、".join(f"{str(seed)[:5]} {'对' if total(g, kind, beta) < total(b, kind, beta) else '错'}"
                            f"（{total(g, kind, beta):.3f} 对 {total(b, kind, beta):.3f}）" for seed, (g, b) in pair_rows.items())
        print(f"  {kind}：两对都对 {ok['both'] / rounds:.0%}（" +
              "，".join(f"{str(seed)[:5]} {ok[seed] / rounds:.0%}" for seed in pair_rows) + f"）；按图等权拟合：{weighted}")


if __name__ == "__main__":
    pair_rows = {}
    print("倒下模型系数（常数、首领、…）：")
    for kind, beta in BETAS.items():
        print(f"  {kind}：{', '.join(f'{v:+.3f}' for v in beta)}")
    print(f"回合模型系数：{', '.join(f'{v:+.3f}' for v in TURN_BETA)}")
    for boss, seed, expected in v13.CHECKS:
        config = GameConfig()
        config.lair_first_draw_top = v13.TOP[boss]
        data = GameData(config)
        results = plan(data, boss, Lair(data, seed))
        print(f"\n== {seed}（{boss}），{len(results)} 个方案")
        exp_key = None
        if expected:
            exp_key = (expected[0], expected[1], tuple("换" if t else "不换" for t in expected[2]))
        for name, higher in SCORES:
            order = ranked(results, name, higher)
            best = order[0]
            line = f"  {name}：第 1 名 {best['key'][0]}；{' → '.join(best['key'][1])}；{'、'.join(best['key'][2])}（{best[name]:.3f}）"
            if exp_key:
                rank = next(k + 1 for k, r in enumerate(order) if r["key"] == exp_key)
                line += f"；实测最好的排第 {rank}"
            for starter, path, swaps, note in PAIRS.get(seed, []):
                pos = [k + 1 for k, r in enumerate(order) if r["key"] == (starter, path, swaps) and not any(r["scientists"])]
                val = next(r[name] for r in order if r["key"] == (starter, path, swaps) and not any(r["scientists"]))
                line += f"；{note[:1]} {val:.3f}（第 {pos[0]}）"
            print(line)
        if seed in PAIRS:
            pair_rows[seed] = tuple(
                [fight_row(t, o, boss) for t, o in next(r for r in results if r["key"] == (st, pa, sw) and not any(r["scientists"]))["场"]]
                for st, pa, sw, _ in PAIRS[seed])
        for starter, path, swaps, note in PAIRS.get(seed, []):
            r = next(r for r in results if r["key"] == (starter, path, swaps) and not any(r["scientists"]))
            print(f"  {note}：{starter}；{' → '.join(path)}：各场 m {[round(x, 2) for x in r['各场m']]}，"
                  f"各场预测倒下 {[round(x, 2) for x in r['各场倒下[m]']]}，预测回合 {r['回合']:.2f}，"
                  f"路上 ΣL {r['路上L']:.3f}，首领 L {r['首领L']:.3f}")
        if seed in PAIRS:
            good, bad = (next(r for r in results if r["key"] == (s, p, w) and not any(r["scientists"]))
                         for s, p, w, _ in PAIRS[seed])
            if good["首领logm"] > bad["首领logm"]:
                cross = (bad["路上logm"] - good["路上logm"]) / (good["首领logm"] - bad["首领logm"])
                print(f"  m 连乘里首领权重大于 {cross:.1f} 时，好的那条排在差的前面"
                      f"（路上 log m 合计 {good['路上logm']:.3f} 对 {bad['路上logm']:.3f}，首领 log m {good['首领logm']:.4f} 对 {bad['首领logm']:.4f}）")
            if good["首领倒下m"] < bad["首领倒下m"]:
                cross = (good["路上倒下m"] - bad["路上倒下m"]) / (bad["首领倒下m"] - good["首领倒下m"])
                head = (f"  倒下[m] 里首领那场要再乘 {cross:.1f} 倍（在拟合出的首领系数之外），好的那条才排在差的前面" if cross > 0
                        else "  倒下[m] 里好的那条路上、首领都更少，首领权重多少都排对")
                print(head + f"（路上 {good['路上倒下m']:.3f} 对 {bad['路上倒下m']:.3f}，首领 {good['首领倒下m']:.3f} 对 {bad['首领倒下m']:.3f}）")
            if bad["首领L"] != good["首领L"]:
                cross = (good["路上L"] - bad["路上L"]) / (bad["首领L"] - good["首领L"])
                print(f"  ΣL 里首领权重大于 {cross:.2f} 时，好的那条排在差的前面" if bad["首领L"] > good["首领L"]
                      else f"  ΣL 里首领权重小于 {cross:.2f} 时，好的那条排在差的前面")
    robustness(pair_rows)
