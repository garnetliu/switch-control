"""整套方案的原型：首领战按回合算（全队一个分），和现在代码里的算法比。"""

import ast
import glob
import itertools
import re
import statistics as st
import sys

from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import Planner, combine, fight, paths

RATE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.31
LAM = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0


class Proto:
    def __init__(self, d, c, boss):
        self.c = c
        self.D = d.rental_damages()
        self.B = {n: b[boss] for n, b in d.boss_attack_defense().items()}

    def case(self, fielded, opp, mates):
        c = self.c
        wait = 0
        stages = []
        for p, o in zip(fielded, opp):
            v, wait = fight(self.D[p][o], wait, c)
            stages.append(v)
        n, m, r = self.B[fielded[-1]]
        own, _ = fight((n, m), wait, c, c.boss_turns)
        attack = own + sum(self.B[x][0] for x in mates)
        turns = max(1.0, 1 / (RATE * max(attack, 0.05)))
        hurt = turns * (r + sum(self.B[x][2] for x in mates)) / 4
        return combine(stages, 1 / (turns * (1 + LAM * hurt)), c)

    def score(self, starter, mates, opp):
        share = (1 - self.c.no_swap_probability) / 3
        best = None
        for swaps in itertools.product((False, True), repeat=3):
            cur = starter
            after = []
            for s, o in zip(swaps, opp):
                cur = o if s else cur
                after.append(cur)
            opts = [
                [(None, 1.0)]
                if s
                else [(None, self.c.no_swap_probability), (0, share), (1, share), (2, share)]
                for s in swaps
            ]
            exp = 0.0
            for case in itertools.product(*opts):
                pr = 1.0
                m = list(mates)
                for o, (t, ch) in zip(opp, case):
                    pr *= ch
                    if t is not None:
                        m[t] = o
                exp += pr * self.case([starter, *after], opp, m)
            if best is None or exp > best[0]:
                best = (exp, swaps)
        return best


def ctx(boss, top):
    c = GameConfig()
    c.lair_first_draw_top = top
    d = GameData(c)
    return c, d, Planner(d, c, boss), Proto(d, c, boss)


def plans(boss, top, seed):
    c, d, P, Q = ctx(boss, top)
    l = Lair(d, seed)
    cand = l.candidates()
    enc = l.encounters()
    rows = []
    for s in range(3):
        team = l.teammates(s)
        for path in paths(l.map_type()):
            o = tuple(enc[str(r)][col] for r, col in path)
            rows.append((Q.score(cand[s], team, o), P.score(cand[s], team, o)[0], cand[s], o))
    return sorted(rows, key=lambda r: -r[0][0])


print(f"RATE={RATE} LAM={LAM}")
print("== 超梦基准图 3076…：原型排名（原型分, 换法 | 现在的总分）")
for r in plans("mewtwo", 24, 3076008315599927110)[:5]:
    print(
        "  ",
        round(r[0][0], 3),
        ["换" if x else "不" for x in r[0][1]],
        "|",
        round(r[1], 3),
        r[2],
        r[3],
    )
print("== 哞哞几张图：原型选中的方案")
for s in (
    9004205710319247536,
    7141377954180009874,
    5938375612842167902,
    9634935719440944093,
    2281029239352938801,
):
    r = plans("tapu-bulu", 23, s)[0]
    print(
        "  ",
        s,
        round(r[0][0], 3),
        ["换" if x else "不" for x in r[0][1]],
        "| 现在",
        round(r[1], 3),
        r[2],
        r[3],
    )
# 实际打过的局
C = {"mewtwo": ctx("mewtwo", 24), "tapu-bulu": ctx("tapu-bulu", 23)}
games = []
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    m = re.search(r"读取到的 seed 是 (\d+)", t)
    rep = re.search(
        r"战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 (\d)/4\n路线：(.*)\n", t
    )
    team = re.search(r"队伍: (\[.*?\])，自己的 PP", t)
    if not (m and rep and team):
        continue
    boss = "tapu-bulu" if "卡璞・哞哞" in t else "mewtwo"
    c, d, P, Q = C[boss]
    names = [n for n, _ in ast.literal_eval(team[1])]
    lair = next(
        (L for L in (Lair(d, int(m[1]), e) for e in range(4)) if names[0] in L.candidates()[:3]),
        None,
    )
    if lair is None:
        continue
    enc = lair.encounters()
    opp = []
    for i, z in enumerate(x.strip() for x in rep[5].split("→")):
        hit = [n for n in enc[str(i + 1)] if d.pokemon_object(n).name("zh-Hans") == z]
        if hit:
            opp.append(hit[0])
    if len(opp) != 3:
        continue
    games.append(
        (
            boss,
            rep[1] == "胜",
            int(rep[2]),
            float(rep[3]),
            Q.score(names[0], names[1:], tuple(opp))[0],
            P.score(names[0], names[1:], tuple(opp))[0],
        )
    )


def auc(xs, ys):
    pos = [x for x, y in zip(xs, ys) if y]
    neg = [x for x, y in zip(xs, ys) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


for boss in ("mewtwo", "tapu-bulu"):
    g = [x for x in games if x[0] == boss]
    w = [x for x in g if x[1]]
    for name, i in (("原型", 4), ("现在", 5)):
        print(
            f"== {boss} {len(g)} 局 {name}: 输赢 AUC {auc([x[i] for x in g], [x[1] for x in g]):.3f}；和倒下 {st.correlation([x[i] for x in g], [x[2] for x in g]):+.2f}；和用时(赢) {st.correlation([x[i] for x in w], [x[3] for x in w]):+.2f}"
        )
