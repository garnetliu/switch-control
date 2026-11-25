"""control_switch.device.check：启动时检查设备。

假设备来自 tests/conftest.py 的 fixture。图片用 cv2 现画：16:9 是 320x180，4:3 是 320x240。
"""

import logging
from collections.abc import Callable, Sequence
from typing import Any

import cv2
import numpy as np
import pytest

from control_switch.device import (
    DeviceCheckError,
    Devices,
    check_devices,
    check_requires,
)
from control_switch.settings import build_settings

MemoryFactory = Callable[..., Any]
ScreenFactory = Callable[[Sequence[bytes]], Any]

TITLE_IDS = ("0100ABF008968000", "01008DB008C2C000")
ALL = frozenset({"screen", "controller", "memory"})


def encode(image: np.ndarray) -> bytes:
    """编码成 PNG 字节（无损，亮度不会变）。"""
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return bytes(buffer)


def lively_image() -> bytes:
    """16:9，黑底、正中间一块白色（宽高各占一半）：不是黑屏。"""
    image = np.zeros((180, 320, 3), np.uint8)
    image[45:135, 80:240] = 255
    return encode(image)


def black_image() -> bytes:
    """16:9，全是 0。"""
    return encode(np.zeros((180, 320, 3), np.uint8))


def dim_image() -> bytes:
    """16:9，整张图亮度都是 16（不是纯 0）。"""
    return encode(np.full((180, 320, 3), 16, np.uint8))


def make_devices(
    make_screen: ScreenFactory,
    controller: Any,
    make_memory: MemoryFactory,
    image: bytes | None = None,
    title_id: str = TITLE_IDS[0],
) -> Devices:
    """三样设备齐全：默认取图是一张正常的 16:9 图，title_id 是剑。"""
    return Devices(
        make_screen([lively_image() if image is None else image]),
        controller,
        make_memory(title_id),
    )


@pytest.fixture
def devices(make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory) -> Devices:
    """三样都正常的设备。"""
    return make_devices(make_screen, controller, make_memory)


