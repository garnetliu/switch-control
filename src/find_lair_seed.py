"""找极巨大冒险里总分最高的 seed：python src/find_lair_seed.py --boss tapu-bulu [--first weezing,doublade] [--workers 4] [--top 10] [--minutes 30] [--floor 0.6]。

只做计算，不连 Switch。不停地试随机 seed，按程序选首发和路线的算法（swsh/lair/plan.py 的 Planner.best）
给每张图算总分，留下总分最高的 --top 个；每进来一个新的就打印。到了 --minutes 或者按 Ctrl-C 时停下，
打印最后的结果。--boss 是首领的 name_id，不给就用配置里的那只。

一批 seed 一起算是先粗筛：队友换不换按期望算（plan.decide 不给 fate 时的算法），筛出来的再用 Planner.best
精确算（队友的变化从 seed 直接算，和程序开局规划一样），榜单按精确的分排。粗筛和 plan.py 是同一套算法：每一关逐回合预测打几个回合（plan.fight），
三关换不换的 8 种换法都算，首领分按队友换上抓到的那几只的各种情况取期望（plan.decide）。

--first 给一只或几只宝可梦的 name_id：不随机试，直接造出「6 只租借里第 1 只是它」的 seed 来试
（见 _construct），这一条不用碰运气，同样的时间相当于多试两百多倍。只能指定第 1 只：
每只都是拿一个随机数当种子洗牌抽出来的，洗牌没法倒推，能凑的只有 seed 到第 2 个随机数这一步。

开头第一次抽数的上限按配置里已经抓到的神兽 lair_caught 算，抓走神兽后会变小（见 GameData.first_draw_top）；
这个值过时了的话，这里找出来的 seed 写进游戏后租借和路线都对不上。
每次抽取只算洗牌后的前 ORDER 张，前 ORDER 张都是首领或者已经抽过的 seed 不要，约占一成多。
"""

import argparse
import functools
import itertools
import multiprocessing
import time

import numpy as np

from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import MAP_TYPES, Lair
from swsh.lair.plan import Plan, Planner, fate, own_hurt, paths, positions

CONFIG = GameConfig()
DATA = GameData(CONFIG)
ROWS = DATA.lair_rows()
SIZE = len(ROWS)
FIRST_DRAW_TOP = DATA.first_draw_top()
# 批量筛的时候队友的变化按期望算，是估的；估的分到了榜尾的这个比例就拿来按程序的算法精确算
SCREEN = 0.75
# 一批里最多精确算几个
EXACT_PER_BATCH = 20
# 一批试多少个 seed
BATCH = 200_000
# 每次抽取只看洗牌后的前 ORDER 张，前 ORDER 张都不能用（首领或者已经抽过）的 seed 不要了
ORDER = 3
# 每次抽取最多用 MT 的前 OUTPUTS 个随机数
OUTPUTS = 16

# 租借宝可梦的编号：伤害表里的顺序。遭遇表里的每一行对应哪个编号，首领那些行和表里没有的是 -1
_damages = DATA.rental_damages()
_bosses = DATA.boss_attack_defense()
RENTALS = list(_damages)
_number = {name: index for index, name in enumerate(RENTALS)}
NUMBER = np.array(
    [-1 if row[2] else _number.get(DATA.name_id(row[0], row[1]), -1) for row in ROWS],
    dtype=np.int64,
)
FLAGGED = np.array([row[2] for row in ROWS], dtype=bool)
# 同一只宝可梦（species 和 form 一样）在表里第一次出现的下标，用来判断抽没抽过
_first: dict[tuple[int, int], int] = {}
CANON = np.array([_first.setdefault((row[0], row[1]), index) for index, row in enumerate(ROWS)])
EXTRA_NEXT = np.array([row[4] != row[5] for row in ROWS], dtype=bool)
PATHS = {
    map_type: [tuple(col for _, col in path) for path in paths(map_type)]
    for map_type in MAP_TYPES.values()
}
# 路线上已知的研究员个数：[地图类型][第几条路线][布局编号]
SCIENTISTS = {
    map_type: [
        np.array(
            [
                sum(
                    DATA.lair_events(map_type, layout).get(position, []).count("scientist")
                    for position in positions(path)
                )
                for layout in range(10)
            ]
        )
        for path in paths(map_type)
    ]
    for map_type in MAP_TYPES.values()
}
# 研究员换给队友的那只在下面几张表里的编号：排在全部租借宝可梦后面，数值是它们的平均（plan.AVERAGE）
UNKNOWN = len(RENTALS)


