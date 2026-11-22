"""control_switch.flow.restart：重启游戏。

没有 HOME 菜单和选用户界面的截图，ImageChecker 上的 has_text、is_black、color_ratio 换成
按事先给定的顺序返回，用完后一直返回最后一个值（wait_for 超时前会反复调用判断，次数定不了）。
"""

import importlib
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.config import BaseConfig
from control_switch.flow.restart import enter_game, restart, restart_to_title
from control_switch.types import Hsv, Rect
from control_switch.vision import ImageChecker

IMAGES = Path(__file__).resolve().parents[1] / "images"
ROUTE = (IMAGES / "路线上的界面-要走哪条路.jpg").read_bytes()

SessionFactory = Callable[..., Any]

HOME_TEXT = "切换用户"
CLOSE_TEXT = "将关闭软件"
PICKER_TEXT = "由谁来游玩软件"
COLORFUL_RATIO = BaseConfig.colorful_ratio
TITLE_ID = "0100ABF008968000"


class Script:
    """按顺序返回给定的值，用完后一直返回最后一个。"""

    def __init__(self, values: Sequence[Any]) -> None:
        self._values = list(values)
        self._position = 0

    def next(self) -> Any:
        value = self._values[min(self._position, len(self._values) - 1)]
        self._position += 1
        return value


def install_checks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    home: Sequence[bool] = (True,),
    close: Sequence[bool] = (True,),
    picker: Sequence[bool] = (True,),
    black: Sequence[bool] = (True,),
    ratio: Sequence[float] = (1.0,),
) -> None:
    """把 ImageChecker 的判断换成按顺序返回。has_text 按要找的文字分成三条各自的顺序。"""
    texts = {
        HOME_TEXT: Script(home),
        CLOSE_TEXT: Script(close),
        PICKER_TEXT: Script(picker),
    }
    black_script = Script(black)
    ratio_script = Script(ratio)

    def has_text(self: ImageChecker, rect: Rect, text: str, min_similarity: float = 0.8) -> bool:
        return bool(texts[text].next())

    def is_black(self: ImageChecker) -> bool:
        return bool(black_script.next())

    def color_ratio(self: ImageChecker, rect: Rect, lower: Hsv, upper: Hsv) -> float:
        return float(ratio_script.next())

    monkeypatch.setattr(ImageChecker, "has_text", has_text)
    monkeypatch.setattr(ImageChecker, "is_black", is_black)
    monkeypatch.setattr(ImageChecker, "color_ratio", color_ratio)


