"""sys-botbase 的 TCP 客户端。

协议：每条命令是一行文本，以 \\r\\n 结尾；有返回值的命令返回一行文本，以 \\n 结尾。
"""

import atexit
import socket
import time


class Switch:
    def __init__(self, host: str, port: int = 6000, timeout: float = 5.0):
        """记录连接参数，不会真的连接。

        host: Switch 的 IP。
        port: sys-botbase 的端口，默认 6000。
        timeout: 连接和收发的超时时间，单位秒。
        """
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None

    def connect(self):
        """连接到 Switch。连不上或超时会抛 OSError。"""
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)

    def close(self):
        """断开连接。没连接时调用也没问题。"""
        if self.sock:
            self.sock.close()
            self.sock = None

    def _send(self, cmd: str):
        """发送一条命令，自动补上 \\r\\n。没连接时抛 ConnectionError。"""
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

    def click(self, button: str, delay: float = 0.15):
        """按一下按键（按下再松开），然后等 delay 秒。

        button: 按键名，例如 A、B、X、Y、HOME、DUP。
        delay: 按完之后等待的秒数，给游戏留出响应时间。
        """
        self._send(f"click {button}")
        time.sleep(delay)

    def title_id(self) -> str:
        """返回当前前台游戏的 Title ID，16 位十六进制文本。"""
        self._send("getTitleID")
        return self._readline()

    def pixel_peek(self) -> bytes:
        """截一张当前画面，返回 JPEG 字节。"""
        self._send("pixelPeek")
        return bytes.fromhex(self._readline())


_instance: Switch | None = None


def connect(host: str, port: int = 6000, timeout: float = 5.0) -> Switch:
    """建立全局唯一的连接，程序退出时自动关闭。重复调用会抛 RuntimeError。"""
    global _instance
    if _instance is not None:
        raise RuntimeError("already connected")
    sw = Switch(host, port, timeout)
    sw.connect()
    atexit.register(sw.close)
    _instance = sw
    return sw


def get() -> Switch:
    """取全局连接。还没调用 connect 会抛 RuntimeError。"""
    if _instance is None:
        raise RuntimeError("not connected")
    return _instance
