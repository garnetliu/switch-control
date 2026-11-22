"""control_switch.device.base：Screen、Controller、Memory 三个接口。

接口是 runtime_checkable 的 Protocol，isinstance 只看有没有这些方法。
"""

from collections.abc import Callable
from typing import Any

from control_switch.device.base import Controller, Memory, Screen
from control_switch.device.botbase import Botbase

ConnectionFactory = Callable[..., Any]


def test_botbase_instance_is_a_screen(make_connection: ConnectionFactory) -> None:
    """Botbase 的实例是 Screen。"""
    assert isinstance(Botbase(make_connection()), Screen)


def test_botbase_instance_is_a_controller(make_connection: ConnectionFactory) -> None:
    """Botbase 的实例是 Controller。"""
    assert isinstance(Botbase(make_connection()), Controller)


def test_botbase_instance_is_a_memory(make_connection: ConnectionFactory) -> None:
    """Botbase 的实例是 Memory。"""
    assert isinstance(Botbase(make_connection()), Memory)


def test_fake_screen_matches_screen(make_screen: Callable[..., Any]) -> None:
    """tests/conftest.py 的假 Screen 符合 Screen。"""
    assert isinstance(make_screen([b"x"]), Screen)


def test_fake_controller_matches_controller(controller: Any) -> None:
    """tests/conftest.py 的假 Controller 符合 Controller。"""
    assert isinstance(controller, Controller)


def test_fake_memory_matches_memory(make_memory: Callable[..., Any]) -> None:
    """tests/conftest.py 的假 Memory 符合 Memory。"""
    assert isinstance(make_memory(), Memory)
