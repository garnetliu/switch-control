"""一关打几个回合：把队友对这一关对手的伤害也算进去，能不能预测得更准。再看首领第 1 回合极巨化的局快多少。"""
import ast, glob, re, statistics as st, itertools
from dataclasses import replace
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.scoring import damage, Field
d = GameData(GameConfig()); D = d.rental_damages(); f = Field()
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in D}
cache = {}
def avg(a, b):  # a 四个普通招式打 b 的平均
    if (a, b) not in cache:
        A, B = replace(d.pokemon_object(a), dynamax=False), d.pokemon_object(b)
        cache[(a, b)] = st.mean(max(damage(A, i, B, f) / 2, 0) for i in range(len(A.moves)))
    return cache[(a, b)]
runs = []
for file in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(file, encoding="utf-8", errors="replace").read()
    r = re.search(r"\n路线：(.*)\n", t); rep = re.search(r"战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟", t)
    if not r or not rep: continue
    opp = [zh.get(x.strip()) for x in r[1].split("→")]
    fights = []; cur = None; pending = False
    for line in t.splitlines():
        m = re.search(r"(\d\d):(\d\d):(\d\d) .*队伍: (\[.*?\])，自己的 PP", line)
        if m: cur = dict(team=[n for n, _ in ast.literal_eval(m[4])], flags=[], at=int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])); fights.append(cur); pending = False
        elif cur is None: continue
        elif "INFO: 极巨化" in line: pending = True
        elif re.search(r"INFO: 用第 \d 个招式", line): cur["flags"].append(pending); pending = False
        m2 = re.search(r"(\d\d):(\d\d):(\d\d) .*抓了首领", line)
        if m2 and cur: cur["end"] = int(m2[1]) * 3600 + int(m2[2]) * 60 + int(m2[3])
    caught = len(re.findall(r"INFO: 抓第 \d 只", t))
    if len(fights) >= 3 and caught >= 3 and all(o for o in opp) and all(x["flags"] and all(n in D for n in x["team"]) for x in fights[:3]):
        runs.append((fights, opp, rep[1] == "胜", float(rep[3])))
print(len(runs), "局")
def sim(pair, wait, own_rate, team, end):
    n, m = pair[0], pair[1]; left = 0; hp = 1.0; t = 0
    while hp > end and t < 10:
        if left > 0: left -= 1; x = m
        elif wait == 0: left = 2; wait = 3; x = m
        else: wait -= 1; x = n
        hp -= own_rate * x + team; t += 1
    return t, wait
dmg = {n: sum(m.base_power > 0 for m in d.pokemon_object(n).moves) / len(d.pokemon_object(n).moves) for n in D}
MEASURES = {"四招平均": lambda m, o: avg(m, o), "最好的招式": lambda m, o: D[m][o][0], "最好的招式×伤害招式占比": lambda m, o: D[m][o][0] * dmg[m]}
for name, fn in MEASURES.items():
    best = []
    for a, b, c, end in itertools.product((0.3, 0.4, 0.5), (0.0, 0.15, 0.3, 0.45, 0.6, 0.8), (0.0, 0.1, 0.2, 0.29), (0.0,)):
        exact = tot = 0; hit = n19 = guess = 0
        for fights, opp, win, minutes in runs:
            wait = 0
            for x, o in zip(fights[:3], opp):
                team = b * sum(fn(m, o) for m in x["team"][1:]) + c
                t, wait = sim(D[x["team"][0]][o], wait, a, team, end); tot += 1; exact += t == len(x["flags"])
            if len(fights) > 3 and fights[3]["flags"]:
                actual = fights[3]["flags"][0]; n19 += actual; guess += wait == 0; hit += actual and wait == 0
        best.append((exact / tot, a, b, c, hit, guess, n19))
    for row in sorted(best, reverse=True)[:2]: print(name, "| 回合数完全对 %.0f%%  自己×%.1f 队友×%.2f 常数%.2f | 首领第1回合极巨化: 实际 %d，预测 %d，猜中 %d" % (row[0] * 100, row[1], row[2], row[3], row[6], row[5], row[4]))
