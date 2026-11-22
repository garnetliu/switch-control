"""按规则从 seed 算出每一场开打时三个队友手上是什么，和日志里实际的队伍比。

比的是结果（每场开打时的队伍），不是中间每一步，所以「队友先换上抓到的、马上又被研究员换掉」这种也能对。
用法：PYTHONPATH=src uv run python 这个脚本 [另外的日志文件...]
"""
import collections, sys
src = open("docs/打分算法探索脚本/队友换不换-连上研究员和背包客.py").read(); src = src[:src.index("res = []\nfor pack, berry")]
exec(src.replace("if ok and events: runs.setdefault((boss, seed, tuple((e[0], e[1] == \"自己\") for e in events)), events)",
                 "if ok and events: runs.setdefault((boss, seed, tuple((e[0], e[1] == \"自己\") for e in events)), events); teams_of[(boss, seed, tuple((e[0], e[1] == \"自己\") for e in events))] = teams").replace("zh = {}; runs = {}", "zh = {}; runs = {}; teams_of = {}"))
stat = collections.Counter(); bad = []
for key, events in runs.items():
    boss, seed, sig = key; teams = teams_of[key]; raw, names = get(boss, seed)
    pos = 1 if boss == "tapu-bulu" else 0; team = list(teams[0][1:]); fight = 0; ok_so_far = True; packs = False
    def compare():
        global ok_so_far
        nonlocal_fight = fight
        if nonlocal_fight >= len(teams): return
        same = team == list(teams[nonlocal_fight][1:])
        tag = ("有背包客之后" if packs else "没遇到背包客") + ("" if ok_so_far else "（前面已经错过）")
        stat[tag + " 总"] += 1; stat[tag + " 对"] += same
        if not same and ok_so_far and len(bad) < 6: bad.append((boss[:3], seed, nonlocal_fight + 1, team[:], list(teams[nonlocal_fight][1:])))
        if not same: ok_so_far = False
    for index, (kind, who, name) in enumerate(events):
        if kind == "抓":
            if fight >= 1: pass
            # 抓是在一场打完之后：先核对这一场开打时的队伍（第 1 场不用核对，就是开局的）
            _, pos = draw(raw, pos, 2); want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            got = None
            if want: got, pos = tie(raw, pos, want)
            if who != "自己" and got is not None: team[got] = name
            fight += 1
        elif kind == "研":
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            if want: got, pos = tie(raw, pos, want); team[got] = names[pos]; pos += 1
        elif kind == "背":
            for _ in range(3): _, pos = draw(raw, pos, 4)
            packs = True
        # 下一件事是「抓」或者没有下一件事了，说明这一段路走完、下一场开打了
        if index + 1 == len(events) or events[index + 1][0] == "抓":
            if fight >= 1: compare()
            # 算错了就按实际的队伍接着往下，免得一处错后面全算错
            if fight < len(teams): team = list(teams[fight][1:])
for k in sorted(stat): print(k, stat[k])
print("头几个对不上的（首领, seed, 第几场开打, 算出来的, 实际的）:")
for b in bad: print("  ", b)
