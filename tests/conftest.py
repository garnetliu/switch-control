"""所有测试共用的假设备、Session 和日志清理。

三个假设备各自照 Screen、Controller、Memory 的方法签名写，放进 Devices 传给 Session，不用 cast。
假设备和 Session 都通过 fixture 给测试用；要传参数的，fixture 返回一个创建它的函数。
测试文件里不能写 from conftest import ...（importlib 导入方式下找不到 conftest），
所以测试文件里这些对象的类型标成 Any 或者 Callable[..., Any]。
"""

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

import pytest

from control_switch.config import BaseConfig
from control_switch.device import Devices
from control_switch.session import Session
from control_switch.settings import load_settings

DEFAULT_TITLE_ID = "0100ABF008968000"


class FakeConfig(BaseConfig):
    """计时全设成最短，log_dir 指到临时目录（failed_dir 由 log_dir 算出来）。"""

    def __init__(self, log_dir: Path) -> None:
        self.interval = 0.0
        self.press_interval = 0.0
        # 不要比 1 秒短：第一次建 ImageChecker 要初始化 OCR，约 0.1 秒
        self.timeout = 1.0
        self.load_timeout = 1.0
        self.boot_timeout = 1.0
        self.log_dir = log_dir
        self.game_title_ids = (DEFAULT_TITLE_ID,)


class FakeScreen:
    """假 Screen：按顺序返回给定的图片，用完后一直返回最后一张，记下 close() 调了几次。"""

    def __init__(self, images: Sequence[bytes]) -> None:
        assert images, "至少要给一张图片"
        self._images = list(images)
        self._position = 0
        self.close_calls = 0

    def pixel_peek(self) -> bytes:
        """按顺序返回事先给定的图片，用完后一直返回最后一张。"""
        index = min(self._position, len(self._images) - 1)
        self._position += 1
        return self._images[index]

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


class FakeController:
    """假 Controller：记下按过的键和摇杆操作，不等待，记下 close() 调了几次。"""

    def __init__(self) -> None:
        # 按过的键，按顺序
        self.pressed: list[str] = []
        # 每次按键传进来的 delay，和 pressed 一一对应
        self.delays: list[float] = []
        # 每次摇杆操作：(side, x, y, hold)
        self.sticks: list[tuple[str, int, int, float]] = []
        self.close_calls = 0

    def click(self, button: str, delay: float = 0.15) -> None:
        """记下按过的键，不等待。"""
        self.pressed.append(button)
        self.delays.append(delay)

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        """记下摇杆操作，不等待。"""
        self.sticks.append((side, x, y, hold))

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


class FakeMemory:
    """假 Memory：按地址返回事先给定的字节，记下读写；没给过的地址一读就报错。

    peek 和 peek_absolute 都按地址在 data 里找，返回的就是给定的字节（不按 size 截）。
    """

    def __init__(
        self,
        title_id: str,
        data: Mapping[int, bytes] | None = None,
        pointers: Mapping[tuple[int, ...], int] | None = None,
    ) -> None:
        self.title = title_id
        self.data = dict(data or {})
        self.pointers = dict(pointers or {})
        # 读过的：(方法名, 地址, 长度)，按顺序
        self.reads: list[tuple[str, int, int]] = []
        # 写过的：(地址, 数据)，按顺序
        self.writes: list[tuple[int, bytes]] = []
        self.close_calls = 0

    def _read(self, method: str, address: int, size: int) -> bytes:
        self.reads.append((method, address, size))
        if address not in self.data:
            raise AssertionError(f"假 Memory 没给过地址 {address:#x}（{method}，长度 {size:#x}）")
        return self.data[address]

    def title_id(self) -> str:
        """返回事先给定的值。"""
        return self.title

    def peek(self, offset: int, size: int) -> bytes:
        """返回 data 里 offset 这个地址对应的字节。"""
        return self._read("peek", offset, size)

    def pointer_all(self, jumps: list[int]) -> int:
        """返回 pointers 里这条指针链对应的值。"""
        key = tuple(jumps)
        if key not in self.pointers:
            raise AssertionError(f"假 Memory 没给过指针链 {[hex(jump) for jump in jumps]}")
        return self.pointers[key]

    def peek_absolute(self, address: int, size: int) -> bytes:
        """返回 data 里 address 这个地址对应的字节。"""
        return self._read("peek_absolute", address, size)

    def poke_absolute(self, address: int, data: bytes) -> None:
        """记下写入，不改 data。"""
        self.writes.append((address, data))

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


@pytest.fixture
def make_screen() -> Callable[[Sequence[bytes]], FakeScreen]:
    """返回一个函数：传入图片字节的列表，返回假 Screen。"""
    return FakeScreen


@pytest.fixture
def controller() -> FakeController:
    """假 Controller。"""
    return FakeController()


@pytest.fixture
def make_memory() -> Callable[..., FakeMemory]:
    """返回一个函数：传入 title_id() 要返回的值（可以不传）、地址对应的字节、指针链对应的值，返回假 Memory。"""

    def factory(
        title_id: str = DEFAULT_TITLE_ID,
        data: Mapping[int, bytes] | None = None,
        pointers: Mapping[tuple[int, ...], int] | None = None,
    ) -> FakeMemory:
        return FakeMemory(title_id, data, pointers)

    return factory


@pytest.fixture
def make_session(
    tmp_path: Path,
    make_screen: Callable[[Sequence[bytes]], FakeScreen],
    controller: FakeController,
    make_memory: Callable[..., FakeMemory],
) -> Callable[..., Session]:
    """返回一个函数：传入图片字节的列表和 title_id() 要返回的值，返回用假设备建的 Session。

    Session 的 step 是初始的空字符串。假 Controller 就是 controller 这个 fixture，
    假 Screen 和假 Memory 可以通过 session.screen、session.memory 取到。
    """

    def factory(images: Sequence[bytes], title_id: str = DEFAULT_TITLE_ID) -> Session:
        devices = Devices(make_screen(images), controller, make_memory(title_id))
        return Session(FakeConfig(tmp_path), load_settings({}), devices)

    return factory


@pytest.fixture
def clean_root_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[logging.Logger]:
    """测试开始前清空根 logger 的 handler，结束时把测试里加上的关掉、清掉，级别还原。"""
    root = logging.getLogger()
    old_level = root.level
    monkeypatch.setattr(root, "handlers", [])
    yield root
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)
    root.setLevel(old_level)
