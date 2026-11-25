"""读 版本20-逐场取数.py 存的逐场表，看 m、d、r、T、L 和实际回合、倒下的关系（docs/实测-逐场校准.md 方向 2～5）。

每张表给两个版本：
  原始：每一场算一次（锁定的图打了很多局，会被少数几张图主导）；
  去重：同一个（队伍, 对手）组合只算一次，回合、倒下取这几场的平均。
路上三关和首领分开。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本20-全部日志逐场校准.py
"""

import json
import math
import os
from collections import defaultdict

import numpy as np

OUT = os.environ.get(
    "FIGHTS_JSON",
    "/private/tmp/claude-503/-Users-garnet-projects-control-switch/6882f779-6294-4dce-875c-e2716eed87ee/scratchpad/fights.json",
)
CHECK_SEEDS = {"3076008315599927110", "12873702124229926581"}
rows = json.load(open(OUT))


def dedup(items):
    groups = defaultdict(list)
    for r in items:
        groups[(tuple(r["team"]), r["opp"], r["stage"] == 3)].append(r)
    out = []
    for group in groups.values():
        first = dict(group[0])
        first["turns"] = float(np.mean([g["turns"] for g in group]))
        first["faints"] = float(np.mean([g["faints"] for g in group]))
        first["n"] = len(group)
        out.append(first)
    return out


def rank(values):
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    values = np.asarray(values, dtype=float)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(x, y):
    if len(x) < 3:
        return float("nan")
    return float(np.corrcoef(rank(x), rank(y))[0, 1])


def bins(items, key, edges, label):
    print(f"  {label}")
    print("  | 区间 | 场数 | 平均回合 | 平均倒下 | 有倒下的比例 |")
    print("  |---|---|---|---|---|")
    for lo, hi in zip(edges, edges[1:]):
        sel = [r for r in items if lo <= key(r) < hi]
        if not sel:
            continue
        t = np.mean([r["turns"] for r in sel])
        f = np.mean([r["faints"] for r in sel])
        any_f = np.mean([r["faints"] > 0 for r in sel])
        print(f"  | {lo:g}～{hi:g} | {len(sel)} | {t:.2f} | {f:.2f} | {any_f:.0%} |")


def groups():
    road = [r for r in rows if r["stage"] < 3]
    boss = [r for r in rows if r["stage"] == 3]
    return [("路上", road), ("首领", boss)]


def section_overview():
    print("\n## 概况")
    print(
        f"共 {len(rows)} 场，{len({r['file'] for r in rows})} 局，{len({r['seed'] for r in rows})} 张图"
    )
    print("| | 场数 | 去重后 | 平均回合 | 平均倒下 | 输的场 |")
    print("|---|---|---|---|---|---|")
    for name, items in groups():
        print(
            f"| {name} | {len(items)} | {len(dedup(items))} | {np.mean([r['turns'] for r in items]):.2f} | "
            f"{np.mean([r['faints'] for r in items]):.3f} | {sum(r['result'] == '输' for r in items)} |"
        )
    print("\n每一关的倒下（方向 5）")
    print("| 场 | 场数 | 平均倒下 | 占全部倒下 | 输在这一场 |")
    print("|---|---|---|---|---|")
    total = sum(r["faints"] for r in rows)
    for stage in range(4):
        sel = [r for r in rows if r["stage"] == stage]
        print(
            f"| {'首领' if stage == 3 else f'第 {stage + 1} 关'} | {len(sel)} | {np.mean([r['faints'] for r in sel]):.3f} | "
            f"{sum(r['faints'] for r in sel) / total:.0%} | {sum(r['result'] == '输' for r in sel)} |"
        )
    print("\n按首领分（首领战）")
    print("| 首领 | 限制级 | 场数 | 平均回合 | 平均倒下 | 路上平均倒下 | 输 |")
    print("|---|---|---|---|---|---|---|")
    for b in sorted({r["boss"] for r in rows}):
        sel = [r for r in rows if r["boss"] == b and r["stage"] == 3]
        road = [r for r in rows if r["boss"] == b and r["stage"] < 3]
        print(
            f"| {b} | {'是' if sel[0]['restricted'] else '否'} | {len(sel)} | {np.mean([r['turns'] for r in sel]):.2f} | "
            f"{np.mean([r['faints'] for r in sel]):.2f} | {np.mean([r['faints'] for r in road]):.3f} | {sum(r['result'] == '输' for r in sel)} |"
        )


