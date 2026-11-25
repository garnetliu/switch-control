"""control_switch.device.botbase：Botbase 发出的命令文本，和 connect_botbase 建连接、注册退出处理。

Botbase 用一个假连接（tests/device/conftest.py 的 make_connection）：记下发出的命令，
按命令返回给定的字节。所有等待的时间（click 的 delay、stick 的 hold）都传 0。
connect_botbase 不连真机：两个连接类换成假的，atexit.register、signal.signal 换成记下参数的函数。
"""

import atexit
import importlib
import signal
from collections.abc import Callable
from types import ModuleType
from typing import Any, ClassVar

import pytest

from control_switch.device.botbase import Botbase, connect_botbase
from control_switch.settings import build_settings

botbase_module: ModuleType = importlib.import_module("control_switch.device.botbase")

ConnectionFactory = Callable[..., Any]


def test_click_sends_click_command(make_connection: ConnectionFactory) -> None:
    """click("A", 0)：发出 "click A"，没有别的命令。"""
    connection = make_connection()
    Botbase(connection).click("A", 0)
    assert connection.sent == ["click A"]
    assert connection.requested == []


def test_stick_sends_push_then_center(make_connection: ConnectionFactory) -> None:
    """stick("LEFT", 0x7FFF, -0x7FFF, 0)：先发推摇杆的命令（负数写成 -0x...），再发回中的命令。"""
    connection = make_connection()
    Botbase(connection).stick("LEFT", 0x7FFF, -0x7FFF, 0)
    assert connection.sent == ["setStick LEFT 0x7fff -0x7fff", "setStick LEFT 0x0 0x0"]


def test_press_sends_press_command(make_connection: ConnectionFactory) -> None:
    """press("A")：只发 "press A"，不发 release，没有别的命令。"""
    connection = make_connection()
    Botbase(connection).press("A")
    assert connection.sent == ["press A"]
    assert connection.requested == []


def test_release_sends_release_command(make_connection: ConnectionFactory) -> None:
    """release("A")：只发 "release A"，没有别的命令。"""
    connection = make_connection()
    Botbase(connection).release("A")
    assert connection.sent == ["release A"]
    assert connection.requested == []


def test_press_stick_sends_only_the_push_command(make_connection: ConnectionFactory) -> None:
    """press_stick("RIGHT", 0x10, 0)：只发推摇杆的命令，不回中。"""
    connection = make_connection()
    Botbase(connection).press_stick("RIGHT", 0x10, 0)
    assert connection.sent == ["setStick RIGHT 0x10 0x0"]


def test_release_stick_sends_center_command(make_connection: ConnectionFactory) -> None:
    """release_stick("RIGHT")：发回中的命令。"""
    connection = make_connection()
    Botbase(connection).release_stick("RIGHT")
    assert connection.sent == ["setStick RIGHT 0x0 0x0"]


def test_pixel_peek_returns_data_of_first_request(make_connection: ConnectionFactory) -> None:
    """pixel_peek：第一次就有数据时返回它，只请求了一次。"""
    connection = make_connection({"pixelPeek": [b"JPEG"]})
    assert Botbase(connection).pixel_peek() == b"JPEG"
    assert connection.requested == ["pixelPeek"]


def test_pixel_peek_retries_when_first_reply_is_empty(make_connection: ConnectionFactory) -> None:
    """pixel_peek：第一次返回空、第二次有数据时，返回第二次的数据，一共请求了两次。"""
    connection = make_connection({"pixelPeek": [b"", b"JPEG"]})
    assert Botbase(connection).pixel_peek() == b"JPEG"
    assert connection.requested == ["pixelPeek", "pixelPeek"]


def test_pixel_peek_raises_connection_error_after_three_empty_replies(
    make_connection: ConnectionFactory,
) -> None:
    """pixel_peek：连着三次都是空，抛 ConnectionError，一共请求了三次。"""
    connection = make_connection({"pixelPeek": [b""]})
    with pytest.raises(ConnectionError):
        Botbase(connection).pixel_peek()
    assert connection.requested == ["pixelPeek"] * 3


def test_title_id_returns_what_the_connection_returns(make_connection: ConnectionFactory) -> None:
    """title_id：返回连接的 title_id()，不发 send 和 request。"""
    connection = make_connection()
    assert Botbase(connection).title_id() == "0100ABF008968000"
    assert connection.sent == []
    assert connection.requested == []


