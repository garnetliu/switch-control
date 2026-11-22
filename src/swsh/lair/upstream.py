"""选首发、路线、抓到后换不换、研究员换不换：PokemonAutomation（AutoMaxLair 的后继）的选法，对手换成按 seed 算出的实际对手。

依据和测试见 docs/调研-其他项目的算法.md（打过多次的图：同一张图里都选中了实测更好的走法；不同图之间分数不能比）。

- 相性 m(X, B) = scoring 的招式分（打出 ÷ 受到），自己用最好的招式，max(普通, (普通 + 极巨) ÷ 2)；
  队友当作「平均队友」（和上游预先算表时一样）：打出 = 自己这一招 + 3 × 全部租借宝可梦按实测出招比例的平均伤害，
  受到 = ¼ 打自己 + ¾ 打全部租借的平均；对手用极巨招式的比例按实测（GameData.max_move_rate）。
- 首发：三只里 m(X, 首领) 最高的。
- 路线：Σ (1, 2, 3) × m(第 i 层对手, 首领)，取最高。首发和路线互不影响，分开选。
- 抓到后换不换：抓了换、抓了不换（按 seed 推出实际是哪个队友换上，或者没人换）比队伍分，
  队伍分 = m(自己, 首领) + 0.5 × 三个队友的 m(队友, 首领)；一样高时不换。
- 研究员：按 seed 算出它实际会给哪只（Walker.offer），自己换成那只后队伍分更高就换。
  （PokemonAutomation 不知道会给谁，用的是「对首领 m 排中间的那只租借」。）

随机数的用法见 Lair.fate；研究员那里自己换的话，三个队友各抽一个之后，紧接着那个数当洗牌种子，洗出来的给自己。
路上没记录过的位置按没有事件算，那里其实有研究员或背包客的话，后面推的会错。
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

from libs.xoroshiro import Xoroshiro
from swsh.field import Field
from swsh.scoring import (
    DYNAMAX_HP,
    average_damage,
    damage,
    select_best_move,
    teammate_damage,
    transform_ditto,
)

from .game_data import GameData
from .lair import Lair, _first
from .plan import Path, paths, positions


class Scorer:
    """一只首领的相性和分，算过的都缓存。"""

    def __init__(self, data: GameData, boss: str):
        self.data = data
        self.boss = boss
        self.rentals = list(data.rental_damages())
        self._matchups: dict[tuple[str, str, tuple[str, ...]], float] = {}
        self._averages: dict[tuple[str, str], float] = {}

    def matchup(self, attacker: str, defender: str, team: Sequence[str] = ()) -> float:
        """attacker 带着具体的队友 team 对 defender 的相性（选法不用，探索脚本在用）。"""
        key = (attacker, defender, tuple(team))
        if key not in self._matchups:
            a = self.data.pokemon_object(attacker)
            b = self.data.pokemon_object(defender)
            if a.name_id == "ditto":
                a = transform_ditto(a, b)
            elif b.name_id == "ditto":
                b = transform_ditto(b, a)
            mates = [self.data.pokemon_object(name) for name in team]
            rate = self.data.max_move_rate(defender)
            base = select_best_move(replace(a, dynamax=False), b, Field(), mates, rate)[2]
            dynamax = select_best_move(replace(a, dynamax=True), b, Field(), mates, rate)[2]
            self._matchups[key] = max(base, (base + dynamax) / 2)
        return self._matchups[key]

    def average_matchup(self, attacker: str, defender: str) -> float:
        """attacker 对 defender 的相性，队友当作全部租借宝可梦的平均。"""
        key = (attacker, defender)
        if key not in self._averages:
            field = Field()
            a = self.data.pokemon_object(attacker)
            b = self.data.pokemon_object(defender)
            if a.name_id == "ditto":
                a = transform_ditto(a, b)
            elif b.name_id == "ditto":
                b = transform_ditto(b, a)
            rentals = [self.data.pokemon_object(name) for name in self.rentals]
            mates = 3 * sum(teammate_damage(member, b, field) for member in rentals) / len(rentals)
            rate = self.data.max_move_rate(defender)
            regular = replace(b, dynamax=False)
            dynamaxed = replace(b, dynamax=True)
            count = min(4, len(dynamaxed.max_moves))
            to_mates = average_damage([regular], rentals, field)
            to_mates_max = average_damage([dynamaxed], rentals, field)
            scores = []
            for is_dynamax in (False, True):
                version = replace(a, dynamax=is_dynamax)
                shrink = DYNAMAX_HP if is_dynamax else 1
                to_self = (
                    sum(
                        damage(regular, index, version, field)
                        for index in range(len(regular.moves))
                    )
                    / len(regular.moves)
                    / shrink
                )
                to_self_max = (
                    sum(damage(dynamaxed, index, version, field) for index in range(count))
                    / count
                    / shrink
                )
                received = (0.25 * to_self + 0.75 * to_mates) * (1 - rate) + (
                    0.25 * to_self_max + 0.75 * to_mates_max
                ) * rate
                best = max(damage(version, index, b, field) for index in range(len(version.moves)))
                scores.append((best + mates) / received if received else 1.0)
            self._averages[key] = max(scores[0], (scores[0] + scores[1]) / 2)
        return self._averages[key]

    def starter_score(self, name: str) -> float:
        return self.average_matchup(name, self.boss)

    def route_score(self, opponents: Sequence[str]) -> float:
        return sum(
            weight * self.average_matchup(name, self.boss)
            for weight, name in zip((1, 2, 3), opponents, strict=True)
        )

    def team_score(self, team: Sequence[str]) -> float:
        """队伍对首领的分：自己的相性 + 0.5 × 三个队友的相性（PokemonAutomation：电脑队友打五折）。"""
        return sum(
            self.average_matchup(name, self.boss) * (1.0 if index == 0 else 0.5)
            for index, name in enumerate(team)
        )


def schedule_of(path: Path, events: dict[str, list[str]]) -> list[str]:
    """这条路线上按先后会遇到的事：catch、scientist、backpacker（树果不占随机数，不算）。"""
    schedule: list[str] = []
    for index, place in enumerate(positions(path)):
        if index and index % 2 == 0:
            schedule.append("catch")
        schedule += [event for event in events.get(place, []) if event != "berry"]
    return schedule


class Walker:
    """沿着路线一件一件推随机数和队伍：抓到一只、研究员、背包客。"""

    def __init__(
        self,
        lair: Lair,
        data: GameData,
        boss: str,
        path: Path,
        team: Sequence[str],
        events: dict[str, list[str]] | None = None,
    ):
        """events 是路上已经知道的事件（GameData.lair_events），不给就按 seed 算出的地图类型和布局取。"""
        self.data = data
        self.rows = data.lair_rows()
        encounters = lair.encounters()
        self.opponents = [encounters[str(row)][col] for row, col in path]
        if events is None:
            events = data.lair_events(lair.map_type(), lair.layout())
        self.schedule = schedule_of(path, events)
        self.rng = Xoroshiro(0)
        self.rng.s0, self.rng.s1 = lair._after
        species = data.boss_pokemon()[boss].id_num
        if any(row[2] and row[0] == species and row[4] != row[5] for row in self.rows):
            self.rng.next_u32()
        self.used = {(row[0], row[1]) for row in lair._picks()}
        self.team = list(team)
        self.index = 0
        self.caught = 0

    def copy(self) -> "Walker":
        other = object.__new__(Walker)
        other.__dict__.update(self.__dict__)
        other.rng = Xoroshiro(0)
        other.rng.s0, other.rng.s1 = self.rng.s0, self.rng.s1
        other.used = set(self.used)
        other.team = list(self.team)
        return other

    def next_event(self) -> str | None:
        return self.schedule[self.index] if self.index < len(self.schedule) else None

    def left(self) -> list[str]:
        """抓完现在这几只之后，后面还要打的对手。"""
        return self.opponents[self.caught :]

    def _wants(self) -> list[int]:
        return [member for member in range(3) if self.rng.next_u32() & 1 == 0]

    def _chosen(self, want: list[int]) -> int | None:
        while want:
            value = self.rng.draw(3)
            if value and value - 1 in want:
                return value - 1
        return None

    def catch(self, take: bool) -> None:
        """抓到下一只，自己 take 换不换。"""
        new = self.opponents[self.caught]
        self.caught += 1
        self.rng.draw(2)
        want = self._wants()
        if take:
            self.team[0] = new
        else:
            taker = self._chosen(want)
            if taker is not None:
                self.team[1 + taker] = new
        self.index += 1

    def offer(self) -> str:
        """现在遇到研究员的话，自己换会拿到哪只（不改动状态）。"""
        trial = self.copy()
        trial._wants()
        row = _first(self.rows, trial.rng.next_u32(), trial.used)
        return self.data.name_id(row[0], row[1])

    def scientist(self, take: bool) -> None:
        """研究员，自己 take 换不换。"""
        want = self._wants()
        if take:
            row = _first(self.rows, self.rng.next_u32(), self.used)
            self.used.add((row[0], row[1]))
            self.team[0] = self.data.name_id(row[0], row[1])
        else:
            member = self._chosen(want)
            if member is not None:
                row = _first(self.rows, self.rng.next_u32(), self.used)
                self.used.add((row[0], row[1]))
                self.team[1 + member] = self.data.name_id(row[0], row[1])
        self.index += 1

    def backpacker(self) -> None:
        for _ in range(3):
            self.rng.draw(4)
        self.index += 1

    def replay(self, choices: Sequence[bool]) -> None:
        """按已经做过的决定（抓到后换不换、研究员换不换，按先后）推到下一个要做决定的地方。"""
        remaining = list(choices)
        while (event := self.next_event()) is not None:
            if event == "backpacker":
                self.backpacker()
            elif not remaining:
                return
            elif event == "catch":
                self.catch(remaining.pop(0))
            else:
                self.scientist(remaining.pop(0))

    def side_events(self, decide: Callable[["Walker"], bool]) -> None:
        """推研究员、背包客，到下一次抓到或者走完为止；研究员换不换用 decide 定。"""
        while (event := self.next_event()) is not None and event != "catch":
            if event == "scientist":
                self.scientist(decide(self))
            else:
                self.backpacker()


def decide_scientist(scorer: Scorer, walker: Walker) -> bool:
    """研究员：按 seed 算出它实际会给的那只，自己换成它后队伍分更高就换。"""
    give = walker.offer()
    if give not in scorer.rentals:
        return False
    trial = list(walker.team)
    trial[0] = give
    return scorer.team_score(trial) > scorer.team_score(walker.team)


def decide_catch(scorer: Scorer, walker: Walker) -> tuple[bool, dict[str, float]]:
    """walker 停在抓到下一只的地方：返回 (换不换, {"换": 分, "不换": 分})。

    两种都按 seed 推出之后的实际队伍比队伍分，一样高时不换。
    不抓和抓了不换完全一样（2026-11-22 实测三局：自己不抓，队友照样拿走），所以不算这一种。
    """
    take = walker.copy()
    take.catch(True)
    leave = walker.copy()
    leave.catch(False)
    scores = {"换": scorer.team_score(take.team), "不换": scorer.team_score(leave.team)}
    return scores["换"] > scores["不换"], scores


def best_path(
    scorer: Scorer, encounters: dict[str, list[str]], map_type: str
) -> tuple[Path, float]:
    """路线分最高的路线和它的分。"""
    scored = [
        (scorer.route_score([encounters[str(row)][col] for row, col in path]), path)
        for path in paths(map_type)
    ]
    score, path = max(scored, key=lambda item: item[0])
    return path, score


def plan_swaps(scorer: Scorer, walker: Walker) -> list[bool]:
    """从开局一路推下去，按上面的规则预计三关换不换（写日志用；真打时每关再按当时的队伍定）。"""
    walker = walker.copy()
    walker.side_events(lambda w: decide_scientist(scorer, w))
    swaps = []
    while walker.next_event() == "catch":
        take, _ = decide_catch(scorer, walker)
        swaps.append(take)
        walker.catch(take)
        walker.side_events(lambda w: decide_scientist(scorer, w))
    return swaps
