"""control_switch.device.capture_card：用采集卡取图。

不打开真的采集卡：假采集卡按事先给定的顺序返回 (ok, 图片)，用完后一直返回最后一个，
记下 release() 的次数，isOpened() 返回事先给定的值；
control_switch.device.capture_card.cv2.VideoCapture 换成返回假采集卡的函数，记下参数和 set 过的属性。
"""

import logging
from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from control_switch.device import DeviceCheckError, Screen
from control_switch.device.capture_card import CaptureCard, open_capture_card
from control_switch.settings import build_settings

Frame = NDArray[np.uint8]
Reading = tuple[bool, Frame | None]


def make_frame(width: int, height: int) -> Frame:
    """给定大小的彩色图，每个像素值不同，编码再解码后大小不变。"""
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


class FakeVideo:
    """假采集卡：按顺序返回给定的 (ok, 图片)，用完后一直返回最后一个。"""

    def __init__(self, readings: Sequence[Reading], *, opened: bool = True) -> None:
        assert readings, "至少要给一个读取结果"
        self._readings = list(readings)
        self._opened = opened
        self.reads = 0
        self.release_calls = 0
        self.properties: dict[int, float] = {}

    def isOpened(self) -> bool:
        """返回事先给定的值。"""
        return self._opened

    def read(self) -> Reading:
        """按顺序返回事先给定的读取结果。"""
        index = min(self.reads, len(self._readings) - 1)
        self.reads += 1
        return self._readings[index]

    def set(self, prop: int, value: float) -> bool:
        """记下设过的属性。"""
        self.properties[prop] = value
        return True

    def release(self) -> None:
        """记下调用次数。"""
        self.release_calls += 1


class FakeVideoCapture:
    """假的 cv2.VideoCapture：记下收到的参数，返回同一个假采集卡。"""

    def __init__(self, video: FakeVideo) -> None:
        self.video = video
        self.args: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> FakeVideo:
        self.args.append(args)
        return self.video


def install(monkeypatch: pytest.MonkeyPatch, video: FakeVideo) -> FakeVideoCapture:
    """把 control_switch.device.capture_card.cv2.VideoCapture 换成返回 video 的函数。"""
    fake = FakeVideoCapture(video)
    monkeypatch.setattr("control_switch.device.capture_card.cv2.VideoCapture", fake)
    return fake


def test_pixel_peek_returns_jpeg_bytes_decodable_to_the_same_size() -> None:
    """给进去 1920x1080 的图：pixel_peek() 返回的字节能用 cv2.imdecode 解回来，仍是 1920x1080。"""
    card = CaptureCard(FakeVideo([(True, make_frame(1920, 1080))]))
    data = card.pixel_peek()
    assert isinstance(data, bytes)
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (1080, 1920)


