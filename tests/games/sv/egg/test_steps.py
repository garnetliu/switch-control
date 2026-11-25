"""control_switch.games.sv.egg.steps：每一步的正常情况和出错情况。

不连设备：图片来自 tests/images/sv/egg/ 的真机截图，或者 conftest 的 World（按键让画面跟着变）
合成的盒子画面；按键记在假 Controller 里；time.sleep、time.monotonic 是假的，不真的等待。
推送换成记录函数，闪光截图存到临时目录。
"""

import importlib
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import cv2
import numpy as np
import pytest

from control_switch.games.sv.egg import STEPS
from control_switch.games.sv.egg.session import EggSession
from control_switch.games.sv.egg.steps import (
    check,
    collect,
    hatch_load,
    hatch_walk,
    initialize,
    picnic,
    sandwich,
    to_basket,
)
from control_switch.session import Frame

check_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.steps.check")
WorldFactory = Callable[..., Any]
EggFactory = Callable[[Callable[[], bytes]], EggSession]
ImageLoader = Callable[[str], bytes]

# 两种队伍。「other」（啪嘧海胆）在孵蛋的队伍里当火焰之躯，孵出来的宝可梦也用它。
# 野餐：第 1 格百变怪，第 2 格亲代（3 项最棒），其余空着；火焰之躯在 flame_box（测试里是盒子 23）第 1 行第 1 列。
# 孵蛋：第 1 格火焰之躯，第 2–6 格放蛋；百变怪在 flame_box 第 1 行第 1 列、亲代在第 2 列。
PICNIC_PARTY: list[str | None] = ["ditto", "parent3", None, None, None, None]
HATCH_PARTY: list[str | None] = ["other", None, None, None, None, None]
FLAME_BOX = 23


def picnic_store() -> dict[tuple[int, int], str]:
    """野餐的队伍时 flame_box 第 1 行的内容。"""
    return {(0, 0): "other"}


def hatch_store(parent: str = "parent3") -> dict[tuple[int, int], str]:
    """孵蛋的队伍时 flame_box 第 1 行的内容。"""
    return {(0, 0): "ditto", (0, 1): parent}


RELEASE_KEYS = ["A", "DDOWN", "DDOWN", "DDOWN", "DDOWN", "A", "DUP", "A", "A"]


def party_with(**slots: str | None) -> list[str | None]:
    """孵蛋的队伍，再把指定下标的格子换掉：s3="egg" 是下标 3（第 4 格）。"""
    party = list(HATCH_PARTY)
    for key, value in slots.items():
        party[int(key[1:])] = value
    return party


@pytest.fixture
def hatch_world(make_world: Callable[..., Any]) -> Callable[..., Any]:
    """返回一个函数：建孵蛋队伍的画面模型（flame_box 第 1 行放着百变怪和亲代），参数同 make_world，
    party 不给就是 HATCH_PARTY；boxes 里给的盒子会盖住默认的。
    """

    def factory(party: Sequence[str | None] = HATCH_PARTY, **kwargs: Any) -> Any:
        boxes = {FLAME_BOX: hatch_store(), **kwargs.pop("boxes", {})}
        return make_world(party=party, boxes=boxes, **kwargs)

    return factory


def contains_run(sequence: Sequence[str], run: Sequence[str]) -> bool:
    """sequence 里有没有连续的一段等于 run。"""
    n = len(run)
    return any(list(sequence[i : i + n]) == list(run) for i in range(len(sequence) - n + 1))


def record_pushes(sw: EggSession, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Path]]]:
    """sw.notifier.send_everyone 换成记录函数，返回记录的列表：(文字, 附件路径)。"""
    pushes: list[tuple[str, list[Path]]] = []

    def send_everyone(text: str, files: Sequence[str | Path] | None = None) -> None:
        pushes.append((text, [Path(path) for path in files or []]))

    monkeypatch.setattr(sw.notifier, "send_everyone", send_everyone)
    return pushes


def sequence_scene(
    controller: Any, images: Sequence[bytes], prompt: bytes, overworld: bytes
) -> Callable[[], bytes]:
    """collect 用的画面：每截一次图按顺序返回 images 里的下一张，用完后一直返回最后一张；
    按过 Y 之后是 prompt（结束野餐的确认），Y 之后再按过 A 是 overworld（野外）。
    """
    peeks = 0

    def scene() -> bytes:
        nonlocal peeks
        pressed: list[str] = controller.pressed
        if "Y" in pressed:
            return overworld if "A" in pressed[pressed.index("Y") :] else prompt
        index = min(peeks, len(images) - 1)
        peeks += 1
        return images[index]

    return scene


# ---------- initialize ----------


@pytest.mark.parametrize(("parent", "best"), [("parent3", 3), ("parent4", 4)])
def test_initialize_picnic_party_reads_parent_in_party_slot_2_and_goes_to_hatch_load(
    make_world: WorldFactory, make_egg: EggFactory, parent: str, best: int
) -> None:
    """initialize：队伍是野餐的（第 1 格百变怪，第 2 格爱吃豚）：parent_best 是队伍第 2 格爱吃豚
    「最棒」的项数，退出盒子（回到野外），直接返回 "hatch_load"。
    """
    world = make_world(
        party=["ditto", parent, None, None, None, None],
        boxes={FLAME_BOX: picnic_store()},
        riding=True,
    )
    sw = make_egg(world.render)
    assert initialize(sw) == "hatch_load"
    assert sw.parent_best == best
    assert world.mode == "overworld"


@pytest.mark.parametrize(("parent", "best"), [("parent3", 3), ("parent4", 4)])
def test_initialize_hatch_party_reads_parent_in_flame_box_and_goes_to_hatch_load(
    hatch_world: WorldFactory, make_egg: EggFactory, parent: str, best: int
) -> None:
    """initialize：队伍是孵蛋的（第 2–6 格都空）：parent_best 读 flame_box 第 1 行第 2 列的爱吃豚，
    退出盒子，返回 "hatch_load"（盒子里可能还有上次没孵的蛋）。
    """
    world = hatch_world(boxes={FLAME_BOX: hatch_store(parent)}, riding=True)
    sw = make_egg(world.render)
    assert initialize(sw) == "hatch_load"
    assert sw.parent_best == best
    assert world.mode == "overworld"


