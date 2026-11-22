"""从日志里把每一局路上遇到的研究员、背包客、树果整理成 data/swsh/lair_event_LUT.json 的初始内容。

用法：PYTHONPATH=src uv run python 这个脚本 [另外的日志文件...]。位置的写法见 GameData.lair_events。
同一个位置前后记的不一样会打印出来，不写进表。
"""
import collections, glob, json, re, sys
from pathlib import Path
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

D = {}
for boss, top in (("mewtwo", 24), ("tapu-bulu", 23)):
    c = GameConfig(); c.lair_first_draw_top = top; D[boss] = GameData(c)
seen = collections.defaultdict(collections.Counter)   # (类型, 布局, 位置) -> {事件组合: 次数}
rounds = 0
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        route = re.search(r"\n路线：(.*)\n", p)
        if not route: continue
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        d = D[boss]; lair = Lair(d, seed); enc = lair.encounters(); cols = []
        for i, z in enumerate(x.strip() for x in route[1].split("→")):
            hit = [k for k, n in enumerate(enc[str(i + 1)]) if d.pokemon_object(n).name("zh-Hans") == z]
            if len(hit) == 1: cols.append(hit[0])
        if len(cols) != 3: continue
        nodes = [(0, 0), *((i + 1, col) for i, col in enumerate(cols)), (4, 0)]
        # 每场战斗开打（队伍血量）之前是一段路
        parts = re.split(r"队伍血量", p)[:-1]
        if not parts: continue
        rounds += 1
        for index, part in enumerate(parts[:4]):
            if index > 0: part = part.split("\n", 1)[-1]
            before, after, forked = [], [], False
            for line in part.splitlines():
                if "岔路口光标" in line: forked = True; continue
                event = "scientist" if "研究员：" in line else "backpacker" if "背包客的道具" in line else "berry" if "树果" in line else None
                target = after if forked else before
                if event and event not in target: target.append(event)
            (row, col), (next_row, next_col) = nodes[index], nodes[index + 1]
            key = (lair.map_type(), lair.layout())
            seen[(*key, f"{row}-{col}")][tuple(before)] += 1
            if forked: seen[(*key, f"{row}-{col}>{next_row}-{next_col}")][tuple(after)] += 1
table = {}; conflicts = 0
for (kind, layout, position), counter in sorted(seen.items()):
    if len(counter) > 1:
        conflicts += 1; print("不一致，不写:", kind, layout, position, dict(counter)); continue
    table.setdefault(kind, {}).setdefault(str(layout), {})[position] = list(next(iter(counter)))
path = Path("data/swsh/lair_event_LUT.json")
path.write_text(json.dumps(table, indent=4, ensure_ascii=False, sort_keys=True), encoding="utf-8")
total = sum(len(v) for layouts in table.values() for v in layouts.values())
events = collections.Counter(e for layouts in table.values() for v in layouts.values() for ev in v.values() for e in ev)
print(f"{rounds} 局，写了 {total} 个位置（{sum(len(v) for v in table.values())} 种布局），不一致 {conflicts} 个；事件 {dict(events)}")
print({kind: sorted(int(k) for k in layouts) for kind, layouts in table.items()})
