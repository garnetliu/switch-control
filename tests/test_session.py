"""control_switch.session：Session 把配置、当前步骤、这一局的截图、通知和三个设备放在一起。

设备用 tests/conftest.py 的假 Screen、假 Controller、假 Memory，直接传给 Session。
"""

from collections.abc import Callable
from typing import Any

import pytest

from control_switch.config import BaseConfig
from control_switch.notifier import Notifier
from control_switch.session import Session


class AllInOne:
    """像 Botbase 那样一个对象同时当 Screen、Controller、Memory 用，记下 close() 调了几次。"""

    def __init__(self) -> None:
        self.close_calls = 0

    def pixel_peek(self) -> bytes:
        return b""

    def click(self, button: str, delay: float = 0.15) -> None:
        pass

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        pass

    def title_id(self) -> str:
        return ""

    def peek(self, offset: int, size: int) -> bytes:
        return b""

    def pointer_all(self, jumps: list[int]) -> int:
        return 0

    def peek_absolute(self, address: int, size: int) -> bytes:
        return b""

    def poke_absolute(self, address: int, data: bytes) -> None:
        pass

    def close(self) -> None:
        self.close_calls += 1


ScreenFactory = Callable[..., Any]
MemoryFactory = Callable[..., Any]


def test_click_is_forwarded_to_controller(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """click("A", 0.5)：转给 controller，按键和 delay 都原样传过去。"""
    session = Session(BaseConfig(), make_screen([b"img"]), controller, make_memory())
    session.click("A", 0.5)
    assert controller.pressed == ["A"]
    assert controller.delays == [0.5]


def test_stick_is_forwarded_to_controller(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """stick("LEFT", 100, -200, 0.08)：转给 controller，四个参数原样传过去。"""
    session = Session(BaseConfig(), make_screen([b"img"]), controller, make_memory())
    session.stick("LEFT", 100, -200, 0.08)
    assert controller.sticks == [("LEFT", 100, -200, 0.08)]


def test_pixel_peek_returns_image_of_screen(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """pixel_peek：返回假 Screen 给的图，按它给的顺序。"""
    session = Session(BaseConfig(), make_screen([b"first", b"second"]), controller, make_memory())
    assert session.pixel_peek() == b"first"
    assert session.pixel_peek() == b"second"


def test_attributes_are_what_was_passed_in(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """config、screen、controller、memory 就是传进来的对象，notifier 是 Notifier。"""
    config = BaseConfig()
    screen = make_screen([b"img"])
    memory = make_memory()
    session = Session(config, screen, controller, memory)
    assert session.config is config
    assert session.screen is screen
    assert session.controller is controller
    assert session.memory is memory
    assert isinstance(session.notifier, Notifier)


def test_step_starts_as_empty_string_and_frames_as_empty_list(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """step 初始是空字符串，frames 初始是空列表。"""
    session = Session(BaseConfig(), make_screen([b"img"]), controller, make_memory())
    assert session.step == ""
    assert session.frames == []


def test_memory_returns_the_memory_when_given(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """memory 给了就能用：取 memory 拿到它，peek 读到假 Memory 给的字节。"""
    memory = make_memory(data={0x10: b"\x01\x02"})
    session = Session(BaseConfig(), make_screen([b"img"]), controller, memory)
    assert session.memory.peek(0x10, 2) == b"\x01\x02"


def test_memory_raises_runtime_error_when_none(make_screen: ScreenFactory, controller: Any) -> None:
    """memory 给 None：取 memory 抛 RuntimeError。"""
    session = Session(BaseConfig(), make_screen([b"img"]), controller, None)
    with pytest.raises(RuntimeError):
        _ = session.memory


def test_close_closes_shared_object_once() -> None:
    """三个设备是同一个对象：close() 只关一次。"""
    shared = AllInOne()
    Session(BaseConfig(), shared, shared, shared).close()
    assert shared.close_calls == 1


def test_close_closes_three_different_objects_once_each(
    make_screen: ScreenFactory, make_memory: MemoryFactory, controller: Any
) -> None:
    """三个设备是三个不同的对象：各关一次。"""
    screen = make_screen([b"img"])
    memory = make_memory()
    session = Session(BaseConfig(), screen, controller, memory)
    session.close()
    assert (screen.close_calls, controller.close_calls, memory.close_calls) == (1, 1, 1)


def test_close_closes_object_shared_by_screen_and_controller_once_and_memory_once(
    make_memory: MemoryFactory,
) -> None:
    """screen 和 controller 是同一个对象、memory 是另一个：两个对象各关一次。"""
    shared = AllInOne()
    memory = make_memory()
    Session(BaseConfig(), shared, shared, memory).close()
    assert shared.close_calls == 1
    assert memory.close_calls == 1


def test_close_with_none_memory_closes_the_other_two(
    make_screen: ScreenFactory, controller: Any
) -> None:
    """memory 是 None：close() 不出错，screen 和 controller 照常各关一次。"""
    screen = make_screen([b"img"])
    session = Session(BaseConfig(), screen, controller, None)
    session.close()
    assert screen.close_calls == 1
    assert controller.close_calls == 1
