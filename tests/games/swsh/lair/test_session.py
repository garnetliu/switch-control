"""control_switch.games.swsh.lair.session：LairSession 从内存读极矿石、球的数量和抓过的神兽。

用假设备创建 LairSession（tests/games/swsh/lair/conftest.py 的 make_lair_session），
GameConfig.game_state_file 等路径指到临时目录。假 Memory 按地址返回事先给定的字节，记下读过的地址。
道具口袋每格 4 字节小端：道具编号 | 数量 << 15。
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from control_switch.device import Devices
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.session import LairSession, _scramble
from control_switch.settings import load_settings

ADDRESSES = GameConfig.addresses
ITEM_POUCH = ADDRESSES.items + ADDRESSES.item_pouch_offset
BALL_POUCH = ADDRESSES.items + ADDRESSES.ball_pouch_offset
DYNITE_ORE = GameConfig.dynite_ore_item
ULTRA_BALL = GameConfig.ball_items["究极球"]
MASTER_BALL = GameConfig.ball_items["大师球"]

SessionFactory = Callable[..., LairSession]


def pouch(slots: int, items: dict[int, int]) -> bytes:
    """一个口袋的字节：每格 4 字节小端，items 是 {道具编号: 数量}，按顺序放在开头几格，其余是空格。"""
    values = [item | count << 15 for item, count in items.items()]
    values += [0] * (slots - len(values))
    return b"".join(value.to_bytes(4, "little") for value in values)


def item_pouch(items: dict[int, int]) -> bytes:
    return pouch(ADDRESSES.item_pouch_slots, items)


def ball_pouch(items: dict[int, int]) -> bytes:
    return pouch(ADDRESSES.ball_pouch_slots, items)


# ---------------------------------------------------------------- ore_count


def test_ore_count_returns_count_of_dynite_ore_in_item_pouch(
    make_lair_session: SessionFactory,
) -> None:
    """道具口袋里有极矿石（道具编号 dynite_ore_item，数量 37）：ore_count() 是 37，读的是道具口袋的地址。"""
    sw = make_lair_session(data={ITEM_POUCH: item_pouch({50: 3, DYNITE_ORE: 37, 60: 9})})
    assert sw.ore_count() == 37
    memory: Any = sw.memory
    assert memory.reads == [("peek", ITEM_POUCH, ADDRESSES.item_pouch_slots * 4)]


def test_ore_count_is_zero_when_pouch_has_no_dynite_ore(
    make_lair_session: SessionFactory,
) -> None:
    """道具口袋里没有极矿石：ore_count() 是 0。"""
    sw = make_lair_session(data={ITEM_POUCH: item_pouch({50: 3, 60: 9})})
    assert sw.ore_count() == 0


# ---------------------------------------------------------------- ball_counts


def test_ball_counts_has_one_entry_when_base_ball_and_legendary_ball_are_the_same(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base_ball 和 legendary_ball 一样（都是究极球）：结果只有一项，数量和球口袋里的一样，读的是球口袋的地址。"""
    monkeypatch.setattr(GameConfig, "base_ball", "究极球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "究极球")
    sw = make_lair_session(data={BALL_POUCH: ball_pouch({MASTER_BALL: 2, ULTRA_BALL: 25})})
    assert sw.ball_counts() == {"究极球": 25}
    memory: Any = sw.memory
    assert memory.reads[0] == ("peek", BALL_POUCH, ADDRESSES.ball_pouch_slots * 4)


def test_ball_counts_has_two_entries_when_balls_differ(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base_ball 是究极球、legendary_ball 是大师球：两项，数量各自和球口袋里的一样。"""
    monkeypatch.setattr(GameConfig, "base_ball", "究极球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "大师球")
    sw = make_lair_session(data={BALL_POUCH: ball_pouch({MASTER_BALL: 2, ULTRA_BALL: 25})})
    assert sw.ball_counts() == {"究极球": 25, "大师球": 2}


def test_ball_counts_leaves_out_ball_whose_name_is_not_in_ball_items(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """legendary_ball 的球名不在 ball_items 里：不在结果里，另一种球照常有。"""
    monkeypatch.setattr(GameConfig, "base_ball", "究极球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "没有这种球")
    sw = make_lair_session(data={BALL_POUCH: ball_pouch({ULTRA_BALL: 25})})
    assert sw.ball_counts() == {"究极球": 25}


def test_ball_counts_leaves_out_base_ball_whose_name_is_not_in_ball_items(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base_ball 的球名不在 ball_items 里：不在结果里，legendary_ball 照常有。"""
    monkeypatch.setattr(GameConfig, "base_ball", "没有这种球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "大师球")
    sw = make_lair_session(data={BALL_POUCH: ball_pouch({MASTER_BALL: 2})})
    assert sw.ball_counts() == {"大师球": 2}


# ---------------------------------------------------------------- caught_legends

TABLE_START, TABLE_END = ADDRESSES.caught_table
# 存档数据块里各神兽开关的数据地址：每只隔 3 个字节，不挨在一起
LEGEND_DATA = 0x60000000
ULTRA_DATA = 0x61000000
KEYS = GameConfig.lair_caught_keys
ULTRA_KEY = GameConfig.lair_ultra_beasts_key


def entry(key: int, pointer: int) -> bytes:
    """表里的一项（0x20 字节）：开头 4 字节编号，+8 处 8 字节数据地址。"""
    return key.to_bytes(4, "little") + bytes(4) + pointer.to_bytes(8, "little") + bytes(16)


def legend_pointer(name: str) -> int:
    return LEGEND_DATA + list(KEYS).index(name) * 3


def caught_memory(
    caught: set[str],
    *,
    skip: str | None = None,
    plain: dict[str, int] | None = None,
    ultra_key: int = ULTRA_KEY,
    ultra_plain: int = 2,
) -> dict[int, bytes]:
    """存档数据块的表，和各个开关的数据，都按「还原后 1 是否、2 是是」放好，值用 _scramble 打乱。

    caught 是抓到的神兽；skip 是表里不放的那一只；plain 里写了的神兽，还原后是这个值
    （不是 1 或 2 就是读不出来）；ultra_key 是 ultra_beasts_entry 那一项里的编号。
    """
    table = b"".join(entry(key, legend_pointer(name)) for name, key in KEYS.items() if name != skip)
    table = table.ljust(TABLE_END - TABLE_START, b"\0")
    size = (len(KEYS) - 1) * 3 + 1
    values = bytearray(size)
    for name, key in KEYS.items():
        value = (plain or {}).get(name, 2 if name in caught else 1)
        values[legend_pointer(name) - LEGEND_DATA] = value ^ _scramble(key)
    return {
        TABLE_START: table,
        LEGEND_DATA: bytes(values),
        ADDRESSES.ultra_beasts_entry: entry(ultra_key, ULTRA_DATA)[:0x10],
        ULTRA_DATA: bytes([ultra_plain ^ _scramble(ULTRA_KEY)]),
    }


def test_caught_legends_reads_caught_legends_and_ultra_beasts_flag(
    make_lair_session: SessionFactory,
) -> None:
    """正常读出：已抓的神兽按 lair_caught_keys 的顺序，究极异兽解锁了。读内存走的都是 sw.memory：
    表（peek）、神兽开关（peek_absolute，从最低地址到最高地址整段）、究极异兽那一项（peek）和它的开关（peek_absolute）。
    """
    names = list(KEYS)
    caught = {names[5], names[0], names[20]}
    sw = make_lair_session(data=caught_memory(caught, ultra_plain=2))
    result = sw.caught_legends()
    assert result == ((names[0], names[5], names[20]), True)
    memory: Any = sw.memory
    assert memory.reads == [
        ("peek", TABLE_START, TABLE_END - TABLE_START),
        ("peek_absolute", LEGEND_DATA, (len(KEYS) - 1) * 3 + 1),
        ("peek", ADDRESSES.ultra_beasts_entry, 0x10),
        ("peek_absolute", ULTRA_DATA, 1),
    ]


def test_caught_legends_with_nothing_caught_and_ultra_beasts_locked(
    make_lair_session: SessionFactory,
) -> None:
    """一只都没抓、究极异兽没解锁（还原后是 1）：返回 ((), False)。"""
    sw = make_lair_session(data=caught_memory(set(), ultra_plain=1))
    assert sw.caught_legends() == ((), False)


def test_caught_legends_unscrambles_ultra_beasts_flag_with_known_value(
    make_lair_session: SessionFactory,
) -> None:
    """究极异兽的开关用固定的字节 0x5D：它的编号 0xB99A1E28 的打乱值是 0x5F（照改动前的代码算出来的），
    0x5D 还原后是 2，解锁了。
    """
    data = caught_memory(set())
    data[ULTRA_DATA] = bytes([0x5D])
    sw = make_lair_session(data=data)
    assert sw.caught_legends() == ((), True)


def test_caught_legends_raises_when_a_legend_key_is_missing_from_table(
    make_lair_session: SessionFactory,
) -> None:
    """表里找不到某只神兽的编号：抛 RuntimeError，报错里有这只神兽的名字。"""
    name = list(KEYS)[3]
    sw = make_lair_session(data=caught_memory(set(), skip=name))
    with pytest.raises(RuntimeError, match=name):
        sw.caught_legends()


def test_caught_legends_raises_when_ultra_beasts_entry_has_wrong_key(
    make_lair_session: SessionFactory,
) -> None:
    """ultra_beasts_entry 那一项的编号不对：抛 RuntimeError，报错里有「编号不对」。"""
    sw = make_lair_session(data=caught_memory(set(), ultra_key=ULTRA_KEY + 1))
    with pytest.raises(RuntimeError, match="编号不对"):
        sw.caught_legends()


@pytest.mark.parametrize("plain", [0, 3])
def test_caught_legends_raises_when_legend_flag_is_neither_1_nor_2(
    make_lair_session: SessionFactory, plain: int
) -> None:
    """某只神兽的开关值还原后是 0 或 3（不是 1 或 2）：抛 RuntimeError，报错里有这只神兽的名字和还原后的值。"""
    name = list(KEYS)[7]
    sw = make_lair_session(data=caught_memory(set(), plain={name: plain}))
    with pytest.raises(RuntimeError, match=name) as error:
        sw.caught_legends()
    assert f"是 {plain}" in str(error.value)


@pytest.mark.parametrize("plain", [0, 3])
def test_caught_legends_raises_when_ultra_beasts_flag_is_neither_1_nor_2(
    make_lair_session: SessionFactory, plain: int
) -> None:
    """究极异兽的开关值还原后是 0 或 3：抛 RuntimeError，报错里有「究极异兽解锁了没有」。"""
    sw = make_lair_session(data=caught_memory(set(), ultra_plain=plain))
    with pytest.raises(RuntimeError, match="究极异兽解锁了没有"):
        sw.caught_legends()


# ---------------------------------------------------------------- Pkhex


def test_pkhex_is_created_with_api_url_from_settings(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pkhex 换成记下参数的假类：用 PKHEX_API_URL=http://x 的 Settings 建 LairSession，假类收到的 api_url 是 http://x。"""
    received: list[str | None] = []

    class RecordingPkhex:
        def __init__(self, api_url: str | None = None) -> None:
            received.append(api_url)

    monkeypatch.setattr("control_switch.games.swsh.lair.session.Pkhex", RecordingPkhex)
    make_lair_session(settings=load_settings({"PKHEX_API_URL": "http://x"}))
    assert received == ["http://x"]


# ---------------------------------------------------------------- MEMORY=none


def test_memory_none_error_names_memory_setting(
    lair_root: Path, make_screen: Callable[..., Any], controller: Any
) -> None:
    """MEMORY=none 时建 LairSession：报错里要写出 MEMORY，使用者才知道是哪一项配置让它跑不了。

    防的是：MEMORY 的 none 是这次新开放、.env.example 里列为可以写的值，但极巨大冒险要读内存，
    写了 none 后 create_devices 照常连上 Switch，建 LairSession 时抛
    RuntimeError("这个脚本要读写内存，但没有配置内存设备")，报错里没有 MEMORY，
    而且使用者明明写了 MEMORY=none，报错却说「没有配置」。这次任务带进来的。
    """
    devices = Devices(make_screen([b"img"]), controller, None)
    with pytest.raises(RuntimeError, match="MEMORY"):
        LairSession(load_settings({"MEMORY": "none"}), devices)
