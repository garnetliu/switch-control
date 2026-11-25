"""路上的研究员、背包客、树果出现在哪一段，是不是由地图类型和路线决定的，和 seed 里那次 draw(9) 有没有关系。"""
import collections, glob, re, sys
import swsh.lair.lair as lair_module
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData

class Recorder(lair_module.Xoroshiro):
    def __init__(self, seed):
        super().__init__(seed); self.draws = []
    def draw(self, top):
        value = super().draw(top); self.draws.append((top, value)); return value
last = {}
class Hook(Recorder):
    def __init__(self, seed):
        super().__init__(seed); last["rng"] = self
lair_module.Xoroshiro = Hook
D = {}
for boss, top in (("mewtwo", 24), ("tapu-bulu", 23)):
    c = GameConfig(); c.lair_first_draw_top = top; D[boss] = GameData(c)
rows = []
files = sorted(glob.glob("runs/logs/swsh-lair/start/*.log")) + sys.argv[1:]
for f in files:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        # 按段切：每个岔路口到下一场开打（队伍血量）之间出了什么
        segs = []; cur = None
        for line in p.splitlines():
            m = re.search(r"岔路口光标从第 \d 列移到第 (\d) 列", line)
            if m: cur = dict(col=int(m[1]), events=[]); segs.append(cur); continue
            if "队伍血量" in line: cur = None; continue
            if cur is None: continue
            if "研究员" in line and "研究员" not in cur["events"]: cur["events"].append("研究员")
            if "背包客" in line and "背包客" not in cur["events"]: cur["events"].append("背包客")
            if "树果" in line and "树果" not in cur["events"]: cur["events"].append("树果")
        if len(segs) < 3 or p.count("队伍血量") < 3: continue
        l = lair_module.Lair(D[boss], seed)
        try: kind = l.map_type()
        except Exception: continue
        nine = [v for top, v in last["rng"].draws if top == 9][0]
        rows.append((seed, kind, nine, tuple(s["col"] for s in segs[:3]), tuple(tuple(s["events"]) for s in segs[:3]), len(segs) > 3))
print(len(rows), "局，", len({r[0] for r in rows}), "个 seed")
# 1. 同一个 seed、同一条路线，每局的事件一样吗
g = collections.defaultdict(set)
for r in rows: g[(r[0], r[3])].add(r[4])
multi = {k: v for k, v in g.items() if sum(1 for r in rows if (r[0], r[3]) == k) > 1}
print("同一个 seed 同一条路线打了多局的有", len(multi), "组，其中事件每局都一样的", sum(len(v) == 1 for v in multi.values()), "组")
# 2. 同一种地图、同一条路线，不同 seed 的事件一样吗
g = collections.defaultdict(lambda: collections.defaultdict(set))
for r in rows: g[(r[1], r[3])][r[4]].add(r[0])
print("\n地图类型 + 路线（三层走的列）→ 出现过的事件组合（seed 个数）")
for k in sorted(g):
    print("  ", k, {" | ".join("+".join(e) or "无" for e in ev): len(s) for ev, s in g[k].items()})
# 3. 加上 draw(9) 的值之后是不是就唯一了
g = collections.defaultdict(lambda: collections.defaultdict(set))
for r in rows: g[(r[1], r[2], r[3])][r[4]].add(r[0])
many = {k: v for k, v in g.items() if sum(len(s) for s in v.values()) > 1}
print(f"\n地图类型 + draw(9) + 路线 相同、有 2 个以上 seed 的 {len(many)} 组，事件全一样的 {sum(len(v) == 1 for v in many.values())} 组")
for k in sorted(many): print("  ", k, {" | ".join("+".join(e) or "无" for e in ev): len(s) for ev, s in many[k].items()})
# 4. draw(9) 的值和「这条路线上有没有事件」的关系
g = collections.defaultdict(collections.Counter)
for r in {(r[0], r[1], r[2], r[3], r[4]) for r in rows}:
    for i, ev in enumerate(r[4]):
        for e in ev or ("无",): g[(r[1], r[2])][e] += 1
print("\n地图类型, draw(9) → 各种事件出现的次数（按段数）")
for k in sorted(g): print("  ", k, dict(g[k]))
