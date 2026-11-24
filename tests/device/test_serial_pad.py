"""control_switch.device.serial_pad：用单片机（伊机控固件）按键。

用假串口，不打开真的串口：假串口记下每次 write 的字节、按事先给定的顺序返回 read 的字节
（用完返回 b""）、记下 close() 的次数。time.sleep 换成只记秒数、不等待的函数，
time.monotonic 换成跟着 sleep 往前走的假时钟。
"""

import time
from collections.abc import Sequence
from typing import Any

import pytest
import serial

from control_switch.device import Controller, DeviceCheckError
from control_switch.device.serial_pad import PRESS_TIME, SerialPad, open_serial_pad
from control_switch.settings import load_settings

OK = b"\xff"
BUSY = b"\xfe"
NEUTRAL = bytes([0x00, 0x00, 0x01, 0x08, 0x04, 0x02, 0x01, 0x80])
MIN_GAP = 0.03


def pack(raw: Sequence[int]) -> bytes:
    """约定里的打包算法：每 7 位一组，最后一个字节最高位置 1。"""
    n = 0
    bits = 0
    out: list[int] = []
    for b in raw:
        n = (n << 8) | b
        bits += 8
        while bits >= 7:
            bits -= 7
            out.append((n >> bits) & 0x7F)
            n &= (1 << bits) - 1
    out[-1] |= 0x80
    return bytes(out)


def unpack(packet: bytes) -> list[int]:
    """把 8 个字节还原成 7 个字节：[按钮高, 按钮低, HAT, LX, LY, RX, RY]。"""
    assert len(packet) == 8
    assert packet[-1] & 0x80
    value = 0
    for b in packet:
        value = (value << 7) | (b & 0x7F)
    return list(value.to_bytes(7, "big"))


class Clock:
    """假时钟和假 sleep：sleep 只记秒数并让时钟往前走；events 按顺序记下 sleep 和 write。"""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []
        self.events: list[tuple[str, Any]] = []

    def monotonic(self) -> float:
        """假的 time.monotonic。"""
        return self.now

    def sleep(self, seconds: float) -> None:
        """假的 time.sleep：记下秒数，时钟往前走。"""
        self.sleeps.append(seconds)
        self.events.append(("sleep", seconds))
        self.now += seconds


class FakeSerial:
    """假串口：符合 SerialPort。write 记下字节和写入时的假时钟，read 按顺序返回。"""

    def __init__(self, clock: Clock, replies: Sequence[bytes] = (), *, fail_write: bool = False):
        self.clock = clock
        self.replies = list(replies)
        self.fail_write = fail_write
        self.writes: list[bytes] = []
        self.write_times: list[float] = []
        self.close_calls = 0
        self.reset_calls = 0

    def write(self, data: bytes) -> int | None:
        """记下字节。fail_write 时抛 OSError。"""
        if self.fail_write:
            raise OSError("写不进去")
        self.writes.append(data)
        self.write_times.append(self.clock.now)
        self.clock.events.append(("write", data))
        return len(data)

    def read(self, size: int) -> bytes:
        """按事先给定的顺序返回，用完返回 b""。"""
        assert size == 1
        return self.replies.pop(0) if self.replies else b""

    def reset_input_buffer(self) -> None:
        """记下调用次数。"""
        self.reset_calls += 1

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """time.sleep、time.monotonic 换成假的。"""
    fake = Clock()
    monkeypatch.setattr(time, "sleep", fake.sleep)
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    return fake


def make_pad(clock: Clock, replies: Sequence[bytes] | None = None) -> tuple[SerialPad, FakeSerial]:
    """建一个 SerialPad，默认每个报文都回 FF。"""
    port = FakeSerial(clock, replies if replies is not None else [OK] * 20)
    return SerialPad(port), port


# ---------- 打包 ----------


def test_neutral_packet_is_the_documented_bytes(clock: Clock) -> None:
    """click 的松开报文（中立报文）是 00 00 01 08 04 02 01 80。"""
    pad, port = make_pad(clock)
    pad.click("A", 0)
    assert port.writes[-1] == NEUTRAL