def corr_table(title, keys):
    print(f"\n{title}")
    print("| 量 | 场 | 和回合（原始 / 去重） | 和倒下（原始 / 去重） |")
    print("|---|---|---|---|")
    for name, items in groups():
        dd = dedup(items)
        for label, key in keys:
            a = spearman([key(r) for r in items], [r["turns"] for r in items])
            b = spearman([key(r) for r in dd], [r["turns"] for r in dd])
            c = spearman([key(r) for r in items], [r["faints"] for r in items])
            e = spearman([key(r) for r in dd], [r["faints"] for r in dd])
            print(f"| {label} | {name} | {a:+.2f} / {b:+.2f} | {c:+.2f} / {e:+.2f} |")


def section_m():
    print("\n## 方向 2：m 和实际回合、倒下")
    edges = [0, 1, 2, 3, 5, 8, 13, 21, 1e9]
    for name, items in groups():
        bins(items, lambda r: r["m"], edges, f"{name}，按 m 分箱（原始）")
        bins(dedup(items), lambda r: r["m"], edges, f"{name}，按 m 分箱（去重）")


def section_dr():
    print("\n## 方向 3：打出 d、受到 r 分开")
    corr_table(
        "Spearman 相关（负数 = 这个量越大，回合 / 倒下越少）",
        [
            ("m", lambda r: r["m"]),
            ("d", lambda r: r["d"]),
            ("r", lambda r: r["r"]),
            ("最脆那只 r", lambda r: r["r_max"]),
            ("T", lambda r: r["T"]),
            ("L = T × r", lambda r: r["L"]),
            ("实际回合 × r", lambda r: r["turns"] * r["r"]),
            ("进场平均血量", lambda r: np.mean(r["hp"])),
            ("进场最低血量", lambda r: min(r["hp"])),
        ],
    )
    for name, items in groups():
        bins(
            items,
            lambda r: r["d"],
            [0, 0.5, 0.75, 1, 1.5, 2, 3, 4, 1e9],
            f"{name}，按 d 分箱（原始）",
        )
        bins(
            items,
            lambda r: r["r"],
            [0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1e9],
            f"{name}，按 r 分箱（原始）",
        )
        bins(
            items,
            lambda r: r["turns"] * r["r"],
            [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 1e9],
            f"{name}，按 实际回合 × r 分箱（原始）",
        )
        bins(
            items,
            lambda r: r["L"],
            [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 1e9],
            f"{name}，按 L = T × r 分箱（原始）",
        )
    print("\n回合主要看 d、倒下主要看 r × 回合？固定一个量分层看另一个（原始）：")
    for name, items in groups():
        print(
            f"  {name}：d 分成高低两半，各自里 r 和倒下的相关；r 分成高低两半，各自里 d 和回合的相关"
        )
        dm = np.median([r["d"] for r in items])
        rm = np.median([r["r"] for r in items])
        for lab, sel in (
            ("d 低", [r for r in items if r["d"] < dm]),
            ("d 高", [r for r in items if r["d"] >= dm]),
        ):
            print(
                f"    {lab}（{len(sel)} 场）：r 和倒下 {spearman([r['r'] for r in sel], [r['faints'] for r in sel]):+.2f}，"
                f"d 和回合 {spearman([r['d'] for r in sel], [r['turns'] for r in sel]):+.2f}"
            )
        for lab, sel in (
            ("r 低", [r for r in items if r["r"] < rm]),
            ("r 高", [r for r in items if r["r"] >= rm]),
        ):
            print(
                f"    {lab}（{len(sel)} 场）：d 和回合 {spearman([r['d'] for r in sel], [r['turns'] for r in sel]):+.2f}，"
                f"r 和倒下 {spearman([r['r'] for r in sel], [r['faints'] for r in sel]):+.2f}"
            )


