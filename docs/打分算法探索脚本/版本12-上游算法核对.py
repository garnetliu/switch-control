"""核对 src/swsh/lair/upstream.py：有实测对比的三张图，选的首发、路线、三关换法要和实测最好的一样。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本12-上游算法核对.py
开头第一次抽数的上限按每只首领当时的（超梦 24、哞哞 23、蝶蝶 21），配置里现在的值算出来的租借会不一样。
"""

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

failed = 0
for boss, seed, expected in CHECKS:
    config = GameConfig()
    config.lair_first_draw_top = TOP[boss]
    data = GameData(config)
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    lair = Lair(data, seed)
    scorer = upstream.Scorer(data, boss)
    began = time.monotonic()
    candidates = lair.candidates()[:3]
    starter = max(range(3), key=lambda index: scorer.starter_score(candidates[index]))
    seconds = time.monotonic() - began
    path, _ = upstream.best_path(scorer, lair.encounters(), lair.map_type())
    walker = upstream.Walker(lair, data, boss, path, [candidates[starter], *lair.teammates(starter)])
    swaps = tuple(upstream.plan_swaps(scorer, walker))
    got = (zh(candidates[starter]), tuple(zh(name) for name in walker.opponents), swaps)
    verdict = "" if expected is None else ("对" if got == expected else "不对")
    failed += verdict == "不对"
    print(f"{seed}（{boss}）：{got[0]}；{' → '.join(got[1])}；{'、'.join('换' if s else '不换' for s in swaps)} {verdict}（选首发用了 {seconds:.1f} 秒）")
print("三张有实测的图都对" if not failed else f"{failed} 张不对")

def route_plan(  # 试过、没放进项目：基准图选成了没打过的斧牙龙 → 龟足巨铠 → 狃拉

    scorer: upstream.Scorer,
    lair: Lair,
    data: GameData,
    map_type: str,
    events: dict[str, list[str]],
    starter: int,
) -> tuple[tuple, list[bool], float]:
    """首发定了以后选路线：上游的路线分，但只算最后真正在首领战队伍里的那几只。

    上游的路线分 = 路上三只（第 1、2、3 层权重 1.0、1.1、1.2）对首领相性的和，默认抓到的三只都会进队伍。
    这里每条路线都按 seed 从头推到首领战（三关换不换、研究员换不换按上面的规则当场定），
    被研究员换走的、抓到后没人要的不算。返回 (路线, 推出来的三关换不换, 路线分)。
    """
    candidates = lair.candidates()
    best: tuple[float, tuple, list[bool]] | None = None
    for path in upstream.paths(map_type):
        walker = upstream.Walker(
            lair, data, scorer.boss, path, [candidates[starter], *lair.teammates(starter)], events
        )
        swaps = upstream.plan_swaps(scorer, walker)
        final = walker.copy()
        final.side_events(lambda w: upstream.decide_scientist(scorer, w))
        for take in swaps:
            final.catch(take)
            final.side_events(lambda w: upstream.decide_scientist(scorer, w))
        score = sum(
            (1 + 0.1 * index) * scorer.matchup(name, scorer.boss)
            for index, name in enumerate(walker.opponents)
            if name in final.team
        )
        if best is None or score > best[0]:
            best = (score, path, swaps)
    assert best is not None
    score, path, swaps = best
    return path, swaps, score


print("\n== 选路线时就把换不换、研究员推进去（每个首发都算一次路线，路线分只算最后在首领战队伍里的，取最高）")
failed = 0
for boss, seed, expected in CHECKS:
    config = GameConfig()
    config.lair_first_draw_top = TOP[boss]
    data = GameData(config)
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")  # noqa: E731
    lair = Lair(data, seed)
    scorer = upstream.Scorer(data, boss)
    began = time.monotonic()
    events = data.lair_events(lair.map_type(), lair.layout())
    # 每个首发都算一次路线，路线分最高的那个首发和路线
    score, starter, path, swaps = max(
        (plan[2], index, plan[0], plan[1])
        for index in range(3)
        for plan in [route_plan(scorer, lair, data, lair.map_type(), events, index)]
    )
    seconds = time.monotonic() - began
    encounters = lair.encounters()
    got = (zh(lair.candidates()[starter]), tuple(zh(encounters[str(r)][c]) for r, c in path), tuple(swaps))
    verdict = "" if expected is None else ("对" if got == expected else "不对")
    failed += verdict == "不对"
    print(f"{seed}（{boss}）：{got[0]}；{' → '.join(got[1])}；{'、'.join('换' if s else '不换' for s in swaps)}，分 {score:.2f} {verdict}（{seconds:.0f} 秒）")
print("三张有实测的图都对" if not failed else f"{failed} 张不对")
