"""等画面：不盲等固定的秒数，而是不停截图，直到画面满足要求。

- wait_for：等画面满足一个条件，条件是一个接收截图、返回是否满足的函数。
- wait_until：不看画面，等一个条件满足，比如前台软件的 Title ID。
- act_until：一直做一个操作，直到画面满足条件（游戏加载时会锁按键，锁多久不确定）。

超时都会抛 TimeoutError，不会退回固定等待：画面一直不对说明流程已经错位，
继续按键只会在错误的画面上乱按。
"""

import os
import time
from collections.abc import Callable

from config.paths import LOG_DIR
from config.timing import ACT_TIMEOUT, POLL_INTERVAL
from lib import switch
from lib.debug_checker import SavingImageChecker, current_step, should_save
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
            save_timeout_frames(first, image)
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(interval)


def act_until(
    action: Callable[[], None],
    condition: Callable[[ImageChecker], bool],
    what: str,
    interval: float = 1.0,
    timeout: float = ACT_TIMEOUT,
) -> ImageChecker:
    """一直做 action（按键、推摇杆），直到 condition(截图) 为真，返回那张截图。

    每做一次之后 interval 秒里一直看画面，满足就返回；没满足就再做一次：
    游戏加载、运行时锁按键的时间不确定，按一次之后画面没反应不代表这次操作失败。
    一直做到 timeout 秒还没满足，把开始等时和最后一帧的截图存进 LOG_DIR，抛 TimeoutError。
    what: 在等什么，写进日志和报错里。
    只用在多按一次也不会出错的地方：condition 满足前，再做一次 action 的效果和之前一样
    （比如光标还没动，再推一次）。
    """
    deadline = time.monotonic() + timeout
    first = None
    attempt = 0
    while True:
        image = capture()
        first = first or image
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            save_timeout_frames(first, image)
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        if attempt:
            log(f"没有反应，再做一次（在等{what}）", "DEBUG")
        action()
        attempt += 1
        poll_deadline = time.monotonic() + interval
        while True:
            image = capture()
            if condition(image):
                return image
            if time.monotonic() >= poll_deadline:
                break
            time.sleep(POLL_INTERVAL)


def save_timeout_frames(first: ImageChecker, last: ImageChecker) -> None:
    """等画面超时时，把开始等时和最后一帧的截图存进 LOG_DIR，用来事后看画面停在哪里。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for name, frame in (("first", first), ("last", last)):
        path = LOG_DIR / f"timeout-{stamp}-{name}.jpg"
        save(frame, str(path))
        log(f"超时的截图: {path}", "WARNING")


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
    """截一张当前画面。使用全局连接，需要先调用 switch.connect。

    要存检查区域时（见 lib/debug_checker.py 的 should_save）返回 SavingImageChecker：
    之后每检查一个区域都会框出来存一张图。
    SAVE_CAPTURE_STEPS 可用逗号分隔步骤名；命中当前步骤时，原图存入 logs/<步骤名>/。
    """
    checker = SavingImageChecker if should_save() else ImageChecker
    image = checker(switch.get().pixel_peek())
    step = current_step()
    save_steps = {name.strip() for name in os.environ.get("SAVE_CAPTURE_STEPS", "").split(",")}
    if step and step in save_steps:
        directory = LOG_DIR / step
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = directory / f"{stamp}-{time.time_ns() % 1_000_000_000:09d}.jpg"
        save(image, str(path))
    return image
