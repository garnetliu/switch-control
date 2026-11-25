"""steps.fetch 里查篮子的部分：collect_eggs_after_sandwich、check_basket_to_collect_eggs、
clear_mons_in_front（照上游 PokemonSV_EggRoutines.cpp）。

每次看画面的函数 _look_at_basket 换成按脚本返回的假函数（"none" 没有对话框、"dialog" 普通对话、
"prompt" 选择框、"unknown" 5 秒都没识别到），每看一次假时钟走几秒，测查篮子的每个分支。
_look_at_basket 自己用换掉识别函数的方式另外测。
"""

import importlib
import itertools
import math
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

fetch_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.steps.fetch")


def scripted(
    stage: Any, states: list[str], seconds: float = 1.0, repeat_last: bool = False
) -> Callable[..., str]:
    """按顺序返回 states 里的状态，每次让假时钟走 seconds 秒；用完了：repeat_last 为真就一直返回最后一个，否则报错。"""
    queue = list(states)

    def look(*args: Any, **kwargs: Any) -> str:
        stage.advance(seconds)
        if len(queue) > 1 or (queue and not repeat_last):
            return queue.pop(0)
        assert queue and repeat_last, "看篮子看得太多次，脚本用完了"
        return queue[0]

    return look


def check(stage: Any, states: list[str], collected: int = 0, **kwargs: Any) -> int:
    """用假的 _look_at_basket 查一次篮子（最多 30 个蛋），返回收完之后的蛋数。"""
    stage.replace(fetch_module, "_look_at_basket", scripted(stage, states, **kwargs))
    return fetch_module._check_basket(stage.sw, 30, collected)


def test_check_basket_presses_a_when_no_dialog_then_leaves_after_talking(stage: Any) -> None:
    """没有对话框、还没和篮子说过话：按 A 去说话；说完（普通对话按 B 关掉）再没有对话框，就结束。蛋数不变。"""
    assert check(stage, ["none", "dialog", "none"]) == 0
    assert stage.clicks() == ["A", "B"]


def test_check_basket_presses_b_on_ordinary_dialog(stage: Any) -> None:
    """普通对话（不是选择框）：按 B 关掉，之后没有对话框就结束。"""
    assert check(stage, ["dialog", "none"]) == 0
    assert stage.clicks() == ["B"]


def test_check_basket_takes_egg_with_a_when_choice_box_and_not_full(stage: Any) -> None:
    """选择框、蛋还没收满：按 A 收下，蛋数加 1（3 变 4），之后的对话按 B 关掉，没有对话框就结束。"""
    assert check(stage, ["prompt", "dialog", "none"], collected=3) == 4
    assert stage.clicks() == ["A", "B"]


def test_check_basket_refuses_with_b_then_confirms_with_a_when_full(stage: Any) -> None:
    """选择框、蛋已经收满 30 个：按 B 不收，对话之后再出现的确认选择框按 A 确认（上游：Confirming refused egg），
    蛋数不变（30）。按键顺序 B、B（关对话）、A、B（关对话）。
    """
    states = ["prompt", "dialog", "prompt", "dialog", "none"]
    assert check(stage, states, collected=30) == 30
    assert stage.clicks() == ["B", "B", "A", "B"]


def test_check_basket_repeats_last_button_on_second_consecutive_choice_box(stage: Any) -> None:
    """连续两次选择框（中间没有别的状态）：第二次重复上一次按的键（A），不再收一个蛋：蛋数只加 1。"""
    assert check(stage, ["prompt", "prompt", "dialog", "none"], collected=3) == 4
    assert stage.clicks() == ["A", "A", "B"]


def test_check_basket_rotates_camera_when_nothing_recognized(stage: Any) -> None:
    """5 秒没识别出画面：右摇杆往左推 0.24 秒转视角，再接着看；之后按正常流程走完。"""
    assert check(stage, ["unknown", "dialog", "none"]) == 0
    assert stage.log[0] == ("stick", "RIGHT", -1.0, 0.0, 0.24)
    assert stage.clicks() == ["B"]


def test_check_basket_raises_runtime_error_after_ten_consecutive_no_dialog(stage: Any) -> None:
    """连续 10 次没有对话框（一直找不到篮子）：抛 RuntimeError，报错里有「篮子」，一共按了 9 次 A（第 10 次直接报错）。"""
    with pytest.raises(RuntimeError, match="篮子"):
        check(stage, ["none"], repeat_last=True)
    assert stage.clicks() == ["A"] * 9


