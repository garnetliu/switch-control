"""device 测试共用的假连接。

假连接符合 Botbase 要求的 Connection：记下发出的命令，按命令返回给定的字节。
测试文件里不能 from conftest import，假连接通过 fixture 给测试用，类型标成 Any。
"""

from collections.abc import Callable, Mapping, Sequence

import pytest


class FakeConnection:
    """假连接：send 的命令记在 sent，request 的命令记在 requested，request 按命令返回给定的字节。"""

    def __init__(
        self,
        replies: Mapping[str, Sequence[bytes]] | None = None,
        *,
        pointer_little_endian: bool = False,
        title: str = "0100ABF008968000",
    ) -> None:
        self.pointer_little_endian = pointer_little_endian
        self.sent: list[str] = []
        self.requested: list[str] = []
        self.close_calls = 0
        self._title = title
        self._replies = {cmd: list(values) for cmd, values in (replies or {}).items()}
        self._positions: dict[str, int] = {}

    def send(self, cmd: str) -> None:
        """记下发出的命令。"""
        self.sent.append(cmd)

    def request(self, cmd: str) -> bytes:
        """记下命令，按这条命令第几次被问返回给定的字节，用完后一直返回最后一个。"""
        self.requested.append(cmd)
        values = self._replies[cmd]
        position = self._positions.get(cmd, 0)
        self._positions[cmd] = position + 1
        return values[min(position, len(values) - 1)]

    def title_id(self) -> str:
        """返回事先给定的值。"""
        return self._title

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


@pytest.fixture
def make_connection() -> Callable[..., FakeConnection]:
    """返回一个函数：传入 {命令: [依次返回的字节]}，可以再传 pointer_little_endian，返回假连接。"""

    def factory(
        replies: Mapping[str, Sequence[bytes]] | None = None,
        *,
        pointer_little_endian: bool = False,
    ) -> FakeConnection:
        return FakeConnection(replies, pointer_little_endian=pointer_little_endian)

    return factory
