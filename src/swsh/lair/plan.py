"""按这张图实际要打的对手，给首发和路线打分。

一局按关卡推：每一关上场的那只打这一关的对手，抓到之后自己换或者不换，最后上场的那只打首领。
换不换按总分定：三关换不换的每种组合都算一遍总分，取最高的。自己换了，这只就轮不到队友；
自己不换，这只会被队友换上，首领战的队伍就变了。

- 总分 = 三关的分和首领分的加权几何平均：第 1、2、3 关的权重是 stage_weights，首领是 1 减三关合计。
  每一项最高是 1：三关都一回合打完、首领一回合打死的图是 1 分。
- 每一关的分 = 1 ÷ 预测这一关打几个回合（见 fight），按自己这个回合的伤害分三档：
  不低于 stage_sure_damage 的算这个回合打完；不低于 stage_likely_damage 的算一回合半；
  再低的按每回合对手掉多少血推（自己的伤害加三个队友的），推出来的回合数再加半个回合，
  推出来第 1 个回合就掉完的算 stage_weak_turns 个回合。
  伤害超过 stage_sure_damage 的部分不加分。
- 每个回合的伤害看这个回合自己有没有极巨化：极巨化了用极巨招式的伤害，没有就用普通招式的。
  一局的第 1 个回合轮到自己极巨化，持续 dynamax_turns 个回合，结束后再过 dynamax_wait 个回合又轮到自己；
  前面几关打了几个回合决定后面哪个回合轮到自己。队友按开局的三只算，队友不会极巨化。
- 首领分是全队四只一起算的（见 Planner.boss）。四只的进攻合计 = 自己首领战第 1 回合的进攻 + 三个队友普通招式的进攻：
  不低于 boss_kill_attack 算能一回合打死，首领分 = boss_turn_rate × 进攻合计（最高 1），不看挨打；
  达不到就先预测打几个回合 = 1 ÷（boss_turn_rate × 进攻合计），这里自己的进攻取前 boss_turns 个回合的平均，
  首领分 = 1 ÷ 回合数 ÷（1 + 预计倒下几只 ÷ boss_hurt_scale）** boss_hurt_exponent。
- 预计倒下几只 = 四只各自倒下的机会相加（见 faint_chance）。一只的机会看「回合数 × 它的挨打」，
  也就是这几个回合首领一直打它的话能打掉它几管血：到 boss_faint_half 管时算一半的机会，
  低于它的很快降到 0，高于它的很快升到 1（boss_faint_power 次方）。挨打低的几乎不算进去，
  容易倒的每一只都差不多算一只。所以同样的挨打合计，集中在一只身上比摊在两只身上分高。
  自己极巨化的回合血量是 dynamax_hp 倍，这几个回合的挨打要除以它（见 own_hurt）。
- 自己不换时，新抓到的那只有 no_swap_probability 的概率没人换，其余平均分给三个队友顶掉原来的；
  首领分按这些情况取期望。

伤害来自 rental_damage_LUT.json（租借宝可梦两两之间），对首领的进攻和挨打来自
boss_attack_defense_LUT.json，都用 src/make_lair_damage.py 生成。数值都是一回合打掉对方血量的比例。
"""

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from .game_config import GameConfig
from .game_data import GameData
from .lair import Lair
from .next_columns import next_columns

# 路线上的三个节点：[(1, 列), (2, 列), (3, 列)]
Path = tuple[tuple[int, int], ...]
# 宝可梦：开局规划时是 name_id，抓到时是带着血量的 Pokemon 对象
Member = TypeVar("Member")


@dataclass(frozen=True)
class Plan:
    """一种首发加一条路线的打分结果。"""

    # 首发在选宝可梦界面三只里的下标
    starter: int
    path: Path
    # 路线上三关的对手
    opponents: tuple[str, ...]
    # 三个队友一开始拿的宝可梦
    teammates: tuple[str, ...]
    total: float
    # 三关的分（三关各自的分按 stage_weights 做的加权几何平均）和首领分
    stage: float
    boss: float
    # 每一关抓到之后自己换不换
    swaps: tuple[bool, ...]


