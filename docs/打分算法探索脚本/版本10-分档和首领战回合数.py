"""版本 10 用到的几项日志统计：前三关按自己的伤害分档后实际打几个回合、几种推轮换的办法哪个准、
带小数的回合数要不要加半个回合、首领战回合数和四只进攻合计的关系。"""
import ast, glob, re, statistics as st
from collections import Counter, defaultdict
import numpy as np
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.plan import Planner, fight, rotate
c = GameConfig(); d = GameData(c); D = d.rental_damages(); BOSS = d.boss_attack_defense()
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in D}
games = []
for file in sorted(glob.glob("logs/swsh-lair/start/*.log")):
    t = open(file, encoding="utf-8", errors="replace").read()
    rep = re.search(r"战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 (\d)/4\n路线：(.*)\n", t)
    teams = list(re.finditer(r"队伍: (\[.*?\])，自己的 PP", t))
    if not rep or not teams: continue
    fights = []
    for i, m in enumerate(teams):
        seg = t[m.end(): teams[i + 1].start() if i + 1 < len(teams) else len(t)]
        fights.append(dict(team=[n for n, _ in ast.literal_eval(m[1])], turns=len(re.findall(r"INFO: 用第 \d 个招式", seg)), faints=len(re.findall(r"有一只倒下了", seg))))
    games.append(dict(boss="tapu-bulu" if "卡璞・哞哞" in t else "mewtwo", win=rep[1] == "胜", caught=int(rep[4]), opp=[zh.get(x.strip()) for x in rep[5].split("→")], fights=fights))

def old(dmg, wait, team):
    """版本 9：全按公式。返回 (带小数的回合数, 整数回合数, wait)。"""
    left = 0; health = 1.0; n = 0
    while True:
        dyn, left, wait = rotate(left, wait, c); n += 1
        hit = c.stage_own_rate * dmg[1 if dyn else 0] + c.stage_team_rate * team + c.stage_base_rate
        if hit >= health or n == c.stage_max_turns: return n - 1 + min(health / hit, 1), n, wait
        health -= hit
def variant(mode):
    """1.3 到 2.0 那一档推轮换的办法：mode 是 1（全按 1 回合）、2（全按 2 回合）、"公式"（公式说这回合打完就 1，否则 2）。"""
    def run(dmg, wait, team):
        left = 0; health = 1.0; n = 0
        while True:
            dyn, left, wait = rotate(left, wait, c); n += 1; v = dmg[1 if dyn else 0]
            hit = c.stage_own_rate * v + c.stage_team_rate * team + c.stage_base_rate
            if v >= c.stage_sure_damage: return n, n, wait
            if v >= c.stage_likely_damage:
                if mode == 2 or (mode == "公式" and hit < health): _, left, wait = rotate(left, wait, c); n += 1
                return n, n, wait
            if hit >= health or n == c.stage_max_turns: return n, n, wait
            health -= hit
    return run
METHODS = {"版本 9 的公式": old, "分档，1.3~2.0 全按 1 回合": variant(1), "分档，1.3~2.0 全按 2 回合": variant(2), "分档，1.3~2.0 看公式": variant("公式"),
           "现在的代码（再加：不到 1.3、公式算 1 回合的按 2 回合）": lambda dmg, wait, team: fight(dmg, wait, c, team)}
