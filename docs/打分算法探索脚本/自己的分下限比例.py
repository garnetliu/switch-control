"""探索 80% 限制的比例：在日志里出现过的每张图上，不同比例会选出什么方案。"""
import glob, re, statistics as st
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import Planner, paths
TOP = {"mewtwo": 24, "tapu-bulu": 23}; E = {}
for b, t in TOP.items():
    c = GameConfig(); c.lair_first_draw_top = t; d = GameData(c); E[b] = (d, Planner(d, c, b))
seeds = {}
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    m = re.search(r"读取到的 seed 是 (\d+)", t)
    if m and "首发" in t: seeds[int(m[1])] = "tapu-bulu" if "卡璞・哞哞" in t else "mewtwo"
seeds[9004205710319247536] = "tapu-bulu"
maps = {}
for s, b in seeds.items():
    d, P = E[b]; l = Lair(d, s); n = l.candidates()[:3]; rows = []
    for i in range(3):
        for path in paths(l.map_type()):
            opp = tuple(l.encounters()[str(r)][col] for r, col in path)
            t, o, m, x = P.score(n[i], l.teammates(i), opp); rows.append((t, o, n[i], "→".join(opp), "".join("换" if k else "留" for k in x)))
    maps[s] = rows
def pick(rows, fl):
    top = max(r[1] for r in rows); return max((r for r in rows if r[1] >= fl * top), key=lambda r: r[0])
FL = (0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0)
print("图数", len(maps))
print("比例 | 和0.8选的不同的图数 | 选中方案: 自己的分平均, 总分平均, 自己的分占这张图最高值的比例(平均/最低)")
base = {s: pick(r, 0.8) for s, r in maps.items()}
for fl in FL:
    p = {s: pick(r, fl) for s, r in maps.items()}
    ratio = [p[s][1] / max(x[1] for x in maps[s]) for s in maps]
    print(f"{fl:4.2f} | {sum(p[s][2:] != base[s][2:] for s in maps):3d} | {st.mean(v[1] for v in p.values()):.3f} {st.mean(v[0] for v in p.values()):.3f} {st.mean(ratio):.2f}/{min(ratio):.2f}")
# 不加限制时，总分最高的方案自己的分占最高值的比例分布：看多少张图会受限制影响
r0 = sorted(pick(r, 0)[1] / max(x[1] for x in r) for r in maps.values())
print("不加限制时选中方案 自己的分/这张图最高值 的分布: <0.5:", sum(x < 0.5 for x in r0), " 0.5~0.7:", sum(0.5 <= x < 0.7 for x in r0), " 0.7~0.8:", sum(0.7 <= x < 0.8 for x in r0), " 0.8~0.9:", sum(0.8 <= x < 0.9 for x in r0), " >=0.9:", sum(x >= 0.9 for x in r0))
for s, name in [(3076008315599927110, "超梦基准"), (3477042723512954677, "超梦 大王铜象那张"), (9004205710319247536, "哞哞 搜出来第1名"), (15116150022334671996, "哞哞 日志最高分"), (6872535256541728132, "哞哞 怪颚龙那张")]:
    print("==", name, s, "自己最高", round(max(x[1] for x in maps[s]), 3))
    last = None
    for fl in FL:
        r = pick(maps[s], fl); cur = (r[2], r[3], r[4])
        if cur != last: print(f"   比例 {fl:4.2f} 起: {r[2]} {r[3]} {r[4]} {r[0]:.3f}={r[1]:.3f}+{r[0]-r[1]:.3f}")
        last = cur
