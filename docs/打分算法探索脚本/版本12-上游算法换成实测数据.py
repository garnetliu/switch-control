"""上游 AutoMaxLair 选首发和路线的办法，换成实测的数据（个体值 31、自己极巨化血量 1.9、每种对手用极巨招式的比例），
在有实测结果的几张图上看它选什么。

上游的办法（提交 HEAD 里的 join.py、score.py）：
- 相性 = scoring.evaluate_matchup：用最好的招式时「打出的伤害 ÷ 受到的伤害」，max(普通, (普通 + 极巨) ÷ 2)。
- 首发 = (对全部租借宝可梦的平均相性 ** 3 × 对首领的相性 ** 2) ** (1/5)，三只里取最高。
- 路线 = 路上三只（第 1、2、3 层权重 1.0、1.1、1.2）对首领的相性加权和，取最高。路线和首发是分开选的。
血量倍数（3.8、4.18）对上游的选法没有影响：所有候选按同一个比例变，排名不变。
相性按上游一样不带队友算。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本12-上游算法换成实测数据.py
"""

import functools
from dataclasses import replace

from swsh.field import Field
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair
from swsh.lair.plan import paths
from swsh.scoring import select_best_move, transform_ditto

# 每只首领那段时间开头第一次抽数的上限（和 版本11-验收.py 一样；蝶蝶是现在的 21）
TOP = {"mewtwo": 24, "tapu-bulu": 23, "tapu-lele": 21}
MAPS = [
    ("mewtwo", 3076008315599927110, "基准图，实测熊猫首发、斧牙龙 → 堵拦熊 → 狃拉最好，心蝙蝠 → 肯泰罗 → 狃拉差"),
    ("tapu-bulu", 9004205710319247536, "哞哞，四张里实测最快"),
    ("tapu-bulu", 6986731677711377285, "哞哞，第 2 快"),
    ("tapu-bulu", 16753139388389203475, "哞哞，第 3 快"),
    ("tapu-bulu", 5938375612842167902, "哞哞，最慢"),
    ("tapu-lele", 12873702124229926581, "蝶蝶，实测火焰鸡首发、托戈德玛尔 → 双剑鞘 → 三地鼠 比 力壮鸡、→ 魔墙人偶 快且稳"),
    ("tapu-lele", 9960686445389280169, "蝶蝶，实测古空棘鱼首发、钻角犀兽 → 三地鼠 → 托戈德玛尔，全胜 9.0 分钟"),
]


@functools.cache
def data_of(boss: str) -> GameData:
    config = GameConfig()
    config.lair_first_draw_top = TOP[boss]
    return GameData(config)


D = data_of("tapu-lele")
RENTALS = list(D.rental_damages())


@functools.cache
def pokemon(name: str):
    return D.pokemon_object(name)


@functools.cache
def matchup(attacker: str, defender: str, measured: bool) -> float:
    """上游的相性。measured 为 False 时对手用极巨招式按上游的 0.3 算。"""
    a, b = pokemon(attacker), pokemon(defender)
    if a.name_id == "ditto":
        a = transform_ditto(a, b)
    elif b.name_id == "ditto":
        b = transform_ditto(b, a)
    rate = D.max_move_rate(defender) if measured else 0.3
    field = Field()
    base = select_best_move(replace(a, dynamax=False), b, field, (), rate)[2]
    dyn = select_best_move(replace(a, dynamax=True), b, field, (), rate)[2]
    return max(base, (base + dyn) / 2)


@functools.cache
def rental_score(name: str, measured: bool) -> float:
    return sum(matchup(name, other, measured) for other in RENTALS) / len(RENTALS)


def zh(name: str) -> str:
    return pokemon(name).name("zh-Hans")


