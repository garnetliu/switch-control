"""给一批 seed 按「打关 + 路线」打分，找某只首领分最高的 seed。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本12-打关加路线找seed.py 首领 seed列表文件 [进程数]

分数（每个首发 × 每条路线都按 seed 推一遍，取最高）：
  打关 = Σ m(打第 i 关时自己那只, 第 i 关对手, 当时的队友)，第 2、3 关是谁按三关换不换、研究员推出来
  路线 = Σ wᵢ × m(第 i 关对手, 首领)，wᵢ = 1.0 / 1.1 / 1.2（上游原来的路线分）
m 是 upstream.Scorer.matchup（上游的相性公式，倍率换成实测的）。第一次抽数的上限按配置现在的名单算。
"""

import sys
from multiprocessing import Pool

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

BOSS = sys.argv[1]
_state = {}


def _init():
    data = GameData(GameConfig())
    _state["data"] = data
    _state["scorer"] = upstream.Scorer(data, BOSS)


def evaluate(seed: int):
    data, scorer = _state["data"], _state["scorer"]
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    try:
        lair = Lair(data, seed)
        candidates = lair.candidates()[:3]
        best = None
        for starter in range(3):
            for path in upstream.paths(lair.map_type()):
                walker = upstream.Walker(lair, data, BOSS, path, [candidates[starter], *lair.teammates(starter)])
                swaps = upstream.plan_swaps(scorer, walker)
                final = walker.copy()
                decide = lambda w: upstream.decide_scientist(scorer, w)  # noqa: E731
                final.side_events(decide)
                fight = 0.0
                for index, take in enumerate(swaps):
                    fight += scorer.matchup(final.team[0], walker.opponents[index], final.team[1:])
                    final.catch(take)
                    final.side_events(decide)
                route = scorer.route_score(walker.opponents)
                if best is None or fight + route > best[0]:
                    best = (fight + route, fight, route, zh(candidates[starter]),
                            " → ".join(zh(o) for o in walker.opponents),
                            "、".join("换" if s else "不换" for s in swaps))
        return seed, best, None
    except Exception as error:  # noqa: BLE001
        return seed, None, repr(error)


if __name__ == "__main__":
    seeds = [int(line) for line in open(sys.argv[2]) if line.strip()]
    with Pool(int(sys.argv[3]) if len(sys.argv) > 3 else 2, _init) as pool:
        results = pool.map(evaluate, seeds)
    ok = sorted((r for r in results if r[1]), key=lambda r: -r[1][0])
    failed = [r for r in results if not r[1]]
    print(f"{BOSS}：{len(ok)} 个算出来，{len(failed)} 个出错")
    for seed, (total, fight, route, starter, path, swaps), _ in ok[:15]:
        print(f"{seed}：总 {total:.2f}（打关 {fight:.2f} + 路线 {route:.2f}）首发 {starter}；{path}；{swaps}")
    for seed, _, error in failed[:5]:
        print(f"出错 {seed}：{error}")
