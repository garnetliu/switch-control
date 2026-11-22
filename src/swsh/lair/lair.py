"""从极巨大冒险 seed 计算租借候选和普通遭遇。"""

from collections.abc import Iterator, Sequence

from libs.xoroshiro import Xoroshiro

from .game_data import GameData

# 地图类型：遭遇前面那次 draw(2) 的值，见 docs/实测-地图类型由seed决定.md
MAP_TYPES = {0: "2x3", 1: "2x2", 2: "3x2"}


def _mt19937(seed: int) -> Iterator[int]:
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


def _first(rows: list[list], seed: int, used: set[tuple[int, int]]) -> list:
    """拿 seed 当 MT 种子把遭遇表洗一遍，取第一行不是首领、也不在 used 里的。"""
    random = _mt19937(seed)
    order: list[int] = list(range(len(rows)))
    for index in range(len(order)):
        while True:
            offset = next(random) & 0x1FF
            if offset <= len(order) - index - 1:
                break
        other = index + offset
        order[index], order[other] = order[other], order[index]
    return next(
        rows[index]
        for index in order
        if not rows[index][2] and (rows[index][0], rows[index][1]) not in used
    )


class Lair:
    """一局冒险的租借候选和普通遭遇。"""

    def __init__(self, data: GameData, seed: int, extra: int = 0):
        """extra: 第一次抽数之后多取几个随机数。

        第一次抽数的上限是 data.first_draw_top()，抽到比它大的游戏会重抽。这个上限会随存档变
        （抓走神兽后变小），配置里的值过时了的话，算出来的租借和真机对不上，
        所以调用的地方还是拿选宝可梦界面的 3 只来对，对不上就让 extra 加 1 重算。
        """
        self._data = data
        self._seed = seed
        self._extra = extra
        self._picked: list[list] | None = None
        # 三个队友依次从三格里选第几格
        self._teammate_draws: list[int] = []
        self._first_draw = 0
        self._map_draw = 0
        self._layout_draw = 0
        self._after = (0, 0)

    def candidates(self) -> list[str]:
        """6 只租借候选，选宝可梦的界面显示的是前 3 只。"""
        return [self._data.name_id(row[0], row[1]) for row in self._picks()[:6]]

    def encounters(self) -> dict[str, list[str]]:
        """按路线图三层返回遭遇，每层 2、4、4 个，顺序和列一致。"""
        names = [self._data.name_id(row[0], row[1]) for row in self._picks()[6:]]
        return {"1": names[:2], "2": names[2:6], "3": names[6:10]}

    def map_type(self) -> str:
        """路线图的类型：2x3、2x2 或 3x2。"""
        self._picks()
        return MAP_TYPES[self._map_draw]

    def layout(self) -> int:
        """路上事件的布局编号，0 到 9：地图类型后面那次 draw(9) 的值。

        同一种地图类型、同一个编号的图，路上哪里有研究员、背包客、树果是一样的
        （日志里 13 组不同 seed 的图全部一样），见 GameData.lair_events。
        """
        self._picks()
        return self._layout_draw

    def boss(self) -> str:
        """在研究员那里选「不指定」时这一局的首领：还没抓到的神兽里的第几只，就是开头第一次抽到的数。"""
        self._picks()
        return self._data.lair_legends()[self._first_draw]

    def fate(
        self, schedule: Sequence[str], boss: str, swaps: Sequence[bool]
    ) -> list[int | tuple[int, str] | None]:
        """队友一路上的选择。seed 定死，但抽几次随机数要看自己每一只抓到后换没换
        （见 docs/实测-打分算法对比.md「研究员给自己的那只、自己换没换会改变抽数」）。

        schedule 是路上按先后会遇到的事：catch（抓到一只）、scientist（研究员）、backpacker（背包客）；
        boss 是首领的 name_id；swaps 是每一只抓到后自己换没换，和 schedule 里的 catch 一一对应。
        返回和 schedule 一一对应的结果：
        - catch：哪个队友换上它（0、1、2），自己换了或者没人换是 None；
        - scientist：(哪个队友换, 换成的宝可梦)，没人换是 None；
        - backpacker：None（只是占掉几个随机数）。

        抽完 10 个对手之后随机数接着这样用：首领是双属性的先用掉 1 个；每抓到一只，先抽一个 0～2 的数
        （管什么还不知道），三个队友各一个随机数（偶数想要）；自己换了就不再抽，自己没换且有人想要，
        才反复抽 0～3（1、2、3 是三个队友）抽到想要的人为止。研究员是三个队友各一个随机数、同样反复抽 0～3
        定是谁、再洗一次牌取一只没出现过的，这是自己在研究员那里不换时的抽法（程序永远不换，见 path.py）；
        背包客是三个队友各抽一个 0～4（拿第几样道具）。
        """
        picked = self._picks()
        rows = self._data.lair_rows()
        rng = Xoroshiro(0)
        rng.s0, rng.s1 = self._after
        species = self._data.boss_pokemon()[boss].id_num
        if any(row[2] and row[0] == species and row[4] != row[5] for row in rows):
            rng.next_u32()
        used = {(row[0], row[1]) for row in picked}

        def wanting() -> list[int]:
            """三个队友各一个随机数，偶数是想要。"""
            return [member for member in range(3) if rng.next_u32() & 1 == 0]

        def chosen(want: list[int]) -> int | None:
            """有人想要就反复抽 0～3，抽到其中一个为止。"""
            while want:
                value = rng.draw(3)
                if value and value - 1 in want:
                    return value - 1
            return None

        catches = iter(swaps)
        result: list[int | tuple[int, str] | None] = []
        for event in schedule:
            if event == "catch":
                rng.draw(2)
                want = wanting()
                result.append(None if next(catches) else chosen(want))
            elif event == "scientist":
                member = chosen(wanting())
                if member is None:
                    result.append(None)
                    continue
                row = _first(rows, rng.next_u32(), used)
                used.add((row[0], row[1]))
                result.append((member, self._data.name_id(row[0], row[1])))
            else:
                if event == "backpacker":
                    for _ in range(3):
                        rng.draw(4)
                result.append(None)
        return result

    def teammates(self, starter: int) -> list[str]:
        """自己选了界面上第 starter 只之后，三个队友依次拿到的宝可梦。

        自己拿走的那格补上第 4 只；队友每拿走一格，补上下一只（第 5、6 只）。
        用留存的 136 张图的开场队伍对过，132 张完全一样。
        """
        self._picks()
        pool = self.candidates()
        slots = pool[:3]
        slots[starter] = pool[3]
        result = []
        for index, draw in enumerate(self._teammate_draws):
            result.append(slots[draw])
            if index < 2:
                slots[draw] = pool[4 + index]
        return result

    def _picks(self) -> list[list]:
        cached = self._picked
        if cached is not None:
            return cached

        rows = self._data.lair_rows()
        partners = 3

        rng = Xoroshiro(self._seed)
        picked: list[list] = []

        def pick() -> list:
            chosen = _first(rows, rng.next_u32(), {(item[0], item[1]) for item in picked})
            picked.append(chosen)
            return chosen

        if partners > 2:
            self._first_draw = rng.draw(self._data.first_draw_top())
        for _ in range(self._extra):
            rng.next_u32()
        for _ in range(4):
            pick()
        teammate_draws = []
        for threshold in (2, 1, 0):
            if partners > threshold:
                teammate_draws.append(rng.draw(2))
            if threshold:
                pick()
        self._teammate_draws = teammate_draws
        self._map_draw = rng.draw(2)
        self._layout_draw = rng.draw(9)
        for _ in range(10):
            row = pick()
            if row[4] != row[5]:
                rng.next_u32()

        self._picked = picked
        # 抽完对手之后随机数的状态，队友的选择接着从这里往下用（见 fate）
        self._after = (rng.s0, rng.s1)
        return picked
