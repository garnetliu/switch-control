"""看画面：截图、出错时存图、等到画面出现、一直按到画面出现。"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from control_switch.session import Frame, Session
from control_switch.vision import ImageChecker


def capture(sw: Session, what: str) -> ImageChecker:
    """截一张当前画面，记在内存里（sw.frames），不写文件。what 是这张图在看什么。

    出错时入口用 save_frames 把这一局记下的图都写进日志目录；
    没出错就在新的一局开始时用 sw.frames.clear() 丢掉。
    """
    data = sw.pixel_peek()
    image = ImageChecker(data)
    sw.frames.append(Frame(time.time(), sw.step, what, data, image.rects))
    return image


def save_frames(sw: Session) -> list[Path]:
    """把内存里这一局的截图按顺序写进 failed_dir/这一次的时间/，返回写下的文件。

    文件名是「序号-时分秒-步骤-在看什么」。这张图上检查过的区域用红框画出来；
    没检查过区域的 JPEG 字节原样写，采集卡的帧到这里才编码。
    """
    directory = sw.config.failed_dir / time.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, frame in enumerate(sw.frames):
        stamp = time.strftime("%H%M%S", time.localtime(frame.time))
        what = frame.what.replace("/", "_")
        path = directory / f"{index:04d}-{stamp}-{frame.step}-{what}.jpg"
        if isinstance(frame.data, bytes) and not frame.rects:
            path.write_bytes(frame.data)
        elif not cv2.imwrite(str(path), _draw_rects(frame)):
            raise OSError(f"无法写入图片：{path}")
        paths.append(path)
    logging.warning(f"这一局的 {len(paths)} 张截图存在 {directory}")
    return paths


def _draw_rects(frame: Frame) -> np.ndarray:
    """把截图上检查过的区域用红框画出来，返回画好的图。"""
    if isinstance(frame.data, bytes):
        decoded = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("截图解码失败")
        image = np.asarray(decoded)
    else:
        image = np.array(frame.data)
    height, width = image.shape[:2]
    for (left, top), (right, bottom) in frame.rects:
        cv2.rectangle(
            image,
            (round(left * width), round(top * height)),
            (round(right * width), round(bottom * height)),
            (0, 0, 255),
            2,
        )
    return image


def wait_until(
        sw: Session,
        condition: Callable[[ImageChecker], bool],
        what: str,
        interval: float = 0.0,
        timeout: float=60.0,
) -> ImageChecker:
    """一直截图，直到 condition(截图) 为真，返回那张截图。

    timeout: 最多等几秒，超时抛 TimeoutError。
    what: 在等什么，写进超时的报错里。
    interval: 两次截图之间等几秒。
    """
    deadline = time.monotonic() + timeout
    while True:
        image = capture(sw, what)
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(interval)


def press_until(
        sw: Session,
        action: Callable[[], None],
        condition: Callable[[ImageChecker], bool],
        what: str,
        interval: float = 0.3,
        timeout: float = 60.0,
) -> ImageChecker:
    """一直做 action（按键、推摇杆），直到 condition(截图) 为真，返回那张截图。

    先做一次再看画面；做完之后 interval 秒里一直看画面，满足就返回，没满足就再做一次。
    timeout: 最多等几秒，超时抛 TimeoutError。
    what: 在等什么，写进超时的报错里。
    interval: 做完一次之后，最多看几秒画面再做下一次。
    """
    deadline = time.monotonic() + timeout
    while True:
        action()
        image = capture(sw, what)
        if condition(image):
            logging.debug(what)
            return image
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        retry_at = time.monotonic() + interval
        while time.monotonic() < retry_at:
            image = capture(sw, what)
            if condition(image):
                logging.debug(what)
                return image
