"""把 runs/logs/swsh-lair/start/*.log 每一局拆成每一场，算出这一场的 m、d、r、T、L 和实际回合、倒下，存成一张表。

一个日志文件是一局。一场：从「队伍: [...]」开始，到「抓第 N 只」（赢）或「还剩 0 条命」（输）结束；
被重启截断、没打完的场丢掉。
- 首领：最后一条「选择传说Boss选中了…「X」」，「不指定」的局跳过。
- 对手：这一场的「对手 X（种类 N）」或「回合数据 对手 X」> 「路线: a → b → c」>
  结尾「第 n 只「X」」的中文名（重名的用这个 seed 的 Lair.encounters() 消歧，first_draw_top 试 10～30）。
- 实际回合：这一场「用第 N 个招式」的次数；倒下：「有一只倒下了」的次数。
- 新日志有「回合数据」（每回合开头四只和对手的血量），额外算：
  实测打出 = 中间几回合对手掉的血 ÷ 战斗最大血 × 战斗血量倍数（路上 3.8、首领 4.18），换回普通血量单位；
  实测受到 = 中间几回合四只各自掉的血比例之和（回血不算）。
- m = upstream.Scorer.matchup（带那一场的三个队友）。d、r 是 m 取的那一招（普通、极巨各自最好的一招）的打出和受到，
  m 取了 (普通 + 极巨) ÷ 2 时 d、r 也取两者平均。T = ceil(战斗血量 ÷ d)，L = T × r（和版本 18 一样）。

结果写到 scratchpad 的 fights.json（路径见 OUT），后面的分析脚本读它。
用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本20-逐场取数.py
"""

import ast
import glob
import json
import math
import os
import re
import sys
from dataclasses import replace

from swsh import scoring
from swsh.field import Field
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

OUT = os.environ.get("FIGHTS_JSON", "/private/tmp/claude-503/-Users-garnet-projects-control-switch/6882f779-6294-4dce-875c-e2716eed87ee/scratchpad/fights.json")
# 只用到这个日志为止（含），日志还在增加，固定下来才能复现
LAST_LOG = os.environ.get("LAST_LOG", "20261121-211244.log")
STAGE_HP, BOSS_HP = 3.8, 4.18
RESTRICTED = {"mewtwo", "lugia", "ho-oh", "kyogre", "groudon", "rayquaza", "dialga", "palkia", "giratina-altered",
              "reshiram", "zekrom", "kyurem", "xerneas", "yveltal", "zygarde-50", "solgaleo", "lunala", "necrozma"}

data = GameData(GameConfig())
rentals = data.rental_pokemon_objects()
bosses = data.boss_pokemon_objects()
ZH = {}
for name_id, obj in list(rentals.items()) + list(bosses.items()):
    ZH.setdefault(obj.name("zh-Hans").replace("・", "·"), set()).add(name_id)


def norm(text):
    return text.replace("・", "·").strip()


def parse(path):
    run = {"file": os.path.basename(path), "seed": None, "boss_zh": None, "route": None, "caught": [], "fights": []}
    cur = None
    for line in open(path, encoding="utf-8"):
        if (m := re.search(r"读取到的 seed 是 (\d+)", line)):
            run["seed"] = int(m.group(1))
        elif (m := re.search(r"选择传说Boss选中了.*「(.+?)」", line)):
            run["boss_zh"] = norm(m.group(1))
        elif (m := re.search(r"INFO: 路线: (.+)$", line)):
            run["route"] = [x.strip() for x in m.group(1).split("→")]
        elif (m := re.search(r"INFO: 队伍: (\[.*?\])，", line)):
            team = ast.literal_eval(m.group(1))
            cur = {"team": [n for n, _ in team], "hp": [h for _, h in team], "turns": 0, "faints": 0, "opp": None,
                   "result": None, "snap": [], "gap": 0, "after_faint": False}
            run["fights"].append(cur)
        elif cur is None or cur["result"]:
            if (m := re.search(r"第 (\d) 只「(.+?)」", line)):
                run["caught"].append(norm(m.group(2)))
            continue
        elif (m := re.search(r"INFO: 对手 ([a-z0-9-]+)（种类", line)):
            cur["opp"] = m.group(1)
        elif (m := re.search(r"回合数据 (对手|自己|队友\d) ([a-z0-9-]+)（种类 \d+）：血量 (\d+)/(\d+)", line)):
            label, name, hp, top = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            if label == "对手":
                cur["opp"] = cur["opp"] or name
                cur["snap"].append({"opp": hp / top if top else 0})
            elif cur["snap"]:
                cur["snap"][-1][label] = hp / top if top else 0
        elif re.search(r"用第 \d 个招式", line):
            cur["turns"] += 1
            cur["after_faint"] = False
        elif "有一只倒下了" in line:
            # 两次倒下之间没有选招：中间至少有一回合自己没选招（多半是自己倒下了），回合数少算
            if cur["after_faint"]:
                cur["gap"] += 1
            cur["after_faint"] = True
            cur["faints"] += 1
            if (m := re.search(r"还剩 (\d+) 条命", line)) and m.group(1) == "0":
                cur["result"] = "输"
        elif re.search(r"INFO: 抓第 \d 只", line):
            cur["result"] = "赢"
    return run