# 研究员换给队友的那只：是哪只事先不知道，各项数值按全部租借宝可梦的平均算
AVERAGE = "average"


@dataclass(frozen=True)
class Fate(Generic[Member]):
    """队友一路上会怎么变。seed 定死，但要看自己每一只抓到后换没换（Lair.fate），换法不同结果不同。"""

    # 接下来每一只抓到的：哪个队友换上它（0、1、2），自己换了或者没人换是 None
    takers: tuple[int | None, ...]
    # 研究员换掉的队友：(在第几只抓到之后，-1 是第一只之前, 哪个队友, 换成的宝可梦)
    changes: tuple[tuple[int, int, Member], ...]


def fate(
    lair: Lair, path: Path, events: dict[str, list[str]], boss: str, swaps: Sequence[bool]
) -> Fate[str]:
    """这条路线上、三关抓到后自己按 swaps 换不换时，队友会怎么变：按路线上已经知道的事件排出先后，
    交给 Lair.fate 算。

    不知道有没有事件的位置按没有算；那里其实有研究员或者背包客的话，它后面的就会算错。
    """
    places = positions(path)
    schedule: list[str] = []
    for index, place in enumerate(places):
        # 位置是「节点、路」交替的：走完一段路到下一个节点，打完抓一只，所以每个节点（起点除外）前面是一次抓
        if index and index % 2 == 0:
            schedule.append("catch")
        schedule += [event for event in events.get(place, []) if event != "berry"]
    takers: list[int | None] = []
    changes: list[tuple[int, int, str]] = []
    for event, result in zip(schedule, lair.fate(schedule, boss, swaps), strict=True):
        if event == "catch":
            takers.append(result if isinstance(result, int) else None)
        elif isinstance(result, tuple):
            changes.append((len(takers) - 1, *result))
    return Fate(tuple(takers), tuple(changes))


def positions(path: Path) -> list[str]:
    """这条路线依次经过的位置，写法和 GameData.lair_events 一样：节点和节点之间的路交替，从起点到首领。"""
    nodes = [(0, 0), *path, (4, 0)]
    result = []
    for (row, col), (next_row, next_col) in itertools.pairwise(nodes):
        result += [f"{row}-{col}", f"{row}-{col}>{next_row}-{next_col}"]
    return result


def paths(map_type: str) -> list[Path]:
    """这种地图上所有的路线，从起点走到第 3 层。"""
    result: list[list[tuple[int, int]]] = [[(0, 0)]]
    for row in (1, 2, 3):
        result = [
            [*path, (row, col)] for path in result for col in next_columns(map_type, *path[-1])
        ]
    return [tuple(path[1:]) for path in result]


def rotate(left: int, wait: int, config: GameConfig) -> tuple[bool, int, int]:
    """极巨化的轮换往前走一个回合，返回 (这个回合自己是不是极巨化的, left, wait)。

    left 是极巨化还剩几个回合，wait 是还要过几个回合才轮到自己极巨化。
    """
    if left > 0:
        return True, left - 1, wait
    if wait == 0:
        return True, config.dynamax_turns - 1, config.dynamax_wait
    return False, left, wait - 1


def own_hurt(wait: int, config: GameConfig) -> float:
    """首领战里自己的挨打要乘的倍数：极巨化的回合血量是 dynamax_hp 倍，挨打就是 1 ÷ dynamax_hp。

    wait 是开打时还要过几个回合才轮到自己极巨化，按前 boss_turns 个回合里极巨化的回合占多少算。
    """
    left = 0
    dynamaxed = 0
    for _ in range(config.boss_turns):
        dynamax, left, wait = rotate(left, wait, config)
        dynamaxed += dynamax
    share = dynamaxed / config.boss_turns
    return 1 - share + share / config.dynamax_hp