for measured in (True,):
    print("== 上游的办法，换成实测数据" if measured else "== 上游原样")
    for boss, seed, note in MAPS:
        data = data_of(boss)
        lair = Lair(data, seed)
        candidates = lair.candidates()[:3]
        starters = sorted(
            ((rental_score(n, measured) ** 3 * matchup(n, boss, measured) ** 2) ** 0.2, n) for n in candidates
        )[::-1]
        encounters = lair.encounters()
        routes = sorted(
            (
                sum((1 + 0.1 * i) * matchup(encounters[str(r)][c], boss, measured) for i, (r, c) in enumerate(path)),
                path,
            )
            for path in paths(lair.map_type())
        )[::-1]
        print(f"{seed}（{note}）")
        print("  首发：" + "，".join(f"{zh(n)} {s:.3f}" for s, n in starters))
        for score, path in routes[:4]:
            print(f"  路线 {score:.3f}：" + " → ".join(zh(encounters[str(r)][c]) for r, c in path))


# ---- 加上换人和研究员：用项目里第一版的组合（docs/实测-打分算法对比.md「各版算法」版本 1）
# 自己的分 = (三关上场那只对该关对手的相性 × 打首领那只对首领的相性 ** 2) ** (1/5)；
# 每个队友的分同样算（按那个位置每一场实际是谁）；总分 = 自己的分 + 0.5 × 三个队友的分之和。
# 三关抓到后换不换 8 种都算，队友怎么变、研究员换掉谁用 plan.fate（自己在研究员那里不换）。
import itertools  # noqa: E402

from swsh.lair.plan import fate  # noqa: E402

KNOWN = {
    3076008315599927110: [("流氓熊猫", ("斧牙龙", "堵拦熊", "狃拉"), (False, False, False), "实测好（6 局全胜，倒下 0.67）"),
                          ("流氓熊猫", ("心蝙蝠", "肯泰罗", "狃拉"), (False, False, False), "实测差（9 局输 1，倒下 1.44）")],
    12873702124229926581: [("火焰鸡", ("托戈德玛尔", "双剑鞘", "三地鼠"), (False, False, True), "实测好（10 局 9.2 分钟，倒下 0）"),
                           ("力壮鸡", ("托戈德玛尔", "双剑鞘", "魔墙人偶"), (False, True, False), "实测差（10 局 10.2 分钟，倒下 9）")],
}


def score(boss, opponents, teams):
    """teams[i] 是第 i 场（0～2 三关，3 首领）开打时的队伍，自己在第一个。"""
    def one(slot):
        values = [matchup(teams[i][slot], opponents[i], True) for i in range(3)]
        values.append(matchup(teams[3][slot], boss, True) ** 2)
        product = 1.0
        for value in values:
            product *= max(value, 1e-9)
        return product ** 0.2
    return one(0) + 0.5 * sum(one(slot) for slot in (1, 2, 3))


print("\n== 上游的相性（实测数据）+ 换人和研究员，版本 1 的组合")
for boss, seed, note in MAPS:
    data = data_of(boss)
    lair = Lair(data, seed)
    candidates = lair.candidates()
    encounters = lair.encounters()
    events = data.lair_events(lair.map_type(), lair.layout())
    plans = []
    for path in paths(lair.map_type()):
        opponents = [encounters[str(r)][c] for r, c in path]
        for swaps in itertools.product((False, True), repeat=3):
            ahead = fate(lair, path, events, boss, swaps)
            for starter in range(3):
                team = [candidates[starter], *lair.teammates(starter)]
                for after, who, new in ahead.changes:
                    if after == -1:
                        team[1 + who] = new
                teams = []
                for i in range(3):
                    teams.append(tuple(team))
                    if swaps[i]:
                        team[0] = opponents[i]
                    elif ahead.takers[i] is not None:
                        team[1 + ahead.takers[i]] = opponents[i]
                    for after, who, new in ahead.changes:
                        if after == i:
                            team[1 + who] = new
                teams.append(tuple(team))
                if any(n not in RENTALS for t in teams for n in t):
                    continue
                plans.append((score(boss, opponents, teams), starter, path, swaps, opponents, teams))
    plans.sort(key=lambda p: -p[0])
    print(f"{seed}（{note}）")
    for total, starter, path, swaps, opponents, teams in plans[:3]:
        print(f"  {total:.3f} {zh(candidates[starter])}：{' → '.join(zh(o) for o in opponents)}，"
              f"{'、'.join('换' if s else '不换' for s in swaps)}；首领战 {'、'.join(zh(n) for n in teams[3])}")
    for name, route, swaps, label in KNOWN.get(seed, []):
        for rank, plan in enumerate(plans, 1):
            if zh(candidates[plan[1]]) == name and tuple(zh(o) for o in plan[4]) == route and plan[3] == swaps:
                print(f"  {label}：{plan[0]:.3f}，第 {rank} 名（共 {len(plans)} 种）")


