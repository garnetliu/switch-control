"""首领战打几个回合和四只的进攻的关系。先跑 首领战回合数-取数据.py。"""

import json
import statistics as st

import numpy as np

D = json.load(open("src/control_switch/games/swsh/data/boss_attack_defense_LUT.json"))
G = [g for g in json.load(open("/tmp/turns_data.json")) if len(g["fights"]) == 4]
rows = []
for g in G:
    f = g["fights"][3]
    names = [n for n, _ in f["team"]]
    hp = [h for _, h in f["team"]]
    if any(n not in D for n in names):
        continue
    a = [D[n][g["boss"]][0] for n in names]
    r = [D[n][g["boss"]][2] for n in names]  # 普通进攻、挨打
    rows.append(
        dict(
            boss=g["boss"],
            turns=f["turns"],
            faints=f["faints"],
            win=g["win"],
            own=a[0],
            mates=sum(a[1:]),
            rown=r[0],
            rmates=sum(r[1:]),
            hp=hp,
            a=a,
            r=r,
            minutes=g["minutes"],
        )
    )
c = lambda x, y: st.correlation(x, y)
for boss in ("mewtwo", "tapu-bulu", "all"):
    R = [x for x in rows if boss == "all" or x["boss"] == boss]
    W = [x for x in R if x["win"]]
    y = np.array([1 / x["turns"] for x in W])
    X = np.array([[x["own"], x["mates"]] for x in W])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    Xi = np.c_[X, np.ones(len(W))]
    ci, *_ = np.linalg.lstsq(Xi, y, rcond=None)
    print(f"== {boss}: {len(R)} 局，赢 {len(W)}")
    print(
        f"   赢的局 1/回合数 = {coef[0]:.2f}×自己进攻 + {coef[1]:.2f}×队友进攻合计（队友每点相当于自己的 {coef[1] / coef[0]:.2f}）；带常数项: {ci.round(2)}"
    )
    for k in (0, 0.15, 0.25, 0.35, 0.5, 1):
        p = [1 / (x["own"] + k * x["mates"]) for x in W]
        print(f"   k={k}: 预测回合 和 实际回合 的相关 {c(p, [x['turns'] for x in W]):+.2f}", end="")
        print(f"；和用时 {c(p, [x['minutes'] for x in W]):+.2f}")
    # 倒下：和 回合×挨打 的关系
    print(
        "   首领战倒下次数 和：实际回合 %+.2f，四只挨打合计 %+.2f，自己挨打 %+.2f，实际回合×四只挨打 %+.2f"
        % (
            c([x["turns"] for x in R], [x["faints"] for x in R]),
            c([x["rown"] + x["rmates"] for x in R], [x["faints"] for x in R]),
            c([x["rown"] for x in R], [x["faints"] for x in R]),
            c([x["turns"] * (x["rown"] + x["rmates"]) for x in R], [x["faints"] for x in R]),
        )
    )
    print(
        "   输赢 和：自己进攻 %+.2f 队友进攻 %+.2f 自己挨打 %+.2f 队友挨打 %+.2f"
        % tuple(
            c([x[k] for x in R], [float(x["win"]) for x in R])
            for k in ("own", "mates", "rown", "rmates")
        )
    )
    print(
        "   平均：回合 %.2f，首领战倒下 %.2f，自己进攻 %.2f，队友进攻合计 %.2f"
        % tuple(st.mean(x[k] for x in R) for k in ("turns", "faints", "own", "mates"))
    )
