"""control_switch.games.swsh.pk8：Pk8Reader。

pkhex 和 peek 都用假的：pkhex 按调用顺序返回事先给定的结果并记下调用，peek 记下地址，
time.sleep 换成不等待。不连 PKHeX 服务。
"""

from typing import Any, cast

import pytest

from control_switch.games.swsh.pk8 import Pk8Reader

Record = dict[str, Any]


class FakePkhex:
    """按调用顺序返回给定的结果，用完后抛错；记下每次传来的脚本和输入。"""

    def __init__(self, results: list[Any]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, script: str, data: dict[str, Any]) -> Any:
        """记下调用，返回下一个结果。"""
        self.calls.append((script, data))
        return self.results[len(self.calls) - 1]


class FakePeek:
    """记下读过的 (地址, 大小)，每次返回由地址决定的字节。"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def __call__(self, address: int, size: int) -> bytes:
        self.calls.append((address, size))
        return bytes([address & 0xFF]) * 2


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """time.sleep 换成只记录不等待，返回记录的列表。"""
    sleeps: list[float] = []
    monkeypatch.setattr("control_switch.games.swsh.pk8.time.sleep", sleeps.append)
    return sleeps


def make_reader(results: list[Any]) -> tuple[Pk8Reader, FakePkhex, FakePeek]:
    pkhex = FakePkhex(results)
    peek = FakePeek()
    return Pk8Reader(cast(Any, pkhex), peek), pkhex, peek


def test_read_pk8_returns_records_when_checksum_valid_first_time(no_sleep: list[float]) -> None:
    """read_pk8：第一次校验和就对，直接返回，只读一轮，不等待。"""
    good = [{"checksumValid": True, "species": 1}, {"checksumValid": True, "species": 2}]
    reader, pkhex, peek = make_reader([good])
    assert reader.read_pk8([0x10, 0x20]) == good
    assert peek.calls == [(0x10, 0x158), (0x20, 0x158)]
    assert len(pkhex.calls) == 1
    assert no_sleep == []


def test_read_pk8_rereads_when_checksum_invalid_then_returns_second(
    no_sleep: list[float],
) -> None:
    """read_pk8：第一次有一条 checksumValid 为 False，第二次都为 True，返回第二次的结果，peek 读了两轮。"""
    bad = [{"checksumValid": True, "species": 1}, {"checksumValid": False, "species": 2}]
    good = [{"checksumValid": True, "species": 1}, {"checksumValid": True, "species": 2}]
    reader, pkhex, peek = make_reader([bad, good])
    assert reader.read_pk8([0x10, 0x20]) == good
    assert peek.calls == [(0x10, 0x158), (0x20, 0x158)] * 2
    assert len(pkhex.calls) == 2
    assert no_sleep == [Pk8Reader.READ_INTERVAL]


def test_read_pk8_raises_after_all_attempts_fail(no_sleep: list[float]) -> None:
    """read_pk8：一直不对，读满 READ_ATTEMPTS（16）轮后抛 RuntimeError。"""
    bad = [{"checksumValid": False}]
    reader, pkhex, peek = make_reader([bad] * 20)
    with pytest.raises(RuntimeError, match="校验失败"):
        reader.read_pk8([0x10])
    assert Pk8Reader.READ_ATTEMPTS == 16
    assert len(pkhex.calls) == 16
    assert len(peek.calls) == 16
    # 最后一轮后不再等待
    assert len(no_sleep) == 15


def test_read_pk8_with_empty_addresses_returns_empty_without_calling_pkhex() -> None:
    """read_pk8：地址列表是空的，返回空列表，没有调 pkhex，也没有读内存。"""
    reader, pkhex, peek = make_reader([])
    assert reader.read_pk8([]) == []
    assert pkhex.calls == []
    assert peek.calls == []


def test_parse_pk8_batch_sends_hex_records_with_script() -> None:
    """parse_pk8_batch：把每条原始记录转成十六进制字符串，连同 PK8_BATCH_SCRIPT 交给 pkhex。"""
    reader, pkhex, _ = make_reader([[{"checksumValid": True}, {"checksumValid": True}]])
    result = reader.parse_pk8_batch([b"\x01\xab", b"\xff\x00"])
    assert result == [{"checksumValid": True}, {"checksumValid": True}]
    assert pkhex.calls == [(Pk8Reader.PK8_BATCH_SCRIPT, {"records": ["01ab", "ff00"]})]


def test_parse_pk8_batch_with_no_records_returns_empty_without_calling_pkhex() -> None:
    """parse_pk8_batch：没有记录时返回空列表，没有调 pkhex。"""
    reader, pkhex, _ = make_reader([])
    assert reader.parse_pk8_batch([]) == []
    assert pkhex.calls == []


def test_parse_pk8_batch_raises_when_result_count_differs() -> None:
    """parse_pk8_batch：pkhex 返回的条数和地址数（记录数）不一样，抛 RuntimeError。"""
    reader, _, _ = make_reader([[{"checksumValid": True}]])
    with pytest.raises(RuntimeError, match="数量不正确"):
        reader.parse_pk8_batch([b"\x00", b"\x01"])


def test_parse_pk8_batch_raises_when_result_is_not_a_list() -> None:
    """parse_pk8_batch：pkhex 返回的不是列表，抛 RuntimeError。"""
    reader, _, _ = make_reader([{"checksumValid": True}])
    with pytest.raises(RuntimeError, match="数量不正确"):
        reader.parse_pk8_batch([b"\x00"])


def test_read_pk8_raises_when_record_count_differs_from_address_count() -> None:
    """read_pk8：pkhex 返回的条数和地址数不一样，抛 RuntimeError（不重读）。"""
    reader, pkhex, _ = make_reader([[{"checksumValid": True}]])
    with pytest.raises(RuntimeError, match="数量不正确"):
        reader.read_pk8([0x10, 0x20])
    assert len(pkhex.calls) == 1