# ---- 完全按上游的规则：首发、路线照上面；抓到后换不换、研究员换不换用上游 catch.py、path.py 的公式（HEAD 里的）
# 换不换：剩 r = 3 - 已抓只数 关，分 = (对后面可能遇到的对手的平均相性 ** r × 对首领的相性 ** 2) ** (1/(r+2))，相性带当时的队友；
#         换的分 = 新抓的当自己；不换的分 = 0.125 × 自己不变 + 0.875 × 三个队友各自换上它的平均；换的分高就换。
#         后面可能遇到的对手 = 没出现过、第一属性和路线上剩下的节点对得上的租借宝可梦。
# 研究员：没出现过的租借宝可梦的 rental_boss_score 平均比自己这只高就换（这一局走到的层数 floor 决定权重）。
# 队友实际怎么变用 plan.fate（自己每关换没换推到哪一步就按哪一步）。
from swsh.lair.plan import positions  # noqa: E402


@functools.cache
def matchup_with(attacker: str, defender: str, team: tuple[str, ...]) -> float:
    a, b = pokemon(attacker), pokemon(defender)
    if a.name_id == "ditto":
        a = transform_ditto(a, b)
    elif b.name_id == "ditto":
        b = transform_ditto(b, a)
    mates = [pokemon(n) for n in team]
    rate = D.max_move_rate(defender)
    base = select_best_move(replace(a, dynamax=False), b, Field(), mates, rate)[2]
    dyn = select_best_move(replace(a, dynamax=True), b, Field(), mates, rate)[2]
    return max(base, (base + dyn) / 2)


def weighted(rental: float, rental_weight: int, boss_score: float, boss_weight: int) -> float:
    total = rental_weight + boss_weight
    return ((rental**rental_weight) * (boss_score**boss_weight)) ** (1 / total)


def upstream_run(boss, seed):
    data = data_of(boss)
    lair = Lair(data, seed)
    candidates = lair.candidates()
    starter = max(range(3), key=lambda s: (rental_score(candidates[s], True) ** 3 * matchup(candidates[s], boss, True) ** 2) ** 0.2)
    encounters = lair.encounters()
    path = max(paths(lair.map_type()), key=lambda p: sum((1 + 0.1 * i) * matchup(encounters[str(r)][c], boss, True) for i, (r, c) in enumerate(p)))
    opponents = [encounters[str(r)][c] for r, c in path]
    events = data.lair_events(lair.map_type(), lair.layout())
    seen = set(candidates) | {n for row in encounters.values() for n in row}
    team = [candidates[starter], *lair.teammates(starter)]
    swaps: list[bool] = []
    notes = []
    teams = []
    scientists = [p for p in positions(path) if "scientist" in events.get(p, [])]

    def ahead():
        return fate(lair, path, events, boss, tuple(swaps + [False] * (3 - len(swaps))))

    for after, who, new in ahead().changes:
        if after == -1:
            team[1 + who] = new
    for i in range(3):
        teams.append(tuple(team))
        caught = opponents[i]
        left_types = {pokemon(o).type_ids[0] for o in opponents[i + 1 :]}
        potential = [n for n in RENTALS if n not in seen and n not in team and set(pokemon(n).type_ids) & left_types]
        r_weight = 3 - (i + 1)

        def team_score(first, rest):
            rental = sum(matchup_with(first, p, tuple(rest)) for p in potential) / len(potential) if potential and r_weight else 1.0
            return weighted(rental, r_weight, matchup_with(first, boss, tuple(rest)), 2)

        own, mates = team[0], team[1:]
        take = team_score(caught, mates)
        stay = team_score(own, mates)
        others = [team_score(own, [caught if k == j else mates[k] for k in range(3)]) for j in range(3)]
        leave = 0.125 * stay + 0.875 * sum(others) / 3
        swaps.append(take > leave)
        notes.append(f"第{i + 1}只 换 {take:.2f} / 不换 {leave:.2f}")
        result = ahead()
        if swaps[-1]:
            team[0] = caught
        elif result.takers[i] is not None:
            team[1 + result.takers[i]] = caught
        for after, who, new in result.changes:
            if after == i:
                team[1 + who] = new
    teams.append(tuple(team))
    # 研究员：上游会不会换（程序现在永远不换，队友怎么变的推算也是按自己不换算的）
    researcher = []
    for place in scientists:
        floor = int(place.split("-")[0]) if ">" not in place else int(place.split(">")[1].split("-")[0])
        names = [n for n in RENTALS if n not in seen]
        rental_weight = max(3 - floor, 0)
        def rbs(n):
            return weighted(rental_score(n, True), rental_weight, matchup(n, boss, True), 2)
        average = sum(rbs(n) for n in names) / len(names)
        researcher.append(f"{place} 平均 {average:.2f} / 自己这只 {rbs(teams[min(floor, 3)][0]):.2f}，{'换' if average > rbs(teams[min(floor, 3)][0]) else '不换'}")
    return candidates[starter], opponents, swaps, teams, notes, researcher


