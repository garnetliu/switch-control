"""用单片机（伊机控固件）按键：电脑通过 TTL 串口发报文，单片机当成手柄插在 Switch 底座上。"""

import atexit
import time
from typing import ClassVar, Protocol

import serial

from control_switch.settings import Settings

from .base import Controller
from .check import DeviceCheckError


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


def _describe(reply: bytes) -> str:
    return reply.hex().upper() if reply else "空"


class SerialPad(Controller):
    """单片机按键，实现 Controller。"""

    # 按键名对应报文里按键字段的位
    BUTTONS: ClassVar[dict[str, int]] = {
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
    # 报文里十字键居中、摇杆居中的值
    HAT_CENTER = 8
    AXIS_CENTER = 128

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
        hat: int | None = None,
        extra_stick: tuple[str, tuple[int, int]] | None = None,
    ) -> bytes:
        """按住的状态加上这一次的按键、十字键、摇杆，做成一个报文。hat 不传时十字键居中。"""
        sticks = dict(self._held_sticks)
        if extra_stick is not None:
            sticks[extra_stick[0]] = extra_stick[1]
        center = (self.AXIS_CENTER, self.AXIS_CENTER)
        buttons = self._held_buttons | extra_buttons
        raw = [
            buttons >> 8,
            buttons & 0xFF,
            self.HAT_CENTER if hat is None else hat,
            *sticks.get("LEFT", center),
            *sticks.get("RIGHT", center),
        ]
        return _pack(bytes(raw))

    def _axis(self, value: int, *, up_is_positive: bool = False) -> int:
        """-STICK_MAX 到 STICK_MAX 换成 0 到 255，中心 128。"""
        if up_is_positive:
            value = -value
        return min(255, max(0, round(self.AXIS_CENTER + value * 127 / self.STICK_MAX)))

    def _stick_position(self, side: str, x: int, y: int) -> tuple[int, int]:
        """摇杆坐标换成报文里的 (x, y)，side 不对抛 ValueError。"""
        if side not in ("LEFT", "RIGHT"):
            raise ValueError(f"side 只能是 LEFT 或 RIGHT，现在是 {side}")
        return self._axis(x), self._axis(y, up_is_positive=True)

    def click(self, button: str, delay: float = 0.15) -> None:
        """发按下的报文，等 0.1 秒，发松开的报文（回到按住的状态），再等 delay 秒。"""
        # 十字键：上 0、右上 1、右 2、右下 3、下 4、左下 5、左 6、左上 7，居中 8
        hats = {"DUP": 0, "DRIGHT": 2, "DDOWN": 4, "DLEFT": 6}
        # 按下和松开两个报文之间隔多久
        press_time = 0.1
        if button in self.BUTTONS:
            packet = self._packet(extra_buttons=self.BUTTONS[button])
        elif button in hats:
            packet = self._packet(hat=hats[button])
        else:
            raise ValueError(f"不认识的按键名：{button}")
        self._send(packet)
        time.sleep(press_time)
        self._send(self._packet())
        time.sleep(delay)

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        """把摇杆推到 (x, y)，保持 hold 秒，再回中。y 正数向上。"""
        position = self._stick_position(side, x, y)
        self._send(self._packet(extra_stick=(side, position)))
        time.sleep(hold)
        self._send(self._packet())

    def press(self, button: str) -> None:
        """按住按键，直到 release。"""
        if button not in self.BUTTONS:
            raise ValueError(f"不认识的按键名：{button}")
        self._held_buttons |= self.BUTTONS[button]
        self._send(self._packet())

    def release(self, button: str) -> None:
        """松开按键。"""
        if button not in self.BUTTONS:
            raise ValueError(f"不认识的按键名：{button}")
        self._held_buttons &= ~self.BUTTONS[button]
        self._send(self._packet())

    def press_stick(self, side: str, x: int, y: int) -> None:
        """把摇杆推到 (x, y) 并一直保持，直到 release_stick。y 正数向上。"""
        self._held_sticks[side] = self._stick_position(side, x, y)
        self._send(self._packet())

    def release_stick(self, side: str) -> None:
        """摇杆回中。"""
        if side not in ("LEFT", "RIGHT"):
            raise ValueError(f"side 只能是 LEFT 或 RIGHT，现在是 {side}")
        self._held_sticks.pop(side, None)
        self._send(self._packet())

    def close(self) -> None:
        """松开所有按住的，发一次中立报文（出错不管），再关串口，可以调多次。"""
        if self._closed:
            return
        self._closed = True
        self._held_buttons = 0
        self._held_sticks.clear()
        try:
            self._send(self._packet())
        except OSError:
            pass
        finally:
            self._port.close()

    def _send(self, packet: bytes) -> None:
        """补够和上一个报文的间隔，发出去，读回应，不是 FF 抛 ConnectionError。"""
        # 两个报文之间至少隔多久（伊机控电脑端的最小间隔）
        min_gap = 0.03
        ok, busy = 0xFF, 0xFE
        if self._last_sent is not None:
            wait = min_gap - (time.monotonic() - self._last_sent)
            if wait > 0:
                time.sleep(wait)
        self._port.write(packet)
        reply = self._port.read(1)
        self._last_sent = time.monotonic()
        if reply == bytes([ok]):
            return
        if reply == bytes([busy]):
            raise ConnectionError("单片机回 FE：它还在跑里面存的脚本，没有收按键")
        raise ConnectionError(f"单片机回应不对，收到 {_describe(reply)}")


def _command(port: SerialPort, data: bytes, expected: int, step: str) -> None:
    """发一条命令，读 1 个字节，不是 expected 就关串口抛 DeviceCheckError。"""
    hint = "检查 TTL 的接线和波特率"
    try:
        port.write(data)
        reply = port.read(1)
    except OSError as error:
        port.close()
        raise DeviceCheckError(f"按键：单片机没有回应（{step}，{error}），{hint}") from error
    if reply != bytes([expected]):
        port.close()
        raise DeviceCheckError(f"按键：单片机没有回应（{step}，收到 {_describe(reply)}），{hint}")


def open_serial_pad(settings: Settings) -> SerialPad:
    """打开串口，握手，停掉单片机里存的脚本。"""
    if settings.serial_port is None:
        raise ValueError(
            f"runs/switches.toml 的 [switch.{settings.switch}] 的 controller 是 serial，要写 serial_port"
        )
    try:
        port = serial.Serial(settings.serial_port, settings.serial_baud, timeout=0.5)
    except (serial.SerialException, OSError) as error:
        raise DeviceCheckError(f"按键：串口 {settings.serial_port} 打不开：{error}") from error
    port.reset_input_buffer()
    _command(port, b"\xa5\xa5\x81", 0x80, "握手")
    _command(port, b"\xa5\x84", 0x83, "停脚本")
    pad = SerialPad(port)
    atexit.register(pad.close)
    return pad
