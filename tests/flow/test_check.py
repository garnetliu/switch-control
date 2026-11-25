"""control_switch.flow.check：确认按键真的送到了画面上的这台 Switch。

control_switch.flow.check.home_shown 换成按事先给定的顺序返回，用完后一直返回最后一个值
（等画面时会反复调用，次数定不了）。不能按 control_switch.flow.restart 这个路径换，
flow/__init__.py 里的同名函数 restart 把它盖住了。
config.check.timeout 设成 1.0，超时的用例不用真等 10 秒。
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from control_switch.device import DeviceCheckError
from control_switch.flow.check import check_controller_reaches_screen

ROUTE = (
    Path(__file__).resolve().parents[1] / "images" / "路线上的界面-要走哪条路.jpg"
).read_bytes()

SessionFactory = Callable[..., Any]


def install_home_shown(monkeypatch: pytest.MonkeyPatch, values: Sequence[bool]) -> list[int]:
    """home_shown 换成按顺序返回 values 的函数，用完后一直返回最后一个；返回的列表里记着调用次数（长度）。"""
    calls: list[int] = []

    def home_shown(sw: Any, screen: Any) -> bool:
        index = min(len(calls), len(values) - 1)
        calls.append(index)
        return values[index]

    monkeypatch.setattr("control_switch.flow.check.home_shown", home_shown)
    return calls


@pytest.fixture
def sw(make_session: SessionFactory, monkeypatch: pytest.MonkeyPatch) -> Any:
    """用假设备建的 Session，config.check.timeout 设成 1.0。"""
    session = make_session([ROUTE])
    monkeypatch.setattr(session.config.check, "timeout", 1.0)
    return session


def test_check_passes_and_presses_home_twice_when_not_on_home_at_first(
    sw: Any, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """原来不在 HOME（HOME 出现，再回去）：按了两次 HOME，不抛。"""
    install_home_shown(monkeypatch, [False, True, False])
    check_controller_reaches_screen(sw)
    assert controller.pressed == ["HOME", "HOME"]


def test_check_passes_and_presses_home_twice_when_on_home_at_first(
    sw: Any, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """原来在 HOME（HOME 消失，再回来）：按了两次 HOME，不抛。"""
    install_home_shown(monkeypatch, [True, False, True])
    check_controller_reaches_screen(sw)
    assert controller.pressed == ["HOME", "HOME"]


def test_check_raises_after_one_press_when_screen_never_changes_after_first_press(
    sw: Any, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第一次按完画面一直不变：抛 DeviceCheckError，只按了一次 HOME。"""
    install_home_shown(monkeypatch, [False])
    with pytest.raises(DeviceCheckError):
        check_controller_reaches_screen(sw)
    assert controller.pressed == ["HOME"]


def test_check_raises_when_screen_never_returns_after_second_press(
    sw: Any, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第二次按完画面一直不回到原来的状态：抛 DeviceCheckError，按了两次 HOME。"""
    install_home_shown(monkeypatch, [False, True])
    with pytest.raises(DeviceCheckError):
        check_controller_reaches_screen(sw)
    assert controller.pressed == ["HOME", "HOME"]
