"""control_switch.flow.wait：截图、等画面、一直按键、存图。"""

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from control_switch.device.botbase import Switch
from control_switch.flow.wait import act_until, capture, press_until, save_frames, wait_for
from control_switch.vision import ImageChecker

IMAGES = Path(__file__).resolve().parents[1] / "images"
ROUTE = (IMAGES / "路线上的界面-要走哪条路.jpg").read_bytes()
RESEARCHER = (IMAGES / "研究员问换不换.jpg").read_bytes()

SwitchFactory = Callable[..., Any]


def is_researcher(image: ImageChecker) -> bool:
    """这张截图就是 RESEARCHER 那张图。"""
    return bool(np.array_equal(image.bgr, ImageChecker(RESEARCHER).bgr))


def never(image: ImageChecker) -> bool:
    return False


def always(image: ImageChecker) -> bool:
    return True


def test_capture_returns_usable_checker_for_the_peeked_image(make_switch: SwitchFactory) -> None:
    """capture 返回的 ImageChecker 里就是 pixel_peek 给的那张图。"""
    fake = make_switch([RESEARCHER])
    image = capture(cast(Switch, fake), "看研究员")
    assert is_researcher(image)


def test_capture_appends_frame_with_step_and_description(make_switch: SwitchFactory) -> None:
    """capture 往 frames 里加一条，带着当时的 step、传进去的说明和图片字节。"""
    fake = make_switch([ROUTE])
    fake.step = "走路"
    before = time.time()
    capture(cast(Switch, fake), "看路线")
    assert len(fake.frames) == 1
    frame = fake.frames[0]
    assert frame.step == "走路"
    assert frame.what == "看路线"
    assert frame.data == ROUTE
    assert before <= frame.time <= time.time()


def test_wait_for_returns_immediately_when_first_image_matches(make_switch: SwitchFactory) -> None:
    """条件第一次就满足时立刻返回，只截了一张图。"""
    fake = make_switch([RESEARCHER])
    image = wait_for(cast(Switch, fake), always, 1.0, "马上就有")
    assert is_researcher(image)
    assert len(fake.frames) == 1


def test_wait_for_returns_the_third_image_when_only_third_matches(
    make_switch: SwitchFactory,
) -> None:
    """第 3 张图才满足时，返回的是第 3 张，一共截了 3 张。"""
    fake = make_switch([ROUTE, ROUTE, RESEARCHER])
    image = wait_for(cast(Switch, fake), is_researcher, 1.0, "第三张")
    assert is_researcher(image)
    assert len(fake.frames) == 3
    assert fake.frames[-1].data == RESEARCHER


def test_wait_for_raises_timeout_error_with_description(make_switch: SwitchFactory) -> None:
    """条件一直不满足时抛 TimeoutError，报错里有传进去的说明。"""
    fake = make_switch([ROUTE])
    with pytest.raises(TimeoutError, match="永远等不到的画面"):
        wait_for(cast(Switch, fake), never, 0.2, "永远等不到的画面")


def test_press_until_does_not_press_when_already_satisfied(make_switch: SwitchFactory) -> None:
    """条件一开始就满足时，一次键都不按。"""
    fake = make_switch([RESEARCHER])
    image = press_until(cast(Switch, fake), always, "已经满足")
    assert is_researcher(image)
    assert fake.pressed == []


def test_press_until_presses_the_given_button(make_switch: SwitchFactory) -> None:
    """条件不满足时按的是 button 指定的键，满足后返回那张图。"""
    fake = make_switch([ROUTE, ROUTE, RESEARCHER])
    image = press_until(cast(Switch, fake), is_researcher, "按 X", button="X")
    assert is_researcher(image)
    assert fake.pressed
    assert set(fake.pressed) == {"X"}


def test_press_until_presses_a_by_default(make_switch: SwitchFactory) -> None:
    """不传 button 时按的是 A。"""
    fake = make_switch([ROUTE, ROUTE, RESEARCHER])
    press_until(cast(Switch, fake), is_researcher, "默认按 A")
    assert fake.pressed
    assert set(fake.pressed) == {"A"}


def test_press_until_waits_press_interval_not_interval_between_presses(
    make_switch: SwitchFactory,
) -> None:
    """按一次之后等画面的时间是 press_interval：它比 timeout 大，超时前只按了一次。

    如果错用 interval（这里是 0），按一次就会马上再按，按键次数会大于 1。
    """
    fake = make_switch([ROUTE])
    fake.config.press_interval = 0.6
    with pytest.raises(TimeoutError):
        press_until(cast(Switch, fake), never, "一直不满足", timeout=0.2)
    assert fake.pressed == ["A"]


