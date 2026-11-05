"""等画面：不盲等固定的秒数，而是不停截图，直到画面满足要求。

- wait_for：等画面满足一个条件，条件是一个接收截图、返回是否满足的函数。
- wait_until：不看画面，等一个条件满足，比如前台软件的 Title ID。

超时都会抛 TimeoutError，不会退回固定等待：画面一直不对说明流程已经错位，
继续按键只会在错误的画面上乱按。
"""

import time
from collections.abc import Callable

from config.paths import LOG_DIR
from config.timing import POLL_INTERVAL
from lib import switch
from lib.log import log
from tool.check_image import ImageChecker
from tool.image import save


def wait_for(
    condition: Callable[[ImageChecker], bool],
    timeout: float,
    what: str,
    interval: float = POLL_INTERVAL,
) -> ImageChecker:
    """不停截图，直到 condition 对截图返回 True，返回那张截图。

    timeout: 最多等几秒，超时抛 TimeoutError。
    what: 在等什么，写进超时的报错里。
    超时时把开始等时和最后一帧的截图存进 LOG_DIR，用来事后看画面停在哪里。
    """
    deadline = time.monotonic() + timeout
    first = None
    while True:
        image = capture()
        first = first or image
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            for name, frame in (("first", first), ("last", image)):
                path = LOG_DIR / f"timeout-{stamp}-{name}.jpg"
                save(frame, str(path))
                log(f"超时的截图: {path}", "WARNING")
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(interval)


def wait_until(check: Callable[[], bool], timeout: float, what: str) -> None:
    """不截图，反复调用 check，直到它返回 True。用于不看画面的条件，比如前台软件的 Title ID。

    timeout: 最多等几秒，超时抛 TimeoutError。what: 在等什么，写进超时的报错里。
    """
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，一直没有等到：{what}")
        time.sleep(POLL_INTERVAL)


def capture() -> ImageChecker:
    """截一张当前画面。使用全局连接，需要先调用 switch.connect。"""
    return ImageChecker(switch.get().pixel_peek())