def test_peek_requests_offset_and_size_in_hex(make_connection: ConnectionFactory) -> None:
    """peek(0x10, 0x4)：请求的命令是 "peek 0x10 0x4"，返回连接给的字节。"""
    connection = make_connection({"peek 0x10 0x4": [b"\x01\x02\x03\x04"]})
    assert Botbase(connection).peek(0x10, 0x4) == b"\x01\x02\x03\x04"
    assert connection.requested == ["peek 0x10 0x4"]


def test_peek_main_requests_peek_main_command(make_connection: ConnectionFactory) -> None:
    """peek_main(0x20, 0x8)：请求的命令是 "peekMain 0x20 0x8"。"""
    connection = make_connection({"peekMain 0x20 0x8": [b"\xaa"]})
    assert Botbase(connection).peek_main(0x20, 0x8) == b"\xaa"
    assert connection.requested == ["peekMain 0x20 0x8"]


def test_peek_absolute_requests_address_and_size_in_hex(
    make_connection: ConnectionFactory,
) -> None:
    """peek_absolute(0x45067A98, 0x20)：请求的命令是 "peekAbsolute 0x45067a98 0x20"。"""
    connection = make_connection({"peekAbsolute 0x45067a98 0x20": [b"\x07"]})
    assert Botbase(connection).peek_absolute(0x45067A98, 0x20) == b"\x07"
    assert connection.requested == ["peekAbsolute 0x45067a98 0x20"]


def test_pointer_peek_requests_size_then_jumps_in_hex(make_connection: ConnectionFactory) -> None:
    """pointer_peek([0x10, 0x20, 0x30], 0x4)：请求的命令是 "pointerPeek 0x4 0x10 0x20 0x30"。"""
    connection = make_connection({"pointerPeek 0x4 0x10 0x20 0x30": [b"\x09\x08\x07\x06"]})
    assert Botbase(connection).pointer_peek([0x10, 0x20, 0x30], 0x4) == b"\x09\x08\x07\x06"
    assert connection.requested == ["pointerPeek 0x4 0x10 0x20 0x30"]


def test_pointer_all_reads_big_endian_when_connection_is_not_little_endian(
    make_connection: ConnectionFactory,
) -> None:
    """pointer_all：连接的 pointer_little_endian 是 False 时，回的 8 字节按大端算。

    请求的命令是 "pointerAll 0x10 0x20"。
    """
    reply = b"\x10\x02\x00\x00\x00\x00\x00\x00"
    connection = make_connection({"pointerAll 0x10 0x20": [reply]}, pointer_little_endian=False)
    assert Botbase(connection).pointer_all([0x10, 0x20]) == 0x1002000000000000
    assert connection.requested == ["pointerAll 0x10 0x20"]


def test_pointer_all_reads_little_endian_when_connection_is_little_endian(
    make_connection: ConnectionFactory,
) -> None:
    """pointer_all：连接的 pointer_little_endian 是 True 时，同样的 8 字节按小端算。"""
    reply = b"\x10\x02\x00\x00\x00\x00\x00\x00"
    connection = make_connection({"pointerAll 0x10 0x20": [reply]}, pointer_little_endian=True)
    assert Botbase(connection).pointer_all([0x10, 0x20]) == 0x210


def test_poke_absolute_sends_data_as_hex(make_connection: ConnectionFactory) -> None:
    """poke_absolute(0x1000, b"\\x01\\xab")：发出的命令是 "pokeAbsolute 0x1000 0x01ab"，数据是十六进制。"""
    connection = make_connection()
    Botbase(connection).poke_absolute(0x1000, b"\x01\xab")
    assert connection.sent == ["pokeAbsolute 0x1000 0x01ab"]
    assert connection.requested == []


def test_close_twice_does_not_raise(make_connection: ConnectionFactory) -> None:
    """close() 调两次不出错。"""
    botbase = Botbase(make_connection())
    botbase.close()
    botbase.close()


