"""照 PokemonAutomation（AutoMaxLair 的后继）的选法，在有实测的图上算（docs/调研-其他项目的算法.md）。

相性 m(X, 首领) 用我们的 upstream.Scorer.matchup。PokemonAutomation 用的是预先算好的表（队友当作全部租借的平均）；
这里默认带按 seed 推出来的实际队友，加参数 --solo 不带队友（第一次算的），
--avg 像上游那样用「平均队友」：打出 = 自己 + 3 × 全部租借按实测出招比例的平均伤害，受到的 ¾ 打的是全部租借的平均。
- 首发：三只里对首领 m 最高的。
- 路线：Σ 第 i 层对手对首领的 m × (1, 2, 3)。PokemonAutomation 只知道属性，用的是「这个属性的租借对首领 m 的平均」；
  这里两种都算：按属性平均（原样）和按 seed 算出的实际对手。
- 抓到后：四种「谁拿」加「没人拿」，队伍分 = Σ 四只对首领的 m（电脑队友 × 0.5，满血不打折），最高的是自己才换。
- 研究员：当作会拿到「对首领 m 排中间的那只租借」，同样比。
队伍怎么变按 seed 推（upstream.Walker）。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本22-PokemonAutomation的算法.py
"""

import statistics
import sys

from swsh.lair import upstream
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

TOP = {"mewtwo": 24, "tapu-lele": 21}
MAPS = [
    (
        "mewtwo",
        3076008315599927110,
        [
            ("好（6 局倒下 4）", "pangoro", ("fraxure", "obstagoon", "sneasel")),
            ("差（9 局倒下 13）", "pangoro", ("swoobat", "tauros", "sneasel")),
        ],
    ),
    (
        "tapu-lele",
        12873702124229926581,
        [
            ("好（22 局倒下 3）", "blaziken", ("togedemaru", "doublade", "dugtrio-alola")),
            ("差（10 局倒下 9）", "combusken", ("togedemaru", "doublade", "mr-mime-galar")),
        ],
    ),
    (
        "tapu-lele",
        9960686445389280169,
        [
            ("实测最好（只打过这一种）", "relicanth", ("rhydon", "dugtrio-alola", "togedemaru")),
        ],
    ),
]


SOLO = "--solo" in sys.argv


AVG = "--avg" in sys.argv
_avg_cache = {}


def m_average(scorer, name, defender_name):
    """自己 name 对 defender_name 的相性，队友当作全部租借宝可梦的平均（和上游预先算表时一样的意思）。"""
    key = (name, defender_name)
    if key in _avg_cache:
        return _avg_cache[key]
    from dataclasses import replace

    from swsh import scoring
    from swsh.field import Field

    data = scorer.data
    field = Field()
    a = data.pokemon_object(name)
    b = data.pokemon_object(defender_name)
    if a.name_id == "ditto":
        a = scoring.transform_ditto(a, b)
    rentals = [data.pokemon_object(n) for n in scorer.rentals]
    mate_damage = 3 * sum(scoring.teammate_damage(t, b, field) for t in rentals) / len(rentals)
    p = data.max_move_rate(defender_name)
    regular, dynamaxed = replace(b, dynamax=False), replace(b, dynamax=True)
    to_mates_regular = scoring.average_damage([regular], rentals, field)
    to_mates_max = scoring.average_damage([dynamaxed], rentals, field)
    scores = {}
    for dynamax in (False, True):
        version = replace(a, dynamax=dynamax)
        shrink = scoring.DYNAMAX_HP if dynamax else 1
        to_self = (
            sum(scoring.damage(regular, i, version, field) for i in range(len(regular.moves)))
            / len(regular.moves)
            / shrink
        )
        count = min(4, len(dynamaxed.max_moves))
        to_self_max = (
            sum(scoring.damage(dynamaxed, i, version, field) for i in range(count)) / count / shrink
        )
        received = (0.25 * to_self + 0.75 * to_mates_regular) * (1 - p) + (
            0.25 * to_self_max + 0.75 * to_mates_max
        ) * p
        best = max(scoring.damage(version, i, b, field) for i in range(len(version.moves)))
        scores[dynamax] = (best + mate_damage) / received if received else 1.0
    value = max(scores[False], (scores[False] + scores[True]) / 2)
    _avg_cache[key] = value
    return value