def test_press_until_raises_timeout_error_with_description(make_switch: SwitchFactory) -> None:
    """一直不满足时抛 TimeoutError，报错里有传进去的说明。"""
    fake = make_switch([ROUTE])
    with pytest.raises(TimeoutError, match="按不出来的画面"):
        press_until(cast(Switch, fake), never, "按不出来的画面", timeout=0.2)


def test_act_until_returns_after_action_done_at_least_once(make_switch: SwitchFactory) -> None:
    """动作做了一次之后条件满足，返回那张图；条件在动作之前不满足。"""
    fake = make_switch([ROUTE])
    calls: list[int] = []

    def action() -> None:
        calls.append(1)

    image = act_until(
        cast(Switch, fake), action, lambda _: len(calls) >= 1, "做一次就行", interval=0.0
    )
    assert calls == [1]
    assert not is_researcher(image)


def test_act_until_does_not_act_when_already_satisfied(make_switch: SwitchFactory) -> None:
    """条件一开始就满足时，动作一次都不做。"""
    fake = make_switch([ROUTE])
    calls: list[int] = []
    act_until(cast(Switch, fake), lambda: calls.append(1), always, "已经满足", interval=0.0)
    assert calls == []


def test_act_until_raises_timeout_error_when_never_satisfied(make_switch: SwitchFactory) -> None:
    """条件一直不满足时，动作做了不止一次，最后抛 TimeoutError，报错里有说明。"""
    fake = make_switch([ROUTE])
    calls: list[int] = []
    with pytest.raises(TimeoutError, match="一直没反应"):
        act_until(
            cast(Switch, fake),
            lambda: calls.append(1),
            never,
            "一直没反应",
            interval=0.05,
            timeout=0.3,
        )
    assert len(calls) > 1


def test_save_frames_writes_one_file_per_frame(make_switch: SwitchFactory) -> None:
    """写出的文件数和 frames 一样，内容和每一帧的图片字节一致，返回的路径就是这些文件。"""
    fake = make_switch([ROUTE, RESEARCHER])
    sw = cast(Switch, fake)
    capture(sw, "第一张")
    capture(sw, "第二张")
    paths = save_frames(sw)
    assert len(paths) == len(fake.frames) == 2
    assert [path.read_bytes() for path in paths] == [frame.data for frame in fake.frames]
    assert all(path.parent.parent == fake.config.failed_dir for path in paths)
    assert len(list(fake.config.failed_dir.rglob("*.jpg"))) == 2


def test_save_frames_names_files_by_index_time_step_and_what(make_switch: SwitchFactory) -> None:
    """文件名是「序号-时分秒-步骤-说明.jpg」，说明里的 / 换成了 _。"""
    fake = make_switch([ROUTE])
    sw = cast(Switch, fake)
    fake.step = "找路"
    capture(sw, "左/右")
    fake.step = "走路"
    capture(sw, "没有斜杠")
    paths = save_frames(sw)
    stamps = [time.strftime("%H%M%S", time.localtime(frame.time)) for frame in fake.frames]
    assert [path.name for path in paths] == [
        f"0000-{stamps[0]}-找路-左_右.jpg",
        f"0001-{stamps[1]}-走路-没有斜杠.jpg",
    ]
    assert re.fullmatch(r"\d{8}-\d{6}", paths[0].parent.name)


def test_save_frames_with_no_frames_writes_nothing(make_switch: SwitchFactory) -> None:
    """frames 是空的时返回空列表，不写文件。"""
    fake = make_switch([ROUTE])
    assert save_frames(cast(Switch, fake)) == []
    assert list(fake.config.failed_dir.rglob("*.jpg")) == []


def test_act_until_raises_timeout_error_at_timeout_even_when_interval_is_longer(
    make_switch: SwitchFactory,
) -> None:
    """防的是：做完一次动作后的 interval 秒里不检查总超时，比 timeout 多等了一整个 interval。

    文档写的是「超过 timeout 秒还没满足，抛 TimeoutError」，报错里也写「等了 timeout 秒」。
    这里 timeout 是 0.2 秒、interval 是 3 秒：应该在 timeout 附近抛错，而不是等满 3 秒。
    """
    fake = make_switch([ROUTE])
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="等了 0.2 秒"):
        act_until(cast(Switch, fake), lambda: None, never, "等不到", interval=3.0, timeout=0.2)
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, f"timeout 是 0.2 秒，实际等了 {elapsed:.2f} 秒"