def fight(
    damages: Sequence[float], wait: int, config: GameConfig, team: float = 0.0
) -> tuple[float, int, int]:
    """自己打前三关的一场，返回 (预测打几个回合, 推轮换用的整数回合数, 打完之后还要过几个回合才轮到自己极巨化)。

    damages 开头两项是 [普通招式的伤害, 极巨招式的伤害]，wait 是开打时还要过几个回合才轮到自己极巨化，
    team 是三个队友普通招式的平均伤害合计。逐回合看自己这个回合的伤害：
    - 不低于 stage_sure_damage：这个回合打完。
    - 不低于 stage_likely_damage：算一回合半。按下面的式子这个回合对手的血掉完了，轮换就按这个回合打完，
      没掉完按再打一个回合。
    - 再低：这个回合对手掉 stage_own_rate × 自己的伤害 + stage_team_rate × team + stage_base_rate，
      掉完为止，最多 stage_max_turns 个回合。预测的回合数是掉完之前的整回合数、最后一个回合用掉的比例、
      再加半个回合（不加的话比日志里的实际回合数平均少半个回合）。第 1 个回合就掉完的比上一档差：
      算 stage_weak_turns 个回合，轮换按 2 个回合。
    极巨化到这一场打完就结束，没用完的回合不留到下一场。
    """
    normal, dynamaxed = damages[0], damages[1]
    left = 0
    health = 1.0
    count = 0
    while True:
        dynamax, left, wait = rotate(left, wait, config)
        value = dynamaxed if dynamax else normal
        count += 1
        if value >= config.stage_sure_damage:
            return float(count), count, wait
        hit = config.stage_own_rate * value + config.stage_team_rate * team + config.stage_base_rate
        down = hit >= health
        if value >= config.stage_likely_damage:
            turns = count + 0.5
            more = not down
        elif not down and count < config.stage_max_turns:
            health -= hit
            continue
        elif count == 1:
            turns = config.stage_weak_turns
            more = True
        else:
            turns = count - 1 + (health / hit if down else 1.0) + 0.5
            more = False
        if more:
            _, left, wait = rotate(left, wait, config)
            count += 1
        return turns, count, wait


def faint_chance(damage: float, config: GameConfig) -> float:
    """首领战里一只倒下的机会。damage 是回合数 × 这只的挨打：这几个回合首领一直打它的话能打掉它几管血。

    机会 = damage ** n ÷（damage ** n + boss_faint_half ** n），n 是 boss_faint_power：
    damage 等于 boss_faint_half 时是一半，是它的一半时只有 6%，是它的两倍时有 94%（n 是 4 的时候）。
    """
    power = damage**config.boss_faint_power
    return power / (power + config.boss_faint_half**config.boss_faint_power)


def combine(stage: float, boss: float, config: GameConfig) -> float:
    """总分：三关的分 stage 和首领分 boss 的加权几何平均，首领的权重是 1 减三关合计。"""
    weight = sum(config.stage_weights)
    return stage**weight * boss ** (1 - weight)


