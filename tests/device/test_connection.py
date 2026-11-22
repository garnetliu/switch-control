"""control_switch.device.botbase 里的两个连接类：_WifiConnection（sys-botbase）和 _UsbConnection（usb-botbase）。

不连真机。WiFi：socket.create_connection 换成返回假 socket 的函数。
USB：大部分测试不调 __init__，直接给连接放上假的 out、into 端点和 timeout_ms；
time.sleep 换成不等待的函数，_reconnect 换成记下调用次数的函数（真的 _reconnect 会调
usb.core.find 找真设备，找不到时会一直找满 30 秒）。
要调 __init__ 的几条（创建、关闭）把 usb.core.find 换成返回假 USB 设备的函数，
usb.util.dispose_resources 换成什么都不做的函数。
"""

import socket
import struct
import time
from collections.abc import Sequence
from typing import Any

import pytest
import usb.core
import usb.util

from control_switch.device.botbase import _hex, _UsbConnection, _WifiConnection

# ---------------------------------------------------------------- _hex


@pytest.mark.parametrize(("value", "expected"), [(5, "0x5"), (0, "0x0"), (-5, "-0x5")])
def test_hex_formats_value_as_hex_text(value: int, expected: str) -> None:
    """_hex：正数写成 0x...，0 写成 0x0，负数写成 -0x...。"""
    assert _hex(value) == expected


# ---------------------------------------------------------------- WiFi


class FakeSocket:
    """假 socket：记下 sendall 的内容和 settimeout、close，recv 按顺序返回给定的块，用完后返回空。"""

    def __init__(self, chunks: Sequence[bytes]) -> None:
        self._chunks = list(chunks)
        self.sent: list[bytes] = []
        self.timeout: float | None = None
        self.close_calls = 0

    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        self.close_calls += 1


def make_wifi(monkeypatch: pytest.MonkeyPatch, chunks: Sequence[bytes] = ()) -> tuple[Any, Any]:
    """socket.create_connection 换成返回假 socket 的函数，返回 (WiFi 连接, 假 socket)。"""
    fake = FakeSocket(chunks)
    addresses: list[tuple[Any, ...]] = []

    def create_connection(address: tuple[str, int], timeout: float | None = None) -> FakeSocket:
        addresses.append(address)
        return fake

    monkeypatch.setattr(socket, "create_connection", create_connection)
    connection = _WifiConnection("192.168.1.50", 6000)
    assert addresses == [("192.168.1.50", 6000)]
    return connection, fake


def test_wifi_init_connects_to_given_host_and_port_and_sets_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创建 WiFi 连接：连的是给定的 (host, port)，socket 的超时设成 timeout。"""
    _, fake = make_wifi(monkeypatch)
    assert fake.timeout == 5.0


def test_wifi_send_writes_command_with_crlf(monkeypatch: pytest.MonkeyPatch) -> None:
    """send("click A")：发出的是 b"click A\\r\\n"。"""
    connection, fake = make_wifi(monkeypatch)
    connection.send("click A")
    assert fake.sent == [b"click A\r\n"]


def test_wifi_request_reads_one_line_and_decodes_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    """request：读到 \\n 为止，把这一行十六进制文本解成字节；命令发出的是带 \\r\\n 的那一行。"""
    connection, fake = make_wifi(monkeypatch, [b"0102ab\n"])
    assert connection.request("peek 0x10 0x3") == b"\x01\x02\xab"
    assert fake.sent == [b"peek 0x10 0x3\r\n"]


def test_wifi_request_joins_line_that_arrives_in_several_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：一行分三块到达（最后一块带 \\r\\n），也能拼成一行再解成字节。"""
    connection, _ = make_wifi(monkeypatch, [b"01", b"02", b"ab\r\n"])
    assert connection.request("peek 0x10 0x3") == b"\x01\x02\xab"


def test_wifi_request_raises_connection_error_when_recv_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：recv 一开始就返回空，抛 ConnectionError。"""
    connection, _ = make_wifi(monkeypatch, [])
    with pytest.raises(ConnectionError):
        connection.request("peek 0x10 0x3")


def test_wifi_request_raises_connection_error_when_line_is_cut_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：收到半行（没有 \\n）之后 recv 返回空，抛 ConnectionError。"""
    connection, _ = make_wifi(monkeypatch, [b"0102"])
    with pytest.raises(ConnectionError):
        connection.request("peek 0x10 0x3")


