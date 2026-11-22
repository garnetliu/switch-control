"""预测的伤害留多少余量，实际才能保证在预测的回合数内打完。

余量 = 预测的那几个回合里一共打掉的血量 ÷ 对手的血量。刚好打完是 1.0，1.6 就是多打出 60%。
"""
import ast, glob, re
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
c = GameConfig(); d = GameData(c); D = d.rental_damages()
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in D}
rows = []
for file in sorted(glob.glob("logs/swsh-lair/start/*.log")):
    t = open(file, encoding="utf-8", errors="replace").read()
    r = re.search(r"\n路线：(.*)\n", t)
    if not r: continue
    opp = [zh.get(x.strip()) for x in r[1].split("→")]
    fights = []; cur = None
    for line in t.splitlines():
        m = re.search(r"队伍: (\[.*?\])，自己的 PP", line)
        if m: cur = dict(team=[n for n, _ in ast.literal_eval(m[1])], turns=0); fights.append(cur); continue
        if cur is not None and re.search(r"INFO: 用第 \d 个招式", line): cur["turns"] += 1
    caught = len(re.findall(r"INFO: 抓第 \d 只", t)); wait = 0
    for i, x in enumerate(fights[:3]):
        if i >= caught or i >= len(opp) or not opp[i] or not x["turns"] or any(n not in D for n in x["team"]): break
        o = opp[i]; own = x["team"][0]; team = sum(D[m][o][2] for m in x["team"][1:])
        left = 0; ww = wait; total = 0.0; done = []   # done[k] = 前 k+1 个回合一共打掉的血量
        for _ in range(10):
            if left > 0: left -= 1; val = D[own][o][1]
            elif ww == 0: left = 2; ww = 3; val = D[own][o][1]
            else: ww -= 1; val = D[own][o][0]
            total += c.stage_own_rate * val + c.stage_team_rate * team + c.stage_base_rate; done.append(total)
            if total >= 1 and len(done) == 1 or (total >= 1 and done[-2] < 1): pred = len(done); wait_after = ww
        rows.append(dict(actual=x["turns"], pred=pred, done=done)); wait = wait_after
print(len(rows), "场")
print("\n一、预测的回合数内打完的把握：按余量分段")
for lo, hi in ((1.0, 1.2), (1.2, 1.4), (1.4, 1.6), (1.6, 1.8), (1.8, 2.2), (2.2, 9)):
    R = [r for r in rows if lo <= r["done"][r["pred"] - 1] < hi]
    if R: print(f"   余量 {lo}~{hi}: {len(R)} 场，实际在预测的回合数内打完的占 {sum(r['actual'] <= r['pred'] for r in R)/len(R):.0%}")
print("\n二、想要 N 个回合内打完：N 个回合的余量至少要多少")
for n in (1, 2, 3):
    print(f"   {n} 个回合内:")
    for need in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
        R = [r for r in rows if r["done"][n - 1] >= need]
        if R: print(f"      余量 ≥ {need}: {len(R)} 场，实际 {n} 个回合内打完的占 {sum(r['actual'] <= n for r in R)/len(R):.0%}")
