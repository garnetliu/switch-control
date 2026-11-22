"""m 里「受到的伤害」拆到每一只身上再合起来，看弱点能不能进分数（docs/打分算法-首发和路线.md）。

每只（自己 + 三个队友）受到的伤害 r = 对手一回合平均打掉它多少血：
  单体招式 ¼ 概率打到它，范围招式每只都打到（× 0.75）；普通 / 极巨按这只对手实测的极巨招式比例混合；
  自己极巨化时 ÷ 1.9；下限 0.01。
合起来：
  原来：受到 = ¼ × 打自己 + ¾ × 打队友的平均（等于四只 r 相加）
  A 几何：受到 = 4 × (r₁ r₂ r₃ r₄)^(1/4)
  B 最脆：受到 = 4 × max(r)
打出的伤害不变（自己这一招 + 三个队友按实测比例）。路线分、组合方式和版本 13 一样（不算不抓）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本14-受到的伤害按每只算.py
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

FLOOR = 0.01
original = scoring.move_score
MODE = {"value": "原来"}


def received_each(attacker, defender, teammates, field, p):
    team = [attacker, *teammates]
    regular = replace(defender, dynamax=False)
    dynamaxed = replace(defender, dynamax=True)
    result = []
    for member in team:
        shrink = scoring.DYNAMAX_HP if (member is attacker and attacker.dynamax) else 1
        normal = 0.0
        for index, move in enumerate(regular.moves):
            if move.is_spread:
                normal += scoring.damage(regular, index, member, field, True)
            else:
                normal += 0.25 * scoring.damage(regular, index, member, field)
        normal /= len(regular.moves)
        count = min(4, len(dynamaxed.max_moves))
        big = sum(0.25 * scoring.damage(dynamaxed, index, member, field) for index in range(count)) / count
        result.append(max((normal * (1 - p) + big * p) / shrink, FLOOR))
    return result


def move_score(attacker, move_index, defender, teammates, field, max_move_probability=scoring.MAX_MOVE_PROBABILITY):
    if MODE["value"] == "原来":
        return original(attacker, move_index, defender, teammates, field, max_move_probability)
    teammates = [m for m in teammates if m is not attacker and m is not defender]
    dealt = scoring.damage(attacker, move_index, defender, field)
    dealt += sum(scoring.teammate_damage(m, defender, field) for m in teammates)
    each = received_each(attacker, defender, teammates, field, max_move_probability)
    if MODE["value"] == "A 几何":
        product = 1.0
        for value in each:
            product *= value
        received = len(each) * product ** (1 / len(each))
    else:
        received = len(each) * max(each)
    return dealt / received


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

for mode in ("原来", "A 几何", "B 最脆"):
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
