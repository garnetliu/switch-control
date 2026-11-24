"""用单片机（伊机控固件）按键：电脑通过 TTL 串口发报文，单片机当成手柄插在 Switch 底座上。"""

import atexit
import time
from typing import Protocol

import serial

from control_switch.settings import Settings

from .check import DeviceCheckError

# 按下和松开两个报文之间隔多久
PRESS_TIME = 0.1
# 两个报文之间至少隔多久（伊机控电脑端的最小间隔）
_MIN_GAP = 0.03

_OK = 0xFF
_BUSY = 0xFE
_HANDSHAKE = b"\xa5\xa5\x81"
_HANDSHAKE_REPLY = 0x80
_STOP_SCRIPT = b"\xa5\x84"
_STOP_SCRIPT_REPLY = 0x83

_BUTTONS = {
    "Y": 0x01,
    "B": 0x02,
    "A": 0x04,
    "X": 0x08,
    "L": 0x10,
    "R": 0x20,
    "ZL": 0x40,
    "ZR": 0x80,
    "MINUS": 0x100,
    "PLUS": 0x200,
    "LSTICK": 0x400,
    "RSTICK": 0x800,
    "HOME": 0x1000,
    "CAPTURE": 0x2000,
}
# 十字键：上 0、右上 1、右 2、右下 3、下 4、左下 5、左 6、左上 7，居中 8
_HATS = {"DUP": 0, "DRIGHT": 2, "DDOWN": 4, "DLEFT": 6}
_HAT_CENTER = 8
_AXIS_CENTER = 128
_HINT = "检查 TTL 的接线和波特率"


class SerialPort(Protocol):
    """用到的串口接口，serial.Serial 符合它。"""

    def write(self, data: bytes, /) -> int | None: ...

    def read(self, size: int, /) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


def _pack(raw: bytes) -> bytes:
    """按 7 位一组打包，最后一个字节最高位置 1（EasyCon SwitchReport.GetBytes）。"""
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


def _report(
    buttons: int = 0,
    hat: int = _HAT_CENTER,
    left: tuple[int, int] = (_AXIS_CENTER, _AXIS_CENTER),
    right: tuple[int, int] = (_AXIS_CENTER, _AXIS_CENTER),
) -> bytes:
    return _pack(bytes([buttons >> 8, buttons & 0xFF, hat, *left, *right]))


_NEUTRAL = _report()


def _axis(value: int, *, up_is_positive: bool = False) -> int:
    """botbase 的 -0x7FFF 到 0x7FFF 换成 0 到 255，中心 128。"""
    if up_is_positive:
        value = -value
    return min(255, max(0, round(_AXIS_CENTER + value * 127 / 0x7FFF)))


def _stick_position(side: str, x: int, y: int) -> tuple[int, int]:
    """摇杆坐标换成报文里的 (x, y)，side 不对抛 ValueError。"""
    if side not in ("LEFT", "RIGHT"):
        raise ValueError(f"side 只能是 LEFT 或 RIGHT，现在是 {side}")
    return _axis(x), _axis(y, up_is_positive=True)


def _describe(reply: bytes) -> str:
    return reply.hex().upper() if reply else "空"


