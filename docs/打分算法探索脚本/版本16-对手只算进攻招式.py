"""m 里受到的伤害只在对手的进攻招式里取平均：对手的变化招式（和它变成的极巨防壁）不算，
打自己、打队友都只在进攻招式里平均，当它每回合都在进攻（docs/打分算法-首发和路线.md）。其它和 scoring.move_score 一样。
路线分、组合方式和版本 13 一样（不算不抓）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本16-对手只算进攻招式.py
"""

import importlib.util
import os
import sys
from dataclasses import replace

from swsh import scoring
from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "--no-skip"]
spec = importlib.util.spec_from_file_location("v13", os.path.join(HERE, "版本13-按实际上场算路线分.py"))
v13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v13)
original = scoring.move_score
MODE = {"value": "原来"}


def move_score(attacker, move_index, defender, teammates, field, max_move_probability=scoring.MAX_MOVE_PROBABILITY):
    """和 scoring.move_score 一样，只是受到的伤害只在对手的进攻招式里取平均（变化招式、极巨防壁不算）。"""
    if MODE["value"] == "原来":
        return original(attacker, move_index, defender, teammates, field, max_move_probability)
    teammates = [m for m in teammates if m is not attacker and m is not defender]
    dealt = scoring.damage(attacker, move_index, defender, field)
    dealt += sum(scoring.teammate_damage(m, defender, field) for m in teammates)
    attacker_move = attacker.moves[move_index]
    regular = replace(defender, dynamax=False)
    attacks = [index for index, move in enumerate(regular.moves) if move.base_power > 0]
    if not attacks:
        return original(attacker, move_index, defender, teammates, field, max_move_probability)
    def to_team(version, indices, spread):
        """对手这几个招式打三个队友的平均（只在 indices 这些进攻招式里平均）。"""
        if not teammates:
            return 0.0
        total = sum(
            scoring.damage(version, index, member, field, spread) for index in indices for member in teammates
        )
        return total / (len(indices) * len(teammates))

    received_regular = 0.0
    for index in attacks:
        move = regular.moves[index]
        if move.is_spread:
            if attacker_move.name_id != "wide-guard" or attacker.dynamax:
                received_regular += scoring.damage(regular, index, attacker, field, True)
                received_regular += 3 * to_team(regular, attacks, True)
        else:
            to_self = scoring.damage(regular, index, attacker, field) / (scoring.DYNAMAX_HP if attacker.dynamax else 1)
            received_regular += 0.25 * to_self + 0.75 * to_team(regular, attacks, False)
    received_regular /= len(attacks)
    dynamaxed = replace(defender, dynamax=True)
    max_attacks = [index for index in attacks if index < min(4, len(dynamaxed.max_moves))]
    received_max = 0.0
    for index in max_attacks:
        to_self = scoring.damage(dynamaxed, index, attacker, field) / (scoring.DYNAMAX_HP if attacker.dynamax else 1)
        received_max += 0.25 * to_self + 0.75 * to_team(dynamaxed, max_attacks, False)
    received_max /= max(len(max_attacks), 1)
    received = received_regular * (1 - max_move_probability) + received_max * max_move_probability
    return dealt / received if received else 1.0


scoring.move_score = move_score

PAIRS = {
    12873702124229926581: [("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), ("不换", "不换", "换"), "9.18 分钟，倒下 0"),
                           ("力壮鸡", ("托戈德玛尔", "双剑鞘", "魔墙人偶"), ("不换", "换", "不换"), "10.20 分钟，倒下 9")],
    3076008315599927110: [("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), ("不换", "不换", "不换"), "6 局全胜，倒下 0.67"),
                          ("流氓熊猫", ("心蝙蝠", "肯泰罗", "狃拉"), ("不换", "不换", "不换"), "9 局 8 胜，倒下 1.44")],
    16238065963362826354: [("梦梦蚀", ("灯罩夜菇", "锹农炮虫", "劈斩司令"), ("换", "换", "不换"), "1 局，11.9 分钟，倒下 0"),
                           ("梦梦蚀", ("灯罩夜菇", "阿勃梭鲁", "魔墙人偶"), ("换", "换", "不换"), "1 局，12.6 分钟，倒下 3")],
}
CHECKS = v13.CHECKS + [("cresselia", 16238065963362826354, None)]

for mode in ("原来", "对手只算进攻招式"):
    MODE["value"] = mode
    print(f"\n######## {mode}")
    for boss, seed, expected in CHECKS:
        config = GameConfig()
        if boss in v13.TOP:
            config.lair_first_draw_top = v13.TOP[boss]
        data = GameData(config)
        results = v13.plan(data, upstream.Scorer(data, boss), Lair(data, seed))
        best = results[0]
        line = f"{seed}（{boss}）第 1：{best[1]}；{' → '.join(best[2])}；{'、'.join(best[3])}（{best[0]:.3f}）"
        if expected:
            exp = (expected[0], expected[1], tuple("换" if t else "不换" for t in expected[2]))
            rank = next((k + 1 for k, r in enumerate(results) if (r[1], r[2], r[3]) == exp), None)
            line += f"，实测最好的排第 {rank} / {len(results)}"
        print(line)
        for starter, path, swaps, note in PAIRS.get(seed, []):
            for k, r in enumerate(results):
                if (r[1], r[2], r[3]) == (starter, path, swaps):
                    print(f"    {starter}；{' → '.join(path)}；{'、'.join(swaps)}：{r[0]:.3f}，第 {k + 1} 名（实测 {note}）")
                    break