def _tables(boss: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """把对 boss 这只首领的数提前算成表，下标是租借宝可梦的编号。

    返回 (first, average, attack, received)：
    - first[等待, 宝可梦]、average[等待, 宝可梦]：首领战开打时还要过「等待」个回合才轮到自己极巨化，
      自己拿这只打首领第 1 回合的进攻、前 boss_turns 个回合平均的进攻（Planner.boss_attack）。
    - attack[宝可梦]、received[宝可梦]：普通招式的进攻、挨打。
    """
    planner = Planner(DATA, CONFIG, boss)
    waits = CONFIG.dynamax_wait + 1
    first = np.zeros((waits, len(RENTALS)))
    average = np.zeros((waits, len(RENTALS)))
    for number, name in enumerate(RENTALS):
        for wait in range(waits):
            first[wait, number], average[wait, number] = planner.boss_attack(name, wait)
    attack = np.array([_bosses[name][boss][0] for name in RENTALS])
    received = np.array([_bosses[name][boss][2] for name in RENTALS])
    # 最后多一项 UNKNOWN：全部租借宝可梦的平均
    return first, average, np.append(attack, attack.mean()), np.append(received, received.mean())


# 租借宝可梦两两之间的伤害：[进攻的, 防守的]，普通招式、极巨招式、普通招式的平均
NORMAL, DYNAMAX, AVERAGE = (
    np.array([[_damages[a][d][index] for d in RENTALS] for a in RENTALS]) for index in range(3)
)
# 队友用的那张多一行 UNKNOWN：全部租借宝可梦的平均
AVERAGE = np.vstack([AVERAGE, AVERAGE.mean(axis=0)])
# 首领和按首领算好的表，_setup 里填；每个进程开始时都要调一次
BOSS = CONFIG.boss
BOSS_FIRST = BOSS_AVERAGE = BOSS_ATTACK = BOSS_RECEIVED = np.zeros(0)
# 首领战里自己的挨打要乘的倍数（plan.own_hurt），下标是开打时还要过几个回合才轮到自己极巨化
OWN_HURT = np.array([own_hurt(wait, CONFIG) for wait in range(CONFIG.dynamax_wait + 1)])
# --first 指定的宝可梦对应的 MT 种子：拿它们洗牌，第 1 张就是指定的宝可梦。没指定是空的
TARGETS = np.zeros(0, dtype=np.uint64)


def _setup(boss: str, first: tuple[str, ...] = ()) -> None:
    global BOSS, BOSS_FIRST, BOSS_AVERAGE, BOSS_ATTACK, BOSS_RECEIVED, TARGETS
    BOSS = boss
    BOSS_FIRST, BOSS_AVERAGE, BOSS_ATTACK, BOSS_RECEIVED = _tables(boss)
    if first:
        wanted = np.array([RENTALS.index(name) for name in first])
        tries = np.random.default_rng().integers(0, 2**32, size=400_000, dtype=np.uint64)
        row, usable = _pick(tries, [])
        TARGETS = tries[usable & np.isin(NUMBER[row], wanted)]


def _rotate(
    active: np.ndarray, left: np.ndarray, wait: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """active 是 True 的那些往前走一个回合，和 plan.rotate 一样：返回 (这个回合是不是极巨化的, left, wait)。"""
    going = left > 0
    start = ~going & (wait == 0)
    change = np.where(going, left - 1, np.where(start, CONFIG.dynamax_turns - 1, left))
    left = np.where(active, change, left)
    change = np.where(start, CONFIG.dynamax_wait, np.where(going, wait, wait - 1))
    wait = np.where(active, change, wait)
    return going | start, left, wait


def _stage(
    fielded: np.ndarray, opponent: np.ndarray, wait: np.ndarray, team: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """一批 seed 各打一关，和 plan.fight 一样：返回 (这一关的分的对数, 打完之后还要过几个回合)。"""
    normal, dynamaxed = NORMAL[fielded, opponent], DYNAMAX[fielded, opponent]
    others = CONFIG.stage_team_rate * team + CONFIG.stage_base_rate
    health = np.ones(len(fielded))
    left = np.zeros(len(fielded), dtype=np.int64)
    turns = np.ones(len(fielded))
    active = np.ones(len(fielded), dtype=bool)
    # 打完之后轮换还要再走一个回合的
    more = np.zeros(len(fielded), dtype=bool)
    for index in range(CONFIG.stage_max_turns):
        if not active.any():
            break
        count = index + 1
        dynamax, left, wait = _rotate(active, left, wait)
        value = np.where(dynamax, dynamaxed, normal)
        hit = CONFIG.stage_own_rate * value + others
        down = hit >= health
        sure = value >= CONFIG.stage_sure_damage
        likely = ~sure & (value >= CONFIG.stage_likely_damage)
        low = ~sure & ~likely & (down | (count == CONFIG.stage_max_turns))
        if count == 1:
            slow = np.full(len(fielded), CONFIG.stage_weak_turns)
        else:
            slow = count - 1 + np.where(down, health / np.where(down, hit, 1.0), 1.0) + 0.5
        done = active & (sure | likely | low)
        turns = np.where(done, np.where(sure, count, np.where(likely, count + 0.5, slow)), turns)
        more |= done & ((likely & ~down) | (low & (count == 1)))
        health = np.where(active & ~done, health - hit, health)
        active &= ~done
    _, left, wait = _rotate(more, left, wait)
    return -np.log(turns), wait


# 下面是一批 seed 一起算的版本，算法和 Xoroshiro、Lair._picks 一样

U = np.uint64
MASK32 = U(0xFFFFFFFF)


class _Rng:
    """一批 Xoroshiro。"""

    def __init__(self, s0: np.ndarray, s1: np.ndarray | None = None):
        self.s0 = s0.copy()
        self.s1 = np.full(len(s0), 0x82A2B175229D6A5B, dtype=U) if s1 is None else s1.copy()

    def take(self, keep: np.ndarray) -> "_Rng":
        return _Rng(self.s0[keep], self.s1[keep])

    def next(self, only: np.ndarray | None = None) -> np.ndarray:
        """每个都取一个随机数；给了 only 就只有 only 是 True 的往前走。"""
        s0, s1 = self.s0, self.s1
        result = (s0 + s1) & MASK32
        mixed = s1 ^ s0
        new0 = ((s0 << U(24)) | (s0 >> U(40))) ^ mixed ^ (mixed << U(16))
        new1 = (mixed << U(37)) | (mixed >> U(27))
        if only is None:
            self.s0, self.s1 = new0, new1
        else:
            self.s0, self.s1 = np.where(only, new0, s0), np.where(only, new1, s1)
        return result

    def draw(self, top: int) -> np.ndarray:
        mask = U((1 << top.bit_length()) - 1)
        todo = np.ones(len(self.s0), dtype=bool)
        result = np.zeros(len(self.s0), dtype=np.int64)
        while todo.any():
            value = self.next(todo) & mask
            done = todo & (value <= U(top))
            result[done] = value[done]
            todo &= ~done
        return result


def _mt_outputs(seed: np.ndarray) -> list[np.ndarray]:
    """每个 MT 种子的前 OUTPUTS 个随机数的低 9 位。"""
    need: dict[int, np.ndarray] = {}
    state = seed.copy()
    for index in range(397 + OUTPUTS):
        if index:
            state = (U(1812433253) * (state ^ (state >> U(30))) + U(index)) & MASK32
        if index <= OUTPUTS or index >= 397:
            need[index] = state
    outputs = []
    for index in range(OUTPUTS):
        y = (need[index] & U(0x80000000)) | (need[index + 1] & U(0x7FFFFFFF))
        value = need[index + 397] ^ (y >> U(1)) ^ np.where(y & U(1), U(0x9908B0DF), U(0))
        value ^= value >> U(11)
        value ^= (value << U(7)) & U(0x9D2C5680)
        value ^= (value << U(15)) & U(0xEFC60000)
        value ^= value >> U(18)
        outputs.append((value & U(0x1FF)).astype(np.int64))
    return outputs


def _pick(seed: np.ndarray, used: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """一次抽取：返回 (抽到的行的下标, 这个结果能不能用)。

    和 Lair._picks 里的 pick 一样洗牌，但只算洗牌后的前 ORDER 张，取里面第一张不是首领、
    也没抽过的。前 ORDER 张都不行的不往下算，标成不能用。
    """
    outputs = _mt_outputs(seed)
    count = len(seed)
    cursor = np.zeros(count, dtype=np.int64)
    valid = np.ones(count, dtype=bool)
    # 洗牌时换过位置的格子：(位置, 现在放的是哪一行)，后记的盖掉先记的
    moved: list[tuple[np.ndarray, np.ndarray]] = []

    def at(position: np.ndarray) -> np.ndarray:
        value = position.copy()
        for where, row in moved:
            value = np.where(position == where, row, value)
        return value

    order = []
    for index in range(ORDER):
        offset = np.zeros(count, dtype=np.int64)
        done = np.zeros(count, dtype=bool)
        for number, output in enumerate(outputs):
            hit = ~done & (cursor <= number) & (output <= SIZE - 1 - index)
            offset = np.where(hit, output, offset)
            cursor = np.where(hit, number + 1, cursor)
            done |= hit
        valid &= done
        here = np.full(count, index, dtype=np.int64)
        other = here + offset
        here_row, other_row = at(here), at(other)
        moved.append((here, other_row))
        moved.append((other, here_row))
        order.append(other_row)

    chosen = np.full(count, -1, dtype=np.int64)
    for row in order:
        usable = ~FLAGGED[row]
        for previous in used:
            usable &= CANON[row] != previous
        take = (chosen < 0) & usable
        chosen[take] = row[take]
    valid &= chosen >= 0
    return np.maximum(chosen, 0), valid


def _rotl(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & 0xFFFFFFFFFFFFFFFF


def _second(seed: int) -> tuple[int, int]:
    """Xoroshiro 走一步之后的两个状态，第 2 个随机数是它们的和的低 32 位，第 1 只租借用它当 MT 种子。"""
    mixed = seed ^ 0x82A2B175229D6A5B
    state0 = _rotl(seed, 24) ^ mixed ^ ((mixed << 16) & 0xFFFFFFFFFFFFFFFF)
    return state0, _rotl(mixed, 37)


def _construct_plan() -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """造 seed 的步骤。两个状态的每一位都是 seed 某些位的异或（再异或一个常数），
    从低位到高位凑它们的和：每一位先把新碰到的 seed 位随机定下来，留一个只在一边出现的位来凑。

    返回 (状态 0 的常数, 状态 1 的常数, 每一位的 (状态 0 用到的 seed 位, 状态 1 用到的, 随机定的, 用来凑的))；
    没有位可以用来凑时最后一项是 0，那一位只能碰运气。
    """
    constant0, constant1 = _second(0)
    masks0, masks1 = [0] * 32, [0] * 32
    for bit in range(64):
        state0, state1 = _second(1 << bit)
        for index in range(32):
            masks0[index] |= ((state0 ^ constant0) >> index & 1) << bit
            masks1[index] |= ((state1 ^ constant1) >> index & 1) << bit
    assigned = 0
    steps = []
    for mask0, mask1 in zip(masks0, masks1, strict=True):
        fresh = (mask0 | mask1) & ~assigned
        single = (mask0 ^ mask1) & ~assigned
        pivot = single & -single
        steps.append((mask0, mask1, fresh & ~pivot, pivot))
        assigned |= fresh
    return constant0, constant1, steps


CONSTANT0, CONSTANT1, CONSTRUCT_STEPS = _construct_plan()


def _parity(value: np.ndarray) -> np.ndarray:
    value = value.copy()
    for shift in (32, 16, 8, 4, 2, 1):
        value ^= value >> U(shift)
    return value & U(1)


def _construct(target: int, count: int) -> np.ndarray:
    """造 seed：第 2 个随机数等于 target。试 count 个，返回凑成功的，约 1/32。"""
    random = np.random.default_rng()
    seed = np.zeros(count, dtype=U)
    carry = np.zeros(count, dtype=U)
    valid = np.ones(count, dtype=bool)
    for index, (mask0, mask1, fresh, pivot) in enumerate(CONSTRUCT_STEPS):
        seed |= random.integers(0, 2**64, size=count, dtype=U) & U(fresh)
        for attempt in range(2):
            bit0 = _parity(seed & U(mask0)) ^ U(CONSTANT0 >> index & 1)
            bit1 = _parity(seed & U(mask1)) ^ U(CONSTANT1 >> index & 1)
            wrong = (bit0 ^ bit1 ^ carry) != U(target >> index & 1)
            if attempt or not pivot:
                break
            seed = np.where(wrong, seed | U(pivot), seed)
        valid &= ~wrong
        carry = (bit0 & bit1) | (bit0 & carry) | (bit1 & carry)
    return seed[valid]


def scan(seeds: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """一批 seed 的总分：(能算的 seed, 总分)。顺序和 Lair._picks 一样，打分和 Planner.best 一样。"""
    rng = _Rng(seeds)
    rng.draw(FIRST_DRAW_TOP)
    valid = np.ones(len(seeds), dtype=bool)
    used: list[np.ndarray] = []

    def pick() -> np.ndarray:
        nonlocal valid
        row, usable = _pick(rng.next(), used)
        used.append(CANON[row])
        valid &= usable & (NUMBER[row] >= 0)
        return row

    pool = [pick() for _ in range(4)]
    draws = []
    for index in range(3):
        draws.append(rng.draw(2))
        if index < 2:
            pool.append(pick())
    kind = rng.draw(2)
    layout = rng.draw(9)
    layers = []
    for size in (2, 4, 4):
        layer = []
        for _ in range(size):
            row = pick()
            layer.append(row)
            rng.next(EXTRA_NEXT[row])
        layers.append(layer)

    seeds, kind, layout = seeds[valid], kind[valid], layout[valid]
    pool = [NUMBER[row[valid]] for row in pool]
    draws = [draw[valid] for draw in draws]
    layers = [[NUMBER[row[valid]] for row in layer] for layer in layers]

    totals = np.zeros(len(seeds))
    for value, map_type in MAP_TYPES.items():
        here = kind == value
        if not here.any():
            continue
        totals[here] = _best_total(
            [number[here] for number in pool],
            [draw[here] for draw in draws],
            [[number[here] for number in layer] for layer in layers],
            PATHS[map_type],
            [count[layout[here]] for count in SCIENTISTS[map_type]],
        )
    return seeds, totals


def _teammates(pool: list[np.ndarray], draws: list[np.ndarray], starter: int) -> list[np.ndarray]:
    """自己选了第 starter 只之后三个队友拿到的，和 Lair.teammates 一样。"""
    slots = [pool[0], pool[1], pool[2]]
    slots[starter] = pool[3]
    result = []
    for index, draw in enumerate(draws):
        result.append(np.choose(draw, slots))
        if index < 2:
            slots = [np.where(draw == slot, pool[4 + index], slots[slot]) for slot in range(3)]
    return result


def _boss(
    first: np.ndarray,
    average: np.ndarray,
    attack: np.ndarray,
    received: list[np.ndarray],
) -> np.ndarray:
    """一批 seed 的首领分，和 Planner.boss 一样。

    first、average 是自己第 1 回合的进攻、前 boss_turns 个回合平均的进攻；attack 是三个队友的进攻合计；
    received 是首领战的四只（自己和三个队友）各自的挨打。
    """
    total = first + attack
    speed = np.clip(CONFIG.boss_turn_rate * (average + attack), 1 / CONFIG.boss_max_turns, 1.0)
    # 预计倒下几只，和 plan.faint_chance 一样。整数次方用连乘，比 ** 快
    half = CONFIG.boss_faint_half**CONFIG.boss_faint_power
    turns = 1 / speed
    faints = np.zeros(len(speed))
    for value in received:
        damage = value * turns
        power = damage
        for _ in range(CONFIG.boss_faint_power - 1):
            power = power * damage
        faints += power / (power + half)
    hurt = 1 + faints / CONFIG.boss_hurt_scale
    power = hurt
    for _ in range(CONFIG.boss_hurt_exponent - 1):
        power = power * hurt
    return np.where(
        total >= CONFIG.boss_kill_attack,
        np.minimum(1.0, CONFIG.boss_turn_rate * total),
        speed / power,
    )


def _best_total(
    pool: list[np.ndarray],
    draws: list[np.ndarray],
    layers: list[list[np.ndarray]],
    routes: list[tuple[int, ...]],
    scientists: list[np.ndarray],
) -> np.ndarray:
    """同一种地图的一批 seed，各自选出来的方案的总分。

    每种首发加路线在 8 种换法里取总分最高的（plan.decide），再在所有首发和路线里取最高的（Planner.best）。
    """
    best = np.full(len(pool[0]), -np.inf)
    for starter in range(3):
        team = _teammates(pool, draws, starter)
        for route, count in zip(routes, scientists, strict=True):
            opponents = [layer[col] for layer, col in zip(layers, route, strict=True)]
            total = _plan_total(pool[starter], team, opponents)
            # 路线上有研究员的：每个研究员换掉一个队友，所有情况的总分取平均（Planner.best）
            for number in range(1, int(count.max()) + 1):
                here = count == number
                if not here.any():
                    continue
                cases = []
                for replaced in itertools.product(range(3), repeat=number):
                    members = [member[here] for member in team]
                    for member in replaced:
                        members[member] = np.full(int(here.sum()), UNKNOWN)
                    cases.append(
                        _plan_total(pool[starter][here], members, [o[here] for o in opponents])
                    )
                total[here] = sum(cases) / len(cases)
            best = np.maximum(best, total)
    return best


def _plan_total(
    starter: np.ndarray, team: list[np.ndarray], opponents: list[np.ndarray]
) -> np.ndarray:
    """一种首发加一条路线、三个队友是 team 时的总分：8 种换法里取最高的（plan.decide）。"""
    weights = CONFIG.stage_weights
    stage_weight = sum(weights)
    share = (1 - CONFIG.no_swap_probability) / 3
    zero = np.zeros(len(starter), dtype=np.int64)
    best = np.full(len(zero), -np.inf)
    others = [sum(AVERAGE[member, opponent] for member in team) for opponent in opponents]
    # 前面几关换不换一样的，这一关上场的和轮到极巨化的回合也一样，只算一次。
    # 键是前面几关的换法，值是 (这一关上场的, 到这一关为止的对数加权和, 打完之后还要过几个回合)
    states = {(): (starter, np.zeros(len(zero)), zero)}
    for index, weight in enumerate(weights):
        following = {}
        for swaps, (fielded, log, wait) in states.items():
            value, wait = _stage(fielded, opponents[index], wait, others[index])
            for swap in (False, True):
                following[(*swaps, swap)] = (
                    opponents[index] if swap else fielded,
                    log + weight * value,
                    wait,
                )
        states = following
    # 三个队友的进攻合计、各自的挨打。键是三只抓到的各被谁换上（None 是没人换），不同换法里重复的只算一次
    sums: dict[tuple[int | None, ...], tuple[np.ndarray, list[np.ndarray]]] = {}
    for swaps, (fielded, log, wait) in states.items():
        options = [
            [(None, 1.0)]
            if swap
            else [(None, CONFIG.no_swap_probability), (0, share), (1, share), (2, share)]
            for swap in swaps
        ]
        first, average = BOSS_FIRST[wait, fielded], BOSS_AVERAGE[wait, fielded]
        own_received = BOSS_RECEIVED[fielded] * OWN_HURT[wait]
        boss = np.zeros(len(zero))
        for case in itertools.product(*options):
            takers = tuple(taker for taker, _ in case)
            if takers not in sums:
                members = list(team)
                for opponent, taker in zip(opponents, takers, strict=True):
                    if taker is not None:
                        members[taker] = opponent
                sums[takers] = (
                    sum(BOSS_ATTACK[member] for member in members),
                    [BOSS_RECEIVED[member] for member in members],
                )
            probability = 1.0
            for _, chance in case:
                probability *= chance
            attack, received = sums[takers]
            boss += probability * _boss(first, average, attack, [own_received, *received])
        best = np.maximum(best, np.exp(log) * boss ** (1 - stage_weight))
    return best


def _scan_batch(floor: float) -> tuple[int, list[tuple[float, float, int]]]:
    """试一批 seed，返回 (试了多少个, 精确算的总分高过 floor 的 [(精确的总分, 粗筛估的总分, seed)])。

    没指定 --first 就随机取；指定了就拿一个 MT 种子造一批第 1 只租借是指定宝可梦的。
    粗筛估的分到了 floor 的 SCREEN 倍的才精确算，一批最多精确算估分最高的 EXACT_PER_BATCH 个：
    精确算一个要零点几秒，榜还没满（floor 是 0）的时候不能把整批都精确算一遍。
    """
    random = np.random.default_rng()
    if len(TARGETS):
        seeds = _construct(int(random.choice(TARGETS)), BATCH * 32)
    else:
        seeds = random.integers(0, 2**64, size=BATCH, dtype=np.uint64)
    found, totals = scan(seeds)
    order = np.argsort(-totals)[:EXACT_PER_BATCH]
    result = []
    for index in order:
        if totals[index] <= SCREEN * floor:
            break
        total = evaluate(int(found[index]))[1].total
        if total > floor:
            result.append((total, float(totals[index]), int(found[index])))
    return len(seeds), result


def evaluate(seed: int) -> tuple[Lair, Plan]:
    """用程序的算法完整算一个 seed：队友一路上的变化从 seed 直接算（Lair.fate），和程序开局规划一样。"""
    lair = Lair(DATA, seed)
    events = DATA.lair_events(lair.map_type(), lair.layout())
    plan = Planner(DATA, CONFIG, BOSS).best(
        lair.candidates()[:3],
        lair.encounters(),
        lair.map_type(),
        lair.teammates,
        events=events,
        fate=functools.cache(lambda path, swaps: fate(lair, path, events, BOSS, swaps)),
    )
    return lair, plan


def _describe(seed: int, total: float) -> str:
    def name(name_id: str) -> str:
        return DATA.pokemon_object(name_id).name(CONFIG.language)

    lair, plan = evaluate(seed)
    candidates = lair.candidates()
    swaps = "、".join("换" if swap else "不换" for swap in plan.swaps)
    mates = "、".join(name(n) for n in plan.teammates)
    route = " → ".join(name(n) for n in plan.opponents)
    lines = [
        f"seed {seed}",
        f"  总分 {plan.total:.3f}（三关 {plan.stage:.3f}，首领 {plan.boss:.3f}）",
        f"  首发 {name(candidates[plan.starter])}（第 {plan.starter + 1} 位），队友 {mates}",
        f"  租借六只：{'、'.join(name(n) for n in candidates)}",
        f"  地图 {lair.map_type()}，路线 {route}，三关抓到后：{swaps}",
    ]
    for row, encounters in lair.encounters().items():
        lines.append(f"  第 {row} 层：{'、'.join(name(n) for n in encounters)}")
    lines.append(f"  批量筛的时候估的总分 {total:.3f}（队友的变化按期望算的）")
    return "\n".join(lines)


def main(
    boss: str,
    first: tuple[str, ...],
    workers: int,
    top: int,
    minutes: float | None,
    start_floor: float,
) -> None:
    _setup(boss)
    print(f"首领 {BOSS}，开头抽数的上限 {FIRST_DRAW_TOP}，留总分最高的 {top} 个", flush=True)
    if first:
        print(f"只试租借第 1 只是 {'、'.join(first)} 的 seed", flush=True)
    best: list[tuple[float, int]] = []
    # 进过榜的 seed 批量筛时估的分
    estimates: dict[int, float] = {}
    tried = 0
    started = reported = time.time()
    with multiprocessing.Pool(workers, _setup, (boss, first)) as pool:
        pending: list = []
        try:
            while minutes is None or time.time() - started < minutes * 60:
                # 榜满了之后，精确算的分要高过榜尾才进榜；榜没满时用 --floor 给的起点
                floor = best[-1][0] if len(best) == top else start_floor
                while len(pending) < workers:
                    pending.append(pool.apply_async(_scan_batch, (floor,)))
                time.sleep(0.05)
                for task in [task for task in pending if task.ready()]:
                    pending.remove(task)
                    size, found = task.get()
                    tried += size
                    for total, estimate, seed in found:
                        estimates[seed] = estimate
                        if len(best) == top and total <= best[-1][0]:
                            continue
                        best = sorted([*best, (total, seed)], reverse=True)[:top]
                        rank = best.index((total, seed)) + 1
                        spent = (time.time() - started) / 60
                        print(
                            f"\n试了 {tried / 1e6:.1f} 百万个，{spent:.1f} 分钟，新进第 {rank} 名：",
                            flush=True,
                        )
                        print(_describe(seed, estimate), flush=True)
                if time.time() - reported > 60:
                    reported = time.time()
                    highest = f"{best[0][0]:.3f}" if best else "还没有"
                    print(f"试了 {tried / 1e6:.0f} 百万个，目前最高分 {highest}", flush=True)
        except KeyboardInterrupt:
            pass
        pool.terminate()
    print(f"\n停止。一共试了 {tried / 1e6:.1f} 百万个，总分最高的 {len(best)} 个：")
    for rank, (total, seed) in enumerate(best, 1):
        print(f"\n第 {rank} 名")
        print(_describe(seed, estimates[seed]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="找极巨大冒险里总分最高的 seed")
    parser.add_argument("--boss", default=CONFIG.boss, help="首领的 name_id，默认用配置里的")
    parser.add_argument(
        "--first",
        default="",
        help="租借第 1 只指定成这几只里的一只，name_id 用逗号隔开；不给就随机试",
    )
    parser.add_argument("--workers", type=int, default=4, help="同时用几个进程算，默认 4")
    parser.add_argument("--top", type=int, default=10, help="留总分最高的几个，默认 10")
    parser.add_argument("--minutes", type=float, default=None, help="跑多少分钟，不给就一直跑")
    parser.add_argument(
        "--floor",
        type=float,
        default=0.0,
        help="已经有的最好的总分，比它低的不进榜，省得从头攒；默认 0",
    )
    arguments = parser.parse_args()
    main(
        arguments.boss,
        tuple(name for name in arguments.first.split(",") if name),
        arguments.workers,
        arguments.top,
        arguments.minutes,
        arguments.floor,
    )
