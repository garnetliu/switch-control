"""伤害表按实测血量（路上 3.8 倍、首领 4.18 倍、个体值 31）重新生成后，按版本 10 定门槛的办法用日志重新统计：
前三关按自己第 1 回合的伤害分档后实际打几个回合、首领战第 1 回合的进攻合计和回合数。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本12-按实测血量重定门槛.py
"""

import ast
import glob
import re
import statistics as st
from collections import Counter

import numpy as np

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.plan import rotate

c = GameConfig()
d = GameData(c)
D = d.rental_damages()
BOSS = d.boss_attack_defense()
ZH = {d.pokemon_object(n).name("zh-Hans"): n for n in [*D, *d.boss_pokemon()]}


def games():
    """日志里每一局：首领、输赢、每一场的队伍、对手、实际回合数、倒下次数。同一局只取一次。"""
    seen = set()
    for file in sorted(glob.glob("logs/swsh-lair/start/*.log")):
        text = open(file, encoding="utf-8", errors="replace").read()
        marks = list(re.finditer(r"(\d\d:\d\d:\d\d) \| INFO: 读取到的 seed 是 (\d+)", text))
        for index, mark in enumerate(marks):
            if (mark[1], mark[2]) in seen:
                continue
            seen.add((mark[1], mark[2]))
            end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
            part = text[mark.start() : end]
            report = re.search(r"战报：\n(胜|负)[^，]*，倒下 \d+ 次，[\d.]+ 分钟，抓到 (\d)/4\n路线：(.*)\n", part)
            teams = list(re.finditer(r"队伍: (\[.*?\])，自己的 PP", part))
            if not report or not teams:
                continue
            route = [ZH.get(x.strip()) for x in report[3].split("→")]
            picks = re.findall(r"(?:选中了第 \d 项「([^」]*)」|改成刷「([^」]*)」|首领是「([^」]*)」)", text[:end])
            boss = next((ZH.get(a or b or e) for a, b, e in reversed(picks) if ZH.get(a or b or e)), None)
            fights = []
            for number, team in enumerate(teams[:4]):
                until = teams[number + 1].start() if number + 1 < len(teams) else len(part)
                piece = part[team.end() : until]
                opponent = re.search(r"INFO: 对手 (\S+?)（种类", part[team.start() : until])
                fights.append(
                    dict(
                        team=[n for n, _ in ast.literal_eval(team[1])],
                        opponent=opponent[1] if opponent else (route[number] if number < 3 else boss),
                        turns=len(re.findall(r"INFO: 用第 \d 个招式", piece)),
                        faints=len(re.findall(r"有一只倒下了", piece)),
                    )
                )
            if len(fights) == 4 and fights[3]["opponent"]:
                boss = fights[3]["opponent"]
            yield dict(win=report[1] == "胜", caught=int(report[2]), boss=boss, fights=fights)


stages, bosses = [], []
for game in games():
    wait = 0
    for number, fight in enumerate(game["fights"]):
        own, opponent = fight["team"][0], fight["opponent"]
        if not fight["turns"] or not opponent:
            break
        if number < 3:
            if opponent not in D or any(n not in D for n in fight["team"]):
                break
            dynamax, _, _ = rotate(0, wait, c)
            stages.append(
                dict(
                    first=D[own][opponent][1 if dynamax else 0],
                    damages=D[own][opponent],
                    wait=wait,
                    team=sum(D[m][opponent][2] for m in fight["team"][1:]),
                    turns=fight["turns"],
                    won=number + 1 < len(game["fights"]) or game["caught"] > number,
                )
            )
        elif game["boss"] in d.boss_pokemon() and all(n in BOSS for n in fight["team"]):
            table = {n: v[game["boss"]] for n, v in BOSS.items()}
            left, w, values = 0, wait, []
            for _ in range(c.boss_turns):
                dynamax, left, w = rotate(left, w, c)
                values.append(table[own][1 if dynamax else 0])
            mates = sum(table[m][0] for m in fight["team"][1:])
            bosses.append(
                dict(
                    boss=game["boss"],
                    win=game["win"],
                    turns=fight["turns"],
                    faints=fight["faints"],
                    first=values[0] + mates,
                    average=sum(values) / len(values) + mates,
                )
            )
        # 按实际回合数推轮换
        left = 0
        for _ in range(fight["turns"]):
            _, left, wait = rotate(left, wait, c)

won = [s for s in stages if s["won"]]
print(f"== 前三关 {len(won)} 场（打赢的），按自己第 1 回合的伤害（新表）")
print("  伤害不低于 | 场数 | 1 回合打完的占比")
for low in np.arange(0.4, 1.61, 0.05):
    above = [s for s in won if s["first"] >= low]
    if above:
        one = sum(s["turns"] == 1 for s in above)
        print(f"  {low:.2f} | {len(above)} | {one}/{len(above)} = {one / len(above):.0%}")
