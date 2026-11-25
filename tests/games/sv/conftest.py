"""朱紫（sv/egg、sv/actions）测试共用：假时钟、会记按键的假设备、可以替换的识别函数和步骤里的小函数。

不用真机截图：步骤里看画面的地方都是调 screens 模块里的函数（screens.is_dialog(image) 这样），
测试用 stage.set_screens 把它们换成读「游戏画面模型」的函数；步骤里 _ 开头的小函数、box 和 fly
里的操作用 stage.replace 换成记录调用的假函数。所以步骤和 box 里必须通过模块属性调用它们
（screens.xxx、box.xxx、fly.xxx、actions.xxx、flow.restart），不能 from ... import xxx。

Stage 记录的 log 里每一项是一个元组：
- 按键：("click", 键)、("press", 键)、("release", 键)
- 摇杆：("stick", 边, x, y, 秒)，x、y 除过 STICK_MAX、保留 3 位小数（所以满推是 1.0，y 正数向上）；
  ("press_stick", 边, x, y)、("release_stick", 边)
- 假函数记的调用：(函数名, 参数...)，不含第一个参数 sw
时间是假的：time.sleep 和按键的 delay、摇杆的 hold 都让假时钟往前走，不真的等待。
"""

import importlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.device import Devices
from control_switch.games.sv.egg.session import EggSession
from control_switch.settings import build_settings

# 一个测试里最多允许按多少次键、截多少次图，超过说明实现停不下来，直接报错
MAX_EVENTS = 3000
MAX_PEEKS = 20000


class Clock:
    """假时钟：sleep 只让时间往前走。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        """假的 time.monotonic。"""
        return self.now

    def sleep(self, seconds: float) -> None:
        """假的 time.sleep。"""
        self.now += seconds


class Shot:
    """假截图：代替 ImageChecker。识别函数都被换掉了，只有 save 会被用到。"""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def save(self, path: str) -> None:
        """写一个假的图片文件。"""
        Path(path).write_bytes(self.data)


class StageScreen:
    """假 Screen：每次截图返回同一串字节，截得太多说明实现停不下来。"""

    def __init__(self) -> None:
        self.peeks = 0
        self.close_calls = 0

    def pixel_peek(self) -> bytes:
        """返回假截图的字节。"""
        self.peeks += 1
        assert self.peeks <= MAX_PEEKS, "截图太多次，实现停不下来"
        return b"shot"

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


@dataclass
class Stage:
    """一个测试用的舞台：Session、假时钟、按键记录，以及替换函数的方法。"""

    sw: EggSession
    clock: Clock
    monkeypatch: pytest.MonkeyPatch
    stick_max: int
    log: list[tuple[Any, ...]] = field(default_factory=list)
    # 每次 click 的时间（假时钟），和 log 里 click 的顺序一一对应
    click_times: list[float] = field(default_factory=list)
    # 每次按键（click）之前调用，参数是键名，让游戏画面模型跟着按键变化
    on_click: Callable[[str], None] | None = None

    def clicks(self) -> list[str]:
        """log 里按过的键（click），按顺序。"""
        return [entry[1] for entry in self.log if entry[0] == "click"]

    def replace(self, module: ModuleType, name: str, value: Any) -> None:
        """把模块里的一个属性换成 value；这个属性必须已经存在。"""
        self.monkeypatch.setattr(module, name, value)

    def stub(self, module: ModuleType, name: str, result: Any = None) -> None:
        """把模块里的函数换成假函数：调用时在 log 里记 (name, 除 sw 外的参数...)，返回 result。

        result 是可调用对象时，用同样的参数（除 sw）调用它，返回它的结果。
        """

        def fake(sw: Any, *args: Any, **kwargs: Any) -> Any:
            self.log.append((name, *args))
            return result(*args, **kwargs) if callable(result) else result

        self.replace(module, name, fake)

    def set_screens(self, **functions: Callable[[], Any]) -> None:
        """把 screens 模块里的识别函数换成不看图片、调 functions 里对应函数的函数。"""
        screens = importlib.import_module("control_switch.games.sv.egg.screens")
        for name, function in functions.items():
            self.replace(screens, name, _ignore_image(function))

    def set_sv_screens(self, **functions: Callable[[], Any]) -> None:
        """同 set_screens，换的是 control_switch.games.sv.screens（几个脚本共用的识别函数，actions.py 用的是它）。"""
        screens = importlib.import_module("control_switch.games.sv.screens")
        for name, function in functions.items():
            self.replace(screens, name, _ignore_image(function))

    def advance(self, seconds: float) -> None:
        """假时钟往前走。"""
        self.clock.sleep(seconds)


def _ignore_image(function: Callable[[], Any]) -> Callable[..., Any]:
    def fake(image: Any, *args: Any, **kwargs: Any) -> Any:
        return function()

    return fake


@pytest.fixture
def stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    controller: Any,
    clean_root_logger: Any,
) -> Stage:
    """用假设备建好的 EggSession，time 和 flow.wait 里的 ImageChecker 都换成假的。

    没有内存设备。config 的 log_dir、shiny_dir 指到临时目录，wait.interval 改成 0.5 秒（少截几次图）。
    """
    clock = Clock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    wait_module = importlib.import_module("control_switch.flow.wait")
    monkeypatch.setattr(wait_module, "ImageChecker", Shot)

    devices = Devices(StageScreen(), controller, None)
    sw = EggSession(build_settings({}), devices)
    sw.config.log_dir = tmp_path / "logs"
    sw.config.shiny_dir = tmp_path / "shinys"
    sw.config.wait.interval = 0.5
    result = Stage(sw, clock, monkeypatch, controller.STICK_MAX)

    def record(entry: tuple[Any, ...]) -> None:
        result.log.append(entry)
        assert len(result.log) <= MAX_EVENTS, "按键太多次，实现停不下来"

    def norm(value: int) -> float:
        return round(value / result.stick_max, 3)

    original_click = controller.click

    def click(button: str, delay: float = 0.15) -> None:
        if result.on_click is not None:
            result.on_click(button)
        record(("click", button))
        result.click_times.append(clock.now)
        original_click(button, delay)
        clock.sleep(delay)

    def stick(side: str, x: int, y: int, hold: float) -> None:
        record(("stick", side, norm(x), norm(y), hold))
        controller.sticks.append((side, x, y, hold))
        clock.sleep(hold)

    def press(button: str) -> None:
        record(("press", button))

    def release(button: str) -> None:
        record(("release", button))

    def press_stick(side: str, x: int, y: int) -> None:
        record(("press_stick", side, norm(x), norm(y)))

    def release_stick(side: str) -> None:
        record(("release_stick", side))

    monkeypatch.setattr(controller, "click", click)
    monkeypatch.setattr(controller, "stick", stick)
    monkeypatch.setattr(controller, "press", press)
    monkeypatch.setattr(controller, "release", release)
    monkeypatch.setattr(controller, "press_stick", press_stick)
    monkeypatch.setattr(controller, "release_stick", release_stick)
    return result