def test_check_basket_resets_no_dialog_count_when_something_else_is_seen(stage: Any) -> None:
    """没有对话框的次数是连续的：9 次没有对话框、1 次没识别、又 9 次没有对话框，不报错，说完话就结束。"""
    states = ["none"] * 9 + ["unknown"] + ["none"] * 9 + ["dialog", "none"]
    assert check(stage, states) == 0


def test_check_basket_raises_timeout_error_after_five_minutes(stage: Any) -> None:
    """一直收不完（每看一次过 100 秒、一直是普通对话）：超过 5 分钟抛 TimeoutError，报错里有「篮子」。"""
    with pytest.raises(TimeoutError, match="篮子"):
        check(stage, ["dialog"], seconds=100.0, repeat_last=True)


@pytest.mark.parametrize(
    ("remaining", "average", "expected"),
    [
        (30, 5.0, 180),
        (20, 10.0, 180),
        (10, 10.0, 180),
        (10, 20.0, 90),
        (2, 7.0, 51),
        (2, 14.0, 30),
        (1, 10.0, 30),
        (30, 0.0, 180),
    ],
)
def test_basket_wait_seconds(remaining: int, average: float, expected: int) -> None:
    """查篮子的间隔（默认 180 秒）：剩下的蛋数不到平均每次收到的数量时，按比例缩短，取整数；最少 30 秒；
    剩下的不比平均少（包括平均是 0）就还是 180 秒。
    """
    assert fetch_module._basket_wait_seconds(180, remaining, average) == expected


def test_basket_wait_seconds_scales_with_given_default() -> None:
    """间隔按传进来的默认值算：默认 120 秒、剩 5 个、平均 10 个：60 秒。"""
    assert fetch_module._basket_wait_seconds(120, 5, 10.0) == 60


@pytest.fixture
def collect(stage: Any) -> Callable[[list[int]], tuple[int, list[int], list[tuple[Any, ...]]]]:
    """返回一个函数：传入每次查篮子新收到的蛋数，用假的查篮子跑一遍 _collect_eggs_after_sandwich。

    返回 (收到的蛋数, 每次等了几秒, 查篮子的调用)。走路、等宝可梦让开都换成什么都不做的假函数，
    等的时候让假时钟走那么多秒；查篮子不花时间；最后一项以后每次都收到 0 个。
    """

    def run(new_eggs: list[int]) -> tuple[int, list[int], list[tuple[Any, ...]]]:
        waits: list[int] = []
        calls: list[tuple[Any, ...]] = []
        queue = list(new_eggs)
        stage.stub(fetch_module, "_walk_to_basket")
        stage.stub(fetch_module, "_clear_mons_in_front")

        def check_basket(sw: Any, max_eggs: int, collected: int) -> int:
            calls.append((max_eggs, collected))
            return min(max_eggs, collected + (queue.pop(0) if queue else 0))

        def wait(sw: Any, seconds: int) -> None:
            waits.append(seconds)
            stage.advance(seconds)

        stage.replace(fetch_module, "_check_basket", check_basket)
        stage.replace(fetch_module, "_wait_for_basket", wait)
        return fetch_module._collect_eggs_after_sandwich(stage.sw), waits, calls

    return run


def test_collect_stops_when_thirty_eggs_collected(collect: Any) -> None:
    """每次收 10 个：查 3 次就收满 30 个停下，中间等了两次，每次 180 秒；每次都按最多 30 个、已收的数量去查。"""
    total, waits, calls = collect([10, 10, 10])
    assert total == 30
    assert waits == [180, 180]
    assert calls == [(30, 0), (30, 10), (30, 20)]


def test_collect_shortens_wait_when_few_eggs_remain(collect: Any) -> None:
    """快收满时缩短间隔：收到 20、8、2 个：第一次查完剩 10 个、平均 20，等 90 秒；
    第二次查完剩 2 个、平均 14，算出来 25 秒，不到 30 就按 30 秒；第三次收满。
    """
    total, waits, _ = collect([20, 8, 2])
    assert total == 30
    assert waits == [90, 30]


def test_collect_gives_up_after_thirty_minutes(collect: Any) -> None:
    """一直收不到蛋：每次等 180 秒，最多等 30 分钟：查第 12 次（过了 1980 秒，超过 1800 秒）时停下，
    只等了 11 次，返回已收到的 0 个，不报错。
    """
    total, waits, calls = collect([])
    assert total == 0
    assert waits == [180] * 11
    assert len(calls) == 12


