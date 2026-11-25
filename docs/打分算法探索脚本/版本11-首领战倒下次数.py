"""首领战倒下几次，用开打前就知道的数（预测的回合数、四只各自的挨打）能预测到什么程度。

比两种算法：版本 10 的「回合数 × 四只的挨打合计」，版本 11 的「四只各自倒下的机会相加」（plan.faint_chance）。
每种都乘一个最合适的系数，再比泊松分布下的对数似然（越大越好）和相关。
队伍用日志里首领战开打时实际的四只，回合数按 Planner.boss 的式子预测。

另外按「前三关预测的回合数 × 对手打四只的伤害合计」分组，看前三关每一场平均倒下几次。
用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本11-首领战倒下次数.py [另外的日志文件...]
"""

import glob
import math
import runpy
import statistics
import sys
from pathlib import Path

from swsh.lair import plan

common = runpy.run_path(str(Path(__file__).with_name("版本11-验收.py")))
collect, config_of, data_of = common["collect"], common["config_of"], common["data_of"]

games = collect(sorted(glob.glob("runs/logs/swsh-lair/start/*.log")) + sys.argv[1:])


def likelihood(predicted: list[float], actual: list[int]) -> float:
    """乘上最合适的系数之后，泊松分布下的对数似然（去掉和预测无关的常数）。"""
    rate = sum(actual) / sum(predicted)
    return sum(
        k * math.log(max(rate * value, 1e-9)) - rate * value
        for value, k in zip(predicted, actual, strict=True)
    )


def waits(game: dict, config) -> list[int]:
    """每一场开打时还要过几个回合才轮到自己极巨化，按实际打的回合数推。"""
    result = []
    wait = 0
    for fight in game["fights"]:
        result.append(wait)
        left = 0
        for _ in range(fight["turns"]):
            _, left, wait = plan.rotate(left, wait, config)
    return result


boss_rows = []
stage_rows = []
for game in games:
    boss = game["boss"]
    config = config_of(boss)
    data = data_of(boss)
    damage = data.rental_damages()
    against = data.boss_attack_defense()
    planner = plan.Planner(data, config, boss)
    start = waits(game, config)
    for number, fight in enumerate(game["fights"][:4]):
        team = fight["team"]
        if any(name not in damage for name in team) or fight["turns"] == 0:
            break
        if number < 3:
            opponent = game["opponents"][number]
            others = sum(damage[name][opponent][2] for name in team[1:])
            turns, _, _ = plan.fight(damage[team[0]][opponent], start[number], config, others)
            stage_rows.append(
                (turns * sum(damage[opponent][name][0] for name in team), fight["faints"])
            )
            continue
        _, average = planner.boss_attack(team[0], start[3])
        attack = sum(against[name][boss][0] for name in team[1:])
        speed = min(max(config.boss_turn_rate * (average + attack), 1 / config.boss_max_turns), 1.0)
        received = [against[name][boss][2] for name in team]
        boss_rows.append(
            (
                boss,
                sum(received) / speed,
                sum(plan.faint_chance(value / speed, config) for value in received),
                fight["faints"],
            )
        )

print(f"首领战 {len(boss_rows)} 场")
for boss in ("mewtwo", "tapu-bulu", None):
    rows = [row for row in boss_rows if boss is None or row[0] == boss]
    actual = [row[3] for row in rows]
    print(f"  {boss or '两只首领合起来'} {len(rows)} 场，平均倒下 {statistics.mean(actual):.2f} 次")
    for label, index in (("回合数 × 挨打合计", 1), ("四只各自倒下的机会相加", 2)):
        values = [row[index] for row in rows]
        print(
            f"    {label}：对数似然 {likelihood(values, actual):.1f}，"
            f"和实际倒下次数的相关 {statistics.correlation(values, actual):+.2f}"
        )

print(f"\n前三关 {len(stage_rows)} 场：预测的回合数 × 对手打四只的伤害合计，和这一场倒下几次")
print(
    f"  相关 {statistics.correlation([a for a, _ in stage_rows], [b for _, b in stage_rows]):+.2f}"
)
for low, high in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 99)):
    part = [faints for value, faints in stage_rows if low <= value < high]
    if part:
        print(f"  {low} 到 {high}：{len(part)} 场，平均倒下 {statistics.mean(part):.2f} 次")