def test_pack_reference_matches_documented_neutral() -> None:
    """测试里的参考打包算法对中立的 7 个字节给出文档里的 8 个字节。"""
    assert pack([0, 0, 8, 128, 128, 128, 128]) == NEUTRAL


def test_click_home_packet_is_packed_from_home_bit(clock: Clock) -> None:
    """click("HOME")：按下的报文是对 [0x10, 0x00, 8, 128, 128, 128, 128] 打包的结果。"""
    pad, port = make_pad(clock)
    pad.click("HOME", 0)
    assert port.writes[0] == pack([0x10, 0x00, 8, 128, 128, 128, 128])


# ---------- click ----------


def test_click_a_writes_a_packet_then_neutral_with_press_time_between(clock: Clock) -> None:
    """click("A", 0)：先写 A 的报文，再写中立报文；两次之间 sleep 了 PRESS_TIME。"""
    pad, port = make_pad(clock)
    pad.click("A", 0)
    assert port.writes == [pack([0x00, 0x04, 8, 128, 128, 128, 128]), NEUTRAL]
    first, second = (i for i, e in enumerate(clock.events) if e[0] == "write")
    assert clock.events[first + 1 : second] == [("sleep", PRESS_TIME)]


def test_press_time_is_a_tenth_of_a_second() -> None:
    """模块常量 PRESS_TIME 是 0.1 秒。"""
    assert PRESS_TIME == 0.1


def test_click_waits_delay_after_neutral(clock: Clock) -> None:
    """click("A", 0.5)：中立报文之后等了 0.5 秒。"""
    pad, _ = make_pad(clock)
    pad.click("A", 0.5)
    assert clock.events[-1] == ("sleep", 0.5)


def test_click_ddown_packet_has_hat_4_and_no_buttons(clock: Clock) -> None:
    """click("DDOWN", 0)：报文 HAT 是 4、按钮是 0。"""
    pad, port = make_pad(clock)
    pad.click("DDOWN", 0)
    assert unpack(port.writes[0]) == [0, 0, 4, 128, 128, 128, 128]


def test_click_unknown_button_raises_value_error_and_writes_nothing(clock: Clock) -> None:
    """不认识的按键名：抛 ValueError，报错里有按键名，没有写任何字节。"""
    pad, port = make_pad(clock)
    with pytest.raises(ValueError) as error:
        pad.click("TURBO", 0)
    assert "TURBO" in str(error.value)
    assert port.writes == []


# ---------- stick ----------


def test_stick_left_up_full_gives_ly_1_and_lx_centered(clock: Clock) -> None:
    """stick("LEFT", 0, 0x7FFF, 1.0)：LY 是 1（y 正数向上，轴值变小）、LX 是 128。"""
    pad, port = make_pad(clock)
    pad.stick("LEFT", 0, 0x7FFF, 1.0)
    assert unpack(port.writes[0]) == [0, 0, 8, 128, 1, 128, 128]


def test_stick_left_x_negative_full_gives_lx_1(clock: Clock) -> None:
    """stick("LEFT", -0x7FFF, 0, 0.5)：LX 是 1，LY 是 128。"""
    pad, port = make_pad(clock)
    pad.stick("LEFT", -0x7FFF, 0, 0.5)
    assert unpack(port.writes[0]) == [0, 0, 8, 1, 128, 128, 128]


def test_stick_sends_neutral_after_waiting_hold(clock: Clock) -> None:
    """stick("LEFT", 0, 0x7FFF, 1.0)：之后发了中立报文，两个报文中间 sleep 了 hold（1.0）。"""
    pad, port = make_pad(clock)
    pad.stick("LEFT", 0, 0x7FFF, 1.0)
    assert len(port.writes) == 2
    assert port.writes[1] == NEUTRAL
    first, second = (i for i, e in enumerate(clock.events) if e[0] == "write")
    assert clock.events[first + 1 : second] == [("sleep", 1.0)]