diffs = defaultdict(list); tiers = defaultdict(list); low = []; bosses = []
for g in games:
    waits = {name: 0 for name in METHODS}; done = 0
    for i, f in enumerate(g["fights"][:3]):
        if i >= g["caught"] or i >= len(g["opp"]) or not g["opp"][i] or not f["turns"] or any(n not in D for n in f["team"]): break
        o = g["opp"][i]; own = f["team"][0]; team = sum(D[m][o][2] for m in f["team"][1:])
        first = D[own][o][1 if waits["版本 9 的公式"] == 0 else 0]
        for name, method in METHODS.items():
            frac, n, waits[name] = method(D[own][o], waits[name], team)
            diffs[name].append(f["turns"] - n)
            if name == "版本 9 的公式":
                tiers["2.0 以上" if first >= 2 else "1.3 到 2.0" if first >= 1.3 else "1.0 到 1.3" if first >= 1 else "1.0 以下"].append((f["turns"], n))
                if first < 1.3: low.append((f["turns"], frac, n))
        done += 1
    if done == 3 and len(g["fights"]) == 4 and g["fights"][3]["turns"] and all(n in BOSS for n in g["fights"][3]["team"]):
        f = g["fights"][3]; P = Planner(d, c, g["boss"]); B = {n: v[g["boss"]] for n, v in BOSS.items()}
        first, average = P.boss_attack(f["team"][0], waits["现在的代码（再加：不到 1.3、公式算 1 回合的按 2 回合）"])
        mates = sum(B[m][0] for m in f["team"][1:])
        bosses.append(dict(boss=g["boss"], win=g["win"], turns=f["turns"], faints=f["faints"], first=first + mates, average=average + mates, received=sum(B[m][2] for m in f["team"])))
print("== 前三关按自己第 1 回合的伤害分档")
for name in ("2.0 以上", "1.3 到 2.0", "1.0 到 1.3", "1.0 以下"):
    v = tiers[name]; cnt = Counter(t for t, _ in v)
    print(f"  {name}: {len(v)} 场，实际回合 {dict(sorted(cnt.items()))}，平均 {st.mean(t for t, _ in v):.2f}，1 回合打完的占 {cnt[1] / len(v):.0%}，公式对的占 {sum(t == n for t, n in v) / len(v):.0%}")
v = [t for t, _, n in low if n == 1]
print(f"  不到 1.3、公式算 1 回合的 {len(v)} 场，实际回合 {dict(sorted(Counter(v).items()))}")
print("== 推轮换用的整数回合数和实际一样的比例")
for name, v in diffs.items():
    print(f"  {name}: {len(v)} 场，完全对 {sum(x == 0 for x in v) / len(v):.1%}，平均差 {st.mean(abs(x) for x in v):.3f} 回合")
print("== 不到 1.3 的场，公式带小数的回合数和实际")
print(f"  {len(low)} 场，实际平均 {st.mean(r[0] for r in low):.2f}，带小数的平均 {st.mean(r[1] for r in low):.2f}，取整的平均 {st.mean(r[2] for r in low):.2f}")
for add in (0, 0.25, 0.5):
    print(f"  加 {add}: 和实际的平均差 {st.mean(abs(r[0] - (r[1] + add)) for r in low):.3f} 回合")
print("== 首领战回合数和四只进攻合计（赢的局）")
for boss in ("mewtwo", "tapu-bulu", "全部"):
    W = [r for r in bosses if r["win"] and boss in ("全部", r["boss"])]
    y = np.array([1 / r["turns"] for r in W]); A = np.array([r["average"] for r in W])
    print(f"  {boss} {len(W)} 局：1 ÷ 回合数 = {(A @ y) / (A @ A):.3f} × 合计，相关 {np.corrcoef(A, y)[0, 1]:.2f}")
for lo, hi in ((0, 1.0), (1.0, 1.3), (1.3, 1.9), (1.9, 2.3), (2.3, 9)):
    s = [r for r in bosses if r["win"] and lo <= r["first"] < hi]
    if s: print(f"  第 1 回合合计 {lo} 到 {hi}: {len(s)} 局，回合 {dict(sorted(Counter(r['turns'] for r in s).items()))}，平均 {st.mean(r['turns'] for r in s):.2f}，首领战平均倒下 {st.mean(r['faints'] for r in s):.2f}")
print(f"  首领战倒下次数和「实际回合 × 四只挨打合计」的相关 {st.correlation([r['turns'] * r['received'] for r in bosses], [float(r['faints']) for r in bosses]):.2f}，和四只挨打合计的相关 {st.correlation([r['received'] for r in bosses], [float(r['faints']) for r in bosses]):.2f}")