def test_collect_clears_mons_before_every_check_and_walks_to_basket_first(
    stage: Any, collect: Any
) -> None:
    """走到篮子前先走路，之后每次查篮子之前都先等篮子前的宝可梦让开。"""
    collect([15, 15])
    names = [entry[0] for entry in stage.log]
    assert names[0] == "_walk_to_basket"
    assert names.count("_clear_mons_in_front") == 2


def test_wait_for_basket_presses_keepalive_button_so_switch_does_not_sleep(stage: Any) -> None:
    """等篮子的时候防 Switch 休眠：等 100 秒，期间一直每隔不超过 keepalive_gap 秒按一下 keepalive_button，
    总共等满 100 秒。
    """
    config = stage.sw.config
    start = stage.clock.now
    fetch_module._wait_for_basket(stage.sw, 100)
    elapsed = stage.clock.now - start
    assert 100 <= elapsed < 102
    assert set(stage.clicks()) == {config.keepalive_button}
    times = [start, *stage.click_times, start + elapsed]
    gaps = [later - earlier for earlier, later in itertools.pairwise(times)]
    assert max(gaps) <= config.keepalive_gap + 1
    assert len(stage.clicks()) >= math.floor(100 / config.keepalive_gap) - 1


def test_look_at_basket_reports_choice_box(stage: Any) -> None:
    """画面上是选择框：返回 "prompt"。"""
    stage.set_screens(is_prompt=lambda: True, is_dialog=lambda: False, has_dialog_box=lambda: True)
    assert fetch_module._look_at_basket(stage.sw) == "prompt"


def test_look_at_basket_reports_ordinary_dialog(stage: Any) -> None:
    """画面上是普通对话（要按键往下翻）：返回 "dialog"。"""
    stage.set_screens(is_prompt=lambda: False, is_dialog=lambda: True, has_dialog_box=lambda: True)
    assert fetch_module._look_at_basket(stage.sw) == "dialog"


def test_look_at_basket_reports_none_when_no_dialog_box(stage: Any) -> None:
    """画面上没有对话框：返回 "none"。"""
    stage.set_screens(
        is_prompt=lambda: False, is_dialog=lambda: False, has_dialog_box=lambda: False
    )
    assert fetch_module._look_at_basket(stage.sw) == "none"


def test_look_at_basket_reports_unknown_after_five_seconds_of_nothing_recognized(
    stage: Any,
) -> None:
    """有对话框但既不是普通对话也不是选择框，一直这样：看了 5 秒之后返回 "unknown"，不抛错。"""
    start = stage.clock.now
    stage.set_screens(is_prompt=lambda: False, is_dialog=lambda: False, has_dialog_box=lambda: True)
    assert fetch_module._look_at_basket(stage.sw) == "unknown"
    assert 5 <= stage.clock.now - start < 7


def test_clear_mons_does_nothing_when_nothing_in_front(stage: Any) -> None:
    """前面没有宝可梦挡着（A 按钮提示不在）：不按任何键。"""
    stage.set_screens(has_a_hint=lambda: False)
    fetch_module._clear_mons_in_front(stage.sw)
    assert stage.log == []


def test_clear_mons_whistles_with_r_and_waits_until_mon_leaves(stage: Any) -> None:
    """有宝可梦挡着（A 按钮提示在）：按 R 吹口哨、等，直到它让开（100 秒后）就停，按的都是 R。"""
    start = stage.clock.now
    stage.set_screens(has_a_hint=lambda: stage.clock.now < start + 100)
    fetch_module._clear_mons_in_front(stage.sw)
    assert set(stage.clicks()) == {"R"}
    assert 2 <= len(stage.clicks()) <= 5


def test_clear_mons_raises_timeout_error_after_twenty_minutes(stage: Any) -> None:
    """宝可梦一直不让开：每 30 秒吹一次口哨，20 分钟后抛 TimeoutError，吹了约 40 次。"""
    start = stage.clock.now
    stage.set_screens(has_a_hint=lambda: True)
    with pytest.raises(TimeoutError):
        fetch_module._clear_mons_in_front(stage.sw)
    assert stage.clock.now - start >= 1200
    assert set(stage.clicks()) == {"R"}
    assert 38 <= len(stage.clicks()) <= 41