print("\n== 完全按上游的规则（首发、路线、抓到后换不换、研究员），相性用实测数据")
for boss, seed, note in MAPS:
    starter, opponents, swaps, teams, notes, researcher = upstream_run(boss, seed)
    print(f"{seed}（{note}）")
    print(f"  {zh(starter)}：{' → '.join(zh(o) for o in opponents)}，{'、'.join('换' if s else '不换' for s in swaps)}（{'；'.join(notes)}）")
    print(f"  每场队伍：{' | '.join('、'.join(zh(n) for n in t) for t in teams)}")
    if researcher:
        print("  研究员：" + "；".join(researcher))


# ---- 上游的公式，期望全部换成按 seed 算出的真实结果：
# 抓到后不换：哪个队友换上它用 seed 算（不再按 0.125 / 0.875 取期望）；研究员：它实际会给自己哪只用 seed 算（不再用平均分）；
# 后面要打的对手是路线上实际的对手（不再用同属性租借宝可梦的平均）。随机数按改正后的顺序逐个事件往下推：
# 抓到一只：draw(2)、三个队友各一个（偶数想要）；自己不换且有人想要才反复 draw(3) 定给谁。
# 研究员：三个队友各一个；自己换：紧接着 1 个数当洗牌种子，洗出来的给自己；自己不换且有人想要：反复 draw(3) 定谁，再 1 个数洗牌给他。
# 背包客：三个 draw(4)。
from libs.xoroshiro import Xoroshiro  # noqa: E402
from swsh.lair.lair import _first  # noqa: E402


def copy_rng(rng):
    other = Xoroshiro(0)
    other.s0, other.s1 = rng.s0, rng.s1
    return other


