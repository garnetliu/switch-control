"""队友换不换、换给谁，从 seed 直接算，和日志对。

10 个对手抽完之后，随机数按路上的先后一组一组地用。每抓到一只是一组：
1. 先抽一个 0～2 的数（抽到 3 重抽），管什么还不知道；
2. 三个队友各一个随机数，偶数是想要，奇数是不想要；
3. 有人想要的话，反复抽 0～3（0 是自己，1、2、3 是三个队友），抽到想要的人为止，就给他。
自己换不换都照样占这些随机数。首领是双属性的（卡璞・哞哞），最前面还要多用掉 1 个。

用法：PYTHONPATH=src uv run python 这个脚本 [另外的日志文件...]。只用路上没遇到研究员、背包客、树果的局。
"""
import ast, collections, glob, inspect, itertools, re, sys, textwrap

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
def stream(lair, count=90):
    """10 个对手之后接着取的原始随机数，和每个随机数当 MT 种子洗出来的那只。"""
    picked = lair._picks(); rng = module.Xoroshiro(0); rng.s0, rng.s1 = lair._after; rows = lair._data.lair_rows(); mt19937 = module._mt19937
    used = {(row[0], row[1]) for row in picked}; raw = []; names = []
    for _ in range(count):
        value = rng.next_u32(); raw.append(value)
        random = mt19937(value); order = list(range(len(rows)))
        for index in range(len(order)):
            while True:
                offset = next(random) & 0x1FF
                if offset <= len(order) - index - 1: break
            order[index], order[index + offset] = order[index + offset], order[index]
        row = next(rows[i] for i in order if not rows[i][2] and (rows[i][0], rows[i][1]) not in used)
        names.append(lair._data.name_id(row[0], row[1]))
    return raw, names
zh = {}
runs = {}
for f in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        parts = p.split("队伍: [")
        teams = [[n for n, _ in ast.literal_eval("[" + x.split("]，自己的 PP")[0] + "]")] for x in parts[1:]]
        route = re.search(r"\n路线：(.*)\n", p)
        if not route or len(teams) < 2: continue
        d = D[boss]
        if boss not in zh: zh[boss] = {d.pokemon_object(n).name("zh-Hans"): n for n in d.rental_damages()}
        opp = [zh[boss].get(x.strip()) for x in route[1].split("→")]
        outcomes = []; clean = True
        for i in range(1, len(teams)):
            seg = parts[i]
            if i - 1 >= len(opp) or opp[i - 1] is None: break
            if any(w in seg for w in ("研究员：", "背包客的道具", "树果的对话")) or (i == 1 and any(w in parts[0] for w in ("研究员：", "背包客的道具", "树果的对话"))): clean = False
            if not clean: break
            if teams[i][0] != teams[i - 1][0]: outcomes.append("自己"); continue
            who = [k for k in range(3) if teams[i - 1][1 + k] != teams[i][1 + k] and teams[i][1 + k] == opp[i - 1]]
            outcomes.append(who[0] if who else None)
        if outcomes: runs.setdefault((boss, seed, tuple(o == "自己" for o in outcomes)), outcomes)
print("干净的局（到出现事件之前）:", len(runs), "；抓到的只数:", sum(len(v) for v in runs.values()))
def draw(raw, pos, top):
    mask = (1 << top.bit_length()) - 1
    while True:
        value = raw[pos] & mask; pos += 1
        if value <= top: return value, pos
def block(raw, pos, lead, tie_single, own_takes, skip_when_own):
    """一只抓到的这一组。返回 (队友里谁想要并且抽到, 下一个位置)。"""
    if own_takes and skip_when_own: return "自己", pos
    if lead: _, pos = draw(raw, pos, 2)
    want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
    if not want: return None, pos
    if len(want) == 1 and not tie_single: return want[0], pos
    for _ in range(60):
        w = raw[pos] & 3; pos += 1
        if w >= 1 and (w - 1) in want: return w - 1, pos
    return None, pos
streams = {}
for lead_rule in ("每组开头都有", "只有第 1 组有", "都没有"):
    for tie_single in (True, False):
        for skip in (False, True):
            stat = collections.defaultdict(lambda: [0, 0])
            for (boss, seed, flags), outcomes in runs.items():
                if (boss, seed) not in streams: streams[(boss, seed)] = stream(Longer(D[boss], seed), 70)[0]
                raw = streams[(boss, seed)]; pos = 0
                for index, outcome in enumerate(outcomes):
                    lead = lead_rule == "每组开头都有" or (lead_rule == "只有第 1 组有" and index == 0)
                    got, pos = block(raw, pos, lead, tie_single, outcome == "自己", skip)
                    if outcome != "自己":
                        stat[(boss[:3], index + 1)][0] += 1; stat[(boss[:3], index + 1)][1] += got == outcome
            line = "，".join(f"{k[0]} 第{k[1]}只 {v[1]}/{v[0]}" for k, v in sorted(stat.items()))
            print(f"开头的 0～2: {lead_rule}；只有一个想要时{'也' if tie_single else '不'}抽；自己换了的那只{'不占' if skip else '照样占'}随机数 → {line}")

print("\n=== 抓超梦之后（tap）：开头那个抽数的上限换一换、前面多垫几个，看哪种对得上 ===")
def block2(raw, pos, lead_top, pad):
    pos += pad
    if lead_top is not None: _, pos = draw(raw, pos, lead_top)
    want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
    if not want: return None, pos
    for _ in range(60):
        w = raw[pos] & 3; pos += 1
        if w >= 1 and (w - 1) in want: return w - 1, pos
    return None, pos
for era in ("tap", "mew"):
    res = []
    for lead_top in [None] + list(range(0, 40)):
        for pad_first in (0, 1, 2):
            for pad_each in (0, 1):
                ok = n = 0; per = collections.defaultdict(lambda: [0, 0])
                for (boss, seed, flags), outcomes in runs.items():
                    if boss[:3] != era: continue
                    raw = streams[(boss, seed)]; pos = pad_first
                    for index, outcome in enumerate(outcomes):
                        got, pos = block2(raw, pos, lead_top, pad_each)
                        if outcome != "自己": n += 1; ok += got == outcome; per[index + 1][0] += 1; per[index + 1][1] += got == outcome
                res.append((ok, n, lead_top, pad_first, pad_each, dict(per)))
    print(f"  {era}:")
    for ok, n, lead_top, pad_first, pad_each, per in sorted(res, key=lambda r: -r[0])[:6]:
        print(f"     {ok}/{n}  开头抽数上限 {lead_top}，最前面多垫 {pad_first} 个，每组前多垫 {pad_each} 个，各只: { {k: f'{v[1]}/{v[0]}' for k, v in sorted(per.items())} }")