def test_stick_right_changes_rx_and_ry(clock: Clock) -> None:
    """stick("RIGHT", 0x7FFF, 0x7FFF, 0.5)：改的是 RX=255、RY=1，LX、LY 保持 128。"""
    pad, port = make_pad(clock)
    pad.stick("RIGHT", 0x7FFF, 0x7FFF, 0.5)
    assert unpack(port.writes[0]) == [0, 0, 8, 128, 128, 255, 1]


def test_stick_y_negative_full_gives_ly_255(clock: Clock) -> None:
    """stick("LEFT", 0, -0x7FFF, 0.5)：y 负数向下，LY 是 255。"""
    pad, port = make_pad(clock)
    pad.stick("LEFT", 0, -0x7FFF, 0.5)
    assert unpack(port.writes[0])[4] == 255


def test_stick_unknown_side_raises_value_error_and_writes_nothing(clock: Clock) -> None:
    """side 不是 LEFT、RIGHT：抛 ValueError，没有写任何字节。"""
    pad, port = make_pad(clock)
    with pytest.raises(ValueError) as error:
        pad.stick("MIDDLE", 0, 0, 0.5)
    assert "MIDDLE" in str(error.value)
    assert port.writes == []


# ---------- 回应 ----------


def test_busy_reply_raises_connection_error_saying_script_is_running(clock: Clock) -> None:
    """报文回 FE：抛 ConnectionError，报错里说单片机在跑脚本。"""
    pad, _ = make_pad(clock, [BUSY])
    with pytest.raises(ConnectionError) as error:
        pad.click("A", 0)
    assert "脚本" in str(error.value)


def test_empty_reply_raises_connection_error(clock: Clock) -> None:
    """报文读不到回应（超时返回空）：抛 ConnectionError。"""
    pad, _ = make_pad(clock, [])
    with pytest.raises(ConnectionError):
        pad.click("A", 0)


def test_other_reply_raises_connection_error_naming_the_byte(clock: Clock) -> None:
    """报文回 00（既不是 FF 也不是 FE）：抛 ConnectionError，报错里有收到的字节。"""
    pad, _ = make_pad(clock, [b"\x00"])
    with pytest.raises(ConnectionError) as error:
        pad.click("A", 0)
    assert "00" in str(error.value)


# ---------- 间隔 ----------


def test_consecutive_clicks_keep_at_least_30ms_between_every_two_packets(clock: Clock) -> None:
    """连着两次 click("A", 0)：每两个报文之间在假时钟上至少隔了 30 ms。"""
    pad, port = make_pad(clock)
    pad.click("A", 0)
    pad.click("A", 0)
    assert len(port.write_times) == 4
    gaps = [b - a for a, b in zip(port.write_times, port.write_times[1:], strict=False)]
    assert all(gap >= MIN_GAP - 1e-9 for gap in gaps)


def test_second_click_waits_when_previous_neutral_was_just_sent(clock: Clock) -> None:
    """click("A", 0) 的中立报文刚发完就再发按下的报文：先 sleep 补够 30 ms，才写第二个按下报文。"""
    pad, port = make_pad(clock)
    pad.click("A", 0)
    sleeps_before = len(clock.sleeps)
    pad.click("A", 0)
    assert sum(clock.sleeps[sleeps_before:]) >= MIN_GAP - 1e-9
    assert port.write_times[2] - port.write_times[1] >= MIN_GAP - 1e-9


# ---------- press / release / press_stick / release_stick ----------

A_ONLY = [0x00, 0x04, 8, 128, 128, 128, 128]


def test_press_a_writes_packet_with_a_button(clock: Clock) -> None:
    """press("A")：写出的报文按钮是 A（0x04），十字键居中、摇杆居中；只写了这一个报文。"""
    pad, port = make_pad(clock)
    pad.press("A")
    assert [unpack(packet) for packet in port.writes] == [A_ONLY]