def real_run(boss, seed):
    data = data_of(boss)
    lair = Lair(data, seed)
    candidates = lair.candidates()
    rows = data.lair_rows()
    starter = max(range(3), key=lambda s: (rental_score(candidates[s], True) ** 3 * matchup(candidates[s], boss, True) ** 2) ** 0.2)
    encounters = lair.encounters()
    path = max(paths(lair.map_type()), key=lambda p: sum((1 + 0.1 * i) * matchup(encounters[str(r)][c], boss, True) for i, (r, c) in enumerate(p)))
    opponents = [encounters[str(r)][c] for r, c in path]
    events = data.lair_events(lair.map_type(), lair.layout())
    schedule = []
    for index, place in enumerate(positions(path)):
        if index and index % 2 == 0:
            schedule.append("catch")
        schedule += [e for e in events.get(place, []) if e != "berry"]

    rng = Xoroshiro(0)
    rng.s0, rng.s1 = lair._after
    species = data.boss_pokemon()[boss].id_num
    if any(row[2] and row[0] == species and row[4] != row[5] for row in rows):
        rng.next_u32()
    used = {(row[0], row[1]) for row in lair._picks()}

    def wants(r):
        return [m for m in range(3) if r.next_u32() & 1 == 0]

    def chosen(r, want):
        while want:
            v = r.draw(3)
            if v and v - 1 in want:
                return v - 1
        return None

    def score(first, rest, caught_count):
        """上游 catch.py 的分，后面的对手用路线上实际剩下的。"""
        left = opponents[caught_count:]
        weight = len(left)
        rental = sum(matchup_with(first, o, tuple(rest)) for o in left) / weight if weight else 1.0
        return weighted(rental, weight, matchup_with(first, boss, tuple(rest)), 2)

    team = [candidates[starter], *lair.teammates(starter)]
    caught = 0
    teams, log = [], []
    for event in schedule:
        if event == "catch":
            teams.append(tuple(team))
            new = opponents[caught]
            caught += 1
            rng.draw(2)
            want = wants(rng)
            taker = chosen(copy_rng(rng), list(want))
            own, mates = team[0], team[1:]
            stay_mates = [new if k == taker else mates[k] for k in range(3)]
            take_score = score(new, mates, caught)
            leave_score = score(own, stay_mates, caught)
            if take_score > leave_score:
                team[0] = new
                log.append(f"抓第{caught}只 换（{take_score:.2f} / {leave_score:.2f}）")
            else:
                chosen(rng, want)
                if taker is not None:
                    team[1 + taker] = new
                log.append(f"抓第{caught}只 不换（{take_score:.2f} / {leave_score:.2f}），{'队友换上' if taker is not None else '没人换'}")
        elif event == "scientist":
            want = wants(rng)
            trial = copy_rng(rng)
            row = _first(rows, trial.next_u32(), used)
            give = data.name_id(row[0], row[1])
            own, mates = team[0], team[1:]
            if give in RENTALS and score(give, mates, caught) > score(own, mates, caught):
                rng.next_u32()
                used.add((row[0], row[1]))
                team[0] = give
                log.append(f"研究员 换成 {zh(give)}（{score(give, mates, caught):.2f} / {score(own, mates, caught):.2f}）")
            else:
                member = chosen(rng, want)
                log.append(f"研究员 不换（给的是 {zh(give) if give in RENTALS else give}）")
                if member is not None:
                    row = _first(rows, rng.next_u32(), used)
                    used.add((row[0], row[1]))
                    team[1 + member] = data.name_id(row[0], row[1])
                    log[-1] += f"，队友换成 {zh(team[1 + member])}"
        elif event == "backpacker":
            for _ in range(3):
                rng.draw(4)
    teams.append(tuple(team))
    return candidates[starter], opponents, teams, log


print("\n== 上游的公式，换人、研究员、后面的对手都用按 seed 算出的真实结果")
for boss, seed, note in MAPS:
    starter, opponents, teams, log = real_run(boss, seed)
    print(f"{seed}（{note}）")
    print(f"  {zh(starter)}：{' → '.join(zh(o) for o in opponents)}；{'；'.join(log)}")
    print(f"  每场队伍：{' | '.join('、'.join(zh(n) for n in t) for t in teams)}")