def section_measured():
    print("\n## 有回合数据的场：预测的 d、r 和实测每回合打出、受到")
    print("| 场 | 场数 | 实测 d ÷ 预测 d 中位 | 相关（Spearman） | 实测 r ÷ 预测 r 中位 | 相关 |")
    print("|---|---|---|---|---|---|")
    for name, items in groups():
        sel = [r for r in items if r["meas_n"] >= 1 and r["d"] > 0 and r["r"] > 0]
        rd = [r["meas_d"] / r["d"] for r in sel]
        rr = [r["meas_r"] / r["r"] for r in sel]
        print(
            f"| {name} | {len(sel)} | {np.median(rd):.2f} | {spearman([r['d'] for r in sel], [r['meas_d'] for r in sel]):+.2f} | "
            f"{np.median(rr):.2f} | {spearman([r['r'] for r in sel], [r['meas_r'] for r in sel]):+.2f} |"
        )


def section_T():
    print("\n## 方向 4：T 的预测和实际回合")
    for name, items in groups():
        print(f"\n{name}：行是预测 T，列是实际回合（原始）")
        top = 6
        print(
            "| T \\ 实际 | "
            + " | ".join(str(k) if k < top else f"{top}+" for k in range(1, top + 1))
            + " | 场数 | 平均实际 |"
        )
        print("|---" * (top + 3) + "|")
        for t in sorted({min(r["T"], top) for r in items}):
            sel = [r for r in items if min(r["T"], top) == t]
            counts = [
                sum(1 for r in sel if min(max(r["turns"], 1), top) == k) for k in range(1, top + 1)
            ]
            print(
                f"| {t if t < top else f'{top}+'} | "
                + " | ".join(str(c) for c in counts)
                + f" | {len(sel)} | {np.mean([r['turns'] for r in sel]):.2f} |"
            )
        exact = np.mean([r["T"] == r["turns"] for r in items])
        print(
            f"  T 正好等于实际回合 {exact:.0%}，平均偏差（实际 − T）{np.mean([r['turns'] - r['T'] for r in items]):+.2f}"
        )
    print("\n战斗血量 ÷ d（不取整）细分，看临界附近：")
    for name, items in groups():
        edges = [
            0,
            0.5,
            0.8,
            1.0,
            1.2,
            1.5,
            1.8,
            2.0,
            2.2,
            2.5,
            2.8,
            3.0,
            3.2,
            3.6,
            4.0,
            5,
            6,
            8,
            1e9,
        ]
        bins(items, lambda r: r["hp_ratio"], edges, f"{name}，按 战斗血量 ÷ d 分箱（原始）")


def section_hp():
    print("\n## 进场血量")
    for name, items in groups():
        bins(
            items,
            lambda r: np.mean(r["hp"]),
            [0, 0.4, 0.6, 0.8, 0.9, 1.0, 1.01],
            f"{name}，按进场平均血量分箱（原始）",
        )
        bins(
            items,
            lambda r: min(r["hp"]),
            [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.01],
            f"{name}，按进场最低血量分箱（原始）",
        )


def section_checks():
    print("\n## 3076（超梦，熊猫首发）两条路线首领战")
    sel = [r for r in rows if r["seed"] == "3076008315599927110" and r["stage"] == 3]
    groups_ = defaultdict(list)
    for r in rows:
        if r["seed"] == "3076008315599927110" and r["stage"] == 0:
            groups_[r["file"]].append(r["opp"])
    for r in sel:
        first = groups_.get(r["file"], ["?"])[0]
        print(
            f"  第 1 关 {first}：队伍 {'/'.join(r['team'])}，进场血量 {[round(h, 2) for h in r['hp']]}，"
            f"m {r['m']:.2f} d {r['d']:.2f} r {r['r']:.3f} r_max {r['r_max']:.3f}，回合 {r['turns']}，倒下 {r['faints']}"
        )


EXCLUDE = CHECK_SEEDS | {"9960686445389280169"}


