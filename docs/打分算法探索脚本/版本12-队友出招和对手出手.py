"""用全部日志统计：队友怎么选招式、路上的对手和首领用极巨招式的比例、首领「陷入困境」时的血量和之后怎么出手。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本12-队友出招和对手出手.py
战斗文字是 OCR 读的，名字按编辑距离对到最近的宝可梦和招式，对不上的不算。
"""

import ast
import collections
import glob
import re
import statistics as st
from dataclasses import replace

from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.scoring import Field, damage
from tools.text import levenshtein

d = GameData(GameConfig())
F = Field()
names = list(d.rental_damages())
ZH = {d.pokemon_object(n).name("zh-Hans"): n for n in [*names, *d.boss_pokemon()]}
BOSSES = set(d.boss_pokemon())
ME = "夜暮林夕"


def closest(text: str, options: list[str], limit: int) -> str | None:
    best = min(options, key=lambda option: levenshtein(text, option))
    return best if levenshtein(text, best) <= limit else None


def fights():
    """每一场：队伍、对手、按顺序的战斗文字和每回合数据。同一局只取一次。"""
    seen = set()
    for path in sorted(glob.glob("logs/swsh-lair/start/*.log")):
        text = open(path, encoding="utf-8", errors="replace").read()
        for part in re.split(r"(?=\d\d:\d\d:\d\d \| INFO: 读取到的 seed 是 \d+)", text)[1:]:
            key = part[:60]
            if key in seen:
                continue
            seen.add(key)
            current = None
            for line in part.splitlines():
                found = re.search(r"队伍: (\[.*?\])，自己的 PP", line)
                if found:
                    current = dict(team=[n for n, _ in ast.literal_eval(found[1])], opponent=None, lines=[])
                    yield current
                    continue
                if current is None:
                    continue
                found = re.search(r"INFO: 对手 (\S+?)（种类", line)
                if found and current["opponent"] is None:
                    current["opponent"] = found[1]
                found = re.search(r"战斗文字: (.+?)出现了", line)
                if found and current["opponent"] is None:
                    current["opponent"] = ZH.get(closest(found[1].strip(), list(ZH), 2) or "")
                current["lines"].append(line)


ALL = [f for f in list(fights()) if f["opponent"]]
print(f"场数 {len(ALL)}")

# ---- 队友出招
count = collections.Counter()
rank = collections.Counter()
rank_total = collections.Counter()
for fight in ALL:
    opponent = d.pokemon_object(fight["opponent"])
    mates = {d.pokemon_object(n).name("zh-Hans"): n for n in fight["team"][1:] if n in names}
    last = None
    for line in fight["lines"]:
        found = re.search(r"战斗文字: (.+?)的(.+?)使出了\S* / (.+?)！", line)
        if not found or ME in found[1]:
            continue
        use = (found[2].strip(), found[3].strip())
        if use == last:
            continue
        last = use
        who = closest(use[0], list(mates), 1)
        if who is None:
            continue
        pokemon = replace(d.pokemon_object(mates[who]), dynamax=False)
        move_names = [m.name("zh-Hans") for m in pokemon.moves]
        move = closest(use[1], move_names, 1)
        if move is None:
            count["没认出来"] += 1
            continue
        index = move_names.index(move)
        status = [m.base_power <= 0 for m in pokemon.moves]
        count[("变化招式数", sum(status), "变化" if status[index] else "进攻")] += 1
        if status[index]:
            continue
        values = [max(damage(pokemon, k, opponent, F), 0) for k in range(len(pokemon.moves))]
        attacks = sorted((k for k in range(len(pokemon.moves)) if not status[k]), key=lambda k: -values[k])
        position = next(r for r, k in enumerate(attacks) if values[k] <= values[index] + 1e-9)
        rank[(len(attacks), position)] += 1
        rank_total[len(attacks)] += 1
print("== 队友出招（只算队友，自己的不算）")
for n in range(4):
    attack, status = count[("变化招式数", n, "进攻")], count[("变化招式数", n, "变化")]
    if attack + status:
        print(f"  带 {n} 个变化招式：出招 {attack + status} 次，用变化招式 {status / (attack + status):.1%}（每招机会一样的话 {n / 4:.0%}）")
print("  出进攻招式时，按对这个对手的伤害排第几（伤害一样的算靠前的）：")
for n in sorted(rank_total):
    shares = "、".join(f"第 {r + 1} {rank[(n, r)] / rank_total[n]:.1%}" for r in range(n))
    print(f"    {n} 个进攻招式，{rank_total[n]} 次：{shares}")