def test_restart_to_title_presses_home_first_when_not_on_home(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一开始不在 HOME：第一个键是 HOME。"""
    install_checks(monkeypatch, home=[False, True])
    sw = make_session([ROUTE])
    restart_to_title(sw)
    assert controller.pressed[0] == "HOME"
    assert controller.pressed.count("HOME") == 1


def test_restart_to_title_does_not_press_home_when_already_on_home(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一开始就在 HOME：一次 HOME 都不按（HOME 上再按 HOME 会回到游戏）。"""
    install_checks(monkeypatch, home=[True])
    sw = make_session([ROUTE])
    restart_to_title(sw)
    assert "HOME" not in controller.pressed


def test_restart_to_title_presses_y_until_close_dialog_then_a_twice(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """按 Y 一直按到关闭软件的确认框出现，之后按了两次 A（先确认关闭，再选用户）。"""
    install_checks(monkeypatch, home=[True], close=[False, False, False, False, True])
    sw = make_session([ROUTE])
    restart_to_title(sw)
    assert controller.pressed[-2:] == ["A", "A"]
    assert controller.pressed.count("A") == 2
    presses_of_y = controller.pressed[:-2]
    assert len(presses_of_y) >= 2
    assert set(presses_of_y) == {"Y"}


def test_restart_to_title_raises_timeout_when_user_picker_never_appears(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """选用户的界面一直不出现：抛 TimeoutError，报错里有「选用户的界面」，只按了一次 A。"""
    install_checks(monkeypatch, picker=[False])
    sw = make_session([ROUTE])
    with pytest.raises(TimeoutError, match="选用户的界面"):
        restart_to_title(sw)
    assert controller.pressed.count("A") == 1


def test_restart_to_title_returns_when_title_id_is_lowercase_with_whitespace(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """title_id() 是 game_title_ids 里那个值的小写、前后带空白的写法，color_ratio 刚好等于 colorful_ratio：正常返回。"""
    install_checks(monkeypatch, ratio=[COLORFUL_RATIO])
    sw = make_session([ROUTE], title_id=" 0100abf008968000\n")
    restart_to_title(sw)
    assert controller.pressed[-2:] == ["A", "A"]


def test_restart_to_title_times_out_when_title_id_not_in_game_title_ids(
    make_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """title_id() 不在 game_title_ids 里：color_ratio 再高也一直等，抛 TimeoutError，有「开场的彩色画面」。"""
    install_checks(monkeypatch, ratio=[1.0])
    sw = make_session([ROUTE], title_id="0100000000000000")
    with pytest.raises(TimeoutError, match="开场的彩色画面"):
        restart_to_title(sw)


def test_restart_to_title_times_out_when_color_ratio_stays_below_colorful_ratio(
    make_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """title_id() 对但 color_ratio 一直低于 colorful_ratio：同样抛 TimeoutError，有「开场的彩色画面」。"""
    install_checks(monkeypatch, ratio=[COLORFUL_RATIO - 0.01])
    sw = make_session([ROUTE], title_id=TITLE_ID)
    with pytest.raises(TimeoutError, match="开场的彩色画面"):
        restart_to_title(sw)


def test_enter_game_does_not_press_a_when_screen_already_black(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """画面一开始就是黑的：一次 A 都不按。"""
    install_checks(monkeypatch, black=[True])
    sw = make_session([ROUTE])
    enter_game(sw)
    assert controller.pressed == []


def test_enter_game_presses_a_twice_when_third_image_is_black(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第 3 张图才变黑：按了 2 次 A。"""
    install_checks(monkeypatch, black=[False, False, True])
    sw = make_session([ROUTE])
    enter_game(sw)
    assert controller.pressed == ["A", "A"]


def test_restart_presses_keys_of_restart_to_title_then_enter_game(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """restart 的按键记录，是 restart_to_title 和 enter_game 各自的按键按顺序合起来的。"""
    scenario: dict[str, Any] = {
        "home": [False, True],
        "close": [False, False, True],
        "black": [False, False, True],
    }
    install_checks(monkeypatch, **scenario)
    restart_to_title(make_session([ROUTE]))
    first = list(controller.pressed)
    controller.pressed.clear()
    install_checks(monkeypatch, **scenario)
    enter_game(make_session([ROUTE]))
    second = list(controller.pressed)
    controller.pressed.clear()
    expected = first + second
    assert expected[0] == "HOME"
    assert expected[-2:] == ["A", "A"]

    install_checks(monkeypatch, **scenario)
    restart(make_session([ROUTE]))
    assert controller.pressed == expected


def test_restart_calls_restart_to_title_before_enter_game(
    make_session: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """restart 先调 restart_to_title，再调 enter_game，都传同一个连接。"""
    module: ModuleType = importlib.import_module("control_switch.flow.restart")
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(module, "restart_to_title", lambda sw: calls.append(("title", sw)))
    monkeypatch.setattr(module, "enter_game", lambda sw: calls.append(("enter", sw)))
    sw = make_session([ROUTE])
    restart(sw)
    assert calls == [("title", sw), ("enter", sw)]


class PressedTooLongError(Exception):
    """测试用的保护：按键持续了太久，说明 enter_game 不会自己停。"""


def test_enter_game_raises_timeout_error_when_screen_never_turns_black(
    make_session: SessionFactory, controller: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """防的是：画面一直不变黑时 enter_game 没有超时，无限按 A，sw.frames 无限变长。

    别的等画面的函数都会超时抛 TimeoutError，入口靠这个存截图、发通知；enter_game 卡住时什么都不会发生。
    假连接的超时都是 1 秒；按键持续 5 秒还没停就抛 PressedTooLongError，免得测试本身卡死。
    """
    install_checks(monkeypatch, black=[False])
    sw = make_session([ROUTE])
    start = time.monotonic()

    def click(button: str, delay: float = 0.15) -> None:
        controller.pressed.append(button)
        if time.monotonic() - start > 5:
            raise PressedTooLongError(f"按了 {len(controller.pressed)} 次 A，画面不变黑就一直按")

    monkeypatch.setattr(controller, "click", click)
    with pytest.raises(TimeoutError):
        enter_game(sw)