def design(r, kind):
    """泊松回归的自变量。kind 见 MODELS。"""
    b = 1.0 if r["stage"] == 3 else 0.0
    lr, lt, lm = math.log(r["r"]), math.log(r["hp_ratio"]), math.log(r["m"])
    restricted = b * (1.0 if r["restricted"] else 0.0)
    return {
        "只分路上 / 首领": [1, b],
        "m": [1, b, lm],
        "m + 限制级首领": [1, b, lm, restricted],
        "L = T × r": [1, b, math.log(r["L"])],
        "L = T × r + 限制级首领": [1, b, math.log(r["L"]), restricted],
        "r、血量 ÷ d 分开": [1, b, lr, lt],
        "r、血量 ÷ d 分开，首领单独系数": [1, b, lr, lt, b * lr, b * lt],
        "r、血量 ÷ d + 最脆那只 r": [1, b, lr, lt, math.log(r["r_max"])],
        "r、血量 ÷ d + 限制级首领": [1, b, lr, lt, restricted],
        "r、血量 ÷ d + 进场最低血量": [1, b, lr, lt, math.log(max(0.05, min(r["hp"])))],
    }[kind]


MODELS = [
    "只分路上 / 首领",
    "m",
    "m + 限制级首领",
    "L = T × r",
    "L = T × r + 限制级首领",
    "r、血量 ÷ d 分开",
    "r、血量 ÷ d 分开，首领单独系数",
    "r、血量 ÷ d + 最脆那只 r",
    "r、血量 ÷ d + 限制级首领",
    "r、血量 ÷ d + 进场最低血量",
]


def poisson_fit(items, kind, target="faints", weights=None):
    """对数连接的泊松回归（牛顿法）：E[target] = exp(design · beta)。weights 是每一场的权重（默认都是 1）。"""
    a = np.array([design(r, kind) for r in items], dtype=float)
    y = np.array([r[target] for r in items], dtype=float)
    w = np.ones(len(items)) if weights is None else np.asarray(weights, dtype=float)
    beta = np.zeros(a.shape[1])
    beta[0] = math.log(np.average(y, weights=w))
    for _ in range(100):
        mu = np.exp(a @ beta)
        step = np.linalg.solve((a * (w * mu)[:, None]).T @ a, a.T @ (w * (y - mu)))
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return beta


def poisson_loglik(items, kind, beta, target="faints"):
    a = np.array([design(r, kind) for r in items], dtype=float)
    y = np.array([r[target] for r in items], dtype=float)
    mu = np.exp(a @ beta)
    return float(np.sum(y * np.log(mu) - mu - np.array([math.lgamma(v + 1) for v in y])))


def seed_weights(items):
    """按图等权：每一场的权重 = 1 ÷ 这张图在 items 里的局数。"""
    runs = defaultdict(set)
    for r in items:
        runs[r["seed"]].add(r["file"])
    return [1 / len(runs[r["seed"]]) for r in items]


def train_rows():
    """拟合用的场：去掉 3076、12873、9960 三张图的所有局。"""
    return [r for r in rows if r["seed"] not in EXCLUDE]


