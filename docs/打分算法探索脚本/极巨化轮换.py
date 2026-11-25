"""验证：自己每 4 个回合可以极巨化一次，极巨化期间（3 回合，或到这场结束）不计回合。"""

import collections
import glob
import re

runs = []
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    fights = []
    cur = None
    pending = False
    for line in t.splitlines():
        if "队伍: [" in line:
            cur = []
            fights.append(cur)
            pending = False
        elif cur is None:
            continue
        elif "INFO: 极巨化" in line:
            pending = True
        elif re.search(r"INFO: 用第 \d 个招式", line):
            cur.append(pending)
            pending = False
    if fights:
        runs.append(fights)


def simulate(fights, wait_after, length=3):
    out = []
    wait = 0
    left = 0
    for fight in fights:
        left = 0  # 这场结束，极巨化也结束
        for actual in fight:
            if left > 0:
                left -= 1
                out.append((False, actual, "极巨化期间"))
            elif wait == 0:
                out.append((True, actual, "该轮到"))
                left = length - 1
                wait = wait_after
            else:
                wait -= 1
                out.append((False, actual, "等待"))
    return out


for wait_after in (3, 4):
    c = collections.Counter()
    perfect = 0
    first_miss = collections.Counter()
    for fights in runs:
        res = simulate(fights, wait_after)
        for p, a, _ in res:
            c[(p, a)] += 1
        ok = all(p == a for p, a, _ in res)
        perfect += ok
        if not ok:
            i = next(i for i, (p, a, _) in enumerate(res) if p != a)
            first_miss[("预测有实际没有" if res[i][0] else "预测没有实际有")] += 1
    tot = sum(c.values())
    print(
        f"极巨化结束后再等 {wait_after} 个回合: {len(runs)} 局 {tot} 个回合；预测和实际一致 {(c[(True, True)] + c[(False, False)]) / tot:.1%}；"
        f"实际极巨化 {c[(True, True)] + c[(False, True)]} 次，预测中 {c[(True, True)]} 次，预测有实际没有 {c[(True, False)]}，预测没有实际有 {c[(False, True)]}；整局全对 {perfect} 局；第一处不一致 {dict(first_miss)}"
    )
