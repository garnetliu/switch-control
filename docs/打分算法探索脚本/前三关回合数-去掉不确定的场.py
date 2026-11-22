"""前三关预测回合和实际：去掉有宝可梦倒下的场、自己用过命中不是 100% 的招式的场，再看准不准。"""
import ast, collections, glob, re, statistics as st
from dataclasses import replace
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.plan import fight
from swsh.scoring import damage, Field
c = GameConfig(); d = GameData(c); D = d.rental_damages(); F = Field()
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in D}
rows = []
for file in sorted(glob.glob("logs/swsh-lair/start/*.log")):
    t = open(file, encoding="utf-8", errors="replace").read()
    r = re.search(r"\n路线：(.*)\n", t)
    if not r: continue
    opp = [zh.get(x.strip()) for x in r[1].split("→")]
    fights = []; cur = None; pending = False
    for line in t.splitlines():
        m = re.search(r"队伍: (\[.*?\])，自己的 PP", line)
        if m: cur = dict(team=[n for n, _ in ast.literal_eval(m[1])], moves=[], faints=0); fights.append(cur); pending = False; continue
        if cur is None: continue
        if "INFO: 极巨化" in line: pending = True
        m = re.search(r"INFO: 用第 (\d) 个招式", line)
        if m: cur["moves"].append((int(m[1]) - 1, pending)); pending = False
        elif "有一只倒下了" in line: cur["faints"] += 1
    caught = len(re.findall(r"INFO: 抓第 \d 只", t)); wait = 0
    for i, x in enumerate(fights[:3]):
        if i >= caught or i >= len(opp) or not opp[i] or not x["moves"] or any(n not in D for n in x["team"]): break
        o = opp[i]; own = x["team"][0]; team = sum(D[m][o][2] for m in x["team"][1:])
        _, pred, wait = fight(D[own][o], wait, c, team)
        # 自己实际用的招式：极巨化期间是极巨招式（必中），其余看招式的命中；再看用的是不是伤害最高的那个
        P = d.pokemon_object(own); O = d.pokemon_object(o); left = 0; sure = True; best_used = True
        for index, flag in x["moves"]:
            if flag: left = 3
            if left > 0: left -= 1; continue
            if index >= len(P.moves): continue  # 百变怪变身后的招式，表里没有
            move = P.moves[index]
            if move.accuracy < 1: sure = False  # 命中是 0 到 1
            normal = replace(P, dynamax=False)
            if damage(normal, index, O, F) / 2 < D[own][o][0] - 1e-6: best_used = False
        # 队友用了哪个招式日志里没有：三个队友的伤害招式命中全是 100% 才算满命中
        mates_sure = all(move.accuracy >= 1 for m in x["team"][1:] for move in d.pokemon_object(m).moves if move.base_power > 0)
        # 三个队友一共有几个变化招式（威力是 0 的）
        status = sum(move.base_power <= 0 for m in x["team"][1:] for move in d.pokemon_object(m).moves)
        rows.append(dict(diff=len(x["moves"]) - pred, faints=x["faints"], sure=sure, best=best_used, mates=mates_sure, status=status))
def show(label, R):
    cnt = collections.Counter(r["diff"] for r in R)
    if not R:
        print(f"{label}: 0 场")
        return
    print(f"{label}: {len(R)} 场，回合数完全对 {cnt[0]/len(R):.0%}，实际多 {sum(v for k, v in cnt.items() if k > 0)/len(R):.0%}，实际少 {sum(v for k, v in cnt.items() if k < 0)/len(R):.0%}，平均差 {st.mean(abs(r['diff']) for r in R):.2f} 回合")
show("全部", rows)
show("没有宝可梦倒下", [r for r in rows if not r["faints"]])
show("自己用的招式命中都是 100%（或极巨招式）", [r for r in rows if r["sure"]])
show("没倒下 + 命中 100%", [r for r in rows if not r["faints"] and r["sure"]])
show("没倒下 + 命中 100% + 自己每回合用的都是伤害最高的招式", [r for r in rows if not r["faints"] and r["sure"] and r["best"]])
show("自己和三个队友的招式都是满命中", [r for r in rows if r["sure"] and r["mates"]])
show("自己和队友都满命中 + 没倒下", [r for r in rows if r["sure"] and r["mates"] and not r["faints"]])
for count in sorted({r["status"] for r in rows}):
    show(f"三个队友一共有 {count} 个变化招式", [r for r in rows if r["status"] == count])
show("三个队友都没有变化招式 + 没倒下", [r for r in rows if r["status"] == 0 and not r["faints"]])
show("队友没有变化招式 + 自己满命中", [r for r in rows if r["status"] == 0 and r["sure"]])
show("队友没有变化招式 + 自己和队友都满命中", [r for r in rows if r["status"] == 0 and r["sure"] and r["mates"]])
show("队友没有变化招式 + 自己和队友都满命中 + 没倒下", [r for r in rows if r["status"] == 0 and r["sure"] and r["mates"] and not r["faints"]])
for count in (1, 2, 3):
    show(f"队友有 {count} 个变化招式 + 自己和队友都满命中", [r for r in rows if r["status"] == count and r["sure"] and r["mates"]])
show("自己有回合用的不是伤害最高的招式", [r for r in rows if not r["best"]])