def m(scorer, name, boss, mates):
    if AVG:
        return m_average(scorer, name, boss)
    return scorer.matchup(name, boss, () if SOLO else tuple(mates))


def team_score(scorer, team, boss):
    """四只对首领的相性相加（每只带队伍里另外三只当队友），电脑队友 × 0.5。"""
    return sum(
        m(scorer, name, boss, team[:index] + team[index + 1 :]) * (1.0 if index == 0 else 0.5)
        for index, name in enumerate(team)
    )


def decide_catch(scorer, walker, boss):
    new = walker.opponents[walker.caught]
    options = {-1: team_score(scorer, walker.team, boss)}
    for slot in range(4):
        trial = list(walker.team)
        trial[slot] = new
        options[slot] = team_score(scorer, trial, boss)
    return max(options, key=options.get) == 0


for boss, seed, routes in MAPS:
    config = GameConfig()
    config.lair_first_draw_top = TOP[boss]
    data = GameData(config)
    zh = lambda name: data.pokemon_object(name).name("zh-Hans")
    scorer = upstream.Scorer(data, boss)
    lair = Lair(data, seed)
    rentals = scorer.rentals
    by_type = {}
    for name in rentals:
        for type_id in data.pokemon_object(name).type_ids:
            by_type.setdefault(type_id, []).append(scorer.matchup(name, boss))
    type_score = {t: statistics.mean(v) for t, v in by_type.items()}
    median_rental = sorted(rentals, key=lambda n: scorer.matchup(n, boss))[len(rentals) // 2]

    candidates = lair.candidates()[:3]
    starter = max(range(3), key=lambda i: m(scorer, candidates[i], boss, lair.teammates(i)))
    encounters = lair.encounters()
    rows = {
        row: {item["col"]: item for item in items}
        for row, items in (lair.map_rows() if hasattr(lair, "map_rows") else {}).items()
    }

    def path_scores(path):
        """路线分：每一层对手对首领的相性，带上抓到它那时的三个队友（按 seed 推，三关都不换）。"""
        names = [encounters[str(r)][c] for r, c in path]
        walker = upstream.Walker(
            lair, data, boss, path, [candidates[starter], *lair.teammates(starter)]
        )
        actual = 0.0
        for weight, name in zip((1, 2, 3), names, strict=True):
            while walker.next_event() not in ("catch", None):
                if walker.next_event() == "backpacker":
                    walker.backpacker()
                else:
                    walker.scientist(False)
            actual += weight * m(scorer, name, boss, walker.team[1:])
            walker.catch(False)
        return names, actual

    scored = sorted((path_scores(p)[1], p) for p in upstream.paths(lair.map_type()))
    scored.reverse()
    print(f"\n== {seed}（{boss}）")
    print(
        "  首发："
        + "，".join(
            f"{zh(c)} {m(scorer, c, boss, lair.teammates(i)):.2f}" for i, c in enumerate(candidates)
        )
        + f" → 选 {zh(candidates[starter])}"
    )
    best_path = scored[0][1]
    for label, route_starter, route in [
        ("PokemonAutomation 选的", candidates[starter], None),
        *[(a, b, c) for a, b, c in routes],
    ]:
        path = (
            best_path
            if route is None
            else next(p for _, p in scored if tuple(encounters[str(r)][c] for r, c in p) == route)
        )
        names, actual = path_scores(path)
        rank = next(k + 1 for k, (_, p) in enumerate(scored) if p == path)
        start_index = candidates.index(route_starter)
        walker = upstream.Walker(
            lair, data, boss, path, [route_starter, *lair.teammates(start_index)]
        )
        swaps = []
        while (event := walker.next_event()) is not None:
            if event == "backpacker":
                walker.backpacker()
            elif event == "scientist":
                trial = list(walker.team)
                trial[0] = median_rental
                walker.scientist(
                    team_score(scorer, trial, boss) > team_score(scorer, walker.team, boss)
                )
            else:
                take = decide_catch(scorer, walker, boss)
                swaps.append("换" if take else "不换")
                walker.catch(take)
        print(
            f"  {label}：{zh(route_starter)}；{' → '.join(zh(n) for n in names)}；{'、'.join(swaps)}；"
            f"路线分 {actual:.2f}（第 {rank} / {len(scored)}）；首领战队伍 {'/'.join(zh(n) for n in walker.team)}"
        )
