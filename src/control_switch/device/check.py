"""启动时检查设备：脚本要的设备有没有、取图能不能用、前台是不是这个脚本的游戏。"""

import logging
from collections.abc import Collection
from typing import TYPE_CHECKING

import cv2
import numpy as np

from control_switch.settings import Settings

if TYPE_CHECKING:
    from .factory import Devices


class DeviceCheckError(RuntimeError):
    """设备检查没通过，报错开头写明是哪一类：取图、按键、内存。"""


def check_requires(settings: Settings, requires: Collection[str]) -> None:
    """只看配置：脚本要读内存而这台机器的 memory 是 none 时抛 DeviceCheckError。不碰设备。"""
    _check_memory_required(requires, settings.memory != "none")


def check_devices(
    devices: "Devices", requires: Collection[str], title_ids: Collection[str] | None
) -> None:
    """按顺序检查设备，遇到第一个不通过的抛 DeviceCheckError。

    按键能不能用，create_devices 连接时就确认了，这里不再检查。
    title_ids 是 None 时不检查前台游戏。
    """
    _check_memory_required(requires, devices.memory is not None)
    _check_screen(devices)
    if devices.memory is not None and title_ids is not None:
        _check_game(devices, title_ids)


def _check_memory_required(requires: Collection[str], has_memory: bool) -> None:
    if "memory" in requires and not has_memory:
        raise DeviceCheckError(
            "内存：这个脚本要读内存，runs/switches.toml 里这台机器的 memory 不能是 none"
        )


def _check_screen(devices: "Devices") -> None:
    try:
        data = devices.screen.pixel_peek()
    except Exception as error:
        raise DeviceCheckError(f"取图：取不到画面：{error}") from error
    if isinstance(data, np.ndarray):
        image = data
    else:
        if not data:
            raise DeviceCheckError("取图：取到的画面是空的")
        try:
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as error:
            raise DeviceCheckError(f"取图：取到的画面解码失败：{error}") from error
    if image is None:
        raise DeviceCheckError("取图：取到的内容不是图片")
    height, width = image.shape[:2]
    # 宽高比和 16:9 差多少以内算 16:9
    aspect_tolerance = 0.01
    if abs(width / height - 16 / 9) > aspect_tolerance:
        raise DeviceCheckError(f"取图：画面不是 16:9，实际是 {width}x{height}")
    # 全黑的标准和 ImageChecker.is_black 一样：亮度不超过 50 的像素占比至少 98%，亮度标准差不超过 10
    dark_value, dark_ratio, dark_std = 50, 0.98, 10
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    if float((value <= dark_value).mean()) >= dark_ratio and float(value.std()) <= dark_std:
        logging.warning("取图：画面全黑，可能没有画面输出")


def _check_game(devices: "Devices", title_ids: Collection[str]) -> None:
    assert devices.memory is not None
    try:
        raw = devices.memory.title_id()
    except Exception as error:
        raise DeviceCheckError(f"内存：读不到前台游戏的 Title ID：{error}") from error
    title_id = raw.strip().upper()
    if not title_id:
        raise DeviceCheckError("内存：没有游戏在运行")
    if title_id not in title_ids:
        raise DeviceCheckError(f"内存：前台不是这个脚本的游戏（Title ID {title_id}）")