class SerialPad:
    """单片机按键，实现 Controller。"""

    def __init__(self, port: SerialPort) -> None:
        self._port = port
        self._last_sent: float | None = None
        self._closed = False
        # press、press_stick 按住的按键和摇杆，之后每个报文都带上
        self._held_buttons = 0
        self._held_sticks: dict[str, tuple[int, int]] = {}

    def _packet(
        self,
        extra_buttons: int = 0,
        hat: int = _HAT_CENTER,
        extra_stick: tuple[str, tuple[int, int]] | None = None,
    ) -> bytes:
        """按住的状态加上这一次的按键、十字键、摇杆，做成一个报文。"""
        sticks = dict(self._held_sticks)
        if extra_stick is not None:
            sticks[extra_stick[0]] = extra_stick[1]
        center = (_AXIS_CENTER, _AXIS_CENTER)
        return _report(
            buttons=self._held_buttons | extra_buttons,
            hat=hat,
            left=sticks.get("LEFT", center),
            right=sticks.get("RIGHT", center),
        )

    def click(self, button: str, delay: float = 0.15) -> None:
        """发按下的报文，等 PRESS_TIME，发松开的报文（回到按住的状态），再等 delay 秒。"""
        if button in _BUTTONS:
            packet = self._packet(extra_buttons=_BUTTONS[button])
        elif button in _HATS:
            packet = self._packet(hat=_HATS[button])
        else:
            raise ValueError(f"不认识的按键名：{button}")
        self._send(packet)
        time.sleep(PRESS_TIME)
        self._send(self._packet())
        time.sleep(delay)

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        """把摇杆推到 (x, y)，保持 hold 秒，再回中。y 正数向上。"""
        position = _stick_position(side, x, y)
        self._send(self._packet(extra_stick=(side, position)))
        time.sleep(hold)
        self._send(self._packet())

    def press(self, button: str) -> None:
        """按住按键，直到 release。"""
        if button not in _BUTTONS:
            raise ValueError(f"不认识的按键名：{button}")
        self._held_buttons |= _BUTTONS[button]
        self._send(self._packet())

    def release(self, button: str) -> None:
        """松开按键。"""
        if button not in _BUTTONS:
            raise ValueError(f"不认识的按键名：{button}")
        self._held_buttons &= ~_BUTTONS[button]
        self._send(self._packet())

    def press_stick(self, side: str, x: int, y: int) -> None:
        """把摇杆推到 (x, y) 并一直保持，直到 release_stick。y 正数向上。"""
        self._held_sticks[side] = _stick_position(side, x, y)
        self._send(self._packet())

    def release_stick(self, side: str) -> None:
        """摇杆回中。"""
        if side not in ("LEFT", "RIGHT"):
            raise ValueError(f"side 只能是 LEFT 或 RIGHT，现在是 {side}")
        self._held_sticks.pop(side, None)
        self._send(self._packet())

    def close(self) -> None:
        """发一次中立报文（出错不管），再关串口，可以调多次。"""
        if self._closed:
            return
        self._closed = True
        try:
            self._send(_NEUTRAL)
        except OSError:
            pass
        finally:
            self._port.close()

    def _send(self, packet: bytes) -> None:
        """补够和上一个报文的间隔，发出去，读回应，不是 FF 抛 ConnectionError。"""
        if self._last_sent is not None:
            wait = _MIN_GAP - (time.monotonic() - self._last_sent)
            if wait > 0:
                time.sleep(wait)
        self._port.write(packet)
        reply = self._port.read(1)
        self._last_sent = time.monotonic()
        if reply == bytes([_OK]):
            return
        if reply == bytes([_BUSY]):
            raise ConnectionError("单片机回 FE：它还在跑里面存的脚本，没有收按键")
        raise ConnectionError(f"单片机回应不对，收到 {_describe(reply)}")


def _command(port: SerialPort, data: bytes, expected: int, step: str) -> None:
    """发一条命令，读 1 个字节，不是 expected 就关串口抛 DeviceCheckError。"""
    try:
        port.write(data)
        reply = port.read(1)
    except OSError as error:
        port.close()
        raise DeviceCheckError(f"按键：单片机没有回应（{step}，{error}），{_HINT}") from error
    if reply != bytes([expected]):
        port.close()
        raise DeviceCheckError(f"按键：单片机没有回应（{step}，收到 {_describe(reply)}），{_HINT}")


def open_serial_pad(settings: Settings) -> SerialPad:
    """打开串口，握手，停掉单片机里存的脚本。"""
    if settings.serial_port is None:
        raise ValueError("CONTROLLER=serial 时要在 .env 里写 SERIAL_PORT")
    try:
        port = serial.Serial(settings.serial_port, settings.serial_baud, timeout=0.5)
    except (serial.SerialException, OSError) as error:
        raise DeviceCheckError(f"按键：串口 {settings.serial_port} 打不开：{error}") from error
    port.reset_input_buffer()
    _command(port, _HANDSHAKE, _HANDSHAKE_REPLY, "握手")
    _command(port, _STOP_SCRIPT, _STOP_SCRIPT_REPLY, "停脚本")
    pad = SerialPad(port)
    atexit.register(pad.close)
    return pad