def encounter_names(seed, caught_zh):
    """用 seed 推这张图的 10 个对手，取能对上已知中文名最多的 first_draw_top，返回 中文名 → name_id。"""
    best = None
    for top in range(10, 31):
        config = GameConfig()
        config.lair_first_draw_top = top
        try:
            lair = Lair(GameData(config), seed)
            names = [n for layer in lair.encounters().values() for n in layer]
        except Exception:
            continue
        table = {norm(rentals[n].name("zh-Hans")): n for n in names if n in rentals}
        hit = sum(1 for c in caught_zh if c in table)
        if best is None or hit > best[0]:
            best = (hit, table)
    return best[1] if best and best[0] == len(caught_zh) else {}


def opponents(run, boss):
    """每一场的对手 name_id（取不到的是 None）。"""
    result = []
    lair_table = None
    for index, fight in enumerate(run["fights"]):
        if index == 3:
            result.append(boss)
            continue
        if fight["opp"]:
            result.append(fight["opp"])
            continue
        if run["route"] and index < len(run["route"]):
            result.append(run["route"][index])
            continue
        if index < len(run["caught"]):
            zh = run["caught"][index]
            ids = ZH.get(zh, set()) - set(bosses)
            if len(ids) == 1:
                result.append(next(iter(ids)))
                continue
            if lair_table is None:
                lair_table = encounter_names(run["seed"], run["caught"][:3]) if run["seed"] else {}
            result.append(lair_table.get(zh))
            continue
        result.append(None)
    return result


def dealt_received(attacker, index, defender, mates, p):
    """scoring.move_score 的分子和分母（和版本 18 一样）。"""
    field = Field()
    mates = [x for x in mates if x is not attacker and x is not defender]
    dealt = scoring.damage(attacker, index, defender, field)
    dealt += sum(scoring.teammate_damage(x, defender, field) for x in mates)
    attacker_move = attacker.moves[index]
    regular = replace(defender, dynamax=False)
    rec = 0.0
    count = len(regular.moves)
    for i, move in enumerate(regular.moves):
        if move.is_spread:
            if attacker_move.name_id != "wide-guard" or attacker.dynamax:
                rec += scoring.damage(regular, i, attacker, field, True) / count
                rec += 3 * scoring.average_damage([regular], mates, field, True) / count
        else:
            rec += scoring._received(regular, i, attacker, mates, field) / count
    dyn = replace(defender, dynamax=True)
    count = min(4, len(dyn.max_moves))
    rec_max = sum(scoring._received(dyn, i, attacker, mates, field) / count for i in range(count))
    return dealt, rec * (1 - p) + rec_max * p


def per_member_received(defender, attacker, mates, p):
    """r 拆到每一只：[自己, 队友1, 队友2, 队友3] 一回合平均掉的血比例（自己不极巨化）。"""
    field = Field()
    members = [attacker, *mates]
    out = []
    for target in members:
        total = 0.0
        regular = replace(defender, dynamax=False)
        count = len(regular.moves)
        for i, move in enumerate(regular.moves):
            dmg = scoring.damage(regular, i, target, field, move.is_spread)
            total += (1 - p) * (dmg if move.is_spread else dmg / 4) / count
        dyn = replace(defender, dynamax=True)
        count = min(4, len(dyn.max_moves))
        for i in range(count):
            total += p * scoring.damage(dyn, i, target, field) / 4 / count
        out.append(total)
    return out


