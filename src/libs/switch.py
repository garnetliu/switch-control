"""和 Switch 上的 botbase 通信：Wi-Fi 用 sys-botbase（TCP），USB 用 usb-botbase。

用哪种由 .env 的 SWITCH_CONNECTION 决定：usb，或者 wifi（默认，要配 SWITCH_IP、SWITCH_PORT）。
两种连接对外的方法完全一样。Switch(boss) 在初始化时自动连接。
"""

import atexit
import os
import signal
import socket
import struct
import threading
import time

import usb.core
import usb.util

from .game_config import GameConfig
from .game_data import GameData
from .game_state import GameState
from .notifier import Notifier
from .pkhex import Pkhex

# 摇杆坐标的最大值
STICK_MAX = 0x7FFF


def _exit_on_signal(signum: int, _frame):
    """收到终止信号时走正常退出流程，让 atexit 注册的 close 把 USB 关掉。"""
    raise SystemExit(128 + signum)


def _hex(value: int) -> str:
    """摇杆坐标转成 botbase 要的十六进制文本，负数写成 -0x...。"""
    return f"-{abs(value):#x}" if value < 0 else f"{value:#x}"


class _WifiConnection:
    """sys-botbase：每条命令是一行文本，以 \\r\\n 结尾；有返回值的命令返回一行文本，以 \\n 结尾。"""

    def __init__(self, host: str, port: int = 6000, timeout: float = 5.0):
        """连接到 Switch。连不上或超时会抛 OSError。"""
        sock = socket.create_connection((host, port), timeout)
        sock.settimeout(timeout)
        self.sock: socket.socket | None = sock

    def send(self, cmd: str) -> None:
        if self.sock is None:
            raise ConnectionError("not connected")
        self.sock.sendall((cmd + "\r\n").encode())

    def _readline(self) -> str:
        """读取一行返回值，读到 \\n 为止，返回去掉首尾空白的文本。"""
        if self.sock is None:
            raise ConnectionError("not connected")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("switch closed connection")
            buf += chunk
        return buf.decode().strip()

    def title_id(self) -> str:
        self.send("getTitleID")
        return self._readline()

    def request(self, cmd: str) -> bytes:
        self.send(cmd)
        # sys-botbase 把数据写成一行十六进制文本
        return bytes.fromhex(self._readline())

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None


class _UsbConnection:
    """usb-botbase（Koi-3088 维护的版本）。

    发命令：先发 4 字节小端的长度（命令长度加 2），再发命令本身，不加 \\r\\n。
    收返回：先收 4 字节小端的长度，再收这么多字节的原始数据（截图就是 JPEG，不是十六进制文本）。
    没有返回值的命令（click、setStick）什么都不回。协议照 SysBot.NET 的 SwitchUSB。
    """

    # usb-botbase 的 USB 设备号
    VENDOR_ID, PRODUCT_ID = 0x057E, 0x3000
    RECONNECT_TIMEOUT = 30

    def __init__(self, timeout: float = 5.0):
        """找到 usb-botbase 并占用它的接口。找不到抛 ConnectionError。

        上次退出时复位过设备的话，要等它重新枚举，这里最多等 5 秒。
        """
        self.timeout_ms = int(timeout * 1000)
        self.device = None
        self.out = None
        self.into = None
        deadline = time.monotonic() + 5
        while True:
            try:
                self._open()
                return
            except (usb.core.USBError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)

    def _open(self):
        device = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)
        if device is None:
            raise ConnectionError("找不到 usb-botbase：USB 线连着吗？Switch 上的插件启动了吗？")
        device.set_configuration()
        interface = device.get_active_configuration()[(0, 0)]
        out = usb.util.find_descriptor(
            interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
        into = usb.util.find_descriptor(
            interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            ),
        )
        if out is None or into is None:
            raise ConnectionError("usb-botbase 没有找到收发端点")
        self.device = device
        self.out = out
        self.into = into

    def _reconnect(self):
        """USB 断开后等设备重新出现，最多等 RECONNECT_TIMEOUT 秒。"""
        self.close()
        deadline = time.monotonic() + self.RECONNECT_TIMEOUT
        last_error = None
        while True:
            try:
                self._open()
                return
            except (usb.core.USBError, ConnectionError) as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                raise ConnectionError(
                    f"USB 连接断开，{self.RECONNECT_TIMEOUT} 秒内没有重新连上"
                ) from last_error
            time.sleep(1)

    def close(self):
        # 进程可能是在发命令的中途退出的，botbase 会一直等剩下的字节，不复位的话下次写入会超时。
        # 复位会让设备重新枚举，所以 __init__ 里要等它一会儿。
        if self.device is not None:
            try:
                self.device.reset()
            except usb.core.USBError:
                pass
            try:
                usb.util.dispose_resources(self.device)
            except usb.core.USBError:
                pass
        self.device = None
        self.out = None
        self.into = None

    def _send_once(self, cmd: str):
        data = cmd.encode()
        self.out.write(struct.pack("<I", len(data) + 2), self.timeout_ms)
        self.out.write(data, self.timeout_ms)

    def send(self, cmd: str):
        try:
            self._send_once(cmd)
        except usb.core.USBError:
            self._reconnect()
            self._send_once(cmd)

    def request(self, cmd: str) -> bytes:
        for attempt in range(2):
            try:
                self.send(cmd)
                return self._receive()
            except usb.core.USBError as exc:
                if attempt:
                    raise ConnectionError("USB 连接反复断开，重连后仍然没有返回") from exc
                self._reconnect()
        raise AssertionError("unreachable")

    def _receive(self) -> bytes:
        """收一次返回：先收长度，再把数据收完。超时抛 usb.core.USBTimeoutError。"""
        size = struct.unpack("<I", bytes(self.into.read(4, self.timeout_ms)))[0]
        data = bytearray()
        while len(data) < size:
            data += bytes(self.into.read(size - len(data), self.timeout_ms))
        return bytes(data)

    def title_id(self) -> str:
        self.send("getTitleID")
        try:
            data = self._receive()
        except usb.core.USBTimeoutError:
            # 没有游戏在运行时 usb-botbase 不回（源码里 main_nso_base 为 0 就直接返回）
            return ""
        return f"{struct.unpack('<Q', data)[0]:016X}"


