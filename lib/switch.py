"""和 Switch 上的 botbase 通信：Wi-Fi 用 sys-botbase（TCP），USB 用 usb-botbase。

用哪种由 .env 的 SWITCH_CONNECTION 决定：usb，或者 wifi（默认，要配 SWITCH_IP、SWITCH_PORT）。
两种连接对外的方法完全一样。USB 截图约 0.1 秒，Wi-Fi 要 1 到 3 秒（真机实测）。
"""

import atexit
import os
import socket
import struct
import time

import usb.core
import usb.util

# 摇杆坐标的最大值
STICK_MAX = 0x7FFF


def _hex(value: int) -> str:
    """摇杆坐标转成 botbase 要的十六进制文本，负数写成 -0x...。"""
    return f"-{abs(value):#x}" if value < 0 else f"{value:#x}"


class Switch:
    """两种连接共用的命令。子类只负责发命令、收返回。"""

    def _send(self, cmd: str):
        raise NotImplementedError

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
        raise NotImplementedError

    def pixel_peek(self) -> bytes:
        """截一张当前画面，返回 JPEG 字节。

        USB 偶尔会回空数据（真机上一晚出现过一次，图片解码直接崩了），空的就再截一次。
        连着几次都是空的抛 ConnectionError。
        """
        # 最多截几次
        tries = 3

        for _ in range(tries):
            self._send("pixelPeek")
            data = self._read_bytes()
            if data:
                return data
        raise ConnectionError(f"截图连着 {tries} 次都是空的")

    def peek(self, offset: int, size: int) -> bytes:
        """读游戏 heap 上 offset 处的 size 个字节。

        和 title_id 一样要挂调试器，读的时候游戏会停一下。
        """
        self._send(f"peek {offset:#x} {size:#x}")
        return self._read_bytes()

    def peek_main(self, offset: int, size: int) -> bytes:
        """读游戏主程序（main）上 offset 处的 size 个字节。"""
        self._send(f"peekMain {offset:#x} {size:#x}")
        return self._read_bytes()

    def pointer_peek(self, jumps: list[int], size: int) -> bytes:
        """按指针链读 size 个字节。

        jumps 是 [main 上的偏移, 中间的偏移..., 最后的偏移]，例如 [[main+A]+B]+C 写成 [A, B, C]：
        从 main+A 读出地址，加 B 再读出地址，最后加 C 不再读地址，直接读数据。
        """
        self._send(f"pointerPeek {size:#x} " + " ".join(f"{jump:#x}" for jump in jumps))
        return self._read_bytes()

    def _read_bytes(self) -> bytes:
        """收一条有数据的返回。"""
        raise NotImplementedError

    def close(self):
        """断开连接。没连接时调用也没问题。"""


class WifiSwitch(Switch):
    """sys-botbase：每条命令是一行文本，以 \\r\\n 结尾；有返回值的命令返回一行文本，以 \\n 结尾。"""

    def __init__(self, host: str, port: int = 6000, timeout: float = 5.0):
        """连接到 Switch。连不上或超时会抛 OSError。

        host: Switch 的 IP。port: sys-botbase 的端口，默认 6000。timeout: 连接和收发的超时，单位秒。
        """
        self.sock: socket.socket | None = socket.create_connection((host, port), timeout)
        self.sock.settimeout(timeout)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _send(self, cmd: str):
        if self.sock is None:
            raise ConnectionError("not connected")
        self.sock.sendall((cmd + "\r\n").encode())

    def _readline(self) -> str:
        """读取一行返回值，读到 \\n 为止，返回去掉首尾空白的文本。

        没连接或对方断开会抛 ConnectionError，超时会抛 TimeoutError。
        """
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
        self._send("getTitleID")
        return self._readline()

    def _read_bytes(self) -> bytes:
        # sys-botbase 把数据写成一行十六进制文本
        return bytes.fromhex(self._readline())


class UsbSwitch(Switch):
    """usb-botbase（Koi-3088 维护的版本）。

    发命令：先发 4 字节小端的长度（命令长度加 2），再发命令本身，不加 \\r\\n。
    收返回：先收 4 字节小端的长度，再收这么多字节的原始数据（截图就是 JPEG，不是十六进制文本）。
    没有返回值的命令（click、setStick）什么都不回。协议照 SysBot.NET 的 SwitchUSB。
    """

    # usb-botbase 的 USB 设备号
    VENDOR_ID, PRODUCT_ID = 0x057E, 0x3000

    def __init__(self, timeout: float = 5.0):
        """找到 usb-botbase 并占用它的接口。找不到抛 ConnectionError。"""
        self.timeout_ms = int(timeout * 1000)
        self.device = usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)
        if self.device is None:
            raise ConnectionError("找不到 usb-botbase：USB 线连着吗？Switch 上的插件启动了吗？")
        self.device.set_configuration()
        interface = self.device.get_active_configuration()[(0, 0)]
        self.out = usb.util.find_descriptor(
            interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
        self.into = usb.util.find_descriptor(
            interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            ),
        )

    def close(self):
        if self.device is not None:
            usb.util.dispose_resources(self.device)
            self.device = None

    def _send(self, cmd: str):
        data = cmd.encode()
        self.out.write(struct.pack("<I", len(data) + 2), self.timeout_ms)
        self.out.write(data, self.timeout_ms)

    def _receive(self) -> bytes:
        """收一次返回：先收长度，再把数据收完。超时抛 usb.core.USBTimeoutError。"""
        size = struct.unpack("<I", bytes(self.into.read(4, self.timeout_ms)))[0]
        data = bytearray()
        while len(data) < size:
            data += bytes(self.into.read(size - len(data), self.timeout_ms))
        return bytes(data)

    def title_id(self) -> str:
        self._send("getTitleID")
        try:
            data = self._receive()
        except usb.core.USBTimeoutError:
            # 没有游戏在运行时 usb-botbase 不回（源码里 main_nso_base 为 0 就直接返回）
            return ""
        return f"{struct.unpack('<Q', data)[0]:016X}"

    def _read_bytes(self) -> bytes:
        return self._receive()


_instance: Switch | None = None


def connect() -> Switch:
    """按 .env 的配置建立全局唯一的连接，程序退出时自动关闭。重复调用会抛 RuntimeError。

    SWITCH_CONNECTION=usb 走 USB；否则走 Wi-Fi，用 SWITCH_IP、SWITCH_PORT。需要先调用 load_env。
    """
    global _instance
    if _instance is not None:
        raise RuntimeError("already connected")
    if os.environ.get("SWITCH_CONNECTION", "wifi").lower() == "usb":
        sw: Switch = UsbSwitch()
    else:
        sw = WifiSwitch(os.environ["SWITCH_IP"], int(os.environ["SWITCH_PORT"]))
    atexit.register(sw.close)
    _instance = sw
    return sw


def get() -> Switch:
    """取全局连接。还没调用 connect 会抛 RuntimeError。"""
    if _instance is None:
        raise RuntimeError("not connected")
    return _instance
