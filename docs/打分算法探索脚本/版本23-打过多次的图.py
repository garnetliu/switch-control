"""日志里完整打过 5 局以上的图，用版本 22 的 PokemonAutomation 选法（--avg，平均队友）算一遍，和实测放在一起。

每张图：算法选的首发、路线；每种实际打过的走法（首发 + 三关对手）的局数、赢、平均倒下、平均用时，
以及它在算法里的首发分、路线分和路线名次。
第一次抽数的上限按日志里的首发和路线反推（试 10～30、多取 0～3 个随机数，候选首发和三关对手都对上的那个）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本23-打过多次的图.py
逐场表用 版本20-逐场取数.py 生成的（环境变量 FIGHTS_JSON）。
"""

import collections
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "--avg"]
source = open(os.path.join(HERE, "版本22-PokemonAutomation的算法.py"), encoding="utf-8").read()
exec(compile(source[: source.index("for boss, seed, routes in MAPS:")], "v22", "exec"))  # noqa: S102

from swsh.lair.lair import Lair  # noqa: E402

FIGHTS = os.environ.get(
    "FIGHTS_JSON",
    "/private/tmp/claude-503/-Users-garnet-projects-control-switch/6882f779-6294-4dce-875c-e2716eed87ee/scratchpad/fights.json",
)
rows = json.load(open(FIGHTS, encoding="utf-8"))
runs = collections.defaultdict(dict)
for row in rows:
    runs[row["file"]][row["stage"]] = row


def minutes(file):
    text = open(os.path.join("runs/logs/swsh-lair/start", file), encoding="utf-8").read()
    found = re.findall(r"用时 ([\d.]+) 分钟", text)
    return float(found[-1]) if found else None


plays = collections.defaultdict(lambda: collections.defaultdict(list))
for file, stages in runs.items():
    if set(stages) != {0, 1, 2, 3}:
        continue
    first = stages[0]
    key = (first["team"][0], stages[0]["opp"], stages[1]["opp"], stages[2]["opp"])
    won = stages[3]["result"] == "赢" if stages[3].get("result") else None
    faints = sum(stages[i]["faints"] for i in range(4))
    plays[(first["seed"], first["boss"])][key].append((faints, won, minutes(file)))

for (seed, boss), variants in sorted(plays.items(), key=lambda kv: (kv[0][1], -sum(len(v) for v in kv[1].values()))):
    if sum(len(v) for v in variants.values()) < 5:
        continue
    seed = int(seed)
    found = None
    for top in range(10, 31):
        config = GameConfig()
        config.lair_first_draw_top = top
        data = GameData(config)
        for extra in range(4):
            lair = Lair(data, seed, extra)
            names = set(lair.candidates()[:3])
            encounters = lair.encounters()
            if all(
                key[0] in names
                and any(tuple(encounters[str(r)][c] for r, c in p) == key[1:] for p in upstream.paths(lair.map_type()))
                for key in variants
            ):
                found = (data, lair)
                break
        if found:
            break
    print(f"\n== {seed}（{boss}）")
    if not found:
        print("  反推不出第一次抽数的上限，跳过")
        continue
    data, lair = found
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    scorer = upstream.Scorer(data, boss)
    _avg_cache.clear()
    candidates = lair.candidates()[:3]
    encounters = lair.encounters()
    starter_scores = {c: m(scorer, c, boss, ()) for c in candidates}
    scored = sorted(
        ((sum(w * m(scorer, encounters[str(r)][c], boss, ()) for w, (r, c) in zip((1, 2, 3), p, strict=True)), p)
         for p in upstream.paths(lair.map_type())),
        reverse=True,
    )
    pick = max(candidates, key=starter_scores.get)
    best_path = tuple(encounters[str(r)][c] for r, c in scored[0][1])
    print("  首发分：" + "，".join(f"{zh(c)} {v:.2f}" for c, v in starter_scores.items())
          + f"；算法选 {zh(pick)}；{' → '.join(zh(n) for n in best_path)}（{scored[0][0]:.2f}，共 {len(scored)} 条）")
    for key, items in sorted(variants.items(), key=lambda kv: -len(kv[1])):
        rank, value = next((k + 1, v) for k, (v, p) in enumerate(scored)
                           if tuple(encounters[str(r)][c] for r, c in p) == key[1:])
        wins = [w for _, w, _ in items if w is not None]
        times = [t for _, _, t in items if t is not None]
        same = "（就是算法选的）" if key[0] == pick and key[1:] == best_path else ""
        print(f"  打过：{zh(key[0])}；{' → '.join(zh(n) for n in key[1:])}{same}：{len(items)} 局，"
              f"赢 {sum(wins)}/{len(wins)}，平均倒下 {statistics.mean(f for f, _, _ in items):.2f}，"
              f"平均 {statistics.mean(times):.1f} 分钟；首发分 {starter_scores[key[0]]:.2f}，路线分 {value:.2f}（第 {rank}）")