class Switch:
    """一条连接和这一局的状态。初始化时按 .env 自动连接。"""

    def __init__(self):
        # 配置和这一局的状态挂在连接上，步骤里用 sw.config、sw.game 取
        self.config = GameConfig()
        self.game = GameState(self.config)
        self.data = GameData(self.config)
        self.pkhex = Pkhex(self.peek)
        # 往 Discord 推送消息，步骤里用 sw.notifier 取
        self.notifier = Notifier()
        self._connect()

    def _connect(self) -> None:
        self._connection: _WifiConnection | _UsbConnection
        """按 .env 的配置连接：usb 走 USB，否则走 Wi-Fi。"""
        if os.environ.get("SWITCH_CONNECTION", "wifi").lower() == "usb":
            self._connection = _UsbConnection()
        else:
            self._connection = _WifiConnection(
                os.environ["SWITCH_IP"], int(os.environ["SWITCH_PORT"])
            )
        atexit.register(self.close)
        if threading.current_thread() is threading.main_thread():
            # SIGKILL 拦不住；SIGTERM、SIGHUP 转成正常退出，退出时 atexit 会关掉 USB
            for sig in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(sig, _exit_on_signal)

    def _send(self, cmd: str):
        assert self._connection is not None
        self._connection.send(cmd)

    def _request_bytes(self, cmd: str) -> bytes:
        assert self._connection is not None
        return self._connection.request(cmd)

    def click(self, button: str, delay: float = 0.15):
        """按一下按键（按下再松开），然后等 delay 秒。

        button: 按键名，例如 A、B、X、Y、HOME、DUP。
        delay: 按完之后等待的秒数，给游戏留出响应时间。
        """
        self._send(f"click {button}")
        time.sleep(delay)

    def stick(self, side: str, x: int, y: int, hold: float):
        """把摇杆推到 (x, y)，保持 hold 秒，再回中。

        side: LEFT 或 RIGHT。
        x, y: 范围 -STICK_MAX 到 STICK_MAX，x 正数向右，y 正数向上。
        hold: 保持的秒数。
        """
        self._send(f"setStick {side} {_hex(x)} {_hex(y)}")
        time.sleep(hold)
        self._send(f"setStick {side} 0x0 0x0")

    def press_stick(self, side: str, x: int, y: int):
        """把摇杆推到 (x, y) 并一直保持，直到 release_stick。参数同 stick。"""
        self._send(f"setStick {side} {_hex(x)} {_hex(y)}")

    def release_stick(self, side: str):
        """摇杆回中。"""
        self._send(f"setStick {side} 0x0 0x0")

    def title_id(self) -> str:
        """当前前台游戏的 Title ID，16 位十六进制文本；没有游戏在运行时返回空字符串。

        botbase 要把调试器挂到游戏进程上才能读，挂着的时候游戏是停的。
        """
        return self._connection.title_id()

    def pixel_peek(self) -> bytes:
        """截一张当前画面，返回 JPEG 字节。

        USB 偶尔会回空数据（真机上一晚出现过一次，图片解码直接崩了），空的就再截一次。
        连着几次都是空的抛 ConnectionError。
        """
        # 最多截几次
        tries = 3

        for _ in range(tries):
            data = self._request_bytes("pixelPeek")
            if data:
                return data
        raise ConnectionError(f"截图连着 {tries} 次都是空的")

    def peek(self, offset: int, size: int) -> bytes:
        """读游戏 heap 上 offset 处的 size 个字节。

        和 title_id 一样要挂调试器，读的时候游戏会停一下。
        """
        return self._request_bytes(f"peek {offset:#x} {size:#x}")

    def peek_main(self, offset: int, size: int) -> bytes:
        """读游戏主程序（main）上 offset 处的 size 个字节。"""
        return self._request_bytes(f"peekMain {offset:#x} {size:#x}")

    def pointer_peek(self, jumps: list[int], size: int) -> bytes:
        """按指针链读 size 个字节。

        jumps 是 [main 上的偏移, 中间的偏移..., 最后的偏移]，例如 [[main+A]+B]+C 写成 [A, B, C]：
        从 main+A 读出地址，加 B 再读出地址，最后加 C 不再读地址，直接读数据。
        """
        return self._request_bytes(
            f"pointerPeek {size:#x} " + " ".join(f"{jump:#x}" for jump in jumps)
        )

    def close(self):
        """断开连接。没连接时调用也没问题。"""
        self._connection.close()