print("  分段 | 场数 | 实际回合")
for low, high in ((0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0), (1.0, 1.1), (1.1, 9)):
    seg = [s for s in won if low <= s["first"] < high]
    if seg:
        count = Counter(s["turns"] for s in seg)
        print(f"  {low:.1f}～{high:.1f} | {len(seg)} | {dict(sorted(count.items()))}，1 回合占 {count[1] / len(seg):.0%}")

print(f"== 首领战 {len(bosses)} 场，赢的 {sum(b['win'] for b in bosses)} 场")
W = [b for b in bosses if b["win"]]
y = np.array([1 / b["turns"] for b in W])
A = np.array([b["average"] for b in W])
print(f"  1 ÷ 回合数 = {(A @ y) / (A @ A):.3f} × 合计（前 {c.boss_turns} 回合自己的平均 + 队友），相关 {np.corrcoef(A, y)[0, 1]:.2f}")
print("  第 1 回合合计不低于 | 局数 | 1 回合打死的占比")
for low in np.arange(0.4, 1.61, 0.05):
    above = [b for b in W if b["first"] >= low]
    if above:
        one = sum(b["turns"] == 1 for b in above)
        print(f"  {low:.2f} | {len(above)} | {one}/{len(above)} = {one / len(above):.0%}")
print(f"  旧门槛按比例换算的参考：首领 {st.median(b['first'] for b in W):.2f} 是第 1 回合合计的中位数")

# 同一张图反复打会让少数几种对局占大头（龙卷云那张图打了近 200 局）：同一种「自己、对手、开局伤害」只算一份，
# 1 回合打完的比例取这一种里的平均
groups = {}
for s in won:
    groups.setdefault((round(s["first"], 4), round(s["team"], 4)), []).append(s["turns"] == 1)
print(f"== 前三关去掉重复（{len(groups)} 种）")
for low in np.arange(0.4, 1.21, 0.05):
    above = [st.mean(v) for (first, _), v in groups.items() if first >= low]
    if above:
        print(f"  不低于 {low:.2f}：{len(above)} 种，1 回合打完的占比平均 {st.mean(above):.0%}")
for low, high in ((0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0), (1.0, 1.1), (1.1, 9)):
    seg = [st.mean(v) for (first, _), v in groups.items() if low <= first < high]
    if seg:
        print(f"  {low:.1f}～{high:.1f}：{len(seg)} 种，1 回合打完的占比平均 {st.mean(seg):.0%}")
bgroups = {}
for b in W:
    bgroups.setdefault(round(b["first"], 4), []).append(b["turns"] == 1)
print(f"== 首领战去掉重复（{len(bgroups)} 种）")
for low in np.arange(0.6, 1.31, 0.1):
    above = [st.mean(v) for first, v in bgroups.items() if first >= low]
    if above:
        print(f"  不低于 {low:.1f}：{len(above)} 种，1 回合打死的占比平均 {st.mean(above):.0%}")

# 门槛定成 stage_sure_damage = 1.0、stage_likely_damage = 0.6 之后，重新拟合每回合掉血的式子：
# 和版本 10 一样，看推出来的整数回合数和实际完全一样的比例
from dataclasses import replace as _replace  # noqa: E402

from control_switch.games.swsh.lair.plan import fight  # noqa: E402

base_config = GameConfig()
base_config.stage_sure_damage, base_config.stage_likely_damage = 1.0, 0.6
best = None
for own_rate in np.arange(0.5, 1.61, 0.1):
    for team_rate in np.arange(0.6, 2.01, 0.1):
        for base_rate in (0.0, 0.05, 0.1, 0.15, 0.2):
            trial = _replace(base_config) if hasattr(base_config, "__dataclass_fields__") else base_config
            trial.stage_own_rate, trial.stage_team_rate, trial.stage_base_rate = own_rate, team_rate, base_rate
            hit = sum(fight(s["damages"], s["wait"], trial, s["team"])[1] == s["turns"] for s in won)
            if best is None or hit > best[0]:
                best = (hit, own_rate, team_rate, base_rate)
print(f"== 每回合掉血 = {best[1]:.1f} × 自己 + {best[2]:.1f} × 队友合计 + {best[3]:.2f}：整数回合数完全对 {best[0]}/{len(won)} = {best[0] / len(won):.0%}")
trial = base_config
trial.stage_own_rate, trial.stage_team_rate, trial.stage_base_rate = best[1], best[2], best[3]
weak = []
for s in won:
    if s["first"] < trial.stage_likely_damage:
        hit = trial.stage_own_rate * s["first"] + trial.stage_team_rate * s["team"] + trial.stage_base_rate
        if hit >= 1:
            weak.append(s["turns"])
if weak:
    print(f"  不到 0.6、式子却说第 1 回合打完的 {len(weak)} 场，实际回合 {dict(sorted(Counter(weak).items()))}，平均 {st.mean(weak):.2f}")
old = GameConfig()
old_hit = None