# ---- 对手用极巨招式的比例，首领分陷入困境之前和之后
uses = collections.defaultdict(lambda: [0, 0])
boss_uses = collections.defaultdict(lambda: {"之前": [0, 0], "之后": [0, 0]})
thresholds = []
per_turn = collections.defaultdict(lambda: {"之前": [], "之后": []})
fifth = collections.defaultdict(collections.Counter)
for fight in ALL:
    opponent = fight["opponent"]
    zh = d.pokemon_object(opponent).name("zh-Hans")
    known = {m.name("zh-Hans") for m in d.pokemon_object(opponent).moves}
    boss = opponent in BOSSES
    trouble = False
    hp_before = None
    acts = 0
    last = None
    for line in fight["lines"]:
        found = re.search(r"回合数据 对手 \S+（种类 \d+）：血量 (\d+)/(\d+)", line)
        if found:
            if boss and hp_before is not None:
                per_turn[opponent]["之后" if trouble else "之前"].append(acts)
            acts = 0
            hp_before = int(found[1]) / int(found[2])
            if trouble and thresholds and thresholds[-1][2] is None:
                thresholds[-1][2] = hp_before
            continue
        if "陷入困境" in line and not trouble:
            trouble = True
            thresholds.append([opponent, hp_before, None])
            continue
        found = re.search(r"战斗文字: (.+?)使出了\S* / (.+?)！", line)
        if not found or "的" in found[1] or closest(found[1].strip(), [zh], 2) is None:
            continue
        move = found[2].strip()
        if (found[1], move) == last:
            continue
        last = (found[1], move)
        acts += 1
        is_max = move.startswith("极巨") or move.startswith("超极巨")
        if boss:
            boss_uses[opponent]["之后" if trouble else "之前"][0] += is_max
            boss_uses[opponent]["之后" if trouble else "之前"][1] += 1
            if trouble and not is_max and closest(move, list(known), 1) is None:
                fifth[opponent][move] += 1
        else:
            uses[opponent][0] += is_max
            uses[opponent][1] += 1
total = [sum(v[0] for v in uses.values()), sum(v[1] for v in uses.values())]
print(f"== 路上的对手用极巨招式：合计 {total[0]}/{total[1]} = {total[0] / total[1]:.1%}，{len(uses)} 种对手")
for opponent, (m, n) in sorted(uses.items(), key=lambda x: -x[1][1])[:25]:
    print(f"  {d.pokemon_object(opponent).name('zh-Hans')}：{m}/{n} = {m / n:.0%}")
print("== 首领用极巨招式（陷入困境之前 / 之后）")
for opponent, v in boss_uses.items():
    a, b = v["之前"], v["之后"]
    print(f"  {d.pokemon_object(opponent).name('zh-Hans')}：之前 {a[0]}/{a[1]}" + (f" = {a[0] / a[1]:.0%}" if a[1] else "")
          + f"，之后 {b[0]}/{b[1]}" + (f" = {b[0] / b[1]:.0%}" if b[1] else ""))
print("== 首领陷入困境：出现这句话之前那个回合开始时的血量 → 之后那个回合开始时的血量")
for opponent in {t[0] for t in thresholds}:
    rows = [t for t in thresholds if t[0] == opponent and t[1] is not None]
    if rows:
        before = [t[1] for t in rows]
        after = [t[2] for t in rows if t[2] is not None]
        print(f"  {d.pokemon_object(opponent).name('zh-Hans')} {len(rows)} 场：之前最低 {min(before):.0%}，"
              + (f"之后最高 {max(after):.0%}，之后的中位 {st.median(after):.0%}" if after else "之后没有读数"))
print("== 首领每回合出手几次（按每回合数据之间数）")
for opponent, v in per_turn.items():
    for when in ("之前", "之后"):
        if v[when]:
            print(f"  {d.pokemon_object(opponent).name('zh-Hans')} {when}：{len(v[when])} 回合，次数分布 {dict(sorted(collections.Counter(v[when]).items()))}")
print("== 陷入困境之后用的、不在数据里 4 个招式之内的招式（第五个招式）")
for opponent, c in fifth.items():
    print(f"  {d.pokemon_object(opponent).name('zh-Hans')}：{dict(c.most_common(3))}")

# ---- 写 data/swsh/max_move_rate.json：战斗选招式时对手用极巨招式的比例（scoring.move_score）
# 出手不到 MIN 次的不单独记，用同类的合计：路上的对手按「路上」，首领按「首领」（陷入困境前后合在一起）
import json  # noqa: E402

MIN = 10
rates = {"路上": round(total[0] / total[1], 3)}
boss_total = [sum(v["之前"][0] + v["之后"][0] for v in boss_uses.values()), sum(v["之前"][1] + v["之后"][1] for v in boss_uses.values())]
rates["首领"] = round(boss_total[0] / boss_total[1], 3)
for opponent, (m, n) in uses.items():
    if n >= MIN:
        rates[opponent] = round(m / n, 3)
for opponent, v in boss_uses.items():
    m, n = v["之前"][0] + v["之后"][0], v["之前"][1] + v["之后"][1]
    if n >= MIN:
        rates[opponent] = round(m / n, 3)
with open("data/swsh/max_move_rate.json", "w", encoding="utf-8") as file:
    json.dump(rates, file, ensure_ascii=False, indent=4)
print(f"== 写了 data/swsh/max_move_rate.json：{len(rates) - 2} 种对手（出手 {MIN} 次以上），路上合计 {rates['路上']}，首领合计 {rates['首领']}")