def decide(
    own: Member,
    teammates: Sequence[Member],
    catches: Sequence[Member],
    stage_score: Callable[[Sequence[Member]], tuple[float, int]],
    boss_score: Callable[[Member, int, Sequence[Member]], float],
    config: GameConfig,
    first: bool | None = None,
    fate: Callable[[tuple[bool, ...]], Fate[Member]] | None = None,
) -> tuple[float, float, float, tuple[bool, ...]]:
    """从现在起每一只抓到的自己换不换，选总分最高的换法。

    fate(换法) 给出这种换法下队友接下来会怎么变（seed 定死的）：给了就照它算，首领战的三个队友是确定的；
    不给就按「自己不换的那只 no_swap_probability 的概率没人换，其余平均分给三个队友」取期望。

    own 是自己现在这只，teammates 是三个队友现在的，catches 是接下来依次抓到的。
    stage_score(after) 给出 (三关的分, 首领战开打时还要过几个回合才轮到自己极巨化)，
    after[i] 是抓到第 i 只、换完之后自己手里的那只；boss_score(自己打首领的那只, 等待的回合数, 三个队友)
    给出首领分。first 指定第一只换不换，不指定就都试。
    返回 (总分, 三关的分, 首领分, 每一只换不换)；总分相同时取换得少的。
    """
    share = (1 - config.no_swap_probability) / 3
    best: tuple[float, float, float, tuple[bool, ...]] | None = None
    for swaps in itertools.product((False, True), repeat=len(catches)):
        if first is not None and swaps[0] != first:
            continue
        after = []
        current = own
        for swap, caught in zip(swaps, catches, strict=True):
            current = caught if swap else current
            after.append(current)
        stage, wait = stage_score(after)

        if fate is not None:
            ahead = fate(swaps)
            members = list(teammates)
            for index in range(-1, len(catches)):
                if index >= 0 and not swaps[index] and ahead.takers[index] is not None:
                    members[ahead.takers[index]] = catches[index]
                for after_catch, member, pokemon in ahead.changes:
                    if after_catch == index:
                        members[member] = pokemon
            boss = boss_score(current, wait, members)
            total = combine(stage, boss, config)
            if best is None or total > best[0]:
                best = (total, stage, boss, swaps)
            continue

        # 自己没换的那只：没人换，或者三个队友之一换上它
        options = [
            [(None, 1.0)]
            if swap
            else [(None, config.no_swap_probability), (0, share), (1, share), (2, share)]
            for swap in swaps
        ]
        boss = 0.0
        for case in itertools.product(*options):
            probability = 1.0
            members = list(teammates)
            for caught, (taker, chance) in zip(catches, case, strict=True):
                probability *= chance
                if taker is not None:
                    members[taker] = caught
            boss += probability * boss_score(current, wait, members)
        total = combine(stage, boss, config)
        if best is None or total > best[0]:
            best = (total, stage, boss, swaps)
    assert best is not None
    return best


