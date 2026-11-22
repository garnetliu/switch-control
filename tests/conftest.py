"""所有测试共用的假连接和日志清理。

假连接不继承 Switch，只有流程代码用到的东西。传给参数标成 Switch 的函数时在测试里用 typing.cast。
"""

import logging
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from control_switch.config import BaseConfig
from control_switch.device.botbase import Frame

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


class FakeSwitch:
    """假连接：按顺序给图片，记下按过的键，不等待。"""

    def __init__(self, images: Sequence[bytes], title: str, log_dir: Path) -> None:
        assert images, "至少要给一张图片"
        self._images = list(images)
        self._title = title
        self._position = 0
        self.pressed: list[str] = []
        self.config = FakeConfig(log_dir)
        self.frames: list[Frame] = []
        self.step = "测试步骤"

    def pixel_peek(self) -> bytes:
        """按顺序返回事先给定的图片，用完后一直返回最后一张。"""
        index = min(self._position, len(self._images) - 1)
        self._position += 1
        return self._images[index]

    def click(self, button: str, delay: float) -> None:
        """记下按过的键，不等待。"""
        self.pressed.append(button)

    def title_id(self) -> str:
        """返回事先给定的值。"""
        return self._title


@pytest.fixture
def make_switch(tmp_path: Path) -> Callable[..., FakeSwitch]:
    """返回一个函数：传入图片字节的列表和 title_id() 要返回的值，返回假连接。"""

    def factory(images: Sequence[bytes], title_id: str = DEFAULT_TITLE_ID) -> FakeSwitch:
        return FakeSwitch(images, title_id, tmp_path)

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
