"""从极巨大冒险 seed 计算租借候选和普通遭遇。"""

from libs.xoroshiro import Xoroshiro

from .game_data import GameData


class Lair:
    """一局冒险的租借候选和普通遭遇。"""

    def __init__(self, data: GameData, seed: int, extra: int = 0):
        """extra: 第一次抽数之后多取几个随机数。

        真机上有的 seed 开头会多用掉一个随机数（seed 5106430911447199167，第一次抽数抽到 26），
        什么情况下会多用还不清楚，所以由调用的地方拿选宝可梦界面的 3 只来对，对不上就加 1 重算。
        """
        self._data = data
        self._seed = seed
        self._extra = extra
        self._picked: list[list] | None = None

    def candidates(self) -> list[str]:
        """6 只租借候选，选宝可梦的界面显示的是前 3 只。"""
        return [self._data.name_id(row[0], row[1]) for row in self._picks()[:6]]

    def encounters(self) -> dict[str, list[str]]:
        """按路线图三层返回遭遇，每层 2、4、4 个，顺序和列一致。"""
        names = [self._data.name_id(row[0], row[1]) for row in self._picks()[6:]]
        return {"1": names[:2], "2": names[2:6], "3": names[6:10]}

    def _picks(self) -> list[list]:
        cached = self._picked
        if cached is not None:
            return cached

        rows = self._data.lair_rows()
        partners = 3

        def mt19937(seed: int):
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

        rng = Xoroshiro(self._seed)
        picked: list[list] = []

        def pick() -> list:
            random = mt19937(rng.next_u32())
            order: list[int] = list(range(len(rows)))
            for index in range(len(order)):
                while True:
                    offset = next(random) & 0x1FF
                    if offset <= len(order) - index - 1:
                        break
                other = index + offset
                order[index], order[other] = order[other], order[index]
            used = {(item[0], item[1]) for item in picked}
            chosen = next(
                rows[index]
                for index in order
                if not rows[index][2] and (rows[index][0], rows[index][1]) not in used
            )
            picked.append(chosen)
            return chosen

        if partners > 2:
            rng.draw(27)
        for _ in range(self._extra):
            rng.next_u32()
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

        self._picked = picked
        return picked
