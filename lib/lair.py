"""从极巨大冒险 seed 计算普通遭遇及其租借数据名。"""

import json
from functools import cache

from config.paths import DATA_DIR
from lib import data

SEED_ADDRESS = 0x4514A4B0
CPU_PARTNERS = 3
MASK64 = (1 << 64) - 1

# Pokémon 池里的自定义 name_id 与游戏表中的 species/form 对应关系。
FORM_NAME_IDS = {
    (26, 1): "raichu-alola",
    (28, 1): "sandslash-alola",
    (51, 1): "dugtrio-alola",
    (53, 1): "persian-alola",
    (105, 1): "marowak-alola",
    (110, 1): "weezing-galar",
    (122, 1): "mr-mime-galar",
    (264, 1): "linoone-galar",
    (423, 1): "gastrodon",
    (550, 0): "basculin-red-striped",
    (550, 1): "basculin-blue-striped",
    (618, 1): "stunfisk-galar",
    (745, 0): "lycanroc-midday",
    (745, 1): "lycanroc-midnight",
}


class _Xoroshiro:
    def __init__(self, seed: int):
        self.s0 = seed & MASK64
        self.s1 = 0x82A2B175229D6A5B

    def next_u32(self) -> int:
        s0, s1 = self.s0, self.s1
        result = (s0 + s1) & 0xFFFFFFFF
        s1 ^= s0
        self.s0 = ((s0 << 24 | s0 >> 40) ^ s1 ^ (s1 << 16)) & MASK64
        self.s1 = (s1 << 37 | s1 >> 27) & MASK64
        return result

    def draw(self, top: int) -> int:
        mask = (1 << top.bit_length()) - 1
        while True:
            value = self.next_u32() & mask
            if value <= top:
                return value


def _mt19937(seed: int):
    state = [seed]
    for index in range(1, 624):
        previous = state[-1]
        state.append((1812433253 * (previous ^ (previous >> 30)) + index) & 0xFFFFFFFF)
    while True:
        for index in range(624):
            y = (state[index] & 0x80000000) | (state[(index + 1) % 624] & 0x7FFFFFFF)
            state[index] = state[(index + 397) % 624] ^ (y >> 1)
            if y & 1:
                state[index] ^= 0x9908B0DF
        for value in state:
            value ^= value >> 11
            value ^= (value << 7) & 0x9D2C5680
            value ^= (value << 15) & 0xEFC60000
            yield (value ^ (value >> 18)) & 0xFFFFFFFF


@cache
def _table() -> list[list]:
    return json.loads((DATA_DIR / "lair_pokemon.json").read_text(encoding="utf-8"))["rows"]


def _picks(seed: int, partners: int = CPU_PARTNERS) -> list[list]:
    """按 seed 依次抽取：前 6 个是租借候选，后 10 个是普通遭遇。"""
    rows = _table()
    rng = _Xoroshiro(seed)
    picked: list[list] = []

    def pick() -> list:
        random = _mt19937(rng.next_u32())
        order = list(range(len(rows)))
        for index in range(len(order)):
            while True:
                offset = next(random) & 0x1FF
                if offset <= len(order) - index - 1:
                    break
            other = index + offset
            order[index], order[other] = order[other], order[index]
        used = {(row[0], row[1]) for row in picked}
        chosen = next(
            rows[index]
            for index in order
            if not rows[index][2] and (rows[index][0], rows[index][1]) not in used
        )
        picked.append(chosen)
        return chosen

    if partners > 2:
        rng.draw(27)
    for _ in range(4):
        pick()
    for threshold in (2, 1, 0):
        if partners > threshold:
            rng.draw(2)
        if threshold:
            pick()
    rng.draw(2)
    rng.draw(9)
    for _ in range(10):
        row = pick()
        if row[4] != row[5]:
            rng.next_u32()
    return picked


def encounters(seed: int, partners: int = CPU_PARTNERS) -> list[list]:
    """返回 seed 对应的 10 个普通遭遇，顺序按第 1、2、4、4 个节点排列。"""
    return _picks(seed, partners)[6:]


def rental_candidates(seed: int, partners: int = CPU_PARTNERS) -> list[str]:
    """返回 seed 对应的 6 只租借候选，前 3 只是初始界面上的候选。"""
    return [encounter_name_id(row) for row in _picks(seed, partners)[:6]]


def encounter_name_id(row: list) -> str:
    """把游戏 encounter row 的 species/form 转成项目相性表使用的 name_id。"""
    species, form = row[:2]
    name_id = FORM_NAME_IDS.get((species, form))
    if name_id is None and form == 0:
        name_id = next(
            (name for name, pokemon in data.rental_pokemon().items() if pokemon.id_num == species),
            None,
        )
    if name_id not in data.boss_matchups():
        raise ValueError(f"没有 species={species}, form={form} 对应的首领相性数据")
    return name_id


def encounter_rows_by_layer(seed: int) -> dict[int, list[str]]:
    """按路线图各层节点顺序返回遭遇宝可梦 name_id：2、4、4。"""
    names = [encounter_name_id(row) for row in encounters(seed)]
    return {1: names[:2], 2: names[2:6], 3: names[6:10]}
