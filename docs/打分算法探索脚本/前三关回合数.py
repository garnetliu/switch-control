"""前三关：实际回合数 和 自己的伤害（按当时是不是极巨化取普通或极巨招式）的关系。"""

import ast
import glob
import re
import statistics as st

import numpy as np
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData

d = GameData(GameConfig())
T = d.rental_damages()
N = {a: {b: v[0] for b, v in row.items()} for a, row in T.items()}
M = {a: {b: v[1] for b, v in row.items()} for a, row in T.items()}
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in N}
rows = []
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    r = re.search(r"\n路线：(.*)\n", t)
    if not r:
        continue
    opp = [zh.get(x.strip()) for x in r[1].split("→")]
    fights = []
    cur = None
    pending = False
    for line in t.splitlines():
        m = re.search(r"队伍: (\[.*?\])，自己的 PP", line)
        if m:
            cur = dict(own=ast.literal_eval(m[1])[0][0], flags=[])
            fights.append(cur)
            pending = False
        elif cur is None:
            continue
        elif "INFO: 极巨化" in line:
            pending = True
        elif re.search(r"INFO: 用第 \d 个招式", line):
            cur["flags"].append(pending)
            pending = False
    caught = len(re.findall(r"INFO: 抓第 \d 只", t))
    for i, fight in enumerate(fights[:3]):
        if (
            i >= len(opp)
            or opp[i] is None
            or fight["own"] not in N
            or i >= caught
            or not fight["flags"]
        ):
            continue
        left = 0
        vals = []
        for flag in fight["flags"]:
            if flag:
                left = 3
            vals.append(M[fight["own"]][opp[i]] if left > 0 else N[fight["own"]][opp[i]])
            left = max(0, left - 1)
        rows.append((i, len(fight["flags"]), st.mean(vals), vals[0], fight["flags"][0]))
print(len(rows), "场")
c = st.correlation
for i in (0, 1, 2, "all"):
    R = [r for r in rows if i == "all" or r[0] == i]
    y = np.array([1 / r[1] for r in R])
    X = np.c_[[r[2] for r in R], np.ones(len(R))]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xc = np.c_[np.minimum([r[2] for r in R], 1.5), np.ones(len(R))]
    cc, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    print(
        f"第 {i if i == 'all' else i + 1} 关 {len(R)} 场: 平均回合 {st.mean(r[1] for r in R):.2f}；1/回合 = {coef[0]:.2f}×自己伤害 + {coef[1]:.2f}，相关 {c([r[2] for r in R], list(y)):+.2f}；伤害封顶 1.5: {cc[0]:.2f}×伤害 + {cc[1]:.2f} 相关 {c(list(np.minimum([r[2] for r in R], 1.5)), list(y)):+.2f}"
    )
print("按自己伤害分段的平均回合数:")
for lo, hi in (
    (0, 0.2),
    (0.2, 0.4),
    (0.4, 0.6),
    (0.6, 0.8),
    (0.8, 1.0),
    (1.0, 1.3),
    (1.3, 1.7),
    (1.7, 9),
):
    R = [r for r in rows if lo <= r[2] < hi]
    if R:
        print(
            f"   {lo}~{hi}: {len(R)} 场，平均 {st.mean(r[1] for r in R):.2f} 回合，1 回合打完的占 {sum(r[1] == 1 for r in R) / len(R):.0%}"
        )