def section_fit():
    train = train_rows()
    print(
        f"\n## 倒下模型：E[这一场倒下] = exp(系数 · 自变量)，泊松回归，拟合用 {len(train)} 场（去掉 3076、12873、9960 的局）"
    )
    seeds = sorted({r["seed"] for r in train})
    np.random.default_rng(0).shuffle(seeds)
    folds = [set(seeds[i::5]) for i in range(5)]
    print(
        "| 模型 | 按图分 5 折交叉验证的对数似然（越大越好） | 系数（常数、首领、…） | 按图等权拟合的系数 |"
    )
    print("|---|---|---|---|")
    for kind in MODELS:
        cv = sum(
            poisson_loglik(
                [r for r in train if r["seed"] in f],
                kind,
                poisson_fit([r for r in train if r["seed"] not in f], kind),
            )
            for f in folds
        )
        beta = poisson_fit(train, kind)
        wbeta = poisson_fit(train, kind, weights=seed_weights(train))
        print(
            f"| {kind} | {cv:.1f} | {', '.join(f'{v:+.3f}' for v in beta)} | {', '.join(f'{v:+.3f}' for v in wbeta)} |"
        )
    print("\n回合模型：E[实际回合] = exp(常数 + 首领 + k · log(战斗血量 ÷ d))")
    a = np.array([[1, r["stage"] == 3, math.log(r["hp_ratio"])] for r in train], dtype=float)
    y = np.array([r["turns"] for r in train], dtype=float)
    beta = np.zeros(3)
    beta[0] = math.log(y.mean())
    for _ in range(100):
        mu = np.exp(a @ beta)
        beta += np.linalg.solve((a * mu[:, None]).T @ a, a.T @ (y - mu))
    mu = np.exp(a @ beta)
    T = np.array([r["T"] for r in train], dtype=float)
    print(
        f"  系数 {', '.join(f'{v:+.3f}' for v in beta)}；平均绝对误差：这个模型 {np.mean(np.abs(mu - y)):.3f}，T 取整 {np.mean(np.abs(T - y)):.3f}"
    )
    print("\n拟合出来的倒下模型，按 m 分箱的预测和实际（训练集，原始）")
    beta = poisson_fit(train, "m")
    for name, items in (
        ("路上", [r for r in train if r["stage"] < 3]),
        ("首领", [r for r in train if r["stage"] == 3]),
    ):
        print(f"  {name}")
        print("  | m 区间 | 场数 | 实际平均倒下 | 预测平均倒下 |")
        print("  |---|---|---|---|")
        for lo, hi in zip([0, 2, 3, 5, 8, 13, 21], [2, 3, 5, 8, 13, 21, 1e9]):
            sel = [r for r in items if lo <= r["m"] < hi]
            if sel:
                pred = np.mean([math.exp(np.dot(design(r, "m"), beta)) for r in sel])
                print(
                    f"  | {lo:g}～{hi:g} | {len(sel)} | {np.mean([r['faints'] for r in sel]):.2f} | {pred:.2f} |"
                )
    for name, items in (
        ("路上", [r for r in train if r["stage"] < 3]),
        ("首领", [r for r in train if r["stage"] == 3]),
    ):
        mu = np.array([math.exp(np.dot(design(r, "m"), beta)) for r in items])
        y = np.array([r["faints"] for r in items], dtype=float)
        share = [float(np.mean(np.exp(-mu) * mu**k / math.factorial(k))) for k in range(4)]
        print(
            f"  {name}：离散度（皮尔逊）{np.sum((y - mu) ** 2 / mu) / (len(y) - 3):.2f}；"
            f"0～3 次的比例 泊松预测 {[round(v, 3) for v in share]}，实际 {[round(float(np.mean(y == k)), 3) for k in range(4)]}"
        )
    print("\n按首领看残差（m 模型，训练集首领战）：实际 ÷ 预测")
    for b in sorted({r["boss"] for r in train}):
        sel = [r for r in train if r["boss"] == b and r["stage"] == 3]
        pred = sum(math.exp(np.dot(design(r, "m"), beta)) for r in sel)
        print(
            f"  {b}：{len(sel)} 场，实际 {sum(r['faints'] for r in sel)}，预测 {pred:.1f}，比 {sum(r['faints'] for r in sel) / pred:.2f}"
        )


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def route_groups(seed):
    """这张图每一局按（首发, 三关对手）分组：{key: [(这一局倒下合计, 赢没赢, [每一场倒下])]}。"""
    runs = defaultdict(list)
    for r in rows:
        if r["seed"] == seed:
            runs[r["file"]].append(r)
    out = defaultdict(list)
    for fights in runs.values():
        fights.sort(key=lambda r: r["stage"])
        if fights[0]["stage"] != 0:
            continue
        key = (fights[0]["team"][0], tuple(r["opp"] for r in fights if r["stage"] < 3))
        out[key].append(
            (
                sum(r["faints"] for r in fights),
                fights[-1]["stage"] == 3 and fights[-1]["result"] == "赢",
                [r["faints"] for r in fights],
            )
        )
    return out