def test_click_while_a_held_presses_a_and_b_then_releases_back_to_a(clock: Clock) -> None:
    """press("A") 之后 click("B", 0)：按下的报文按钮是 A|B（0x06），松开的报文按钮是 A，不是中立。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.click("B", 0)
    assert [unpack(packet) for packet in port.writes[1:]] == [
        [0x00, 0x06, 8, 128, 128, 128, 128],
        A_ONLY,
    ]


def test_click_hat_while_a_held_keeps_a_in_both_packets(clock: Clock) -> None:
    """press("A") 之后 click("DDOWN", 0)：按下的报文是 A 加十字键下（HAT 4），松开的报文是 A、十字键居中。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.click("DDOWN", 0)
    assert [unpack(packet) for packet in port.writes[1:]] == [
        [0x00, 0x04, 4, 128, 128, 128, 128],
        A_ONLY,
    ]


def test_press_two_buttons_combines_them(clock: Clock) -> None:
    """press("A")、press("LSTICK")：第二个报文的按钮是 A|LSTICK（0x0404）。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.press("LSTICK")
    assert unpack(port.writes[-1]) == [0x04, 0x04, 8, 128, 128, 128, 128]


def test_press_stick_left_up_then_click_carries_ly_1(clock: Clock) -> None:
    """press_stick("LEFT", 0, 0x7FFF) 之后 click("A", 0)：按下和松开的两个报文 LY 都是 1，
    按下的报文按钮是 A，松开的报文按钮是 0。
    """
    pad, port = make_pad(clock)
    pad.press_stick("LEFT", 0, 0x7FFF)
    pad.click("A", 0)
    assert [unpack(packet) for packet in port.writes[1:]] == [
        [0x00, 0x04, 8, 128, 1, 128, 128],
        [0x00, 0x00, 8, 128, 1, 128, 128],
    ]


def test_press_stick_writes_packet_with_stick_position(clock: Clock) -> None:
    """press_stick("RIGHT", 0x7FFF, 0)：写出的报文 RX=255、RY=128，LX、LY 保持 128。"""
    pad, port = make_pad(clock)
    pad.press_stick("RIGHT", 0x7FFF, 0)
    assert unpack(port.writes[-1]) == [0, 0, 8, 128, 128, 255, 128]


def test_stick_while_other_stick_held_keeps_the_held_one(clock: Clock) -> None:
    """press_stick("RIGHT", 0x7FFF, 0) 之后 stick("LEFT", 0, 0x7FFF, 0)：
    推的报文 LY=1 且 RX 仍是 255；回中的报文回到「按住的状态」，LY=128、RX 仍是 255，不是全中立。
    """
    pad, port = make_pad(clock)
    pad.press_stick("RIGHT", 0x7FFF, 0)
    pad.stick("LEFT", 0, 0x7FFF, 0)
    assert [unpack(packet) for packet in port.writes[1:]] == [
        [0, 0, 8, 128, 1, 255, 128],
        [0, 0, 8, 128, 128, 255, 128],
    ]


def test_release_button_and_stick_return_to_neutral(clock: Clock) -> None:
    """press("A")、press_stick("LEFT", 0, 0x7FFF) 之后 release("A")、release_stick("LEFT")：
    最后写出的报文是中立报文；再 click("B", 0)，松开的报文也是中立。
    """
    pad, port = make_pad(clock)
    pad.press("A")
    pad.press_stick("LEFT", 0, 0x7FFF)
    pad.release("A")
    pad.release_stick("LEFT")
    assert port.writes[-1] == NEUTRAL
    pad.click("B", 0)
    assert [unpack(packet) for packet in port.writes[-2:]] == [
        [0x00, 0x02, 8, 128, 128, 128, 128],
        [0x00, 0x00, 8, 128, 128, 128, 128],
    ]


def test_release_a_keeps_held_stick(clock: Clock) -> None:
    """press("A")、press_stick("LEFT", 0, 0x7FFF) 之后只 release("A")：最后的报文按钮是 0，LY 仍是 1。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.press_stick("LEFT", 0, 0x7FFF)
    pad.release("A")
    assert unpack(port.writes[-1]) == [0, 0, 8, 128, 1, 128, 128]


