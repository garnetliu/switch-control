"""路线分按每一层实际上场的自己算（docs/打分算法-首发和路线.md「路线分」）。

路线分 = ( m(打第 1 关的自己, E₁) × m(打第 2 关的自己, E₂) × m(打第 3 关的自己, E₃) × m(打首领的自己, 首领)² )^(1/5)
首发 × 路线 × 每一关打完「抓了换 / 抓了不换 / 不抓」× 每次研究员换不换，全部组合都推一遍，取最高。
m 带上那一场实际的三个队友（按 seed 推出来的）；加参数 --solo 不带队友（第一次试算的算法）。

不抓：这一只谁都拿不到，队伍不变。不抓时随机数怎么走还没实测，先按两种假设：
  默认：不抓就不抽数（抓到后那几个随机数都不抽）；
  --skip-draws：照样抽（和「抓了不换」抽一样多的数），只是没人换。
加 --no-skip 不算不抓（第二次试算的算法）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本13-按实际上场算路线分.py
"""

import sys
import time

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

TOP = {"mewtwo": 24, "tapu-bulu": 23, "tapu-lele": 21}
CHECKS = [
    ("mewtwo", 3076008315599927110, ("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), (False, False, False))),
    ("tapu-lele", 12873702124229926581, ("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), (False, False, True))),
    ("tapu-lele", 9960686445389280169, ("古空棘鱼", ("钻角犀兽", "三地鼠", "托戈德玛尔"), (True, False, False))),
    ("tapu-bulu", 6986731677711377285, None),
    ("tapu-bulu", 9004205710319247536, None),
    ("tapu-bulu", 16753139388389203475, None),
    ("tapu-bulu", 5938375612842167902, None),
]


def outcomes(walker: upstream.Walker):
    """从 walker 现在的位置往后，每次抓到、研究员都分换和不换两种推下去。

    产出 (抓到后换不换, 研究员换不换, 每一关的队伍, 首领战的队伍)，队伍是 (自己, 队友1, 队友2, 队友3)。
    """

    def walk(w, catches, scientists, fighters):
        while (event := w.next_event()) == "backpacker":
            w.backpacker()
        if event is None:
            yield tuple(catches), tuple(scientists), tuple(fighters), tuple(w.team)
            return
        if event == "catch":
            # 打这一关的是抓之前的队伍
            fighter = tuple(w.team)
            for choice in CATCH_CHOICES:
                trial = w.copy()
                if choice == "不抓":
                    skip(trial)
                else:
                    trial.catch(choice == "换")
                yield from walk(trial, catches + [choice], scientists, fighters + [fighter])
        else:
            for take in (False, True):
                trial = w.copy()
                trial.scientist(take)
                yield from walk(trial, catches, scientists + [take], fighters)

    yield from walk(walker.copy(), [], [], [])


SOLO = "--solo" in sys.argv
CATCH_CHOICES = ("不换", "换") if "--no-skip" in sys.argv else ("不换", "换", "不抓")


def skip(w: upstream.Walker) -> None:
    """这一关打完不抓：队伍不变。随机数按 --skip-draws 的假设走。"""
    if "--skip-draws" in sys.argv:
        team = list(w.team)
        w.catch(False)
        w.team = team
    else:
        w.caught += 1
        w.index += 1


def m(scorer, team, defender):
    return scorer.matchup(team[0], defender, () if SOLO else team[1:])


def route_score(scorer, fighters, opponents, boss_fighter):
    product = m(scorer, boss_fighter, scorer.boss) ** 2
    for fighter, opponent in zip(fighters, opponents, strict=True):
        product *= m(scorer, fighter, opponent)
    if product <= 0:
        return None
    return product ** 0.2


def plan(data, scorer, lair):
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    candidates = lair.candidates()[:3]
    results = []
    for starter in range(3):
        for path in upstream.paths(lair.map_type()):
            walker = upstream.Walker(lair, data, scorer.boss, path, [candidates[starter], *lair.teammates(starter)])
            for catches, scientists, fighters, boss_fighter in outcomes(walker):
                score = route_score(scorer, fighters, walker.opponents, boss_fighter)
                if score is None:
                    continue
                results.append((score, zh(candidates[starter]), tuple(zh(o) for o in walker.opponents),
                                catches, scientists, [zh(f[0]) for f in fighters], zh(boss_fighter[0])))
    results.sort(key=lambda r: -r[0])
    return results


if __name__ == "__main__":
    for boss, seed, expected in CHECKS:
        config = GameConfig()
        config.lair_first_draw_top = TOP[boss]
        data = GameData(config)
        scorer = upstream.Scorer(data, boss)
        began = time.monotonic()
        results = plan(data, scorer, Lair(data, seed))
        verdict = ""
        if expected:
            expected = (expected[0], expected[1], tuple("换" if t else "不换" for t in expected[2]))
            best = results[0]
            verdict = "对" if (best[1], best[2], best[3]) == expected else "不对"
            rank = next((k + 1 for k, r in enumerate(results) if (r[1], r[2], r[3]) == expected), None)
            verdict += f"（实测最好的方案排第 {rank} / {len(results)}）"
        print(f"\n{seed}（{boss}）{verdict}，{time.monotonic() - began:.0f} 秒")
        for score, starter, path, catches, scientists, fighters, boss_fighter in results[:3]:
            swaps = "、".join(catches)
            extra = f"；研究员 {'、'.join('换' if t else '不换' for t in scientists)}" if scientists else ""
            print(f"  {score:.3f} 首发 {starter}；{' → '.join(path)}；{swaps}{extra}；上场 {'/'.join(fighters)} → 首领 {boss_fighter}")
