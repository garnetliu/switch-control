"""从「战斗文字」日志里统计队友每回合出的招式：是不是伤害最高的、多少是变化招式、同一张图每局出的一不一样。

用法：PYTHONPATH=src uv run python 这个脚本 日志文件...（程序输出的日志，里面要有「战斗文字:」）
"""
import ast
import collections
import re
import sys
from dataclasses import replace

from control_switch.vision.text import levenshtein
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.scoring import Field, damage

d = GameData(GameConfig()); F = Field()
names = list(d.rental_damages())
zh = {d.pokemon_object(n).name("zh-Hans"): n for n in names}
bosses = {b.name(): k for k, b in d.boss_pokemon().items()}
ME = "夜暮林夕"
def closest(text, options, limit):
    best = min(options, key=lambda o: levenshtein(text, o))
    return best if levenshtein(text, best) <= limit else None
rounds = []
for path in sys.argv[1:]:
    t = open(path, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        fights = []; cur = None
        for line in p.splitlines():
            m = re.search(r"队伍: (\[.*?\])，自己的 PP", line)
            if m:
                cur = dict(team=[n for n, _ in ast.literal_eval(m[1])], opp=None, uses=[]); fights.append(cur); continue
            if cur is None: continue
            m = re.search(r"战斗文字: (.+?)出现了", line)
            if m and cur["opp"] is None:
                who = closest(m[1].strip(), list(zh) + list(bosses), 2)
                cur["opp"] = zh.get(who) or bosses.get(who)
            m = re.search(r"战斗文字: (.+?)的(.+?)使出了\S* / (.+?)！", line)
            if m and ME not in m[1]:
                cur["uses"].append((m[2].strip(), m[3].strip()))
        if fights: rounds.append((seed, fights))
print("局数", len(rounds), "；场数", sum(len(f) for _, f in rounds), "；队友出招记录", sum(len(x["uses"]) for _, f in rounds for x in f))
stat = collections.Counter(); per_mon = collections.defaultdict(collections.Counter); first = collections.defaultdict(collections.Counter)
for seed, fights in rounds:
    for index, fight in enumerate(fights):
        if fight["opp"] is None: continue
        try: O = d.pokemon_object(fight["opp"])
        except Exception: continue
        mates = {d.pokemon_object(n).name("zh-Hans"): n for n in fight["team"][1:]}
        seen_first = set()
        for mon_zh, move_zh in fight["uses"]:
            key = closest(mon_zh, list(mates), 1)
            if key is None: continue
            P = replace(d.pokemon_object(mates[key]), dynamax=False)
            move_names = [m.name("zh-Hans") for m in P.moves]
            mv = closest(move_zh, move_names, 1)
            if mv is None: stat["招式没认出来"] += 1; continue
            i = move_names.index(mv)
            dmg = [max(damage(P, k, O, F), 0) for k in range(len(P.moves))]
            best = max(dmg)
            kind = "变化招式" if P.moves[i].base_power <= 0 else "伤害最高的" if dmg[i] >= best - 1e-9 else "有伤害但不是最高的"
            stat[kind] += 1; per_mon[mates[key]][(mv, kind)] += 1
            if (key) not in seen_first:
                seen_first.add(key); first[(seed, index, mates[key])][mv] += 1
total = sum(v for k, v in stat.items() if k != "招式没认出来")
print("队友的出招：", {k: f"{v}（{v/total:.0%}）" for k, v in stat.items() if k != "招式没认出来"}, "；没认出来", stat["招式没认出来"])
# 带变化招式的队友，出变化招式的比例
has = collections.Counter(); use = collections.Counter()
for mon, c in per_mon.items():
    n_status = sum(m.base_power <= 0 for m in d.pokemon_object(mon).moves)
    tot = sum(c.values()); st = sum(v for (mv, kind), v in c.items() if kind == "变化招式")
    has[n_status] += tot; use[n_status] += st
print("按这只带几个变化招式分：", {k: f"出招 {has[k]} 次，其中变化招式 {use[k]} 次（{use[k]/has[k]:.0%}，随机选的话是 {k/4:.0%}）" for k in sorted(has)})
# 同一张图、同一场、同一只队友，每局第 1 回合出的招式一不一样
multi = {k: v for k, v in first.items() if sum(v.values()) >= 5}
same = sum(1 for v in multi.values() if len(v) == 1)
print(f"同一张图同一场同一只队友、打了 5 局以上的 {len(multi)} 组：第 1 回合每局出同一招的 {same} 组")
for k, v in sorted(multi.items(), key=lambda kv: (kv[0][0], kv[0][1]))[:12]: print("   ", k[0], f"第 {k[1] + 1} 场", d.pokemon_object(k[2]).name("zh-Hans"), dict(v))
print("出招最多的几只队友：")
for mon, c in sorted(per_mon.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
    print("   ", d.pokemon_object(mon).name("zh-Hans"), {f"{mv}（{kind}）": v for (mv, kind), v in c.most_common()})
