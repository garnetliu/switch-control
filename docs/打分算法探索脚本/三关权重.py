"""探索三关的权重：用日志里实际打过的局、基准图和几张有实测的图来比。"""
import ast, glob, re, statistics as st, itertools
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import Planner, paths
TOP = {"mewtwo": 24, "tapu-bulu": 23}
def env(boss, own, mate, tw, sw=(0.3, 0.2, 0.1)):
    c = GameConfig(); c.stage_weights = sw; c.lair_first_draw_top = TOP[boss]; c.own_boss_exponents = own; c.teammate_boss_exponents = mate; c.teammate_weight = tw
    d = GameData(c); return c, d, Planner(d, c, boss)
games = []
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    m = re.search(r"读取到的 seed 是 (\d+)", t)
    rep = re.search(r"第 (\d+) 轮战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 (\d)/4\n路线：(.*)\n", t)
    team = re.search(r"队伍: (\[.*?\])，自己的 PP", t)
    if not (m and rep and team): continue
    boss = "tapu-bulu" if "卡璞・哞哞" in t else "mewtwo"
    c, d, _ = env(boss, (1, 1), (1, 1), 0.2)
    names = [n for n, _ in ast.literal_eval(team[1])]
    lair = next((L for L in (Lair(d, int(m[1]), e) for e in range(4)) if names[0] in L.candidates()[:3]), None)
    if lair is None: continue
    enc = lair.encounters(); opp = []
    for i, z in enumerate(x.strip() for x in rep[6].split("→")):
        hit = [n for n in enc[str(i + 1)] if d.pokemon_object(n).name("zh-Hans") == z]
        if hit: opp.append(hit[0])
    if len(opp) != 3: continue
    games.append((boss, names[0], tuple(names[1:]), tuple(opp), rep[2] == "胜", int(rep[3]), float(rep[4])))
def auc(xs, ys):
    pos = [x for x, y in zip(xs, ys) if y]; neg = [x for x, y in zip(xs, ys) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
BL = Lair(env("mewtwo", (1, 1), (1, 1), 0.2)[1], 3076008315599927110)
def bench(P):
    n = BL.candidates()[:3]; rows = []
    for s in range(3):
        for path in paths(BL.map_type()):
            opp = tuple(BL.encounters()[str(r)][col] for r, col in path)
            t, o, m, x = P.score(n[s], BL.teammates(s), opp); rows.append((t, o, n[s], "→".join(opp)))
    top = max(r[1] for r in rows); ok = sorted((r for r in rows if r[1] >= 0.8 * top), reverse=True); key = [(r[2], r[3]) for r in ok]
    fa = {(r[2], r[3]): r[0] for r in rows}; A = ("pangoro", "fraxure→obstagoon→sneasel"); B = ("pangoro", "swoobat→tauros→sneasel")
    weak = next(i + 1 for i, r in enumerate(sorted(rows, reverse=True)) if r[2] != "pangoro")
    return (key.index(A) + 1 if A in key else 99), fa[A] / fa[B] - 1, weak

D0 = env("mewtwo", (1, 1), (1, 1), 0.2)[1].rental_damages()
def choose(seed, boss, sw):
    c, d, P = env(boss, (1.1, 0.9), (0.9, 1.1), 0.2, sw)
    l = Lair(d, seed); n = l.candidates()[:3]
    p = P.best(n, l.encounters(), l.map_type(), l.teammates)
    own = n[p.starter]; dm = []
    for o, s in zip(p.opponents, p.swaps): dm.append([round(x, 2) for x in D0[own][o]]); own = o if s else own
    return f"{n[p.starter]} {'→'.join(p.opponents)} {''.join('换' if x else '留' for x in p.swaps)} 伤害{dm}"
SHAPES = [(0.3, 0.2, 0.1), (0.25, 0.2, 0.15), (0.2, 0.2, 0.2), (0.15, 0.2, 0.25), (0.1, 0.2, 0.3),
          (0.15, 0.1, 0.05), (0.1, 0.1, 0.1), (0.05, 0.1, 0.15), (0.0, 0.0, 0.0),
          (0.4, 0.25, 0.15), (0.27, 0.27, 0.26), (0.15, 0.25, 0.4), (0.4, 0.1, 0.1), (0.1, 0.1, 0.4), (0.1, 0.4, 0.1)]
print("局数", {b: sum(x[0] == b for x in games) for b in TOP})
print("三关权重(首领=1-合计) | 超梦: 输赢AUC 倒下相关 用时相关 | 哞哞: AUC 倒下 用时 | 基准: 斧牙龙名次 领先 无80%线时非熊猫最高")
for sw in SHAPES:
    res = {}
    for boss in TOP:
        _, _, P = env(boss, (1.1, 0.9), (0.9, 1.1), 0.2, sw)
        g = [x for x in games if x[0] == boss]; sc = [P.score(x[1], x[2], x[3])[0] for x in g]
        w = [(s, x) for s, x in zip(sc, g) if x[4]]
        res[boss] = (auc(sc, [x[4] for x in g]), st.correlation(sc, [x[5] for x in g]), st.correlation([s for s, _ in w], [x[6] for _, x in w]))
        if boss == "mewtwo": b = bench(P)
    m, u = res["mewtwo"], res["tapu-bulu"]
    print(f"{sw} 首领{1-sum(sw):.2f} | {m[0]:.3f} {m[1]:+.2f} {m[2]:+.2f} | {u[0]:.3f} {u[1]:+.2f} {u[2]:+.2f} | {b[0]} {b[1]:+.1%} {b[2]}")
print()
for seed, boss, name in [(9004205710319247536, "tapu-bulu", "哞哞 搜出来第1名(实测8.0分 换换换)"), (15116150022334671996, "tapu-bulu", "哞哞 日志最高分(逐电犬 11.3~14.2分)"), (6872535256541728132, "tapu-bulu", "哞哞 怪颚龙赢的那张(留换留 12.1分)"), (3477042723512954677, "mewtwo", "超梦 大王铜象那张")]:
    print("==", name); last = None
    for sw in SHAPES[:9]:
        r = choose(seed, boss, sw)
        print(f"   {sw}: {r}" if r != last else f"   {sw}: 同上"); last = r