class Planner:
    """给首发和路线打分。"""

    def __init__(self, data: GameData, config: GameConfig, boss: str):
        damage = data.rental_damages()
        # {租借宝可梦: [普通进攻, 极巨进攻, 挨打]}
        against = {name: bosses[boss] for name, bosses in data.boss_attack_defense().items()}
        # 再加一只 AVERAGE：每一项都是全部租借宝可梦的平均
        count = len(damage)
        self._damage = {
            **damage,
            AVERAGE: {
                defender: [
                    sum(row[defender][index] for row in damage.values()) / count
                    for index in range(3)
                ]
                for defender in damage
            },
        }
        self._boss = {
            **against,
            AVERAGE: [
                sum(row[index] for row in against.values()) / len(against) for index in range(3)
            ],
        }
        self._config = config

    def stages(
        self, fielded: Sequence[str], opponents: Sequence[str], teammates: Sequence[str]
    ) -> tuple[float, int]:
        """三关的分：每一关的分是 1 ÷ 预测的回合数，按 stage_weights 做加权几何平均。

        fielded 是三关各是哪只上场，opponents 是三关的对手，teammates 是三个队友（预测回合数用）。
        返回 (三关的分, 首领战开打时还要过几个回合才轮到自己极巨化)。
        """
        config = self._config
        wait = 0
        total = 0.0
        for weight, pokemon, opponent in zip(config.stage_weights, fielded, opponents, strict=True):
            team = sum(self._damage[member][opponent][2] for member in teammates)
            turns, _, wait = fight(self._damage[pokemon][opponent], wait, config, team)
            total -= weight * math.log(turns)
        return math.exp(total / sum(config.stage_weights)), wait

    def boss_attack(self, name: str, wait: int) -> tuple[float, float]:
        """name 这只打首领时自己的进攻：(第 1 回合的, 前 boss_turns 个回合平均的)。

        wait 是首领战开打时还要过几个回合才轮到自己极巨化，轮到的回合用极巨招式的进攻。
        """
        normal, dynamaxed = self._boss[name][:2]
        left = 0
        values = []
        for _ in range(self._config.boss_turns):
            dynamax, left, wait = rotate(left, wait, self._config)
            values.append(dynamaxed if dynamax else normal)
        return values[0], sum(values) / len(values)

    def boss(self, own: str, wait: int, teammates: Sequence[str]) -> float:
        """首领分：own 是自己打首领的那只，wait 是开打时还要过几个回合才轮到自己极巨化，teammates 是三个队友。

        四只的进攻合计（自己第 1 回合的 + 队友普通招式的）不低于 boss_kill_attack 算能一回合打死，
        只看进攻合计；否则预测打几个回合，再算这几个回合里四只预计倒下几只（faint_chance），倒得越多分越低。
        """
        config = self._config
        first, average = self.boss_attack(own, wait)
        attack = sum(self._boss[member][0] for member in teammates)
        if first + attack >= config.boss_kill_attack:
            return min(1.0, config.boss_turn_rate * (first + attack))
        # 1 ÷ 回合数，回合数最少 1 个、最多 boss_max_turns 个
        speed = min(max(config.boss_turn_rate * (average + attack), 1 / config.boss_max_turns), 1.0)
        faints = faint_chance(self._boss[own][2] * own_hurt(wait, config) / speed, config) + sum(
            faint_chance(self._boss[member][2] / speed, config) for member in teammates
        )
        hurt = 1 + faints / config.boss_hurt_scale
        return speed / hurt**config.boss_hurt_exponent

    def score(
        self,
        starter: str,
        teammates: Sequence[str],
        opponents: Sequence[str],
        fate: Callable[[tuple[bool, ...]], Fate[str]] | None = None,
    ) -> tuple[float, float, float, tuple[bool, ...]]:
        """返回 (总分, 三关的分, 首领分, 每一关抓到之后自己换不换)。fate 见 decide。"""
        return decide(
            starter,
            teammates,
            opponents,
            lambda after: self.stages([starter, *after[:-1]], opponents, teammates),
            self.boss,
            self._config,
            fate=fate,
        )

    def best(
        self,
        candidates: Sequence[str],
        encounters: dict[str, list[str]],
        map_type: str,
        teammates: Callable[[int], list[str]],
        starters: Sequence[int] = (0, 1, 2),
        events: dict[str, list[str]] | None = None,
        fate: Callable[[Path, tuple[bool, ...]], Fate[str]] | None = None,
    ) -> Plan:
        """在 starters 这几种首发和这张图所有路线里，选总分最高的。

        candidates 是选宝可梦界面的三只，encounters 是每层的遭遇，teammates(首发下标) 给出三个队友。
        events 是这张图路上已经知道的事件（GameData.lair_events）。路线上每有一个研究员，
        就有一个队友手上的被换成事先不知道的一只（日志里 68 次遇到研究员，平均每次正好换掉 1 只）：
        是哪个队友按三个机会一样算，换上来的按 AVERAGE 算，各种情况的分取平均。
        不知道有没有研究员的位置按没有算。

        fate(路线, 换法) 给出这条路线上、三关按这种换法时队友会怎么变（见上面的 fate 函数）：给了就照它算，
        研究员换掉谁、换成什么也在里面，不再用 AVERAGE。
        """
        events = events or {}
        plans = []
        for starter in starters:
            team = teammates(starter)
            for path in paths(map_type):
                opponents = tuple(encounters[str(row)][col] for row, col in path)
                if fate is not None:
                    total, stage, boss, swaps = self.score(
                        candidates[starter],
                        team,
                        opponents,
                        lambda swaps, path=path: fate(path, swaps),
                    )
                    plans.append(
                        Plan(starter, path, opponents, tuple(team), total, stage, boss, swaps)
                    )
                    continue
                scientists = sum(
                    events.get(position, []).count("scientist") for position in positions(path)
                )
                # 每个研究员换掉哪个队友的所有情况；没有研究员就只有原来的三个队友这一种
                teams = []
                for replaced in itertools.product(range(3), repeat=scientists):
                    members = list(team)
                    for member in replaced:
                        members[member] = AVERAGE
                    teams.append(members)
                scores = [self.score(candidates[starter], members, opponents) for members in teams]
                total, stage, boss = (
                    sum(score[index] for score in scores) / len(scores) for index in range(3)
                )
                # 换不换是按原来的三个队友定的，只是写日志用；真打的时候每抓到一只再按当时的队伍算
                swaps = (
                    self.score(candidates[starter], team, opponents)[3]
                    if scientists
                    else scores[0][3]
                )
                plans.append(Plan(starter, path, opponents, tuple(team), total, stage, boss, swaps))
        return max(plans, key=lambda plan: plan.total)
