"""日志里实际打过的每一局，按现在的算法给它实际用的首发和路线算分，和实际结果对照。"""
import ast, glob, re, statistics as st
from collections import defaultdict
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import Planner
ctx = {}
for boss, top in (("mewtwo", 24), ("tapu-bulu", 23)):
    c = GameConfig(); c.lair_first_draw_top = top; d = GameData(c); ctx[boss] = (c, d, Planner(d, c, boss))
ZH = lambda d, n: d.pokemon_object(n).name("zh-Hans") if hasattr(d.pokemon_object(n), "name") else n
games = []; skipped = defaultdict(int)
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    m = re.search(r"读取到的 seed 是 (\d+)", t)
    rep = re.search(r"第 (\d+) 轮战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 (\d)/4\n路线：(.*)\n", t)
    team = re.search(r"队伍: (\[.*?\])，自己的 PP", t)
    if not rep or not team: skipped["没打完或没战报"] += 1; continue
    boss = "tapu-bulu" if "卡璞・哞哞" in t else "mewtwo"
    c, d, P = ctx[boss]
    names = [n for n, _ in ast.literal_eval(team[1])]
    seed = int(m[1]) if m else None
    if seed is None: skipped["锁定的局日志里没有 seed"] += 1; continue
    lair = next((L for L in (Lair(d, seed, e) for e in range(4)) if names[0] in L.candidates()[:3]), None)
    if lair is None: skipped["seed 对不上首发"] += 1; continue
    enc = lair.encounters(); route_zh = [x.strip() for x in rep[6].split("→")]
    opp = []
    for i, z in enumerate(route_zh):
        hit = [n for n in enc[str(i + 1)] if d.pokemon_object(n).name("zh-Hans") == z]
        if not hit: break
        opp.append(hit[0])
    if len(opp) != 3: skipped["路线对不上"] += 1; continue
    total, stage, boss_score, swaps = P.score(names[0], names[1:], tuple(opp))
    games.append(dict(boss=boss, seed=seed, starter=names[0], opp=tuple(opp), win=rep[2] == "胜", falls=int(rep[3]), minutes=float(rep[4]), total=total, own=stage, mate=boss_score, round=int(rep[1])))
print("解析到", len(games), "局；跳过", dict(skipped))
def auc(xs, ys):
    pos = [x for x, y in zip(xs, ys) if y]; neg = [x for x, y in zip(xs, ys) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg)) if pos and neg else float("nan")
def corr(a, b):
    return st.correlation(a, b) if len(a) > 2 else float("nan")
BEST = {"mewtwo": ("超梦基准 熊猫走斧牙龙", 0.234), "tapu-bulu": ("搜出来的 9004…536", 0.777)}
for boss in ("mewtwo", "tapu-bulu"):
    g = [x for x in games if x["boss"] == boss]
    grp = defaultdict(list)
    for x in g: grp[(x["seed"], x["starter"], x["opp"])].append(x)
    rows = sorted(grp.items(), key=lambda kv: -kv[1][0]["total"])
    wins = [x for x in g if x["win"]]
    print(f"\n== {boss}: {len(g)} 局，{len(rows)} 种（图+首发+路线），胜 {len(wins)}")
    print(f"   总分对输赢的 AUC {auc([x['total'] for x in g],[x['win'] for x in g]):.3f}；三关的分 {auc([x['own'] for x in g],[x['win'] for x in g]):.3f}")
    print(f"   总分和倒下次数的相关 {corr([x['total'] for x in g],[x['falls'] for x in g]):+.2f}；和用时（赢的局）{corr([x['total'] for x in wins],[x['minutes'] for x in wins]):+.2f}；三关的分和用时 {corr([x['own'] for x in wins],[x['minutes'] for x in wins]):+.2f}")
    name, best = BEST[boss]
    over = [(k, v) for k, v in rows if v[0]["total"] > best + 1e-9]
    print(f"   最好的图（{name}）{best}；实际打过的方案里分数比它高的有 {len(over)} 种")
    def show(k, v):
        w = [x for x in v if x["win"]]
        zh = lambda n: ctx[boss][1].pokemon_object(n).name("zh-Hans")
        print(f"   {v[0]['total']:.3f}（三关 {v[0]['own']:.3f}，首领 {v[0]['mate']:.3f}）| {len(v)} 局 胜 {len(w)} | 用时 {st.mean(x['minutes'] for x in w):.1f} | 倒下 {st.mean(x['falls'] for x in v):.2f} | {zh(k[1])}: {'→'.join(zh(o) for o in k[2])} | {k[0]}" if w else
              f"   {v[0]['total']:.3f}（三关 {v[0]['own']:.3f}，首领 {v[0]['mate']:.3f}）| {len(v)} 局 胜 0 | 用时 - | 倒下 {st.mean(x['falls'] for x in v):.2f} | {zh(k[1])}: {'→'.join(zh(o) for o in k[2])} | {k[0]}")
    print("   -- 分数最高的 10 种"); [show(k, v) for k, v in rows[:10]]
    print("   -- 分数最低的 5 种"); [show(k, v) for k, v in rows[-5:]]
    # 按分数分三段
    gs = sorted(g, key=lambda x: -x["total"]); n = len(gs) // 3
    for label, part in (("高分三分之一", gs[:n]), ("中间", gs[n:2 * n]), ("低分三分之一", gs[2 * n:])):
        w = [x for x in part if x["win"]]
        print(f"   {label}: 分数 {part[-1]['total']:.2f}~{part[0]['total']:.2f}，{len(part)} 局，胜率 {len(w)/len(part):.0%}，赢的平均用时 {st.mean(x['minutes'] for x in w):.1f}，平均倒下 {st.mean(x['falls'] for x in part):.2f}")
