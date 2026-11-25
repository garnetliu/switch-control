"""control_switch.games.sv.egg.config：EggConfig.fly_icon 指向包里的图标文件。"""

from pathlib import Path

import cv2

from control_switch.games import sv
from control_switch.games.sv.egg.config import EggConfig


def test_fly_icon_is_inside_sv_package() -> None:
    """fly_icon 等于 sv 包目录下 data/fly_icon.png，类型是 Path。"""
    assert isinstance(EggConfig.fly_icon, Path)
    assert EggConfig.fly_icon == Path(sv.__file__).parent / "data" / "fly_icon.png"


def test_fly_icon_exists() -> None:
    """fly_icon 文件存在。"""
    assert EggConfig.fly_icon.is_file()


def test_fly_icon_readable_by_cv2() -> None:
    """cv2.imread 能把 fly_icon 读成图像。"""
    assert cv2.imread(str(EggConfig.fly_icon)) is not None
