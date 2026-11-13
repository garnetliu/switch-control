"""等画面：截图和按键都用传进来的 switch。"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from libs import ImageChecker, Switch
from libs.switch import Frame


def capture(sw: Switch, what: str) -> ImageChecker:
    """截一张当前画面，记在内存里（sw.frames），不写文件。what 是这张图在看什么。

    出错时入口用 save_frames 把这一局记下的图都写进日志目录；
    没出错就在新的一局开始时用 sw.frames.clear() 丢掉。
    """
    data = sw.pixel_peek()
    sw.frames.append(Frame(time.time(), sw.step, what, data))
    return ImageChecker(data)


def save_frames(sw: Switch) -> list[Path]:
    """把内存里这一局的截图按顺序写进 failed_dir/这一次的时间/，返回写下的文件。

    文件名是「序号-时分秒-步骤-在看什么」。
    """
    directory = sw.config.failed_dir / time.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, frame in enumerate(sw.frames):
        stamp = time.strftime("%H%M%S", time.localtime(frame.time))
        what = frame.what.replace("/", "_")
        path = directory / f"{index:04d}-{stamp}-{frame.step}-{what}.jpg"
        path.write_bytes(frame.data)
        paths.append(path)
    logging.warning(f"这一局的 {len(paths)} 张截图存在 {directory}")
    return paths


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
    while True:
        image = capture(sw, what)
        if condition(image):
            return image
        if time.monotonic() >= deadline:
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
    超过 timeout 秒还没满足，抛 TimeoutError。
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
    超过 timeout 秒还没满足，抛 TimeoutError。
    """
    timeout = sw.config.timeout if timeout is None else timeout
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        image = capture(sw, what)
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        if attempt:
            logging.debug(f"没有反应，再做一次（在等{what}）")
        action()
        attempt += 1
        poll_deadline = time.monotonic() + interval
        while True:
            image = capture(sw, what)
            if condition(image):
                return image
            if time.monotonic() >= poll_deadline:
                break
            time.sleep(sw.config.interval)