cache = {}


def features(team, opp, boss):
    key = (tuple(team), opp, opp == boss)
    if key in cache:
        return cache[key]
    a = data.pokemon_object(team[0])
    b = data.pokemon_object(opp)
    if a.name_id == "ditto":
        a = scoring.transform_ditto(a, b)
    elif b.name_id == "ditto":
        b = scoring.transform_ditto(b, a)
    mates = [data.pokemon_object(n) for n in team[1:]]
    p = data.max_move_rate(opp)
    parts = {}
    for dynamax in (False, True):
        version = replace(a, dynamax=dynamax)
        index, _, score = scoring.select_best_move(version, b, Field(), mates, p)
        d, r = dealt_received(version, index, b, mates, p)
        parts[dynamax] = (score, d, r)
    base, dyn = parts[False], parts[True]
    if (base[0] + dyn[0]) / 2 > base[0]:
        m, d, r = (base[0] + dyn[0]) / 2, (base[1] + dyn[1]) / 2, (base[2] + dyn[2]) / 2
    else:
        m, d, r = base
    hp = BOSS_HP if opp == boss else STAGE_HP
    T = max(1, math.ceil(hp / d)) if d > 0 else 99
    members = per_member_received(b, replace(a, dynamax=False), mates, p)
    result = {"m": m, "d": d, "r": r, "T": T, "L": T * r, "hp_ratio": hp / d if d > 0 else 99,
              "r_max": max(members), "r_members": members}
    cache[key] = result
    return result


def measured(fight, battle_hp):
    """回合数据里中间几回合的实测打出（普通血量单位）和受到（四只掉血比例之和），都是每回合平均。"""
    snaps = [s for s in fight["snap"] if all(k in s for k in ("opp", "自己", "队友1", "队友2", "队友3"))]
    if len(snaps) < 2:
        return None
    dealt, recv = [], []
    for a, b in zip(snaps, snaps[1:]):
        dealt.append(max(0.0, a["opp"] - b["opp"]) * battle_hp)
        recv.append(sum(max(0.0, a[k] - b[k]) for k in ("自己", "队友1", "队友2", "队友3")))
    return sum(dealt) / len(dealt), sum(recv) / len(recv), len(dealt)


def main():
    rows, skipped = [], {"没有选首领那一行或选了不指定": 0, "认不出对手": 0, "没打完": 0}
    files = [p for p in sorted(glob.glob("runs/logs/swsh-lair/start/*.log")) if os.path.basename(p) <= LAST_LOG]
    zh_boss = {norm(o.name("zh-Hans")): n for n, o in bosses.items()}
    for path in files:
        run = parse(path)
        if not run["fights"]:
            continue
        boss = zh_boss.get(run["boss_zh"])
        if boss is None:
            skipped["没有选首领那一行或选了不指定"] += len(run["fights"])
            continue
        opps = opponents(run, boss)
        before = 0
        for index, (fight, opp) in enumerate(zip(run["fights"], opps)):
            if index > 3:
                break
            if fight["result"] is None:
                skipped["没打完"] += 1
                continue
            if opp is None:
                skipped["认不出对手"] += 1
                before += fight["faints"]
                continue
            f = features(fight["team"], opp, boss)
            battle_hp = BOSS_HP if index == 3 else STAGE_HP
            meas = measured(fight, battle_hp)
            rows.append({
                "file": run["file"], "seed": str(run["seed"]), "boss": boss, "restricted": boss in RESTRICTED,
                "stage": index, "team": fight["team"], "hp": fight["hp"], "opp": opp,
                "turns": fight["turns"], "faints": fight["faints"], "result": fight["result"],
                "faints_before": before, "snaps": len(fight["snap"]), "gap": fight["gap"],
                "meas_d": meas[0] if meas else None, "meas_r": meas[1] if meas else None, "meas_n": meas[2] if meas else 0,
                **f,
            })
            before += fight["faints"]
            sys.stdout.flush()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rows, open(OUT, "w"), ensure_ascii=False)
    print(f"{len(files)} 个日志（{os.path.basename(files[0])} ～ {os.path.basename(files[-1])}），取到 {len(rows)} 场；跳过 {skipped}；写到 {OUT}")


if __name__ == "__main__":
    main()
