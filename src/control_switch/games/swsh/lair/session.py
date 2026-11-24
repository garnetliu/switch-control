"""极巨大冒险用的 Session：还带着这一局的状态、游戏数据和 PK8 读取。"""

from control_switch.device import Devices
from control_switch.games.swsh.pk8 import Pk8Reader
from control_switch.pkhex import Pkhex
from control_switch.session import Session
from control_switch.settings import Settings

from .game_config import GameConfig
from .game_data import GameData
from .game_state import GameState


class LairSession(Session):
    """步骤里用 sw.config、sw.game、sw.data、sw.pkhex 取。"""

    config: GameConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(GameConfig(), settings, devices)
        title_id = self.memory.title_id().strip().upper()
        if title_id not in self.config.lair_version_exclusives:
            raise RuntimeError(f"不是剑或盾，Title ID 是 {title_id!r}")
        self.config.lair_other_version = self.config.lair_version_exclusives[title_id]
        self.game = GameState(self.config, keep_path=settings.keep_path)
        self.data = GameData(self.config)
        self.pkhex = Pk8Reader(Pkhex(settings.pkhex_api_url), self.memory.peek)

    def ore_count(self) -> int:
        """从内存读极矿石的数量。"""
        addresses = self.config.addresses
        return self._item_count(
            addresses.item_pouch_offset, addresses.item_pouch_slots, self.config.dynite_ore_item
        )

    def ball_counts(self) -> dict[str, int]:
        """从内存读配置里用来抓宝可梦的球的数量：普通的和抓首领的，一样就只有一项。

        不知道道具编号的球不在结果里。
        """
        addresses = self.config.addresses
        counts: dict[str, int] = {}
        for ball in (self.config.base_ball, self.config.legendary_ball):
            if ball in self.config.ball_items:
                counts[ball] = self._item_count(
                    addresses.ball_pouch_offset,
                    addresses.ball_pouch_slots,
                    self.config.ball_items[ball],
                )
        return counts

    def caught_legends(self) -> tuple[tuple[str, ...], bool]:
        """从存档数据读 (已经抓到的神兽, 究极异兽解锁了没有)，神兽按 lair_caught_keys 的顺序。

        内存里有一张存档数据块的表，按编号从小到大排，每项 0x20 字节：开头 4 字节是编号，
        第 8 字节起 8 字节是数据的绝对地址。开关型的数据只有 1 字节，和存档文件里一样是打乱过的
        （_scramble），还原后 1 是否、2 是是。表里找不到编号或者值不是 1、2 抛 RuntimeError。
        """
        addresses = self.config.addresses
        start, end = addresses.caught_table
        table = self.memory.peek(start, end - start)
        pointers = {
            int.from_bytes(table[offset : offset + 4], "little"): int.from_bytes(
                table[offset + 8 : offset + 16], "little"
            )
            for offset in range(0, len(table), 0x20)
        }
        keys = self.config.lair_caught_keys
        missing = [name for name, key in keys.items() if key not in pointers]
        if missing:
            raise RuntimeError(f"存档数据块的表里找不到这些神兽的编号：{missing}")
        low = min(pointers[key] for key in keys.values())
        high = max(pointers[key] for key in keys.values())
        values = self.memory.peek_absolute(low, high - low + 1)
        caught = tuple(
            name for name, key in keys.items() if self._flag(key, values[pointers[key] - low], name)
        )

        key = self.config.lair_ultra_beasts_key
        entry = self.memory.peek(addresses.ultra_beasts_entry, 0x10)
        if int.from_bytes(entry[:4], "little") != key:
            raise RuntimeError("存档数据块的表里「究极异兽解锁了没有」那一项的编号不对")
        value = self.memory.peek_absolute(int.from_bytes(entry[8:16], "little"), 1)[0]
        return caught, self._flag(key, value, "究极异兽解锁了没有")

    @staticmethod
    def _flag(key: int, value: int, what: str) -> bool:
        """还原一个开关型数据块的值。key 是它的编号，value 是内存里那 1 字节。"""
        plain = value ^ _scramble(key)
        if plain not in (1, 2):
            raise RuntimeError(f"「{what}」读出来的值是 {plain}，应该是 1 或 2")
        return plain == 2

    def _item_count(self, offset: int, slots: int, item: int) -> int:
        """从内存读背包一个口袋里某个道具的数量，口袋里没有返回 0。

        offset 是这个口袋在道具块里的位置，slots 是它有几格，item 是道具编号。
        """
        data = self.memory.peek(self.config.addresses.items + offset, slots * 4)
        for start in range(0, len(data), 4):
            value = int.from_bytes(data[start : start + 4], "little")
            if value & 0x7FF == item:
                return (value >> 15) & 0x3FF
        return 0


def _scramble(key: int) -> int:
    """存档数据块打乱用的第一个字节（PKHeX 的 SCXorShift32）：编号里有几个 1 就把它变换几次，取最低 8 位。"""
    for _ in range(key.bit_count()):
        key ^= (key << 2) & 0xFFFFFFFF
        key ^= key >> 15
        key ^= (key << 13) & 0xFFFFFFFF
    return key & 0xFF
