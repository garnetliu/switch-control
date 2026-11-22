"""前三关预测回合和实际的偏差，和这一场有没有倒下、自己是不是比对手慢的关系。"""
import ast, glob, re, statistics as st, collections
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.plan import fight
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
        if m: cur = dict(team=[n for n, _ in ast.literal_eval(m[1])], turns=0, faints=0); fights.append(cur)
        elif cur is None: continue
        elif re.search(r"INFO: 用第 \d 个招式", line): cur["turns"] += 1
        elif "有一只倒下了" in line: cur["faints"] += 1
    caught = len(re.findall(r"INFO: 抓第 \d 只", t)); wait = 0
    for i, x in enumerate(fights[:3]):
        if i >= caught or i >= len(opp) or not opp[i] or not x["turns"] or any(n not in D for n in x["team"]): break
        o = opp[i]; own = x["team"][0]; team = sum(D[m][o][2] for m in x["team"][1:])
        # 预测回合
        n = 0; w = wait
        for turns in range(1, 11):
            v, w2 = fight(D[own][o], wait, c, team, turns)
            # 用 fight 自己预测的回合数
        _, wait_after = fight(D[own][o], wait, c, team)
        hp = 1.0; left = 0; ww = wait; pred = 0
        while hp > 0 and pred < 10:
            if left > 0: left -= 1; val = D[own][o][1]
            elif ww == 0: left = 2; ww = 3; val = D[own][o][1]
            else: ww -= 1; val = D[own][o][0]
            hp -= c.stage_own_rate * val + c.stage_team_rate * team + c.stage_base_rate; pred += 1
        P, O = d.pokemon_object(own), d.pokemon_object(o)
        slower = sum(d.pokemon_object(m).stats[5] < O.stats[5] for m in x["team"])
        rows.append((x["turns"] - pred, x["faints"], slower, D[o][own][0]))
        wait = wait_after
print(len(rows), "场；实际回合 − 预测回合 的分布:", sorted(collections.Counter(r[0] for r in rows).items()))
for label, pick in (("实际比预测多", lambda r: r[0] > 0), ("一样", lambda r: r[0] == 0), ("实际比预测少", lambda r: r[0] < 0)):
    R = [r for r in rows if pick(r)]
    print(f"{label}: {len(R)} 场，这一场有倒下的占 {sum(r[1] > 0 for r in R)/len(R):.0%}，平均倒下 {st.mean(r[1] for r in R):.2f} 次，四只里比对手慢的平均 {st.mean(r[2] for r in R):.1f} 只")
A = [r for r in rows if r[1] > 0]; B = [r for r in rows if r[1] == 0]
print(f"有倒下的 {len(A)} 场：实际比预测平均多 {st.mean(r[0] for r in A):+.2f} 回合；没倒下的 {len(B)} 场：{st.mean(r[0] for r in B):+.2f} 回合，回合数完全对的占 {sum(r[0]==0 for r in B)/len(B):.0%}")
