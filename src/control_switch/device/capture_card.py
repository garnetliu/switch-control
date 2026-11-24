"""用采集卡取图：从 Switch 底座输出的画面里取，原样 1920×1080，不缩小。"""

import logging
from typing import Protocol

import cv2
from cv2.typing import MatLike

from control_switch.settings import Settings

from .check import DeviceCheckError

_WIDTH = 1920
_HEIGHT = 1080
# 读不到画面时最多读几次
_READ_ATTEMPTS = 3


class VideoSource(Protocol):
    """cv2.VideoCapture 和测试里的假采集卡都符合。"""

    def read(self) -> tuple[bool, MatLike | None]: ...

    def release(self) -> None: ...


class CaptureCard:
    """用采集卡取图，实现 Screen。"""

    def __init__(self, video: VideoSource) -> None:
        self._video = video
        self._released = False

    def pixel_peek(self) -> bytes:
        """读一帧，编码成 JPEG 字节。读不到时再读，连续 3 次读不到抛 ConnectionError。"""
        for _ in range(_READ_ATTEMPTS):
            ok, image = self._video.read()
            if ok and image is not None:
                break
        else:
            raise ConnectionError("取图：采集卡读不到画面")
        encoded, buffer = cv2.imencode(".jpg", image)
        if not encoded:
            raise ConnectionError("取图：采集卡的画面编码失败")
        return buffer.tobytes()

    def close(self) -> None:
        """释放采集卡，调用多次只释放一次。"""
        if self._released:
            return
        self._released = True
        self._video.release()


def open_capture_card(settings: Settings) -> CaptureCard:
    """打开 settings.capture_device 号采集卡，要求 1920×1080；打不开或读不到画面抛 DeviceCheckError。"""
    index = settings.capture_device
    video = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not video.isOpened():
        raise DeviceCheckError(
            f"取图：采集卡打不开（CAPTURE_DEVICE={index}），检查采集卡有没有插好、序号对不对"
        )
    video.set(cv2.CAP_PROP_FRAME_WIDTH, _WIDTH)
    video.set(cv2.CAP_PROP_FRAME_HEIGHT, _HEIGHT)
    ok, image = video.read()
    if not ok or image is None:
        video.release()
        raise DeviceCheckError(
            f"取图：采集卡打开了但读不到画面（CAPTURE_DEVICE={index}），检查终端有没有摄像头权限"
        )
    height, width = image.shape[:2]
    if (width, height) != (_WIDTH, _HEIGHT):
        logging.warning(
            f"取图：采集卡的画面是 {width}×{height}，不是 {_WIDTH}×{_HEIGHT}，"
            f"可能 CAPTURE_DEVICE={index} 指到了别的摄像头"
        )
    return CaptureCard(video)
