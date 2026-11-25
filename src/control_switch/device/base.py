"""设备的接口：取图、按键、读写内存各一个。具体用什么硬件实现，由 device 下的其他模块决定。"""

from typing import ClassVar, Protocol, runtime_checkable


@runtime_checkable
class Screen(Protocol):
    """取图。"""

    def pixel_peek(self) -> bytes:
        """截一张当前画面，返回 JPEG 字节。"""
        ...

    def close(self) -> None: ...


@runtime_checkable
class Controller(Protocol):
    """按键和摇杆。实现它的类要显式继承，STICK_MAX 从这里继承下来。"""

    # 摇杆坐标的范围是 -STICK_MAX 到 STICK_MAX
    STICK_MAX: ClassVar[int] = 0x7FFF

    def click(self, button: str, delay: float = 0.15) -> None:
        """按一下按键（按下再松开），然后等 delay 秒。"""
        ...

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        """把摇杆推到 (x, y)，保持 hold 秒，再回中。"""
        ...

    def press(self, button: str) -> None:
        """按住按键，直到 release。"""
        ...

    def release(self, button: str) -> None:
        """松开按键。"""
        ...

    def press_stick(self, side: str, x: int, y: int) -> None:
        """把摇杆推到 (x, y) 并一直保持，直到 release_stick。"""
        ...

    def release_stick(self, side: str) -> None:
        """摇杆回中。"""
        ...

    def close(self) -> None: ...


@runtime_checkable
class Memory(Protocol):
    """读写游戏内存。"""

    def title_id(self) -> str:
        """当前前台游戏的 Title ID，16 位十六进制文本；没有游戏在运行时返回空字符串。"""
        ...

    def peek(self, offset: int, size: int) -> bytes:
        """读游戏 heap 上 offset 处的 size 个字节。"""
        ...

    def pointer_all(self, jumps: list[int]) -> int:
        """按指针链算出绝对地址，不读数据。"""
        ...

    def peek_absolute(self, address: int, size: int) -> bytes:
        """读绝对地址 address 处的 size 个字节。"""
        ...

    def poke_absolute(self, address: int, data: bytes) -> None:
        """把 data 写到绝对地址 address。"""
        ...

    def close(self) -> None: ...
