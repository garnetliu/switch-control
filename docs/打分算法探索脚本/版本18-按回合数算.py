"""每一场换算成「几回合打完」和「打完之前挨了多少打」，不再用没有上限的比值 m（docs/打分算法-首发和路线.md）。

每一场（队伍 = 自己 + 三个队友，对手 B）：
  打出 d = 自己最好那一招 + 三个队友按实测比例（和 scoring.move_score 一样，以 B 的普通血量为 1）
  受到 r = B 一回合平均打掉我方的血（和 scoring.move_score 一样，以挨打那只的血量为 1）
  回合 T = 向上取整(B 的战斗血量 ÷ d)，至少 1；B 的战斗血量：路上 3.8，首领 4.18（实测）
  挨打 L = T × r
  「最好那一招」按 L 最小选；普通、极巨各算一次，取 min(普通, (普通 + 极巨) ÷ 2)（和 m 的取法对应）
路线：回合合计 ΣT，挨打合计 ΣL（首领那场 × 2）。都是越小越好。
首发 × 路线 × 换不换 × 研究员换不换，组合方式和版本 13 一样（不算不抓）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本18-按回合数算.py
"""

import importlib.util
import math
import os
import sys
from dataclasses import replace

from swsh import scoring
from swsh.field import Field
from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "--no-skip"]
spec = importlib.util.spec_from_file_location("v13", os.path.join(HERE, "版本13-按实际上场算路线分.py"))
v13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v13)

STAGE_HP, BOSS_HP = 3.8, 4.18


def dealt_received(attacker, index, defender, teammates, field, p):
    """scoring.move_score 的分子和分母。"""
    teammates = [m for m in teammates if m is not attacker and m is not defender]
    dealt = scoring.damage(attacker, index, defender, field)
    dealt += sum(scoring.teammate_damage(m, defender, field) for m in teammates)
    attacker_move = attacker.moves[index]
    regular = replace(defender, dynamax=False)
    received_regular = 0.0
    for i, move in enumerate(regular.moves):
        count = len(regular.moves)
        if move.is_spread:
            if attacker_move.name_id != "wide-guard" or attacker.dynamax:
                received_regular += scoring.damage(regular, i, attacker, field, True) / count
                received_regular += 3 * scoring.average_damage([regular], teammates, field, True) / count
        else:
            received_regular += scoring._received(regular, i, attacker, teammates, field) / count
    dynamaxed = replace(defender, dynamax=True)
    count = min(4, len(dynamaxed.max_moves))
    received_max = sum(scoring._received(dynamaxed, i, attacker, teammates, field) / count for i in range(count))
    return dealt, received_regular * (1 - p) + received_max * p


cache = {}


def fight(data, team, opponent, boss):
    """一场的 (回合 T, 挨打 L)。"""
    key = (team, opponent, boss)
    if key in cache:
        return cache[key]
    a = data.pokemon_object(team[0])
    b = data.pokemon_object(opponent)
    if a.name_id == "ditto":
        a = scoring.transform_ditto(a, b)
    elif b.name_id == "ditto":
        b = scoring.transform_ditto(b, a)
    mates = [data.pokemon_object(name) for name in team[1:]]
    p = data.max_move_rate(opponent)
    hp = BOSS_HP if opponent == boss else STAGE_HP
    options = {}
    for dynamax in (False, True):
        version = replace(a, dynamax=dynamax)
        best = None
        for index in range(len(version.moves)):
            if version.pp[index] <= 0:
                continue
            dealt, received = dealt_received(version, index, b, mates, Field(), p)
            turns = max(1, math.ceil(hp / dealt)) if dealt > 0 else 99
            loss = turns * received
            if best is None or loss < best[1]:
                best = (turns, loss)
        options[dynamax] = best
    base, dyn = options[False], options[True]
    mixed = ((base[0] + dyn[0]) / 2, (base[1] + dyn[1]) / 2)
    result = mixed if mixed[1] < base[1] else base
    cache[key] = result
    return result


def plan(data, boss, lair):
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    scorer = upstream.Scorer(data, boss)
    candidates = lair.candidates()[:3]
    results = []
    for starter in range(3):
        for path in upstream.paths(lair.map_type()):
            walker = upstream.Walker(lair, data, boss, path, [candidates[starter], *lair.teammates(starter)])
            for catches, scientists, fighters, boss_team in v13.outcomes(walker):
                turns = loss = 0.0
                for team, opponent in zip(fighters, walker.opponents, strict=True):
                    t, l = fight(data, team, opponent, boss)
                    turns += t
                    loss += l
                t, l = fight(data, boss_team, boss, boss)
                turns += t
                loss += 2 * l
                results.append((loss, turns, zh(candidates[starter]), tuple(zh(o) for o in walker.opponents), catches, scientists))
    del scorer
    return results


PAIRS = {
    12873702124229926581: [("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), ("不换", "不换", "换"), "9.18 分钟，倒下 0"),
                           ("力壮鸡", ("托戈德玛尔", "双剑鞘", "魔墙人偶"), ("不换", "换", "不换"), "10.20 分钟，倒下 9")],
    3076008315599927110: [("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), ("不换", "不换", "不换"), "6 局全胜，倒下 0.67"),
                          ("流氓熊猫", ("心蝙蝠", "肯泰罗", "狃拉"), ("不换", "不换", "不换"), "9 局 8 胜，倒下 1.44")],
    16238065963362826354: [("梦梦蚀", ("灯罩夜菇", "锹农炮虫", "劈斩司令"), ("换", "换", "不换"), "1 局，11.9 分钟，倒下 0"),
                           ("梦梦蚀", ("灯罩夜菇", "阿勃梭鲁", "魔墙人偶"), ("换", "换", "不换"), "1 局，12.6 分钟，倒下 3")],
}

if __name__ == "__main__":
    for boss, seed, expected in v13.CHECKS + [("cresselia", 16238065963362826354, None)]:
        config = GameConfig()
        if boss in v13.TOP:
            config.lair_first_draw_top = v13.TOP[boss]
        data = GameData(config)
        cache.clear()
        results = plan(data, boss, Lair(data, seed))
        by_loss = sorted(results, key=lambda r: (r[0], r[1]))
        by_turns = sorted(results, key=lambda r: (r[1], r[0]))
        best = by_loss[0]
        line = f"\n{seed}（{boss}）挨打最少：{best[2]}；{' → '.join(best[3])}；{'、'.join(best[4])}（挨打 {best[0]:.2f}，回合 {best[1]:.1f}）"
        if expected:
            exp = (expected[0], expected[1], tuple("换" if t else "不换" for t in expected[2]))
            rank = next(k + 1 for k, r in enumerate(by_loss) if (r[2], r[3], r[4]) == exp)
            line += f"；实测最好的按挨打排第 {rank} / {len(results)}"
        print(line)
        for starter, path, swaps, note in PAIRS.get(seed, []):
            for k, r in enumerate(by_loss):
                if (r[2], r[3], r[4]) == (starter, path, swaps):
                    rt = next(j + 1 for j, x in enumerate(by_turns) if x is r)
                    print(f"    {starter}；{' → '.join(path)}；{'、'.join(swaps)}：挨打 {r[0]:.2f}（第 {k + 1}），回合 {r[1]:.1f}（第 {rt}）；实测 {note}")
                    break