def test_wifi_title_id_returns_line_without_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """title_id()：发出 getTitleID，返回去掉首尾空白的那一行。"""
    connection, fake = make_wifi(monkeypatch, [b"  0100ABF008968000 \r\n"])
    assert connection.title_id() == "0100ABF008968000"
    assert fake.sent == [b"getTitleID\r\n"]


def test_wifi_send_after_close_raises_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """close() 之后再 send：抛 ConnectionError。"""
    connection, _ = make_wifi(monkeypatch)
    connection.close()
    with pytest.raises(ConnectionError):
        connection.send("click A")


def test_wifi_close_twice_does_not_raise_and_closes_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() 调两次不出错，socket 被关了。"""
    connection, fake = make_wifi(monkeypatch)
    connection.close()
    connection.close()
    assert fake.close_calls >= 1


def test_wifi_pointer_little_endian_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """WiFi 连接的 pointer_little_endian 是 False。"""
    connection, _ = make_wifi(monkeypatch)
    assert connection.pointer_little_endian is False


# ---------------------------------------------------------------- USB


class FakeOut:
    """假的发端点：write 记下 (数据, 超时)；errors 里按顺序给每次 write 要不要抛错。"""

    def __init__(self, errors: Sequence[Exception | None] = ()) -> None:
        self._errors = list(errors)
        self.writes: list[tuple[bytes, int]] = []

    def write(self, data: bytes, timeout: int) -> None:
        if self._errors:
            error = self._errors.pop(0)
            if error is not None:
                raise error
        self.writes.append((bytes(data), timeout))


class FakeInto:
    """假的收端点：read 记下要读多少字节，按顺序返回给定的字节，遇到异常就抛。"""

    def __init__(self, results: Sequence[bytes | Exception]) -> None:
        self._results = list(results)
        self.sizes: list[int] = []
        self.timeouts: list[int] = []

    def read(self, size: int, timeout: int) -> bytes:
        self.sizes.append(size)
        self.timeouts.append(timeout)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


TIMEOUT_MS = 1234


class UsbHarness:
    """不调 __init__ 建的 USB 连接，加上 _reconnect 被调了几次。"""

    def __init__(self, connection: Any, out: FakeOut, into: FakeInto) -> None:
        self.connection = connection
        self.out = out
        self.into = into
        self.reconnects = 0


def make_usb(
    monkeypatch: pytest.MonkeyPatch,
    *,
    errors: Sequence[Exception | None] = (),
    results: Sequence[bytes | Exception] = (),
) -> UsbHarness:
    """不调 __init__，直接放上假端点和 timeout_ms；time.sleep 不等待，_reconnect 只记次数。"""
    connection = object.__new__(_UsbConnection)
    out = FakeOut(errors)
    into = FakeInto(results)
    connection.out = out
    connection.into = into
    connection.timeout_ms = TIMEOUT_MS
    harness = UsbHarness(connection, out, into)

    def reconnect() -> None:
        harness.reconnects += 1

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(connection, "_reconnect", reconnect)
    return harness


def test_usb_send_writes_length_plus_two_then_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """send("click A")：先写 4 字节小端的 9（命令长度 7 加 2），再写命令本身；两次写用的超时都是 timeout_ms。"""
    usb_ = make_usb(monkeypatch)
    usb_.connection.send("click A")
    assert usb_.out.writes == [
        (struct.pack("<I", 9), TIMEOUT_MS),
        (b"click A", TIMEOUT_MS),
    ]


def test_usb_request_reads_length_then_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """request：发出命令，先读 4 字节长度，再读这么多字节的数据并返回；读用的超时是 timeout_ms。"""
    usb_ = make_usb(monkeypatch, results=[struct.pack("<I", 3), b"\x01\x02\x03"])
    assert usb_.connection.request("peek 0x10 0x3") == b"\x01\x02\x03"
    assert usb_.out.writes[-1][0] == b"peek 0x10 0x3"
    assert usb_.into.sizes == [4, 3]
    assert usb_.into.timeouts == [TIMEOUT_MS, TIMEOUT_MS]


def test_usb_request_keeps_reading_until_all_data_arrived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：长度是 5，数据分两次到达（2 字节、3 字节）：读满为止，返回拼好的 5 字节；第二次只要剩下的 3 字节。"""
    usb_ = make_usb(monkeypatch, results=[struct.pack("<I", 5), b"ab", b"cde"])
    assert usb_.connection.request("pixelPeek") == b"abcde"
    assert usb_.into.sizes == [4, 5, 3]