def test_initialize_egg_in_party_slot_5_resets_counters_and_goes_to_hatch_walk(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """initialize：孵蛋的队伍第 5 格里有蛋：eggs_in_box 归零、eggs_in_party 是 1，退出盒子，返回 "hatch_walk"。"""
    world = hatch_world(party=party_with(s4="egg"), riding=True)
    sw = make_egg(world.render)
    sw.eggs_in_box = 9
    assert initialize(sw) == "hatch_walk"
    assert sw.eggs_in_box == 0
    assert sw.eggs_in_party == 1
    assert sw.parent_best == 3
    assert world.mode == "overworld"


def test_initialize_hatched_pokemon_in_party_goes_to_check(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """initialize：孵蛋的队伍第 2 格是上次孵出来还没看的宝可梦（啪嘧海胆）：不抛错，退出盒子，返回 "check"。"""
    world = hatch_world(party=party_with(s1="other"), riding=True)
    sw = make_egg(world.render)
    assert initialize(sw) == "check"
    assert world.mode == "overworld"


def test_initialize_egg_and_hatched_pokemon_in_party_goes_to_check_first(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """initialize：孵蛋的队伍里第 4 格是孵出来的、第 5 格是蛋：先去 "check"，不去 hatch_walk。"""
    world = hatch_world(party=party_with(s3="other", s4="egg"), riding=True)
    sw = make_egg(world.render)
    assert initialize(sw) == "check"


def test_initialize_parent_missing_from_flame_box_raises_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """initialize：队伍第 2 格不是爱吃豚（当成孵蛋的队伍），flame_box 第 1 行第 2 列也不是：抛 RuntimeError。"""
    world = make_world(
        party=["ditto", "other", None, None, None, None],
        boxes={FLAME_BOX: {(0, 0): "ditto"}},
        riding=True,
    )
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        initialize(sw)


# ---------- picnic ----------


def test_picnic_with_picnic_party_opens_picnic_without_swapping(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """picnic：队伍已经是野餐的（百变怪、亲代）：不换队伍（不按 Y），退出盒子后按 L 转镜头，
    再开主菜单进「野餐」；picnics 加 1，返回 "sandwich"。
    """
    world = make_world(party=PICNIC_PARTY, boxes={FLAME_BOX: picnic_store()}, riding=False)
    sw = make_egg(world.render)
    assert picnic(sw) == "sandwich"
    assert sw.picnics == 1
    assert world.mode == "picnic"
    assert "Y" not in controller.pressed
    last_x = len(controller.pressed) - 1 - controller.pressed[::-1].index("X")
    assert controller.pressed.index("L") < last_x
    assert world.party == PICNIC_PARTY


def test_picnic_swaps_hatch_party_back_to_picnic_party(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """picnic：队伍是孵蛋的（火焰之躯）：转到 flame_box，火焰之躯和队伍第 1 格交换（百变怪回队伍），
    第 2 列的亲代放回队伍第 2 格；之后队伍是百变怪、亲代，flame_box 第 1 列是火焰之躯、第 2 列空；
    盒子转回 egg_boxes[0]；返回 "sandwich"。
    """
    world = hatch_world(riding=False)
    sw = make_egg(world.render)
    assert picnic(sw) == "sandwich"
    assert world.party == PICNIC_PARTY
    assert world.boxes[FLAME_BOX] == picnic_store()
    assert world.box_number == sw.config.egg_boxes[0]
    assert world.mode == "picnic"


def test_picnic_flame_box_slot_2_is_not_parent_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """picnic：队伍是孵蛋的，但 flame_box 第 1 行第 2 列不是亲代：抛 RuntimeError，队伍没有被换。"""
    world = hatch_world(boxes={FLAME_BOX: {(0, 0): "ditto"}}, riding=False)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        picnic(sw)
    assert world.party == HATCH_PARTY
    assert sw.picnics == 0


def test_picnic_still_riding_presses_plus_first(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """picnic：开始时还骑着坐骑：先关菜单按 PLUS 下来，再开菜单进「野餐」；返回 "sandwich"，不再骑着。"""
    world = make_world(party=PICNIC_PARTY, boxes={FLAME_BOX: picnic_store()}, riding=True)
    sw = make_egg(world.render)
    assert picnic(sw) == "sandwich"
    assert "PLUS" in controller.pressed
    assert world.riding is False
    assert world.mode == "picnic"


def test_picnic_never_shows_picnic_screen_raises_timeout_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """picnic：开了菜单按 A 之后一直不出现野餐画面（30 秒）：抛 TimeoutError（wait_for 超时）。"""
    world = make_world(
        party=PICNIC_PARTY, boxes={FLAME_BOX: picnic_store()}, riding=False, picnic_fails=True
    )
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        picnic(sw)
    assert sw.picnics == 0


# ---------- sandwich ----------


def sandwich_scene(
    controller: Any, load_image: ImageLoader, recipe: bytes, picnic_after: int | None
) -> Callable[[], bytes]:
    """sandwich 用的画面，跟着按过的 A 的次数走：0 次是野餐，1 次是桌子的菜单，2 次是 recipe（食谱），
    3 次是选签子，之后是做三明治；按到 picnic_after 次 A 之后回到野餐（None 就不回）。
    """

    def scene() -> bytes:
        count = controller.pressed.count("A")
        if picnic_after is not None and count >= picnic_after:
            return load_image("野餐.jpg")
        if count == 0:
            return load_image("野餐.jpg")
        if count == 1:
            return load_image("桌子菜单.jpg")
        if count == 2:
            return recipe
        if count == 3:
            return load_image("选三明治签.jpg")
        return load_image("三明治效果.jpg")

    return scene


def test_sandwich_makes_super_peanut_butter_sandwich_and_goes_to_to_basket(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：走到桌子前按 A，选「做料理」，食谱 17 是超级花生酱，做完吃掉回到野餐画面：
    返回 "to_basket"；放香蕉时 A 按住了 3 次、松开了 3 次；结束时所有按住的键和摇杆都松开了；
    进食谱之后按了 5 次 DDOWN。
    """
    scene = sandwich_scene(controller, load_image, load_image("食谱-17.jpg"), picnic_after=8)
    sw = make_egg(scene)
    assert sandwich(sw) == "to_basket"
    events = controller.events
    assert events.count(("press", "A")) == 3
    assert events.count(("release", "A")) == 3
    assert controller.pressed.count("DDOWN") == 5
    held_buttons = {e[1] for e in events if e[0] == "press"} - {
        e[1] for e in events if e[0] == "release"
    }
    held_sticks = {e[1] for e in events if e[0] == "press_stick"} - {
        e[1] for e in events if e[0] == "release_stick"
    }
    assert held_buttons == set()
    assert held_sticks == set()


def test_sandwich_recipe_17_not_super_peanut_butter_raises_runtime_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：食谱画面有「食谱」标题，但按了 5 次 DDOWN 之后右侧读不到「超级花生酱」
    （可能没解锁或材料不够）：抛 RuntimeError，报错里有「超级花生酱」；没有开始做。
    """
    image = np.frombuffer(load_image("食谱-17.jpg"), np.uint8)
    recipe = cv2.imdecode(image, cv2.IMREAD_COLOR)
    assert recipe is not None
    height, width = recipe.shape[:2]
    # 右侧「超级花生酱」所在的区域涂成纯灰
    recipe[
        round(0.21 * height) : round(0.26 * height), round(0.57 * width) : round(0.80 * width)
    ] = 128
    ok, buffer = cv2.imencode(".jpg", recipe)
    assert ok
    scene = sandwich_scene(controller, load_image, buffer.tobytes(), picnic_after=None)
    sw = make_egg(scene)
    with pytest.raises(RuntimeError) as error:
        sandwich(sw)
    assert "超级花生酱" in str(error.value)
    assert controller.pressed.count("DDOWN") == 5
    assert controller.pressed.count("A") == 2


def test_sandwich_no_dialog_after_pressing_a_whistles_and_raises_runtime_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：走到桌子前按 A 之后一直没出对话框（前面有宝可梦挡着）：按 R 吹口哨再试，
    试了几次都不行，抛 RuntimeError。
    """
    sw = make_egg(lambda: load_image("野餐.jpg"))
    with pytest.raises(RuntimeError):
        sandwich(sw)
    assert "R" in controller.pressed
    assert "A" in controller.pressed


# ---------- to_basket ----------


def test_to_basket_dismounts_walks_route_presses_l_5_times_and_goes_to_collect(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """to_basket：先按 PLUS 收回坐骑，再走篮子的路线（路线里有 5 次「btn:L」，就是按 5 次 L）；
    eggs_in_box 归零，返回 "collect"；路线走完所有摇杆都回中了。
    """
    sw = make_egg(lambda: load_image("野餐.jpg"))
    sw.eggs_in_box = 5
    assert to_basket(sw) == "collect"
    assert controller.pressed == ["PLUS", "L", "L", "L", "L", "L"]
    assert sw.eggs_in_box == 0
    pushed = [e[1] for e in controller.events if e[0] == "press_stick"]
    released = [e[1] for e in controller.events if e[0] == "release_stick"]
    assert sorted(set(pushed)) == sorted(set(released))


# ---------- collect ----------


def collect_images(load_image: ImageLoader, *names: str) -> list[bytes]:
    return [load_image(name) for name in names]


def press_scene(
    controller: Any, images: Sequence[bytes], prompt: bytes, overworld: bytes
) -> Callable[[], bytes]:
    """collect 用的画面，跟着按键走：按过 n 次键（Y 之前）就显示 images[n]，用完后一直是最后一张；
    按过 Y 之后是 prompt（结束野餐的确认），Y 之后再按过 A 是 overworld（野外）。
    """

    def scene() -> bytes:
        pressed: list[str] = controller.pressed
        if "Y" in pressed:
            return overworld if "A" in pressed[pressed.index("Y") :] else prompt
        return images[min(len(pressed), len(images) - 1)]

    return scene


def test_collect_takes_egg_when_prompt_shows_and_ends_picnic_when_box_is_full(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：按 A 查篮子，之后依次是篮子的对话、「要领走蛋吗」的是/否、「已领走」的对话、回到野餐：
    普通对话按 B 推进（不按 A，免得把没认出的是/否按成「是」），是/否按 A；eggs_in_box 加 1，
    按键是 A、B、A、B；这时到了 max_eggs（1），接着 leave_picnic 的 Y、A，返回 "hatch_load"。
    """
    images = collect_images(
        load_image,
        "野餐.jpg",
        "篮子-看了一看.jpg",
        "篮子-要领走蛋吗.jpg",
        "篮子-已领走蛋.jpg",
        "野餐.jpg",
    )
    scene = press_scene(controller, images, load_image("结束野餐确认.jpg"), load_image("野外.jpg"))
    sw = make_egg(scene)
    sw.config.max_eggs = 1
    assert collect(sw) == "hatch_load"
    assert sw.eggs_in_box == 1
    assert controller.pressed == ["A", "B", "A", "B", "Y", "A"]


def test_collect_refuses_when_full_then_answers_yes_to_the_second_prompt(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：eggs_in_box 已经等于 max_eggs（2），第一个是/否按 B（不领），之后会再出一个是/否，
    按 A（选「是」）并清掉标记；eggs_in_box 不变；按键是 A、B、B、A、B，然后 Y、A 收野餐。
    """
    images = collect_images(
        load_image,
        "野餐.jpg",
        "篮子-看了一看.jpg",
        "篮子-要领走蛋吗.jpg",
        "篮子-要领走蛋吗.jpg",
        "篮子-还有蛋.jpg",
        "野餐.jpg",
    )
    scene = press_scene(controller, images, load_image("结束野餐确认.jpg"), load_image("野外.jpg"))
    sw = make_egg(scene)
    sw.config.max_eggs = 2
    sw.eggs_in_box = 2
    assert collect(sw) == "hatch_load"
    assert sw.eggs_in_box == 2
    assert controller.pressed == ["A", "B", "B", "A", "B", "Y", "A"]


def test_collect_dialog_that_never_ends_raises_timeout_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：篮子的对话一直不结束（画面一直是对话框）：整个循环超过 collect_timeout（默认 300 秒，这里改成 20 秒）后抛 TimeoutError；
    之后只按 B 推进，不按 A，没有领蛋。
    """
    sw = make_egg(lambda: load_image("篮子-看了一看.jpg"))
    # 默认 300 秒要截很多次图，测试里缩短，只看超时本身
    sw.config.collect_timeout = 20.0
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        collect(sw)
    assert time.monotonic() - start >= sw.config.collect_timeout
    assert controller.pressed[0] == "A"
    assert set(controller.pressed[1:]) == {"B"}
    assert sw.eggs_in_box == 0


def test_collect_time_is_up_presses_y_then_a_and_goes_to_hatch_load(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：离三明治做好超过 picnic_minutes（这里设成 0 分钟）：查完篮子之后按 Y、A 收野餐，
    返回 "hatch_load"，egg_index 是 0；eggs_in_box 没到 max_eggs 也一样。
    """
    images = collect_images(load_image, "篮子-没有蛋.jpg", "野餐.jpg")
    scene = sequence_scene(
        controller, images, load_image("结束野餐确认.jpg"), load_image("野外.jpg")
    )
    sw = make_egg(scene)
    sw.config.picnic_minutes = 0
    assert collect(sw) == "hatch_load"
    assert sw.eggs_in_box == 0
    assert controller.pressed[-2:] == ["Y", "A"]


def test_collect_not_full_and_not_time_yet_keeps_pressing_and_goes_back_to_collect(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：这次查完 eggs_in_box 没到 max_eggs、离三明治做好也没到 picnic_minutes：
    不按 Y；等 basket_interval 秒，期间一直有按键（不让 Switch 休眠）；返回 "collect"。
    """
    images = collect_images(load_image, "篮子-没有蛋.jpg", "野餐.jpg")
    scene = sequence_scene(
        controller, images, load_image("结束野餐确认.jpg"), load_image("野外.jpg")
    )
    sw = make_egg(scene)
    sw.sandwich_at = time.monotonic()
    start = time.monotonic()
    assert collect(sw) == "collect"
    assert "Y" not in controller.pressed
    assert len(controller.pressed) > 1
    assert controller.pressed[0] == "A"
    assert time.monotonic() - start >= sw.config.basket_interval


def test_collect_never_sees_dialog_whistles_turns_camera_and_raises_runtime_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """collect：按 A 之后一直没有对话框（没走到篮子前）：按过 R 吹口哨，连着 10 次不行后右摇杆往左转镜头，
    试满 20 次抛 RuntimeError，报错里有「篮子」。
    """
    sw = make_egg(lambda: load_image("野餐.jpg"))
    with pytest.raises(RuntimeError) as error:
        collect(sw)
    assert "篮子" in str(error.value)
    assert "R" in controller.pressed
    assert controller.pressed.count("A") >= 20
    assert any(e[0] in ("stick", "press_stick") and e[1] == "RIGHT" for e in controller.events)
    assert sw.eggs_in_box == 0


# ---------- hatch_load ----------


def test_hatch_load_finds_eggs_on_screen_and_puts_them_in_party_slots_2_and_3(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：队伍已经是孵蛋的；盒子 21 里有两个蛋（中间不连着）：看画面认出蛋，放进队伍第 2、3 格，
    第 4–6 格还是空的；eggs_in_party 是 2；退出盒子，返回 "hatch_walk"。
    """
    world = hatch_world(box={(0, 0): "egg", (2, 4): "egg"}, cursor=("party", 0), riding=True)
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert world.party == ["other", "egg", "egg", None, None, None]
    assert world.boxes[21] == {}
    assert sw.eggs_in_party == 2
    assert world.mode == "overworld"


def test_hatch_load_takes_at_most_5_eggs_front_to_back(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：盒子 21 里有 7 个蛋：从前往后拿 5 个放进队伍第 2–6 格，eggs_in_party 是 5，
    盒子里还剩最后两个（第 0 行第 5 列、第 1 行第 0 列）。
    """
    box = {(0, k): "egg" for k in range(6)} | {(1, 0): "egg"}
    world = hatch_world(box=box, cursor=("party", 0), riding=True)
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert world.party[1:] == ["egg"] * 5
    assert sorted(world.boxes[21]) == [(0, 5), (1, 0)]
    assert sw.eggs_in_party == 5


def test_hatch_load_goes_through_egg_boxes_in_order_until_party_is_full(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_load：盒子 21 里 3 个蛋、22 里 3 个：按 21、22 的顺序找，拿满 5 个就不再往后
    （21 转到 22 按 R）：21 的蛋拿光，22 里按行列顺序拿前两个，剩最后一个；eggs_in_party 是 5。
    """
    world = hatch_world(
        boxes={
            21: {(0, 0): "egg", (0, 1): "egg", (4, 5): "egg"},
            22: {(0, 2): "egg", (1, 1): "egg", (3, 3): "egg"},
        },
        cursor=("party", 0),
        riding=True,
    )
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert world.party[1:] == ["egg"] * 5
    assert world.boxes[21] == {}
    assert world.boxes[22] == {(3, 3): "egg"}
    assert sw.eggs_in_party == 5
    assert "R" in controller.pressed


def test_hatch_load_no_egg_anywhere_turns_back_to_first_box_and_goes_to_picnic(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_load：egg_boxes（21、22）里一个蛋都没有（打开时盒子停在 22）：按 21、22 的顺序各看一遍
    （先认队伍要转到 flame_box 23：R；23 到 21：L、L；21 到 22：R），最后转回 egg_boxes[0]（再 L），退出盒子，返回 "picnic"；队伍没变。
    """
    world = hatch_world(box_number=22, cursor=("box", 0, 0), riding=True)
    sw = make_egg(world.render)
    assert hatch_load(sw) == "picnic"
    assert world.box_number == 21
    assert world.party == HATCH_PARTY
    assert world.mode == "overworld"
    assert [key for key in controller.pressed if key in ("L", "R")] == ["R", "L", "L", "R", "L"]
    assert "Y" not in controller.pressed


def test_hatch_load_slot_is_not_an_egg_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：画面上认成蛋的那一格，光标过去读到的名字不是「蛋」：抛 RuntimeError，队伍里没有放进东西。"""
    world = hatch_world(
        box={(0, 0): "other"},
        paint_eggs=frozenset({(0, 0)}),
        cursor=("party", 0),
        riding=True,
    )
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        hatch_load(sw)
    assert world.party == HATCH_PARTY


def test_hatch_load_keeps_egg_left_in_party_and_fills_only_empty_slots(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：队伍第 2 格还留着蛋：算进 eggs_in_party，新蛋只放进第 3–6 格（盒子里 3 个都拿走）。"""
    world = hatch_world(
        party=party_with(s1="egg"), box={(0, k): "egg" for k in range(3)}, riding=True
    )
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert sw.eggs_in_party == 4
    assert world.party[1:5] == ["egg"] * 4
    assert world.party[5] is None
    assert world.boxes[21] == {}


def test_hatch_load_other_pokemon_in_party_slot_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：拿蛋前队伍第 5 格是别的宝可梦：抛 RuntimeError，报错里有「第 5 格」。"""
    world = hatch_world(party=party_with(s4="other"), box={(0, 0): "egg"}, riding=True)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError, match="第 5 格"):
        hatch_load(sw)


def test_hatch_load_from_picnic_party_swaps_to_hatch_party_then_loads_eggs(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：队伍是野餐的：先转到 flame_box，火焰之躯和队伍第 1 格的百变怪交换，队伍第 2 格的亲代
    放进第 2 列；然后在 egg_boxes 里找蛋放进队伍第 2 格起；返回 "hatch_walk"。
    """
    world = make_world(
        party=PICNIC_PARTY,
        boxes={FLAME_BOX: picnic_store(), 21: {(0, 0): "egg"}},
        riding=True,
    )
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert world.party == ["other", "egg", None, None, None, None]
    assert world.boxes[FLAME_BOX] == hatch_store()
    assert sw.eggs_in_party == 1


def test_hatch_load_flame_box_slot_1_empty_raises_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：队伍第 1、2 格是百变怪、爱吃豚，但 flame_box 第 1 行两列都是空的（认不出是哪种组法）：
    抛 RuntimeError，报错里写出四个位置读到的名字（Ditto、爱吃豚、盒子 23），队伍没变。
    """
    world = make_world(party=PICNIC_PARTY, boxes={FLAME_BOX: {}}, riding=True)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError) as error:
        hatch_load(sw)
    for text in ("Ditto", "爱吃豚", "盒子 23"):
        assert text in str(error.value)
    assert world.party == PICNIC_PARTY


def test_hatch_load_flame_box_slot_2_not_empty_raises_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：队伍是野餐的，但 flame_box 第 1 行第 2 列不是空的（放不下亲代）：抛 RuntimeError，队伍没变。"""
    world = make_world(
        party=PICNIC_PARTY,
        boxes={FLAME_BOX: {(0, 0): "other", (0, 1): "other"}},
        riding=True,
    )
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        hatch_load(sw)
    assert world.party == PICNIC_PARTY


# ---------- hatch_walk ----------


def load_one_egg(world: Any, sw: EggSession) -> int:
    """盒子里放一个蛋，用 hatch_load 放进队伍，返回这时已经按过的键数。"""
    world.box = {(0, 0): "egg"}
    assert hatch_load(sw) == "hatch_walk"
    return len(world.controller.pressed)


def assert_everything_released(world: Any) -> None:
    """所有按住的键和摇杆都松开了。"""
    assert world.held == set()
    assert world.sticks == {}


def test_hatch_walk_hatches_egg_and_releases_everything(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_walk：绕圈走到蛋要孵了（对话框），按 A 看孵化动画，回到野外：hatched 加 1，返回 "check"，
    结束时所有按住的键和摇杆都松开了；孵之前是按住 LSTICK、左右摇杆绕圈的。
    """
    world = hatch_world(riding=True, events=["hatch"])
    sw = make_egg(world.render)
    load_one_egg(world, sw)
    assert hatch_walk(sw) == "check"
    assert sw.hatched == 1
    assert world.hatched == 1
    assert world.mode == "overworld"
    assert_everything_released(world)


def test_hatch_walk_rides_first_when_not_riding(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_walk：开始时没骑坐骑：先按 PLUS 骑上，然后才绕圈；孵完返回 "check"。"""
    world = hatch_world(riding=True, events=["hatch"])
    sw = make_egg(world.render)
    before = load_one_egg(world, sw)
    world.riding = False
    assert hatch_walk(sw) == "check"
    assert "PLUS" in controller.pressed[before:]
    assert world.riding is True
    assert sw.hatched == 1


def test_hatch_walk_battle_menu_runs_away_with_ddown_3_times_and_a(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_walk：绕圈时遇到野生宝可梦（战斗菜单）：松开摇杆，按 DDOWN 三次到「逃走」再按 A，
    逃走之后继续绕圈，蛋孵出来后 hatched 是 1；结束时所有按住的键和摇杆都松开了。
    """
    world = hatch_world(riding=True, events=["battle", "hatch"])
    sw = make_egg(world.render)
    before = load_one_egg(world, sw)
    assert hatch_walk(sw) == "check"
    assert contains_run(controller.pressed[before:], ["DDOWN", "DDOWN", "DDOWN", "A"])
    assert world.escapes == 1
    assert sw.hatched == 1
    assert_everything_released(world)


def test_hatch_walk_cannot_run_away_5_times_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_walk：战斗菜单一直逃不掉：试了 5 次（每次 DDOWN 三下加 A）之后抛 RuntimeError。"""
    world = hatch_world(riding=True, events=["battle"], escape_fails=True)
    sw = make_egg(world.render)
    before = load_one_egg(world, sw)
    with pytest.raises(RuntimeError):
        hatch_walk(sw)
    after = controller.pressed[before:]
    assert after.count("A") == 5
    assert after.count("DDOWN") == 15


# ---------- check ----------


def test_check_shiny_pushes_once_saves_screenshot_saves_game_and_is_done(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """check：队伍第 5 格是闪光：推送一次，文字里有「闪光」、名字「爱吃豚」和格子「5」，附一张存在
    shiny_dir 里的截图；退出盒子后存档（开菜单 X、R 等确认框、A 等「记录」的对话，再按 B 退回野外）；
    存上了所以只推送一次；返回 "done"。
    """
    world = hatch_world(party=party_with(s3="parent3", s4="shiny"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "done"
    assert len(pushes) == 1
    text, files = pushes[0]
    assert "闪光" in text
    assert "爱吃豚" in text
    assert "5" in text
    assert len(files) == 1
    assert files[0].is_file()
    assert files[0].parent == tmp_path / "shinys"
    assert contains_run(controller.pressed, ["X", "R", "A"])
    assert controller.pressed[-1] == "B"
    assert len(pushes) == 1


def test_check_better_than_parent_swaps_with_parent_and_releases_old_parent(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：队伍第 5 格的 4 项最棒比亲代（3 项）好：按 Y 拿起，转到 flame_box，和第 1 行第 2 列的亲代交换，
    parent_best 变成 4，光标回到队伍第 5 格，换下来的原亲代被放生；没有推送；返回 "hatch_load"。
    flame_box 第 1 行第 2 列现在是新亲代，队伍里只剩火焰之躯。
    """
    world = hatch_world(party=party_with(s4="parent4"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "hatch_load"
    assert "Y" in controller.pressed
    assert sw.parent_best == 4
    assert world.party == HATCH_PARTY
    assert world.boxes[FLAME_BOX] == hatch_store("parent4")
    assert pushes == []
    assert world.mode == "overworld"


def test_check_not_better_than_parent_releases_it_with_ddown_4_a_dup_a(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：队伍第 4 格也是 3 项最棒，不比亲代好：不按 Y，放生它：按键里有连续的
    A、DDOWN×4、A（选放生）、DUP、A（确认框选「是」）、A（关掉对话）；parent_best 不变；
    返回 "hatch_load"，没有推送。
    """
    world = hatch_world(party=party_with(s3="parent3"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "hatch_load"
    assert "Y" not in controller.pressed
    assert contains_run(controller.pressed, RELEASE_KEYS)
    assert sw.parent_best == 3
    assert world.party == HATCH_PARTY
    assert pushes == []


def test_check_looks_at_slots_6_5_4_and_releases_every_worse_one(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：队伍第 4、5、6 格的爱吃豚都不比亲代好：从第 6 格往上依次放生（每放生一次按键里有一段
    A、DDOWN×4、A、DUP、A、A），结束时队伍只剩火焰之躯。
    """
    world = hatch_world(party=party_with(s3="parent3", s4="parent3", s5="parent3"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 4
    record_pushes(sw, monkeypatch)
    assert check(sw) == "hatch_load"
    assert world.party == HATCH_PARTY
    assert controller.pressed.count("DUP") >= 3
    assert contains_run(controller.pressed, RELEASE_KEYS)


def test_check_slot_is_not_parent_name_and_not_shiny_is_released(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：队伍第 4 格不是爱吃豚（盒子里以前留下的别的蛋孵出来的），也不是闪光：不抛错、不推送、
    不和亲代比（不按 Y），放生它；parent_best 不变，返回 "hatch_load"。
    """
    world = hatch_world(party=party_with(s3="other"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "hatch_load"
    assert pushes == []
    assert "Y" not in controller.pressed
    assert contains_run(controller.pressed, RELEASE_KEYS)
    assert sw.parent_best == 3
    assert world.party == HATCH_PARTY


def test_check_does_not_release_unhatched_egg_in_party(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：队伍第 4 格是孵出来的宝可梦、第 5 格还是没孵的蛋（initialize 遇到这种情况会先去 check）：
    只能放生孵出来的那只，蛋要留在队伍里，不能当成「不是爱吃豚」放生掉。
    """
    world = hatch_world(party=party_with(s3="other", s4="egg"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    record_pushes(sw, monkeypatch)
    check(sw)
    assert "egg" in world.party


# ---------- 每一步开始前清掉上一步的截图 ----------


class _StopAtFirstPeek(Exception):
    """测试用：第一次截图就停下。"""


@pytest.mark.parametrize("name", sorted(set(STEPS) - {"to_basket"}))
def test_every_step_clears_frames_before_it_starts(name: str, make_egg: EggFactory) -> None:
    """约定「每一步开始前，sw.frames.clear()」：每一步在第一次截图之前，上一步留下的截图要清掉，
    不然跑几个小时 sw.frames 越堆越多（每张 1920×1080 的 JPEG），出错时也会把几小时的截图全写盘。
    """

    def scene() -> bytes:
        raise _StopAtFirstPeek

    sw = make_egg(scene)
    marker = Frame(0.0, "上一步", "旧截图", b"old")
    sw.frames.append(marker)
    with pytest.raises(_StopAtFirstPeek):
        STEPS[name](sw)
    assert marker not in sw.frames


def test_to_basket_clears_frames(make_egg: EggFactory, load_image: ImageLoader) -> None:
    """约定「每一步开始前，sw.frames.clear()」：to_basket 不截图，跑完上一步的截图也要清掉。"""
    sw = make_egg(lambda: load_image("野餐.jpg"))
    marker = Frame(0.0, "上一步", "旧截图", b"old")
    sw.frames.append(marker)
    to_basket(sw)
    assert marker not in sw.frames


# ---------- 没被测到的出错路径 ----------


def test_hatch_walk_circling_10_minutes_without_hatching_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_walk：一直绕圈（没有对话框、没有战斗）超过 10 分钟一个都没孵：抛 RuntimeError，
    报错前所有按住的键和摇杆都松开了。
    """
    world = hatch_world(riding=True, events=[])
    sw = make_egg(world.render)
    load_one_egg(world, sw)
    with pytest.raises(RuntimeError, match="绕圈"):
        hatch_walk(sw)
    world.sync()
    assert_everything_released(world)


def test_sandwich_never_back_to_picnic_after_eating_raises_timeout_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：插完签子后一直按 A，60 秒都没回到野餐画面：抛 TimeoutError；放香蕉按住的 A 都松开了。"""
    scene = sandwich_scene(controller, load_image, load_image("食谱-17.jpg"), picnic_after=None)
    sw = make_egg(scene)
    with pytest.raises(TimeoutError):
        sandwich(sw)
    events = controller.events
    assert events.count(("press", "A")) == events.count(("release", "A"))


def test_sandwich_unknown_filling_move_raises_and_releases_a_and_stick(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：filling_moves 里写错了动作名：抛 ValueError 说明不认识哪个动作，按住的 A 和左摇杆都松开。"""
    scene = sandwich_scene(controller, load_image, load_image("食谱-17.jpg"), picnic_after=8)
    sw = make_egg(scene)
    sw.config.filling_moves = (("A+", 0.5), ("X", 0.1))
    with pytest.raises(ValueError, match="X"):
        sandwich(sw)
    assert controller.events[-2:] == [("release", "A"), ("release_stick", "LEFT")]


# ---------- 修改 4：确认、重试和超时 ----------


def test_check_shiny_but_save_fails_pushes_again_asking_for_manual_save(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：闪光，但存档没存上（按 R 之后不出确认框）：不悄悄停下，再推送一次「没存上档，请手动存档」，
    仍然返回 "done"；一共推送两次，第一次是闪光的。
    """
    world = hatch_world(party=party_with(s3="parent3", s4="shiny"), riding=True, save_fails=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "done"
    assert len(pushes) == 2
    assert "闪光" in pushes[0][0]
    assert "没存上档" in pushes[1][0]
    assert "手动存档" in pushes[1][0]


def test_check_shiny_appearing_before_release_is_announced_not_released(
    hatch_world: WorldFactory,
    make_egg: EggFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check：看名字时不是闪光，放生之前再看一次 panel_shiny 变成了闪光（这里把 read_shiny 换成先 False 后 True）：
    不放生，走闪光流程：推送、返回 "done"；没有按 A、DDOWN×4、A 选放生。
    """
    readings = iter([False, True])
    monkeypatch.setattr(check_module, "read_shiny", lambda sw: next(readings))
    world = hatch_world(party=party_with(s3="parent3"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    pushes = record_pushes(sw, monkeypatch)
    assert check(sw) == "done"
    assert len(pushes) == 1
    assert not contains_run(controller.pressed, RELEASE_KEYS[:6])
    assert world.party[3] == "parent3"


def test_check_better_parent_lands_in_flame_box_and_old_parent_is_released_after_checks(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """check：队伍第 5 格 4 项最棒比亲代好：和 flame_box 第 1 行第 2 列交换，两边读回来都对
    （盒子里是 4 项最棒、队伍这一格是原来的 3 项最棒的亲代）才放生，parent_best 到最后才变成 4。
    """
    world = hatch_world(party=party_with(s4="parent4"), riding=True)
    sw = make_egg(world.render)
    sw.parent_best = 3
    assert check(sw) == "hatch_load"
    assert sw.parent_best == 4
    assert world.boxes[FLAME_BOX][(0, 1)] == "parent4"
    assert world.party == HATCH_PARTY


def test_check_swapped_parent_in_box_has_wrong_best_count_raises_without_releasing(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """check：交换之后 flame_box 第 1 行第 2 列读到的最棒项数不对（这里放进去的是 3 项的，应该是 4 项）：
    抛 RuntimeError，没有放生（没有按 A、DDOWN×4、A），parent_best 不变。
    """
    world = hatch_world(party=party_with(s4="parent4"), riding=True, swap_stores="parent3")
    sw = make_egg(world.render)
    sw.parent_best = 3
    with pytest.raises(RuntimeError, match="最棒"):
        check(sw)
    assert not contains_run(controller.pressed, RELEASE_KEYS[:6])
    assert sw.parent_best == 3


def test_initialize_presses_plus_when_panel_is_not_on_judge_page(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """initialize：读亲代时面板不在能力判定页：按 PLUS 切过去再读；parent_best 读对（3）。"""
    world = hatch_world(riding=True, judge_page=False)
    sw = make_egg(world.render)
    assert initialize(sw) == "hatch_load"
    assert "PLUS" in controller.pressed
    assert sw.parent_best == 3


def test_initialize_panel_stuck_off_judge_page_raises_runtime_error(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """initialize：PLUS 按 10 次面板还是不在判定页：抛 RuntimeError。"""
    world = hatch_world(riding=True, judge_page=False, judge_stuck=True)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        initialize(sw)


def test_picnic_completes_half_done_swap_back_to_picnic_party(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """picnic：上次换到一半（队伍第 1 格已经是百变怪，第 2 格空，亲代还在 flame_box 第 2 列，
    火焰之躯在第 1 列）：按实际位置补完剩下的一次搬动，队伍变成百变怪、亲代，返回 "sandwich"。
    """
    world = make_world(
        party=["ditto", None, None, None, None, None],
        boxes={FLAME_BOX: {(0, 0): "other", (0, 1): "parent3"}},
        riding=False,
    )
    sw = make_egg(world.render)
    assert picnic(sw) == "sandwich"
    assert world.party == PICNIC_PARTY
    assert world.boxes[FLAME_BOX] == picnic_store()


def test_picnic_unrecognized_party_raises_runtime_error_listing_four_names(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """picnic：队伍第 1、2 格和 flame_box 第 1 行两列四个位置认不出是哪种组法：抛 RuntimeError，
    报错里写出四个位置读到的名字。
    """
    world = make_world(
        party=["parent3", "ditto", None, None, None, None],
        boxes={FLAME_BOX: {(0, 0): "ditto"}},
        riding=False,
    )
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError) as error:
        picnic(sw)
    message = str(error.value)
    for text in ("爱吃豚", "Ditto", "盒子 23"):
        assert text in message


def test_picnic_waits_after_picnic_screen_for_ball_throw_animation(
    make_world: WorldFactory, make_egg: EggFactory, clock: Any
) -> None:
    """picnic：认出野餐画面之后再等 picnic_settle_wait（8 秒，丢精灵球的动画期间人不能动）才返回。"""
    world = make_world(party=PICNIC_PARTY, boxes={FLAME_BOX: picnic_store()}, riding=False)
    sw = make_egg(world.render)
    before = clock.now
    picnic(sw)
    assert clock.now - before >= sw.config.picnic_settle_wait


def test_hatch_load_completes_half_done_swap_to_hatch_party(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_load：上次换到一半（队伍第 1 格已经是火焰之躯，第 2 格还是亲代，百变怪在 flame_box 第 1 列，
    第 2 列空）：按实际位置补完剩下的搬动（亲代放进 flame_box 第 2 列）再找蛋。
    """
    world = make_world(
        party=["other", "parent3", None, None, None, None],
        boxes={FLAME_BOX: {(0, 0): "ditto"}, 21: {(0, 0): "egg"}},
        riding=True,
    )
    sw = make_egg(world.render)
    assert hatch_load(sw) == "hatch_walk"
    assert world.boxes[FLAME_BOX] == hatch_store()
    assert world.party == ["other", "egg", None, None, None, None]


# ---------- hatch_walk：逃跑和孵化结束 ----------


def test_hatch_walk_after_fleeing_presses_b_on_dialog_until_overworld_is_stable(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_walk：逃走之后先出一个对话框（真机上出过）：按 B 推进，回到野外并稳定后才算逃掉，继续绕圈孵蛋。"""
    world = hatch_world(riding=True, events=["battle", "hatch"], flee_dialog=True)
    sw = make_egg(world.render)
    before = load_one_egg(world, sw)
    assert hatch_walk(sw) == "check"
    assert "B" in controller.pressed[before:]
    assert world.escapes == 1
    assert sw.hatched == 1


def test_hatch_walk_battle_appears_while_pressing_a_for_hatch_flees_then_finishes(
    hatch_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """hatch_walk：按 A 看孵化的过程中出现战斗菜单：先逃走（DDOWN×3、A），再回到野外，hatched 加 1。"""
    world = hatch_world(riding=True, events=["hatch_battle"])
    sw = make_egg(world.render)
    before = load_one_egg(world, sw)
    assert hatch_walk(sw) == "check"
    assert contains_run(controller.pressed[before:], ["DDOWN", "DDOWN", "DDOWN", "A"])
    assert world.escapes == 1
    assert sw.hatched == 1
    assert_everything_released(world)


def test_hatch_walk_dialog_after_overworld_means_hatch_is_not_over_yet(
    hatch_world: WorldFactory, make_egg: EggFactory
) -> None:
    """hatch_walk：回到野外之后画面又出了一帧对话框（还没孵完）：不算孵完，不重复计数；
    野外稳定下来后 hatched 只加 1，结束时按住的键和摇杆都松开了。
    """
    world = hatch_world(riding=True, events=["hatch"], late_dialog=True)
    sw = make_egg(world.render)
    load_one_egg(world, sw)
    assert hatch_walk(sw) == "check"
    assert world.late_countdown == 0
    assert sw.hatched == 1
    assert_everything_released(world)


# ---------- sandwich：每一步认画面 ----------


def test_sandwich_table_menu_a_swallowed_presses_a_again_until_recipe_shows(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：桌子菜单上第一次按 A 没进食谱（被吞掉）：隔几秒再按一次，食谱画面出来才往下做。"""

    def scene() -> bytes:
        count = controller.pressed.count("A")
        if count >= 9:
            return load_image("野餐.jpg")
        if count == 0:
            return load_image("野餐.jpg")
        if count <= 2:
            return load_image("桌子菜单.jpg")
        if count == 3:
            return load_image("食谱-17.jpg")
        if count == 4:
            return load_image("选三明治签.jpg")
        return load_image("三明治效果.jpg")

    sw = make_egg(scene)
    assert sandwich(sw) == "to_basket"
    assert controller.pressed.count("DDOWN") == 5


def test_sandwich_never_reaches_pick_screen_raises_timeout_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：食谱 17 对了，但按 A 之后一直进不了选签子的界面：抛 TimeoutError，没有开始放香蕉。"""

    def scene() -> bytes:
        count = controller.pressed.count("A")
        if count == 0:
            return load_image("野餐.jpg")
        if count == 1:
            return load_image("桌子菜单.jpg")
        return load_image("食谱-17.jpg")

    sw = make_egg(scene)
    with pytest.raises(TimeoutError):
        sandwich(sw)
    assert ("press", "A") not in controller.events


def test_sandwich_pick_screen_a_does_not_start_making_raises_timeout_error(
    make_egg: EggFactory, controller: Any, load_image: ImageLoader
) -> None:
    """sandwich：进了选签子的界面，但按 A 之后一直还是这个界面（没开始做）：抛 TimeoutError，没有开始放香蕉。"""

    def scene() -> bytes:
        count = controller.pressed.count("A")
        if count == 0:
            return load_image("野餐.jpg")
        if count == 1:
            return load_image("桌子菜单.jpg")
        if count == 2:
            return load_image("食谱-17.jpg")
        return load_image("选三明治签.jpg")

    sw = make_egg(scene)
    with pytest.raises(TimeoutError):
        sandwich(sw)
    assert ("press", "A") not in controller.events
