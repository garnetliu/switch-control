"""研究员换给队友的那只能不能从 seed 算出来。

做法：照 Lair._picks 抽完 6 只租借和 10 个对手之后，随机数接着往下取，每取一个都拿它当 MT 种子洗一次牌，
取第一张不是首领、也不在那 16 只里的，看第几个随机数洗出来的正好是研究员给的那只。
"""
import ast, collections, glob, inspect, re, sys, textwrap
import swsh.lair.lair as module
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData

class Longer(module.Lair):
    def later(self, count):
        """接着往下取 count 个随机数，各自洗出来的那只的 name_id。"""
        picked = self._picks(); rng = module.Xoroshiro(0); rng.s0, rng.s1 = self._after; rows = self._data.lair_rows(); mt19937 = module._mt19937
        used = {(row[0], row[1]) for row in picked}
        out = []
        for _ in range(count):
            random = mt19937(rng.next_u32()); order = list(range(len(rows)))
            for index in range(len(order)):
                while True:
                    offset = next(random) & 0x1FF
                    if offset <= len(order) - index - 1: break
                order[index], order[index + offset] = order[index + offset], order[index]
            row = next(rows[i] for i in order if not rows[i][2] and (rows[i][0], rows[i][1]) not in used)
            out.append(self._data.name_id(row[0], row[1]))
        return out
D = {}
for boss, top in (("mewtwo", 24), ("tapu-bulu", 23)):
    c = GameConfig(); c.lair_first_draw_top = top; D[boss] = GameData(c)
found = collections.Counter(); events = {}
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        parts = p.split("队伍: [")
        teams = [[n for n, _ in ast.literal_eval("[" + x.split("]，自己的 PP")[0] + "]")] for x in parts[1:]]
        order = 0
        for i in range(1, len(teams)):
            if "研究员：" not in parts[i]: continue
            order += 1
            m = re.search(r"换成 (\S+) 的总分", parts[i]); just = m[1] if m else None
            new = [b for a, b in zip(teams[i - 1][1:], teams[i][1:]) if a != b and b != just]
            if len(new) == 1: events[(boss, seed, order, i)] = new[0]   # i：第几场战斗之前遇到的
print("不同的（seed, 第几个研究员）:", len(events))
rows = []
for (boss, seed, order, stage), name in sorted(events.items()):
    lair = Longer(D[boss], seed); later = lair.later(60)
    where = [k + 1 for k, n in enumerate(later) if n == name]
    two = sum(1 for row in lair._picks()[6:] if row[4] != row[5])
    rows.append((seed, order, stage, name, where[0] if where else None, lair.map_type(), lair.layout(), two))
    found[where[0] if where else None] += 1
print("研究员给的那只是 10 个对手之后第几个随机数洗出来的:", sorted(found.items(), key=lambda kv: (kv[0] is None, kv[0])))
print("60 个里碰巧对上的概率大约", f"{60/226:.0%}", "；前 20 个里对上的有", sum(v for k, v in found.items() if k and k <= 20), "/", len(events))
for r in rows: print("  ", r)
