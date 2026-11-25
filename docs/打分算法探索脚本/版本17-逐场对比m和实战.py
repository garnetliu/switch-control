"""把同一个 seed 不同路线打过的每一局拆成每一场：实际队伍、回合数、倒下次数，和那一场的 m 放在一起比。

每一场的队伍取进战斗时记的「队伍: [...]」（name_id，早期日志也有）；
回合 = 这一场里自己选招式的次数（「用第 N 个招式」）；倒下 = 「有一只倒下了」；
对手 = 「路线: a → b → c」（name_id），没有这一行的按结尾「第 n 只「X」」的中文名对回去。
m 是现在的算法（upstream.Scorer.matchup，带那一场实际的三个队友）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本17-逐场对比m和实战.py
"""

import ast
import glob
import re
import statistics
from collections import defaultdict

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData

SEEDS = {
    3076008315599927110: "mewtwo",
    12873702124229926581: "tapu-lele",
    16238065963362826354: "cresselia",
}
data = GameData(GameConfig())
zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731


def parse(path):
    """返回 (三关对手 name_id 或中文名, [每一场 {team, turns, faints}])。"""
    route, caught, fights, cur = None, [], [], None
    for line in open(path, encoding="utf-8"):
        m = re.search(r"INFO: 路线: (.+)$", line)
        if m:
            route = [x.strip() for x in m.group(1).split("→")]
            continue
        m = re.search(r"INFO: 队伍: (\[.*?\])，", line)
        if m:
            team = [name for name, _ in ast.literal_eval(m.group(1))]
            if cur is None or cur.get("closed"):
                cur = {"team": team, "turns": 0, "faints": 0}
                fights.append(cur)
            continue
        if cur is None:
            continue
        if re.search(r"用第 \d 个招式", line):
            cur["turns"] += 1
        elif "有一只倒下了" in line:
            cur["faints"] += 1
        elif re.search(r"INFO: 抓第 \d 只", line):
            cur["closed"] = True
        m = re.search(r"第 \d 只「(.+?)」", line)
        if m:
            caught.append(m.group(1))
    return route, caught[:3], fights


rows = defaultdict(list)
for seed, boss in SEEDS.items():
    scorer = upstream.Scorer(data, boss)
    logs = [p for p in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")) if f"读取到的 seed 是 {seed}" in open(p, encoding="utf-8").read()]
    parsed = [parse(p) for p in logs]
    # 这个 seed 的中文名 → name_id（从有路线那一行的日志里收集）
    names = {}
    for route, _, _ in parsed:
        if route:
            for name in route:
                names[zh(name)] = name
    for route, caught, fights in parsed:
        if not route:
            if len(caught) < 3 or any(c not in names for c in caught):
                continue
            route = [names[c] for c in caught]
        if len(fights) != 4:
            continue
        key = " → ".join(zh(x) for x in route)
        starter = zh(fights[0]["team"][0])
        for index, fight in enumerate(fights):
            opp = boss if index == 3 else route[index]
            team = fight["team"]
            value = scorer.matchup(team[0], opp, team[1:])
            rows[(seed, starter, key, index)].append((value, fight["turns"], fight["faints"], "/".join(zh(x) for x in team)))

for (seed, starter, route, index), items in sorted(rows.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2], kv[0][3])):
    if index == 0:
        print(f"\n== {seed}：{starter} 首发；{route}（{len(items)} 局）")
    ms = [i[0] for i in items]
    teams = sorted({i[3] for i in items})
    label = "首领" if index == 3 else f"第 {index + 1} 关"
    print(
        f"  {label}：m 中位 {statistics.median(ms):.2f}（{min(ms):.2f}～{max(ms):.2f}），回合 平均 {statistics.mean(i[1] for i in items):.2f}，"
        f"倒下 平均 {statistics.mean(i[2] for i in items):.2f}（合计 {sum(i[2] for i in items)}）；队伍 {len(teams)} 种，例：{teams[0]}"
    )
