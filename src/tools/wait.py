"""等画面：截图和按键都用传进来的 switch。"""

import logging
import time
from collections.abc import Callable

from libs import ImageChecker, Switch
from tools.save_image import save_check


def capture(sw: Switch) -> ImageChecker:
    """截一张当前画面。"""
    return ImageChecker(sw.pixel_peek())


def wait_for(
    sw: Switch,
    condition: Callable[[ImageChecker], bool],
    timeout: float,
    what: str,
    interval: float | None = None,
) -> ImageChecker:
    """不停截图，直到 condition 对截图返回 True，返回那张截图。

    timeout: 最多等几秒，超时抛 TimeoutError。
    what: 在等什么，写进超时的报错里。
    """
    interval = sw.config.interval if interval is None else interval
    deadline = time.monotonic() + timeout
    first = None
    while True:
        image = capture(sw)
        first = first or image
        if condition(image):
            save_check(sw, image, what, *image.checked)
            return image
        if time.monotonic() >= deadline:
            save_timeout_frames(sw, first, image, f"等了 {timeout} 秒，画面一直没有出现：{what}")
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(interval)


def press_until(
    sw: Switch,
    done: Callable[[ImageChecker], bool],
    what: str,
    button: str = "A",
    timeout: float | None = None,
) -> ImageChecker:
    """一直按 button，直到 done(截图) 为真，返回那张截图。

    每次按之前都先判定，已经满足就不再按，不会按在要等的菜单上。
    超过 timeout 秒还没满足，存下截图并抛 TimeoutError。
    what: 在等什么，写进日志和报错里。
    """
    return act_until(
        sw,
        lambda: sw.click(button, 0),
        done,
        what,
        interval=sw.config.interval,
        timeout=sw.config.timeout if timeout is None else timeout,
    )


def act_until(
    sw: Switch,
    action: Callable[[], None],
    condition: Callable[[ImageChecker], bool],
    what: str,
    interval: float = 1.0,
    timeout: float | None = None,
) -> ImageChecker:
    """一直做 action，直到 condition(截图) 为真，返回那张截图。

    每做一次之后 interval 秒里一直看画面，满足就返回；没满足就再做一次。
    超过 timeout 秒还没满足，存下截图并抛 TimeoutError。
    """
    timeout = sw.config.timeout if timeout is None else timeout
    deadline = time.monotonic() + timeout
    first = None
    attempt = 0
    while True:
        image = capture(sw)
        first = first or image
        if condition(image):
            save_check(sw, image, what, *image.checked)
            return image
        if time.monotonic() >= deadline:
            save_timeout_frames(sw, first, image, f"等了 {timeout} 秒，画面一直没有出现：{what}")
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        if attempt:
            logging.debug(f"没有反应，再做一次（在等{what}）")
        action()
        attempt += 1
        poll_deadline = time.monotonic() + interval
        while True:
            image = capture(sw)
            if condition(image):
                save_check(sw, image, what, *image.checked)
                return image
            if time.monotonic() >= poll_deadline:
                break
            time.sleep(sw.config.interval)


def save_timeout_frames(sw: Switch, first: ImageChecker, last: ImageChecker, reason: str) -> None:
    """等画面超时时，把开始等时和最后一帧的截图存进日志目录，连同超时原因一起推送。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    paths = []
    for name, frame in (("first", first), ("last", last)):
        path = sw.config.log_dir / f"timeout-{stamp}-{name}.jpg"
        frame.save(str(path))
        logging.warning(f"超时的截图: {path}")
        paths.append(path)
    sw.notifier.send(f"超时：{reason}", files=paths)