def test_pixel_peek_does_not_resize_other_sizes() -> None:
    """给进去 1280x720 的图：解出来还是 1280x720，不缩小、不裁剪。"""
    card = CaptureCard(FakeVideo([(True, make_frame(1280, 720))]))
    decoded = cv2.imdecode(np.frombuffer(card.pixel_peek(), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (720, 1280)


def test_pixel_peek_reads_again_when_first_read_fails() -> None:
    """第一次读不到、第二次读到：正常返回，一共读了两次。"""
    video = FakeVideo([(False, None), (True, make_frame(64, 36))])
    data = CaptureCard(video).pixel_peek()
    assert data
    assert video.reads == 2


def test_pixel_peek_reads_again_when_image_is_none_with_ok_true() -> None:
    """ok 是 True 但图片是 None 也算读不到：再读一次，第二次读到就正常返回。"""
    video = FakeVideo([(True, None), (True, make_frame(64, 36))])
    assert CaptureCard(video).pixel_peek()
    assert video.reads == 2


def test_pixel_peek_raises_connection_error_after_three_failed_reads() -> None:
    """连续 3 次读不到：抛 ConnectionError，报错里有「采集卡」，一共只读了 3 次。"""
    video = FakeVideo([(False, None)])
    with pytest.raises(ConnectionError) as error:
        CaptureCard(video).pixel_peek()
    assert "采集卡" in str(error.value)
    assert video.reads == 3


def test_pixel_peek_raises_connection_error_when_encoding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cv2.imencode 编码失败（返回 False）：抛 ConnectionError。"""
    monkeypatch.setattr(
        "control_switch.device.capture_card.cv2.imencode", lambda ext, image: (False, None)
    )
    with pytest.raises(ConnectionError):
        CaptureCard(FakeVideo([(True, make_frame(64, 36))])).pixel_peek()


def test_close_twice_releases_once_without_error() -> None:
    """close() 调两次：release() 只调了一次，不出错。"""
    video = FakeVideo([(True, make_frame(64, 36))])
    card = CaptureCard(video)
    card.close()
    card.close()
    assert video.release_calls == 1


def test_capture_card_is_a_screen() -> None:
    """CaptureCard 的实例是 Screen。"""
    assert isinstance(CaptureCard(FakeVideo([(True, make_frame(64, 36))])), Screen)


def test_open_uses_capture_device_index_avfoundation_and_sets_1920x1080(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正常打开：cv2.VideoCapture 收到 capture_device 的序号和 cv2.CAP_AVFOUNDATION，
    设了宽 1920、高 1080，返回 CaptureCard。
    """
    video = FakeVideo([(True, make_frame(1920, 1080))])
    fake = install(monkeypatch, video)
    card = open_capture_card(build_settings({"capture_device": 2}))
    assert isinstance(card, CaptureCard)
    assert fake.args == [(2, cv2.CAP_AVFOUNDATION)]
    assert video.properties[cv2.CAP_PROP_FRAME_WIDTH] == 1920
    assert video.properties[cv2.CAP_PROP_FRAME_HEIGHT] == 1080
    assert video.release_calls == 0


def test_open_raises_device_check_error_with_index_when_not_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """isOpened() 是 False：抛 DeviceCheckError，报错以「取图」开头，里面有序号。"""
    install(monkeypatch, FakeVideo([(True, make_frame(1920, 1080))], opened=False))
    with pytest.raises(DeviceCheckError) as error:
        open_capture_card(build_settings({"capture_device": 9}))
    message = str(error.value)
    assert message.startswith("取图")
    assert "9" in message


def test_open_raises_device_check_error_and_releases_when_first_frame_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第一帧读不到：抛 DeviceCheckError，报错以「取图」开头，有「摄像头权限」，假采集卡被释放了。"""
    video = FakeVideo([(False, None)])
    install(monkeypatch, video)
    with pytest.raises(DeviceCheckError) as error:
        open_capture_card(build_settings({}))
    message = str(error.value)
    assert message.startswith("取图")
    assert "摄像头权限" in message
    assert video.release_calls == 1


def test_open_releases_when_first_frame_is_none_with_ok_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第一帧 ok 是 True 但图片是 None：同样抛 DeviceCheckError，假采集卡被释放了。"""
    video = FakeVideo([(True, None)])
    install(monkeypatch, video)
    with pytest.raises(DeviceCheckError):
        open_capture_card(build_settings({}))
    assert video.release_calls == 1


def test_open_warns_with_actual_size_when_first_frame_is_1280x720(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """第一帧是 1280x720：记了一条 WARNING 日志，里面有 1280，照样返回 CaptureCard，没有释放。"""
    video = FakeVideo([(True, make_frame(1280, 720))])
    install(monkeypatch, video)
    with caplog.at_level(logging.WARNING):
        card = open_capture_card(build_settings({}))
    assert isinstance(card, CaptureCard)
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "1280" in warnings[0].getMessage()
    assert video.release_calls == 0


def test_open_does_not_warn_when_first_frame_is_1920x1080(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """第一帧是 1920x1080：没有 WARNING 日志。"""
    install(monkeypatch, FakeVideo([(True, make_frame(1920, 1080))]))
    with caplog.at_level(logging.WARNING):
        open_capture_card(build_settings({}))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_video_source_read_return_type_says_image_or_none() -> None:
    """约定写的是 read() -> tuple[bool, 图片或 None]。

    防的是第二项标成 Any：Any 里看不出可能是 None，pyright 也不会要求调用的地方先判断 None。
    第二项要写成具体的图片类型（例如 cv2.typing.MatLike）并且包含 None。
    """
    import types
    import typing

    from control_switch.device.capture_card import VideoSource

    returned = typing.get_type_hints(VideoSource.read)["return"]
    assert typing.get_origin(returned) is tuple
    ok_type, image_type = typing.get_args(returned)
    assert ok_type is bool
    assert image_type is not Any, "图片标成了 Any，看不出可能是 None"
    assert typing.get_origin(image_type) in (typing.Union, types.UnionType)
    assert type(None) in typing.get_args(image_type)
