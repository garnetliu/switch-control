"""Xoroshiro 随机数生成器。"""


class Xoroshiro:
    MASK64 = (1 << 64) - 1

    def __init__(self, seed: int):
        self.s0 = seed & self.MASK64
        self.s1 = 0x82A2B175229D6A5B

    def next_u32(self) -> int:
        s0, s1 = self.s0, self.s1
        result = (s0 + s1) & 0xFFFFFFFF
        s1 ^= s0
        self.s0 = ((s0 << 24 | s0 >> 40) ^ s1 ^ (s1 << 16)) & self.MASK64
        self.s1 = (s1 << 37 | s1 >> 27) & self.MASK64
        return result

    def draw(self, top: int) -> int:
        mask = (1 << top.bit_length()) - 1
        while True:
            value = self.next_u32() & mask
            if value <= top:
                return value