def warnings_in(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """caplog 里级别是 WARNING 的记录。"""
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_check_devices_passes_when_all_devices_are_fine(devices: Devices) -> None:
    """三样都正常：不抛。"""
    check_devices(devices, ALL, TITLE_IDS)


def test_check_devices_raises_with_memory_hint_when_memory_missing(
    make_screen: ScreenFactory, controller: Any
) -> None:
    """requires 有 memory，devices.memory 是 None：抛 DeviceCheckError，报错里有 MEMORY。"""
    devices = Devices(make_screen([lively_image()]), controller, None)
    with pytest.raises(DeviceCheckError, match="memory"):
        check_devices(devices, ALL, TITLE_IDS)


def test_check_devices_error_is_runtime_error() -> None:
    """DeviceCheckError 是 RuntimeError 的子类。"""
    assert issubclass(DeviceCheckError, RuntimeError)


def test_check_devices_passes_when_memory_missing_but_not_required(
    make_screen: ScreenFactory, controller: Any
) -> None:
    """requires 没有 memory，devices.memory 是 None：不抛（也不读 title_id）。"""
    devices = Devices(make_screen([lively_image()]), controller, None)
    check_devices(devices, frozenset({"screen", "controller"}), TITLE_IDS)


def test_check_devices_raises_when_screen_returns_empty_bytes(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory
) -> None:
    """取图返回空字节：抛 DeviceCheckError，报错以「取图」开头。"""
    devices = make_devices(make_screen, controller, make_memory, image=b"")
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("取图")


def test_check_devices_raises_when_pixel_peek_raises_connection_error(
    devices: Devices, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pixel_peek 抛 ConnectionError：抛 DeviceCheckError（不是原来的异常），报错以「取图」开头。"""

    def broken() -> bytes:
        raise ConnectionError("断开了")

    monkeypatch.setattr(devices.screen, "pixel_peek", broken)
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("取图")


def test_check_devices_raises_when_image_bytes_are_not_an_image(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory
) -> None:
    """取图返回的字节解码不出图片：抛 DeviceCheckError，报错以「取图」开头。"""
    devices = make_devices(make_screen, controller, make_memory, image=b"not an image")
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("取图")


def test_check_devices_raises_screen_error_when_decoding_raises(
    make_screen: ScreenFactory,
    controller: Any,
    make_memory: MemoryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cv2.imdecode 抛 cv2.error（不是返回 None）：抛 DeviceCheckError（不是 cv2.error），报错以「取图」开头。

    防的是解码抛异常这一支（device/check.py 里 imdecode 外面的 try）没人测：真实的非空坏字节
    imdecode 只返回 None，走不到这一支，只能把 imdecode 换掉。
    """

    def broken(*args: Any) -> Any:
        raise cv2.error("解码崩了")

    monkeypatch.setattr(cv2, "imdecode", broken)
    devices = make_devices(make_screen, controller, make_memory, image=lively_image())
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("取图")


def test_check_devices_rejects_empty_bytes_before_decoding(
    make_screen: ScreenFactory,
    controller: Any,
    make_memory: MemoryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取图返回空字节：在解码之前就报错，cv2.imdecode 一次都没被调。

    约定要求空字节先判断；只看报错开头分不出来，因为去掉这个判断，imdecode 抛的 cv2.error
    也会被接住报成「取图」。
    """
    decoded: list[int] = []
    real = cv2.imdecode

    def spy(*args: Any) -> Any:
        decoded.append(1)
        return real(*args)

    monkeypatch.setattr(cv2, "imdecode", spy)
    devices = make_devices(make_screen, controller, make_memory, image=b"")
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("取图")
    assert decoded == []


def test_check_devices_raises_with_actual_size_when_aspect_is_4_to_3(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory
) -> None:
    """取图返回 320x240（4:3）的图：抛 DeviceCheckError，报错里有实际的宽 320 和高 240。"""
    image = encode(np.full((240, 320, 3), 128, np.uint8))
    devices = make_devices(make_screen, controller, make_memory, image=image)
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    message = str(error.value)
    assert message.startswith("取图")
    assert "320" in message
    assert "240" in message


def test_check_devices_warns_on_root_logger_when_image_is_all_black(
    make_screen: ScreenFactory,
    controller: Any,
    make_memory: MemoryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """取图返回全黑的 16:9 图：不抛，有一条警告日志，记录的 name 是 "root"（写根 logger）。"""
    devices = make_devices(make_screen, controller, make_memory, image=black_image())
    with caplog.at_level(logging.DEBUG):
        check_devices(devices, ALL, TITLE_IDS)
    records = warnings_in(caplog)
    assert len(records) == 1
    assert records[0].name == "root"


def test_check_devices_warns_when_image_is_uniformly_dim_not_pure_black(
    make_screen: ScreenFactory,
    controller: Any,
    make_memory: MemoryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """整张图亮度都是 16（不是纯 0）的 16:9 图：也算全黑，不抛，有一条警告日志。"""
    devices = make_devices(make_screen, controller, make_memory, image=dim_image())
    with caplog.at_level(logging.DEBUG):
        check_devices(devices, ALL, TITLE_IDS)
    assert len(warnings_in(caplog)) == 1


def test_check_devices_does_not_warn_when_image_has_white_block_on_black(
    devices: Devices, caplog: pytest.LogCaptureFixture
) -> None:
    """黑底、正中间一块白色（宽高各占一半）的 16:9 图：不抛，没有警告日志。"""
    with caplog.at_level(logging.DEBUG):
        check_devices(devices, ALL, TITLE_IDS)
    assert warnings_in(caplog) == []


def test_check_devices_raises_when_title_id_raises_connection_error(
    devices: Devices, monkeypatch: pytest.MonkeyPatch
) -> None:
    """title_id 抛 ConnectionError：抛 DeviceCheckError，报错以「内存」开头。"""

    def broken() -> str:
        raise ConnectionError("断开了")

    assert devices.memory is not None
    monkeypatch.setattr(devices.memory, "title_id", broken)
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("内存")


@pytest.mark.parametrize("title_id", ["", "   ", "\n"])
def test_check_devices_raises_when_title_id_is_empty(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory, title_id: str
) -> None:
    """title_id 是空字符串（或只有空白）：抛 DeviceCheckError，报错以「内存」开头。"""
    devices = make_devices(make_screen, controller, make_memory, title_id=title_id)
    with pytest.raises(DeviceCheckError) as error:
        check_devices(devices, ALL, TITLE_IDS)
    assert str(error.value).startswith("内存")


def test_check_devices_raises_with_value_when_title_id_is_other_game(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory
) -> None:
    """title_id 是别的游戏（大写、没有空白）：抛 DeviceCheckError，报错里有这个值。"""
    other = "0100000000000000"
    devices = make_devices(make_screen, controller, make_memory, title_id=other)
    with pytest.raises(DeviceCheckError, match=other):
        check_devices(devices, ALL, TITLE_IDS)


@pytest.mark.parametrize(
    "title_id", ["0100abf008968000", " 0100ABF008968000\n", "\t01008db008c2c000 "]
)
def test_check_devices_accepts_title_id_with_other_case_or_whitespace(
    make_screen: ScreenFactory, controller: Any, make_memory: MemoryFactory, title_id: str
) -> None:
    """title_id 大小写、前后空白不同但是同一个游戏：不抛。"""
    devices = make_devices(make_screen, controller, make_memory, title_id=title_id)
    check_devices(devices, ALL, TITLE_IDS)


def test_check_devices_does_not_read_title_id_when_title_ids_is_none(
    devices: Devices, monkeypatch: pytest.MonkeyPatch
) -> None:
    """title_ids 传 None：不读 title_id，不抛。"""
    reads: list[str] = []

    def spy() -> str:
        reads.append("title_id")
        return "0100000000000000"

    assert devices.memory is not None
    monkeypatch.setattr(devices.memory, "title_id", spy)
    check_devices(devices, ALL, None)
    assert reads == []


def test_check_requires_raises_with_memory_hint_when_memory_is_none() -> None:
    """requires 有 memory，settings.memory 是 "none"：抛 DeviceCheckError，报错里有 MEMORY。"""
    with pytest.raises(DeviceCheckError, match="memory"):
        check_requires(build_settings({"memory": "none"}), ALL)


def test_check_requires_passes_when_memory_is_botbase() -> None:
    """requires 有 memory，settings.memory 是 "botbase"：不抛。"""
    check_requires(build_settings({"memory": "botbase"}), ALL)


def test_check_requires_passes_when_memory_not_required() -> None:
    """requires 没有 memory，settings.memory 是 "none"：不抛。"""
    check_requires(build_settings({"memory": "none"}), frozenset({"screen", "controller"}))