class FakeWifi:
    """假的 WiFi 连接类：记下创建时的参数，close() 记下调用次数。"""

    created: ClassVar[list["FakeWifi"]] = []

    def __init__(self, host: str, port: int = 6000, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.close_calls = 0
        FakeWifi.created.append(self)

    def close(self) -> None:
        self.close_calls += 1


class FakeUsb:
    """假的 USB 连接类：记下创建了几个，close() 记下调用次数。"""

    created: ClassVar[list["FakeUsb"]] = []

    def __init__(self, timeout: float = 5.0) -> None:
        self.close_calls = 0
        FakeUsb.created.append(self)

    def close(self) -> None:
        self.close_calls += 1


class Registrations:
    """atexit.register 和 signal.signal 收到的参数。"""

    def __init__(self) -> None:
        self.atexit: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []
        self.signals: dict[int, Callable[..., Any]] = {}


@pytest.fixture
def registrations(monkeypatch: pytest.MonkeyPatch) -> Registrations:
    """两个连接类换成假的，atexit.register、signal.signal 换成记下参数的函数。"""
    recorded = Registrations()
    FakeWifi.created = []
    FakeUsb.created = []

    def fake_register(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Callable[..., Any]:
        recorded.atexit.append((func, args, kwargs))
        return func

    def fake_signal(signum: int, handler: Callable[..., Any]) -> None:
        recorded.signals[signum] = handler

    monkeypatch.setattr(botbase_module, "_WifiConnection", FakeWifi)
    monkeypatch.setattr(botbase_module, "_UsbConnection", FakeUsb)
    monkeypatch.setattr(atexit, "register", fake_register)
    monkeypatch.setattr(signal, "signal", fake_signal)
    return recorded


def test_connect_botbase_with_usb_creates_usb_connection(registrations: Registrations) -> None:
    """switch_connection 是 usb：建了一个 USB 连接，没有建 WiFi 连接，返回 Botbase。"""
    botbase = connect_botbase(build_settings({"connection": "usb"}))
    assert isinstance(botbase, Botbase)
    assert len(FakeUsb.created) == 1
    assert FakeWifi.created == []


@pytest.mark.parametrize("connection", [None, "wifi"])
def test_connect_botbase_with_wifi_creates_wifi_connection_from_ip_and_port(
    registrations: Registrations, connection: str | None
) -> None:
    """switch_connection 没写或是 wifi：建 WiFi 连接，用的是 switch_ip、switch_port（整数）。"""
    machine: dict[str, Any] = {"ip": "192.168.1.50", "port": 6001}
    if connection is not None:
        machine["connection"] = connection
    botbase = connect_botbase(build_settings(machine))
    assert isinstance(botbase, Botbase)
    assert len(FakeWifi.created) == 1
    assert (FakeWifi.created[0].host, FakeWifi.created[0].port) == ("192.168.1.50", 6001)
    assert FakeUsb.created == []


def test_connect_botbase_registers_exit_function_that_closes_the_botbase(
    registrations: Registrations,
) -> None:
    """connect_botbase：用 atexit 注册了一个退出时调用的函数，调用它会关掉返回的 Botbase（连接的 close 被调了）。"""
    botbase = connect_botbase(build_settings({"connection": "usb"}))
    assert isinstance(botbase, Botbase)
    assert len(registrations.atexit) == 1
    func, args, kwargs = registrations.atexit[0]
    assert FakeUsb.created[0].close_calls == 0
    func(*args, **kwargs)
    assert FakeUsb.created[0].close_calls == 1


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
def test_connect_botbase_registers_signal_handler_that_exits_with_128_plus_signal(
    registrations: Registrations, sig: signal.Signals
) -> None:
    """SIGTERM、SIGHUP 都注册了处理函数；调用处理函数抛 SystemExit，退出码是 128 加信号值。"""
    connect_botbase(build_settings({"connection": "usb"}))
    assert sig in registrations.signals
    with pytest.raises(SystemExit) as error:
        registrations.signals[sig](sig, None)
    assert error.value.code == 128 + sig


def test_connect_botbase_wifi_without_ip_raises_value_error_naming_switch_ip(
    registrations: Registrations,
) -> None:
    """WiFi 连接、有端口没有 ip（port = 6000）：抛 ValueError，报错里有 ip，两个连接类都没有被调用。"""
    with pytest.raises(ValueError) as error:
        connect_botbase(build_settings({"port": 6000}))
    assert "要写 ip" in str(error.value)
    assert FakeWifi.created == []
    assert FakeUsb.created == []


def test_connect_botbase_wifi_without_port_raises_value_error_naming_switch_port(
    registrations: Registrations,
) -> None:
    """WiFi 连接、有 ip 没有端口（ip = 192.168.1.2）：抛 ValueError，报错里有 port，两个连接类都没有被调用。"""
    with pytest.raises(ValueError) as error:
        connect_botbase(build_settings({"ip": "192.168.1.2"}))
    assert "要写 port" in str(error.value)
    assert FakeWifi.created == []
    assert FakeUsb.created == []
