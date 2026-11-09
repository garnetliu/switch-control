"""宝可梦相关的共用类型。"""

import math
from dataclasses import dataclass, field
from typing import NamedTuple

from config.game import LANGUAGE


@dataclass(frozen=True)
class Move:
    id_num: int
    name_id: str
    names: dict[str, str]
    type_id: str
    category: str
    base_power: float
    accuracy: float
    pp: int
    effect: str
    probability: float | None
    is_spread: bool
    correction_factor: float

    @property
    def power(self) -> float:
        """修正后的威力。"""
        return self.base_power * self.correction_factor

    def name(self, language: str = LANGUAGE) -> str:
        """招式名，没有这种语言的名字就返回 name_id。"""
        return self.names.get(language, self.name_id)


@dataclass
class Pokemon:
    id_num: int
    name_id: str
    names: dict[str, str]
    ability_name_id: str
    abilities: dict[str, str]
    type_ids: list[str]
    types: list[dict[str, str]]
    base_stats: tuple[int, ...]
    moves: tuple[Move, ...]
    max_moves: tuple[Move, ...]
    level: int
    ivs: tuple[int, ...]
    evs: tuple[int, ...]
    nature: tuple[float, ...]
    # 剩余血量，0 到 1
    hp: float = 1.0
    # 每个招式剩余的 PP，顺序和 moves 一致；不传就是满的
    pp: list[int] = field(default_factory=list)
    # 正在极巨化
    dynamax: bool = False
    # 异常状态，例如 "burn"；没有就是 None
    status: str | None = None

    def __post_init__(self) -> None:
        # 复制宝可梦（dataclasses.replace）时也复制一份 PP，扣 PP 不会改到共用的数据
        self.pp = list(self.pp) if self.pp else [move.pp for move in self.moves]

    @property
    def stats(self) -> tuple[float, ...]:
        """能力值：HP、攻击、防御、特攻、特防、速度，按等级、个体值、努力值、性格算出。"""
        base, ivs, evs = self.base_stats, self.ivs, self.evs
        hp = math.floor((2 * base[0] + ivs[0] + evs[0] // 4) * self.level / 100) + self.level + 10
        others = (
            math.floor(
                (math.floor((2 * base[i] + ivs[i] + evs[i] // 4) * self.level / 100) + 5)
                * self.nature[i]
            )
            for i in range(1, 6)
        )
        return (hp, *others)

    def name(self, language: str = LANGUAGE) -> str:
        """宝可梦的名字，没有这种语言的名字就返回 name_id。"""
        return self.names.get(language, self.name_id)

    def ability(self, language: str = LANGUAGE) -> str:
        """特性名，没有这种语言的名字就返回 ability_name_id。"""
        return self.abilities.get(language, self.ability_name_id)


class Match(NamedTuple):
    """把识别出的文字匹配到一只宝可梦的结果。"""

    pokemon: Pokemon
    # 识别出的文字和这只宝可梦的标准文字之间的编辑距离，越小越像
    distance: int
    # 识别出的文字
    text: str

    @property
    def is_poor(self) -> bool:
        """匹配得不好：编辑距离超过识别文字长度的三分之一。"""
        return self.distance > len(self.text) / 3