# ---- 同上，但每次决定换不换时，两种选择各自往后推：把下一场战斗之前的研究员、背包客按实际结果推完（研究员换不换也按上游规则），
# 用推完以后的队伍打分。自己换不换会改变随机数，研究员换掉谁也跟着变。
def real_run2(boss, seed):
    data = data_of(boss)
    lair = Lair(data, seed)
    candidates = lair.candidates()
    rows = data.lair_rows()
    starter = max(range(3), key=lambda s: (rental_score(candidates[s], True) ** 3 * matchup(candidates[s], boss, True) ** 2) ** 0.2)
    encounters = lair.encounters()
    path = max(paths(lair.map_type()), key=lambda p: sum((1 + 0.1 * i) * matchup(encounters[str(r)][c], boss, True) for i, (r, c) in enumerate(p)))
    opponents = [encounters[str(r)][c] for r, c in path]
    events = data.lair_events(lair.map_type(), lair.layout())
    schedule = []
    for index, place in enumerate(positions(path)):
        if index and index % 2 == 0:
            schedule.append("catch")
        schedule += [e for e in events.get(place, []) if e != "berry"]

    def wants(r):
        return [m for m in range(3) if r.next_u32() & 1 == 0]

    def chosen(r, want):
        while want:
            v = r.draw(3)
            if v and v - 1 in want:
                return v - 1
        return None

    def score(first, rest, caught_count):
        left = opponents[caught_count:]
        weight = len(left)
        rental = sum(matchup_with(first, o, tuple(rest)) for o in left) / weight if weight else 1.0
        return weighted(rental, weight, matchup_with(first, boss, tuple(rest)), 2)

    def side_events(rng, team, used, start, caught, log):
        """从 schedule[start] 开始推研究员、背包客，碰到下一次抓或者走完为止，返回停下的位置。"""
        index = start
        while index < len(schedule) and schedule[index] != "catch":
            event = schedule[index]
            if event == "scientist":
                want = wants(rng)
                trial = copy_rng(rng)
                row = _first(rows, trial.next_u32(), used)
                give = data.name_id(row[0], row[1])
                own, mates = team[0], team[1:]
                if give in RENTALS and score(give, mates, caught) > score(own, mates, caught):
                    rng.next_u32()
                    used.add((row[0], row[1]))
                    team[0] = give
                    log.append(f"研究员 换成 {zh(give)}")
                else:
                    member = chosen(rng, want)
                    log.append("研究员 不换")
                    if member is not None:
                        row = _first(rows, rng.next_u32(), used)
                        used.add((row[0], row[1]))
                        team[1 + member] = data.name_id(row[0], row[1])
                        log[-1] += f"，队友换成 {zh(team[1 + member])}"
            elif event == "backpacker":
                for _ in range(3):
                    rng.draw(4)
            index += 1
        return index

    rng = Xoroshiro(0)
    rng.s0, rng.s1 = lair._after
    species = data.boss_pokemon()[boss].id_num
    if any(row[2] and row[0] == species and row[4] != row[5] for row in rows):
        rng.next_u32()
    used = {(row[0], row[1]) for row in lair._picks()}
    team = [candidates[starter], *lair.teammates(starter)]
    log, teams = [], []
    index = side_events(rng, team, used, 0, 0, log)
    caught = 0
    while index < len(schedule):
        teams.append(tuple(team))
        new = opponents[caught]
        caught += 1
        rng.draw(2)
        want = wants(rng)
        options = {}
        for take in (True, False):
            r, t, u, l = copy_rng(rng), list(team), set(used), []
            if take:
                t[0] = new
            else:
                taker = chosen(r, list(want))
                if taker is not None:
                    t[1 + taker] = new
            nxt = side_events(r, t, u, index + 1, caught, l)
            options[take] = (score(t[0], t[1:], caught), r, t, u, l, nxt)
        take = options[True][0] > options[False][0]
        log.append(f"抓第{caught}只 {'换' if take else '不换'}（推完后面的研究员：换 {options[True][0]:.2f} / 不换 {options[False][0]:.2f}）")
        _, rng, team, used, extra, index = options[take]
        log += extra
    teams.append(tuple(team))
    return candidates[starter], opponents, teams, log


print("\n== 上游的公式 + 真实结果，决定换不换时把后面的研究员也推完")
for boss, seed, note in MAPS:
    starter, opponents, teams, log = real_run2(boss, seed)
    print(f"{seed}（{note}）")
    print(f"  {zh(starter)}：{' → '.join(zh(o) for o in opponents)}；{'；'.join(log)}")
    print(f"  每场队伍：{' | '.join('、'.join(zh(n) for n in t) for t in teams)}")
