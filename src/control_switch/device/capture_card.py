"""用采集卡取图：从 Switch 底座输出的画面里取，原样 1920×1080，不缩小。"""

import logging
from typing import Protocol

import cv2
from cv2.typing import MatLike

from control_switch.settings import Settings

from .check import DeviceCheckError


class VideoSource(Protocol):
    """cv2.VideoCapture 和测试里的假采集卡都符合。"""

    def read(self) -> tuple[bool, MatLike | None]: ...

    def release(self) -> None: ...


class CaptureCard:
    """用采集卡取图，实现 Screen。"""

    def __init__(self, video: VideoSource) -> None:
        self._video = video
        self._released = False

    def pixel_peek(self) -> MatLike:
        """读一帧，原样返回 BGR 数组，不编码。读不到时再读，连续 3 次读不到抛 ConnectionError。"""
        # 读不到画面时最多读几次
        attempts = 3
        for _ in range(attempts):
            ok, image = self._video.read()
            if ok and image is not None:
                break
        else:
            raise ConnectionError("取图：采集卡读不到画面")
        return image

    def close(self) -> None:
        """释放采集卡，调用多次只释放一次。"""
        if self._released:
            return
        self._released = True
        self._video.release()


def open_capture_card(settings: Settings) -> CaptureCard:
    """打开 settings.capture_device 号采集卡，要求 1920×1080；打不开或读不到画面抛 DeviceCheckError。"""
    index = settings.capture_device
    # 要的画面大小
    width, height = 1920, 1080
    video = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not video.isOpened():
        raise DeviceCheckError(
            f"取图：采集卡打不开（capture_device = {index}），检查采集卡有没有插好、序号对不对"
        )
    video.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    video.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    ok, image = video.read()
    if not ok or image is None:
        video.release()
        raise DeviceCheckError(
            f"取图：采集卡打开了但读不到画面（capture_device = {index}），检查终端有没有摄像头权限"
        )
    actual_height, actual_width = image.shape[:2]
    if (actual_width, actual_height) != (width, height):
        logging.warning(
            f"取图：采集卡的画面是 {actual_width}×{actual_height}，不是 {width}×{height}，"
            f"可能 capture_device = {index} 指到了别的摄像头"
        )
    return CaptureCard(video)
