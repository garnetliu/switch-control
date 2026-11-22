"""遇到研究员之后，队友手上的宝可梦变成了什么：换了几只，换上来的对首领是更强还是更弱。"""
import ast, glob, json, re, statistics as st, sys
B = json.load(open("data/swsh/boss_attack_defense_LUT.json"))
import collections
rows = []; rounds = collections.Counter(); result = collections.defaultdict(list)
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        rep = re.search(r"倒下 (\d+) 次，用时 ([\d.]+) 分钟", p); won = "抓了首领" in p
        parts = p.split("队伍: [")
        teams = [ast.literal_eval("[" + x.split("]，自己的 PP")[0] + "]") for x in parts[1:]]
        had = False
        for i in range(1, len(teams)):
            seg = parts[i]
            if "研究员：" not in seg: continue
            had = True
            caught = set(re.findall(r"决定换成 (\S+)", seg)) | set(re.findall(r"继续用 (\S+)", seg))
            # 这一段刚抓到的那只：上一场的对手，可能被队友换上
            before = [n for n, _ in teams[i - 1]][1:]; after = [n for n, _ in teams[i]][1:]
            m = re.search(r"换成 (\S+) 的总分", seg); just = m[1] if m else None
            for old, new in zip(before, after):
                if old != new and new != just and old in B and new in B:
                    rows.append((boss, old, new, B[old][boss][0], B[new][boss][0], B[old][boss][2], B[new][boss][2]))
            rounds[boss] += 1
        if rep: result[(boss, had)].append((won, int(rep[1]), float(rep[2])))
print("遇到研究员的次数:", dict(rounds), "；队友被研究员换掉的只数:", len(rows))
for boss in ("mewtwo", "tapu-bulu"):
    R = [r for r in rows if r[0] == boss]
    if not R: continue
    print(f"{boss}: 换了 {len(R)} 只，平均每次遇到研究员换 {len(R)/rounds[boss]:.2f} 只；对首领的进攻 换之前平均 {st.mean(r[3] for r in R):.2f} → 之后 {st.mean(r[4] for r in R):.2f}，变强的 {sum(r[4] > r[3] for r in R)} 只、变弱的 {sum(r[4] < r[3] for r in R)} 只；挨打 {st.mean(r[5] for r in R):.2f} → {st.mean(r[6] for r in R):.2f}")
    for r in R[:8]: print("    ", r[1], "→", r[2], f"进攻 {r[3]:.2f} → {r[4]:.2f}，挨打 {r[5]:.2f} → {r[6]:.2f}")
print()
for key in sorted(result):
    R = result[key]; W = [r for r in R if r[0]]
    print(f"{key[0]} {'路上有研究员' if key[1] else '没有研究员'}: {len(R)} 局，胜率 {len(W)/len(R):.0%}，赢的平均用时 {st.mean(r[2] for r in W):.1f} 分钟，平均倒下 {st.mean(r[1] for r in R):.2f}")
