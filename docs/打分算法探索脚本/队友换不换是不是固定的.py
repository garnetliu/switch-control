"""同一个 seed、同一条路线、自己每一关换不换也一样的几局，队友手上的宝可梦每局是不是完全一样。

一样就说明队友换不换、换给谁、研究员给什么都是 seed 定死的，不是每局临时随机的。
"""
import ast, collections, glob, re, sys
groups = collections.defaultdict(list)
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        teams = [tuple(n for n, _ in ast.literal_eval(x)) for x in re.findall(r"队伍: (\[.*?\])，自己的 PP", p)]
        if len(teams) < 2: continue
        # 自己每一场上场的是谁，就包含了首发、路线上换没换
        own = tuple(team[0] for team in teams)
        route = re.search(r"\n路线：(.*)\n", p)
        for depth in range(2, len(teams) + 1):
            # 到第 depth 场开打为止：自己的选择一样的归一组，看队友是不是一样
            groups[(seed, route[1] if route else "", own[:depth])].append(tuple(team[1:] for team in teams[:depth]))
same = diff = 0; examples = []
by_depth = collections.defaultdict(lambda: [0, 0])
for key, runs in groups.items():
    if len(runs) < 2: continue
    ok = len(set(runs)) == 1
    by_depth[len(key[2])][0 if ok else 1] += 1
    if ok: same += 1
    else:
        diff += 1
        if len(examples) < 4: examples.append((key[0], key[2], collections.Counter(run[-1] for run in runs).most_common(3)))
print(f"打了 2 局以上、自己的选择一样的组: {same + diff}，队友每局完全一样的 {same}，有不一样的 {diff}")
for depth in sorted(by_depth): print(f"   到第 {depth} 场开打为止: 一样 {by_depth[depth][0]} 组，不一样 {by_depth[depth][1]} 组")
for e in examples: print("   不一样的例子:", e)
