"""版本 10 的参数换成别的值会怎样：超梦基准图选不选得对、哞哞三张实测过的图的顺序、日志里的输赢和用时。
每一行只改列出的那几个参数，其余用 game_config 里现在的值。"""

import ast
import glob
import re
import statistics as st

from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import Planner, paths

TOP = {"mewtwo": 24, "tapu-bulu": 23}
BENCH = 3076008315599927110
BULU = (9004205710319247536, 6986731677711377285, 5938375612842167902)


def context(boss, **changes):
    c = GameConfig()
    c.lair_first_draw_top = TOP[boss]
    for key, value in changes.items():
        setattr(c, key, value)
    d = GameData(c)
    return d, Planner(d, c, boss)


games = []
D0 = {boss: context(boss)[0] for boss in TOP}
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
    d = D0[boss]
    names = [n for n, _ in ast.literal_eval(team[1])]
    lair = next(
        (L for L in (Lair(d, int(m[1]), e) for e in range(4)) if names[0] in L.candidates()[:3]),
        None,
    )
    if lair is None:
        continue
    opp = []
    for i, z in enumerate(x.strip() for x in rep[5].split("→")):
        hit = [n for n in lair.encounters()[str(i + 1)] if d.pokemon_object(n).name("zh-Hans") == z]
        if hit:
            opp.append(hit[0])
    if len(opp) == 3:
        games.append((boss, names[0], names[1:], tuple(opp), rep[1] == "胜", float(rep[3])))


def auc(xs, ys):
    pos = [x for x, y in zip(xs, ys) if y]
    neg = [x for x, y in zip(xs, ys) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def plans(d, P, seed):
    l = Lair(d, seed)
    rows = []
    for s in range(3):
        for path in paths(l.map_type()):
            o = tuple(l.encounters()[str(r)][col] for r, col in path)
            rows.append((P.score(l.candidates()[s], l.teammates(s), o), l.candidates()[s], o))
    return sorted(rows, key=lambda r: -r[0][0])


def show(label, **changes):
    d, P = context("mewtwo", **changes)
    r = plans(d, P, BENCH)
    want = next(
        x
        for x in r
        if x[1] == "pangoro"
        and x[2] == ("fraxure", "obstagoon", "sneasel")
        and x[0][3] == (False, False, False)
    )
    lead = want[0][0] / max(x[0][0] for x in r if x is not want) - 1
    out = [f"基准图{'对' if r[0] is want else '错'} {lead:+.1%}"]
    d2, P2 = context("tapu-bulu", **changes)
    totals = [plans(d2, P2, s)[0][0][0] for s in BULU]
    out.append(
        "哞哞 "
        + " / ".join(f"{x:.3f}" for x in totals)
        + (" 对" if totals[0] > totals[1] > totals[2] else " 错")
    )
    for boss, P in (("mewtwo", P), ("tapu-bulu", P2)):
        g = [x for x in games if x[0] == boss]
        sc = [P.score(x[1], x[2], x[3])[0] for x in g]
        w = [(s, x[5]) for s, x in zip(sc, g) if x[4]]
        out.append(
            f"{boss} {len(g)} 局 输赢 AUC {auc(sc, [x[4] for x in g]):.3f} 和用时的相关 {st.correlation([s for s, _ in w], [m for _, m in w]):+.2f}"
        )
    print(f"{label} | " + " | ".join(out), flush=True)


show("现在的参数")
for scale, exponent in ((1.5, 2), (2.5, 2), (4.0, 2), (1.5, 3), (4.0, 3), (2.5, 4), (4.0, 4)):
    show(
        f"boss_hurt_scale {scale}，boss_hurt_exponent {exponent}",
        boss_hurt_scale=scale,
        boss_hurt_exponent=exponent,
    )
for value in (2.2, 2.4):
    show(f"boss_kill_attack {value}", boss_kill_attack=value)
for value in (0.31, 0.34, 0.40):
    show(f"boss_turn_rate {value}", boss_turn_rate=value)
for value in (1.8, 2.2):
    show(f"stage_sure_damage {value}", stage_sure_damage=value)
for value in (1.2, 1.5):
    show(f"stage_likely_damage {value}", stage_likely_damage=value)
show("不分档（两个门槛都设成 99）", stage_sure_damage=99, stage_likely_damage=99)
show("首领战不判断一回合打死（boss_kill_attack 设成 99）", boss_kill_attack=99)
for weights in ((0.2, 0.2, 0.2), (0.2, 0.15, 0.1), (0.35, 0.25, 0.1)):
    show(f"stage_weights {weights}", stage_weights=weights)
