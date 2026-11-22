"""m 按最坏情况算（极小化极大的思路），算的是下限，实战一般比分数好（docs/打分算法-首发和路线.md）。

招式分 = 打出 ÷ 受到
  打出 = 自己最好的那一招（就是这一招）+ 每个队友最差的那一招（带变化招式的就是 0，等于轮空）
  受到 = 对手打得最狠的那一下：对手全部招式（普通 + 极巨）× 我方四只，取伤害最大的
         （范围招式按打多个目标 × 0.75；打到自己且自己极巨化时 ÷ 1.9）
m = max(普通, (普通 + 极巨) ÷ 2)；路线分、组合方式和版本 13 一样（不算不抓）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本15-最坏情况.py
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


def worst_teammate(member, defender, field):
    """队友最差的那一招打 defender 的伤害；变化招式按 0。"""
    version = replace(member, dynamax=False)
    values = [
        0.0 if move.base_power <= 0 else max(scoring.damage(version, index, defender, field), 0.0)
        for index, move in enumerate(version.moves)
    ]
    return min(values) if values else 0.0


def worst_received(attacker, defender, teammates, field):
    """对手打得最狠的那一下：全部招式 × 我方四只取最大。"""
    worst = 0.0
    for version in (replace(defender, dynamax=False), replace(defender, dynamax=True)):
        moves = version.max_moves[:4] if version.dynamax else version.moves
        for index, move in enumerate(moves):
            spread = (not version.dynamax) and move.is_spread
            for member in [attacker, *teammates]:
                value = scoring.damage(version, index, member, field, spread)
                if member is attacker and attacker.dynamax:
                    value /= scoring.DYNAMAX_HP
                worst = max(worst, value)
    return worst


def move_score(attacker, move_index, defender, teammates, field, max_move_probability=scoring.MAX_MOVE_PROBABILITY):
    if MODE["value"] == "原来":
        return original(attacker, move_index, defender, teammates, field, max_move_probability)
    teammates = [m for m in teammates if m is not attacker and m is not defender]
    dealt = scoring.damage(attacker, move_index, defender, field)
    dealt += sum(worst_teammate(m, defender, field) for m in teammates)
    received = worst_received(attacker, defender, teammates, field)
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

for mode in ("原来", "最坏情况"):
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