def test_release_stick_keeps_held_button(clock: Clock) -> None:
    """press("A")、press_stick("LEFT", 0, 0x7FFF) 之后只 release_stick("LEFT")：最后的报文按钮仍是 A，LY 回到 128。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.press_stick("LEFT", 0, 0x7FFF)
    pad.release_stick("LEFT")
    assert unpack(port.writes[-1]) == A_ONLY


def test_close_while_holding_sends_neutral_not_held_state(clock: Clock) -> None:
    """press("A")、press_stick("LEFT", 0, 0x7FFF) 之后 close()：最后一个报文是全中立，串口关了一次。"""
    pad, port = make_pad(clock)
    pad.press("A")
    pad.press_stick("LEFT", 0, 0x7FFF)
    pad.close()
    assert port.writes[-1] == NEUTRAL
    assert port.close_calls == 1


# ---------- close ----------


def test_close_sends_neutral_and_closes_port(clock: Clock) -> None:
    """close()：发了一次中立报文，关了串口。"""
    pad, port = make_pad(clock)
    pad.close()
    assert port.writes == [NEUTRAL]
    assert port.close_calls == 1


def test_close_twice_closes_port_once_without_error(clock: Clock) -> None:
    """close() 调两次：串口只关一次，不出错。"""
    pad, port = make_pad(clock)
    pad.close()
    pad.close()
    assert port.close_calls == 1


def test_close_still_closes_port_when_neutral_write_fails(clock: Clock) -> None:
    """发中立报文时 write 抛 OSError：close() 不出错，串口照样关了。"""
    port = FakeSerial(clock, [OK], fail_write=True)
    SerialPad(port).close()
    assert port.close_calls == 1


def test_close_still_closes_port_when_neutral_gets_no_reply(clock: Clock) -> None:
    """中立报文读不到回应（ConnectionError）：close() 不出错，串口照样关了。"""
    pad, port = make_pad(clock, [])
    pad.close()
    assert port.close_calls == 1


def test_serial_pad_is_a_controller(clock: Clock) -> None:
    """SerialPad 的实例是 Controller。"""
    pad, _ = make_pad(clock)
    assert isinstance(pad, Controller)


# ---------- open_serial_pad ----------


class Opener:
    """假的 serial.Serial：记下收到的参数，返回同一个假串口，或抛错。"""

    def __init__(self, port: FakeSerial, error: Exception | None = None) -> None:
        self.port = port
        self.error = error
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeSerial:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.port


def install_opener(
    monkeypatch: pytest.MonkeyPatch,
    clock: Clock,
    replies: Sequence[bytes],
    error: Exception | None = None,
) -> Opener:
    """把 control_switch.device.serial_pad.serial.Serial 换成返回假串口的函数。"""
    opener = Opener(FakeSerial(clock, replies), error)
    monkeypatch.setattr("control_switch.device.serial_pad.serial.Serial", opener)
    return opener


def test_open_serial_pad_uses_port_and_baud_then_handshakes_and_stops_script(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """正常：用 SERIAL_PORT、SERIAL_BAUD 和 timeout=0.5 打开；先写 A5 A5 81、再写 A5 84；
    返回的是 SerialPad，串口没有被关。
    """
    opener = install_opener(monkeypatch, clock, [b"\x80", b"\x83"])
    settings = load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1", "SERIAL_BAUD": "115200"})
    pad = open_serial_pad(settings)
    assert isinstance(pad, SerialPad)
    assert opener.calls == [(("/dev/cu.usbserial-1", 115200), {"timeout": 0.5})]
    assert opener.port.writes == [b"\xa5\xa5\x81", b"\xa5\x84"]
    assert opener.port.close_calls == 0


def test_open_serial_pad_uses_default_baud_9600(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """SERIAL_BAUD 没写：用 9600 打开。"""
    opener = install_opener(monkeypatch, clock, [b"\x80", b"\x83"])
    open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    assert opener.calls[0][0] == ("/dev/cu.usbserial-1", 9600)


def test_open_serial_pad_without_serial_port_raises_value_error_and_does_not_open(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """没有 SERIAL_PORT：抛 ValueError，报错里有 SERIAL_PORT，没有打开串口。"""
    opener = install_opener(monkeypatch, clock, [])
    with pytest.raises(ValueError) as error:
        open_serial_pad(load_settings({}))
    assert "SERIAL_PORT" in str(error.value)
    assert opener.calls == []


def test_open_serial_pad_serial_exception_raises_device_check_error_with_port(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """Serial 抛 serial.SerialException：抛 DeviceCheckError，报错以「按键」开头，里面有串口路径。"""
    install_opener(monkeypatch, clock, [], serial.SerialException("没有这个设备"))
    with pytest.raises(DeviceCheckError) as error:
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    message = str(error.value)
    assert message.startswith("按键")
    assert "/dev/cu.usbserial-1" in message


@pytest.mark.parametrize(
    "replies",
    [
        pytest.param([], id="握手读到空"),
        pytest.param([b"\x00"], id="握手读到别的字节"),
        pytest.param([b"\x80", b"\x00"], id="停脚本读到别的字节"),
    ],
)
def test_open_serial_pad_bad_reply_raises_device_check_error_and_closes_port(
    monkeypatch: pytest.MonkeyPatch, clock: Clock, replies: list[bytes]
) -> None:
    """握手或停脚本读不到回应、读到不对的字节：抛 DeviceCheckError，报错以「按键」开头、
    有「没有回应」，串口被关了。
    """
    opener = install_opener(monkeypatch, clock, replies)
    with pytest.raises(DeviceCheckError) as error:
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    message = str(error.value)
    assert message.startswith("按键")
    assert "没有回应" in message
    assert opener.port.close_calls >= 1


class FailingReadSerial(FakeSerial):
    """read 抛 OSError 的假串口（例如读的时候 TTL 被拔掉）。"""

    def read(self, size: int) -> bytes:
        """抛 OSError。"""
        raise OSError("读不到")


@pytest.mark.parametrize(
    ("port_factory", "step"),
    [
        pytest.param(
            lambda clock: FakeSerial(clock, [], fail_write=True), "握手", id="握手时写失败"
        ),
        pytest.param(lambda clock: FailingReadSerial(clock, []), "握手", id="握手时读失败"),
    ],
)
def test_open_serial_pad_os_error_during_handshake_raises_device_check_error_and_closes(
    monkeypatch: pytest.MonkeyPatch, clock: Clock, port_factory: Any, step: str
) -> None:
    """防止：握手时 write、read 抛 OSError（串口打开后 TTL 被拔掉）原样漏出去、串口没关。
    应该抛 DeviceCheckError，报错以「按键」开头、有「没有回应」和是哪一步，串口关了一次。
    """
    port = port_factory(clock)
    monkeypatch.setattr(
        "control_switch.device.serial_pad.serial.Serial", lambda *args, **kwargs: port
    )
    with pytest.raises(DeviceCheckError) as error:
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    message = str(error.value)
    assert message.startswith("按键")
    assert "没有回应" in message
    assert step in message
    assert port.close_calls == 1


def test_open_serial_pad_os_error_when_stopping_script_names_the_step(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """防止：停脚本那一步 read 抛 OSError 时报错没写明是「停脚本」、串口没关。"""

    class StopScriptReadFails(FakeSerial):
        def read(self, size: int) -> bytes:
            if len(self.writes) >= 2:
                raise OSError("读不到")
            return super().read(size)

    port = StopScriptReadFails(clock, [b"\x80"])
    monkeypatch.setattr(
        "control_switch.device.serial_pad.serial.Serial", lambda *args, **kwargs: port
    )
    with pytest.raises(DeviceCheckError) as error:
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    assert "停脚本" in str(error.value)
    assert port.close_calls == 1


@pytest.mark.parametrize(
    ("button", "buttons", "hat"),
    [
        ("A", 0x04, 8),
        ("B", 0x02, 8),
        ("X", 0x08, 8),
        ("Y", 0x01, 8),
        ("L", 0x10, 8),
        ("R", 0x20, 8),
        ("ZL", 0x40, 8),
        ("ZR", 0x80, 8),
        ("MINUS", 0x100, 8),
        ("PLUS", 0x200, 8),
        ("LSTICK", 0x400, 8),
        ("RSTICK", 0x800, 8),
        ("HOME", 0x1000, 8),
        ("CAPTURE", 0x2000, 8),
        ("DUP", 0, 0),
        ("DRIGHT", 0, 2),
        ("DDOWN", 0, 4),
        ("DLEFT", 0, 6),
    ],
)
def test_every_button_name_maps_to_documented_bit_or_hat(
    clock: Clock, button: str, buttons: int, hat: int
) -> None:
    """约定里的 18 个按键名：按下的报文是任务文件里的按钮位或 HAT，摇杆都居中。"""
    pad, port = make_pad(clock)
    pad.click(button, 0)
    assert unpack(port.writes[0]) == [buttons >> 8, buttons & 0xFF, hat, 128, 128, 128, 128]


@pytest.mark.parametrize(("value", "axis"), [(0x10000, 255), (-0x10000, 0), (0x4000, 192)])
def test_stick_x_out_of_range_is_clamped(clock: Clock, value: int, axis: int) -> None:
    """x 超出 ±0x7FFF 时限制在 0–255；中间值按 round(128 + v * 127 / 0x7FFF) 换算。"""
    pad, port = make_pad(clock)
    pad.stick("LEFT", value, 0, 0)
    assert unpack(port.writes[0])[3] == axis


def test_open_serial_pad_registers_pad_close_with_atexit(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """防止：程序退出时（例如 Ctrl+C）单片机还保持着最后一个按下的报文。
    握手成功后要用 atexit 注册 pad.close：调用它会发中立报文、关串口。
    """
    registered: list[Any] = []
    monkeypatch.setattr(
        "control_switch.device.serial_pad.atexit.register", lambda func: registered.append(func)
    )
    opener = install_opener(monkeypatch, clock, [b"\x80", b"\x83", OK])
    pad = open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    assert registered == [pad.close]
    registered[0]()
    assert opener.port.writes[-1] == NEUTRAL
    assert opener.port.close_calls == 1


@pytest.mark.parametrize(
    "replies",
    [
        pytest.param([], id="握手读到空"),
        pytest.param([b"\x80", b"\x00"], id="停脚本读到别的字节"),
    ],
)
def test_open_serial_pad_does_not_register_atexit_when_handshake_fails(
    monkeypatch: pytest.MonkeyPatch, clock: Clock, replies: list[bytes]
) -> None:
    """握手或停脚本失败：抛 DeviceCheckError，不注册 atexit。"""
    registered: list[Any] = []
    monkeypatch.setattr(
        "control_switch.device.serial_pad.atexit.register", lambda func: registered.append(func)
    )
    install_opener(monkeypatch, clock, replies)
    with pytest.raises(DeviceCheckError):
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    assert registered == []


def test_open_serial_pad_does_not_register_atexit_when_port_cannot_open(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    """串口打不开：不注册 atexit。"""
    registered: list[Any] = []
    monkeypatch.setattr(
        "control_switch.device.serial_pad.atexit.register", lambda func: registered.append(func)
    )
    install_opener(monkeypatch, clock, [], serial.SerialException("没有这个设备"))
    with pytest.raises(DeviceCheckError):
        open_serial_pad(load_settings({"SERIAL_PORT": "/dev/cu.usbserial-1"}))
    assert registered == []


@pytest.mark.parametrize("call", ["press", "release"])
def test_press_and_release_unknown_button_raise_value_error_naming_it(
    call: str, clock: Clock
) -> None:
    """press、release 传了不认识的按键名：抛 ValueError，报错里有这个名字，不发报文。"""
    pad, port = make_pad(clock)
    sent = len(port.writes)
    with pytest.raises(ValueError, match="ZZ"):
        getattr(pad, call)("ZZ")
    assert len(port.writes) == sent


def test_release_stick_wrong_side_raises_value_error(clock: Clock) -> None:
    """release_stick 传了 LEFT、RIGHT 以外的：抛 ValueError。"""
    pad, _ = make_pad(clock)
    with pytest.raises(ValueError, match="LEFT 或 RIGHT"):
        pad.release_stick("UP")