def test_usb_send_reconnects_once_and_resends_when_first_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send：第一次写抛 usb.core.USBError，重连一次，再把长度和命令都发一遍。"""
    usb_ = make_usb(monkeypatch, errors=[usb.core.USBError("断了")])
    usb_.connection.send("click A")
    assert usb_.reconnects == 1
    assert [data for data, _ in usb_.out.writes] == [struct.pack("<I", 9), b"click A"]


def test_usb_request_reconnects_and_asks_again_after_one_read_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：读返回时抛一次 USBError，重连 1 次后重发命令，第二次读成功就返回数据。"""
    usb_ = make_usb(
        monkeypatch,
        results=[usb.core.USBError("断了"), struct.pack("<I", 2), b"\x0a\x0b"],
    )
    assert usb_.connection.request("pixelPeek") == b"\x0a\x0b"
    assert usb_.reconnects == 1
    assert [data for data, _ in usb_.out.writes].count(b"pixelPeek") == 2


def test_usb_request_raises_connection_error_when_read_fails_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request：读返回时 into.read 连着两次抛 USBError，抛 ConnectionError，报错里有「反复断开」，_reconnect 被调了 1 次。"""
    usb_ = make_usb(monkeypatch, results=[usb.core.USBError("断了"), usb.core.USBError("又断了")])
    with pytest.raises(ConnectionError, match="反复断开"):
        usb_.connection.request("pixelPeek")
    assert usb_.reconnects == 1


def test_usb_title_id_returns_empty_string_when_read_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """title_id()：读超时（usb.core.USBTimeoutError，没有游戏在运行）返回空字符串；发出的命令是 getTitleID。"""
    usb_ = make_usb(monkeypatch, results=[usb.core.USBTimeoutError("超时")])
    assert usb_.connection.title_id() == ""
    assert usb_.out.writes[-1][0] == b"getTitleID"


def test_usb_title_id_returns_16_digit_uppercase_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    """title_id()：返回的 8 字节按小端算，写成 16 位大写十六进制。"""
    usb_ = make_usb(
        monkeypatch,
        results=[struct.pack("<I", 8), struct.pack("<Q", 0x0100ABF008968000)],
    )
    assert usb_.connection.title_id() == "0100ABF008968000"


def test_usb_open_raises_connection_error_when_device_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """usb.core.find 返回 None：_open 抛 ConnectionError，报错里有「找不到 usb-botbase」。"""
    usb_ = make_usb(monkeypatch)
    monkeypatch.setattr(usb.core, "find", lambda **kwargs: None)
    with pytest.raises(ConnectionError, match="找不到 usb-botbase"):
        usb_.connection._open()


def test_usb_pointer_little_endian_is_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """USB 连接的 pointer_little_endian 是 True。"""
    assert make_usb(monkeypatch).connection.pointer_little_endian is True


# ---- USB 连接的创建和关闭：要调 __init__


class FakeEndpoint:
    """假的端点，只有地址。"""

    def __init__(self, address: int) -> None:
        self.bEndpointAddress = address


class FakeUsbDevice:
    """假 USB 设备：记下 reset() 被调了几次，set_configuration() 什么都不做。"""

    def __init__(self) -> None:
        self.reset_calls = 0
        self.out = FakeEndpoint(0x01)
        self.into = FakeEndpoint(0x81)

    def reset(self) -> None:
        self.reset_calls += 1

    def set_configuration(self) -> None:
        pass

    def get_active_configuration(self) -> dict[tuple[int, int], list[FakeEndpoint]]:
        return {(0, 0): [self.out, self.into]}


@pytest.fixture
def usb_device(monkeypatch: pytest.MonkeyPatch) -> FakeUsbDevice:
    """usb.core.find 换成返回这个假设备的函数，usb.util.dispose_resources 换成什么都不做。"""
    device = FakeUsbDevice()
    monkeypatch.setattr(usb.core, "find", lambda **kwargs: device)
    monkeypatch.setattr(usb.util, "dispose_resources", lambda dev: None)
    return device


def test_usb_init_resets_device_once_then_opens_it(usb_device: FakeUsbDevice) -> None:
    """创建 USB 连接后：reset() 被调了 1 次（创建时先复位一次再打开），发和收的端点都有。"""
    connection = _UsbConnection()
    assert usb_device.reset_calls == 1
    assert connection.out is usb_device.out
    assert connection.into is usb_device.into


def test_usb_close_resets_once_and_clears_device_and_second_close_is_harmless(
    usb_device: FakeUsbDevice,
) -> None:
    """close()：调了一次 reset()，之后 device 是 None；再调一次 close() 不出错，reset() 的次数不再增加。"""
    connection = _UsbConnection()
    before = usb_device.reset_calls
    connection.close()
    assert usb_device.reset_calls == before + 1
    assert connection.device is None
    connection.close()
    assert usb_device.reset_calls == before + 1


def test_usb_init_raises_connection_error_when_device_never_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """usb.core.find 一直返回 None：创建时抛 ConnectionError。time.monotonic 每次调用往后走 3 秒，不真的等。"""
    clock = [0.0]

    def monotonic() -> float:
        clock[0] += 3.0
        return clock[0]

    monkeypatch.setattr(usb.core, "find", lambda **kwargs: None)
    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    with pytest.raises(ConnectionError, match="找不到 usb-botbase"):
        _UsbConnection()


def test_usb_open_raises_connection_error_when_endpoints_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """找到了设备，但接口上没有收发端点：_open 抛 ConnectionError，报错里有「没有找到收发端点」。"""
    device = FakeUsbDevice()
    monkeypatch.setattr(device, "get_active_configuration", lambda: {(0, 0): []})
    monkeypatch.setattr(usb.core, "find", lambda **kwargs: device)
    connection = object.__new__(_UsbConnection)
    with pytest.raises(ConnectionError, match="没有找到收发端点"):
        connection._open()


def test_usb_reconnect_resets_and_opens_device_again(usb_device: FakeUsbDevice) -> None:
    """_reconnect：先关掉（复位一次），设备还在，马上重新打开：收发端点又都有了。"""
    connection = _UsbConnection()
    before = usb_device.reset_calls
    connection._reconnect()
    assert usb_device.reset_calls == before + 1
    assert connection.out is usb_device.out
    assert connection.into is usb_device.into


def test_usb_reconnect_waits_until_device_shows_up_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """_reconnect：第一次找不到设备，过一会儿又出现了：等一下再找，重连成功。"""
    device = FakeUsbDevice()
    answers: list[FakeUsbDevice | None] = [device, device, None, device]
    sleeps: list[float] = []
    monkeypatch.setattr(usb.core, "find", lambda **kwargs: answers.pop(0))
    monkeypatch.setattr(usb.util, "dispose_resources", lambda dev: None)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    connection = _UsbConnection()
    connection._reconnect()
    assert connection.out is device.out
    assert len(sleeps) == 1


def test_usb_reconnect_raises_connection_error_when_device_never_shows_up(
    usb_device: FakeUsbDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_reconnect：一直找不到设备（time.monotonic 每次往后走 40 秒，超过 30 秒）：抛 ConnectionError，
    报错里有「30 秒内没有重新连上」。
    """
    connection = _UsbConnection()
    clock = [0.0]

    def monotonic() -> float:
        clock[0] += 40.0
        return clock[0]

    monkeypatch.setattr(usb.core, "find", lambda **kwargs: None)
    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    with pytest.raises(ConnectionError, match="30 秒内没有重新连上"):
        connection._reconnect()


def test_usb_close_ignores_usb_errors_from_reset_and_dispose(
    usb_device: FakeUsbDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """close()：复位或者释放资源时抛 USBError（设备已经拔了）：不抛出来，device、端点都清成 None。"""
    connection = _UsbConnection()

    def broken(*args: object) -> None:
        raise usb.core.USBError("设备已经不在了")

    monkeypatch.setattr(usb_device, "reset", broken)
    monkeypatch.setattr(usb.util, "dispose_resources", broken)
    connection.close()
    assert connection.device is None
    assert connection.out is None
    assert connection.into is None