PAIRS = {
    "3076008315599927110": (
        ("pangoro", ("fraxure", "obstagoon", "sneasel")),
        ("pangoro", ("swoobat", "tauros", "sneasel")),
    ),
    "12873702124229926581": (
        ("blaziken", ("togedemaru", "doublade", "dugtrio-alola")),
        ("combusken", ("togedemaru", "doublade", "mr-mime-galar")),
    ),
}


def section_noise():
    print(
        "\n## 3076、12873 两条路线的实测（全部日志现算，只算四场对手都认得出的局），差别有多大把握"
    )
    print("二项检验：两边倒下率一样时，倒下按局数分到两边，好的那边只有这么少或更少的概率（单边）")
    print(
        "| 图 | 路线 | 局数 | 赢 | 倒下合计 | 每局 | 每一场平均倒下 | 每一场平均 m | 每一场进场最低血量 | 整局概率 | 首领战概率 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for seed, (good, bad) in PAIRS.items():
        runs = defaultdict(list)
        for r in rows:
            if r["seed"] == seed:
                runs[r["file"]].append(r)
        sides = {}
        for label, key in (("好", good), ("差", bad)):
            sides[label] = [
                sorted(fs, key=lambda r: r["stage"])
                for fs in runs.values()
                if sorted(fs, key=lambda r: r["stage"])[0]["stage"] == 0
                and (
                    min(fs, key=lambda r: r["stage"])["team"][0],
                    tuple(r["opp"] for r in sorted(fs, key=lambda r: r["stage"]) if r["stage"] < 3),
                )
                == key
            ]
        g, b = sides["好"], sides["差"]
        gf, bf = sum(r["faints"] for fs in g for r in fs), sum(r["faints"] for fs in b for r in fs)
        p_all = binom_cdf(gf, gf + bf, len(g) / (len(g) + len(b)))
        gb = sum(r["faints"] for fs in g for r in fs if r["stage"] == 3)
        bb = sum(r["faints"] for fs in b for r in fs if r["stage"] == 3)
        p_boss = binom_cdf(gb, gb + bb, len(g) / (len(g) + len(b)))
        for label, key in (("好", good), ("差", bad)):
            items = sides[label]
            per = lambda f: ", ".join(
                f"{np.mean([f(fs[k]) for fs in items if len(fs) > k]):.2f}" for k in range(4)
            )
            print(
                f"| {seed[:5]} | {label}：{key[0]}；{' → '.join(key[1])} | {len(items)} | "
                f"{sum(fs[-1]['stage'] == 3 and fs[-1]['result'] == '赢' for fs in items)} | "
                f"{sum(r['faints'] for fs in items for r in fs)} | {np.mean([sum(r['faints'] for r in fs) for fs in items]):.2f} | "
                f"{per(lambda r: r['faints'])} | {per(lambda r: r['m'])} | {per(lambda r: min(r['hp']))} | {p_all:.3f} | {p_boss:.3f} |"
            )
    print(
        "\n3076 两条每局倒下按 0.60 / 1.44 算，两边各打 n 局、倒下正好是期望值（取整）时整局的概率："
    )
    for n in (5, 10, 15, 20, 25, 30):
        a, b = round(0.60 * n), round(1.44 * n)
        print(f"  各 {n} 局：{a} 次对 {b} 次，概率 {binom_cdf(a, a + b, 0.5):.3f}")


def section_gap():
    print("\n## 回合数少算了多少")
    for name, items in groups():
        with_f = [r for r in items if r["faints"] > 0]
        print(
            f"  {name}：{len(items)} 场里 {sum(r['gap'] > 0 for r in items)} 场有「两次倒下之间没选招」，"
            f"合计 {sum(r['gap'] for r in items)} 次（有倒下的 {len(with_f)} 场，回合 {np.mean([r['turns'] for r in items]):.2f}）"
        )


if __name__ == "__main__":
    section_overview()
    section_m()
    section_dr()
    section_measured()
    section_T()
    section_hp()
    section_checks()
    section_fit()
    section_noise()
    section_gap()
