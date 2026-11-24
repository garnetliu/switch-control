"""control_switch.games.sv.egg.box.move_cursor：在盒子画面里把光标移到队伍或盒子的某一格。

画面用 conftest 的 World：按键让光标（模型里）真的移动，截图是按光标位置合成的盒子画面。
时间用假时钟，不真的等待。
"""

from collections.abc import Callable
from typing import Any

import pytest

from control_switch.games.sv.egg.box import (
    ensure_judge,
    exit_to_overworld,
    leave_picnic,
    menu_to_row,
    move_cursor,
    open_menu,
    pick_up,
    put_down,
    read_name,
    read_shiny,
    release_current,
    select_box,
    set_riding,
    stable_egg_cells,
)

WorldFactory = Callable[..., Any]
EggFactory = Callable[[Callable[[], bytes]], Any]
EMPTY_PARTY: list[str | None] = [None] * 6


def open_box(world: Any) -> None:
    """让模型直接处在盒子画面（move_cursor 从打开了的盒子开始）。"""
    world.mode = "box"


def test_move_cursor_from_box_origin_to_party_3_presses_dleft_first(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """("box", 0, 0) 到 ("party", 3)：先换列，第一下是 DLEFT（到队伍第 0 格），再 DDOWN 三下。"""
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("party", 3))
    assert controller.pressed == ["DLEFT", "DDOWN", "DDOWN", "DDOWN"]
    assert world.cursor == ("party", 3)


def test_move_cursor_from_party_to_box_cell_changes_column_before_row(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """("party", 3) 到 ("box", 1, 2)：DRIGHT 到盒子第 3 行第 0 列，再 DRIGHT 两下换到第 2 列，
    最后 DUP 两下到第 1 行；换列都在上下之前。
    """
    world = make_world(party=EMPTY_PARTY, cursor=("party", 3))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("box", 1, 2))
    assert controller.pressed == ["DRIGHT", "DRIGHT", "DRIGHT", "DUP", "DUP"]
    assert world.cursor == ("box", 1, 2)


def test_move_cursor_from_party_row_5_goes_up_first_because_right_is_search_button(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """("party", 5) 到 ("box", 4, 1)：队伍第 6 格往右是「搜寻」按钮，所以先按 DUP 到第 5 格，
    再 DRIGHT 到盒子第 4 行第 0 列，再 DRIGHT 一下到第 1 列。
    """
    world = make_world(party=EMPTY_PARTY, cursor=("party", 5))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("box", 4, 1))
    assert controller.pressed == ["DUP", "DRIGHT", "DRIGHT"]
    assert world.cursor == ("box", 4, 1)


def test_move_cursor_presses_dup_when_cursor_is_outside_the_cells(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """光标跑到格子外面（认不出是哪一格）：先按 DUP 回到格子里，再接着往目标走。
    ("box", 2, 0) 到 ("box", 3, 0)：第一下 DDOWN 光标跑出去了，然后 DUP 回来，再 DDOWN。
    """
    world = make_world(party=EMPTY_PARTY, cursor=("box", 2, 0), out_on_first_move=True)
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("box", 3, 0))
    assert controller.pressed == ["DDOWN", "DUP", "DDOWN"]
    assert world.cursor == ("box", 3, 0)


def test_move_cursor_within_box_moves_columns_then_rows(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """("box", 0, 0) 到 ("box", 2, 3)：先 DRIGHT 三下，再 DDOWN 两下。"""
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("box", 2, 3))
    assert controller.pressed == ["DRIGHT"] * 3 + ["DDOWN"] * 2
    assert world.cursor == ("box", 2, 3)


def test_move_cursor_within_party_only_moves_up_or_down(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """("party", 4) 到 ("party", 2)：只按 DUP 两下。"""
    world = make_world(party=EMPTY_PARTY, cursor=("party", 4))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("party", 2))
    assert controller.pressed == ["DUP", "DUP"]


def test_move_cursor_already_there_presses_nothing(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """光标已经在目标格：一个键都不按。"""
    world = make_world(party=EMPTY_PARTY, cursor=("party", 3))
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("party", 3))
    assert controller.pressed == []


def test_move_cursor_presses_again_when_cursor_did_not_move(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """按了一下光标没动（第一下被游戏吞了）：等不到 box_cursor 变化，再按一次。
    ("box", 0, 0) 到 ("party", 0)：DLEFT 按了两次。
    """
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0), drop_moves=1)
    open_box(world)
    sw = make_egg(world.render)
    move_cursor(sw, ("party", 0))
    assert controller.pressed == ["DLEFT", "DLEFT"]
    assert world.cursor == ("party", 0)


def test_move_cursor_gives_up_after_30_presses_with_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """光标一直不动：按满 30 下后抛 RuntimeError，不会按第 31 下。"""
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0), frozen=True)
    open_box(world)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        move_cursor(sw, ("party", 3))
    assert len(controller.pressed) == 30
    assert set(controller.pressed) == {"DLEFT"}


def test_move_cursor_error_counts_cells_from_1(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """补充约定「报错里的第几格从 1 数」：到不了队伍第 4 格（下标 3）时，报错要写「第 4 格」，
    不能把内部的 ('party', 3) 直接给人看（人会以为是第 3 格）。
    """
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0), frozen=True)
    open_box(world)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError) as error:
        move_cursor(sw, ("party", 3))
    message = str(error.value)
    assert "第 4 格" in message
    assert "('party', 3)" not in message


def test_menu_to_row_moves_down_one_row_at_a_time_then_presses_a(
    make_egg: EggFactory, controller: Any, load_image: Callable[[str], bytes]
) -> None:
    """menu_to_row：光标在第 1 行（盒子），要到第 2 行（野餐）：按 DDOWN，等行号变了，再按 A；
    按 A 之后菜单消失（进了这一行）就不再按。
    """

    def scene() -> bytes:
        if "A" in controller.pressed:
            return load_image("野餐.jpg")
        moved = "DDOWN" in controller.pressed
        return load_image("主菜单-野餐.jpg" if moved else "主菜单-盒子-骑着.jpg")

    sw = make_egg(scene)
    menu_to_row(sw, 2)
    assert controller.pressed == ["DDOWN", "A"]


def test_menu_to_row_moves_up_with_dup(
    make_egg: EggFactory, controller: Any, load_image: Callable[[str], bytes]
) -> None:
    """menu_to_row：光标在第 2 行，要到第 1 行：按 DUP 再按 A，A 之后菜单消失。"""

    def scene() -> bytes:
        if "A" in controller.pressed:
            return load_image("盒子-打开.jpg")
        moved = "DUP" in controller.pressed
        return load_image("主菜单-盒子-骑着.jpg" if moved else "主菜单-野餐.jpg")

    sw = make_egg(scene)
    menu_to_row(sw, 1)
    assert controller.pressed == ["DUP", "A"]


def test_exit_to_overworld_gives_up_after_10_b_with_runtime_error(
    make_egg: EggFactory, controller: Any, load_image: Callable[[str], bytes]
) -> None:
    """exit_to_overworld：按了 10 次 B 还在盒子里：抛 RuntimeError，没有多按。"""
    sw = make_egg(lambda: load_image("盒子-打开.jpg"))
    with pytest.raises(RuntimeError, match="10"):
        exit_to_overworld(sw)
    assert controller.pressed == ["B"] * 10


def test_set_riding_still_wrong_after_plus_raises_runtime_error(
    make_egg: EggFactory, controller: Any, load_image: Callable[[str], bytes]
) -> None:
    """set_riding(False)：按了 PLUS 之后菜单里还是写「下来」（骑着）：抛 RuntimeError，报错里说要「下来」。"""

    def scene() -> bytes:
        pressed = controller.pressed
        if pressed and pressed[-1] in ("B", "PLUS"):
            return load_image("野外-骑着.jpg")
        return load_image("主菜单-盒子-骑着.jpg")

    sw = make_egg(scene)
    with pytest.raises(RuntimeError, match="下来"):
        set_riding(sw, False)
    assert "PLUS" in controller.pressed


def list_scene(images: list[bytes]) -> Callable[[], bytes]:
    """每截一次图返回 images 里的下一张，用完后一直返回最后一张。"""
    peeks = 0

    def scene() -> bytes:
        nonlocal peeks
        image = images[min(peeks, len(images) - 1)]
        peeks += 1
        return image

    return scene


# ---------- open_menu、menu_to_row 的重按 ----------


def test_open_menu_presses_x_again_when_first_press_is_swallowed(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """open_menu：第一次按 X 被游戏吞掉（画面没变）：隔 menu_retry 秒再按一次，菜单出来后不再按。"""
    world = make_world(party=EMPTY_PARTY, swallow={"X": 1})
    sw = make_egg(world.render)
    open_menu(sw)
    assert controller.pressed == ["X", "X"]
    assert world.mode == "menu"


def test_open_menu_never_appears_raises_timeout_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """open_menu：X 一直没反应：抛 TimeoutError。"""
    world = make_world(party=EMPTY_PARTY, swallow={"X": 10**6})
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        open_menu(sw)


def test_menu_to_row_presses_a_again_when_menu_is_still_there(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """menu_to_row：第一次按 A 被吞掉（菜单还在）：隔 menu_enter_interval 秒再按一次，进去之后不再按。"""
    world = make_world(party=EMPTY_PARTY, riding=True, swallow={"A": 1})
    world.mode = "menu"
    sw = make_egg(world.render)
    menu_to_row(sw, 1)
    assert controller.pressed == ["A", "A"]
    assert world.mode == "box"


def test_menu_to_row_menu_never_closes_raises_timeout_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """menu_to_row：A 一直按不进去（菜单一直在）：抛 TimeoutError。"""
    world = make_world(party=EMPTY_PARTY, riding=True, swallow={"A": 10**6})
    world.mode = "menu"
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        menu_to_row(sw, 1)


# ---------- leave_picnic ----------


def test_leave_picnic_presses_y_then_a_until_overworld(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """leave_picnic：按 Y 出确认框，按 A 回到野外；各按一次。"""
    world = make_world(party=EMPTY_PARTY)
    world.mode = "picnic"
    sw = make_egg(world.render)
    leave_picnic(sw)
    assert controller.pressed == ["Y", "A"]
    assert world.mode == "overworld"


def test_leave_picnic_retries_y_when_first_press_is_swallowed(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """leave_picnic：第一次按 Y 没反应：隔几秒再按一次（Y、Y、A）。"""
    world = make_world(party=EMPTY_PARTY, swallow={"Y": 1})
    world.mode = "picnic"
    sw = make_egg(world.render)
    leave_picnic(sw)
    assert controller.pressed == ["Y", "Y", "A"]
    assert world.mode == "overworld"


def test_leave_picnic_waits_after_overworld_before_returning(
    make_world: WorldFactory, make_egg: EggFactory, clock: Any
) -> None:
    """leave_picnic：回到野外之后再等 leave_final_wait（3 秒）才返回。"""
    world = make_world(party=EMPTY_PARTY)
    world.mode = "picnic"
    sw = make_egg(world.render)
    start = clock.now
    leave_picnic(sw)
    assert clock.now - start >= sw.config.leave_final_wait


def test_leave_picnic_no_confirm_prompt_in_25_seconds_raises_timeout_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """leave_picnic：Y 一直没有出确认框：抛 TimeoutError。"""
    world = make_world(party=EMPTY_PARTY, swallow={"Y": 10**6})
    world.mode = "picnic"
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        leave_picnic(sw)


def test_leave_picnic_never_back_to_overworld_raises_timeout_error(
    load_image: Callable[[str], bytes], make_egg: EggFactory, controller: Any
) -> None:
    """leave_picnic：按 A 之后一直回不到野外（20 秒）：抛 TimeoutError。"""

    def scene() -> bytes:
        return load_image("结束野餐确认.jpg" if "Y" in controller.pressed else "野餐.jpg")

    sw = make_egg(scene)
    with pytest.raises(TimeoutError):
        leave_picnic(sw)


def test_exit_to_overworld_in_picnic_leaves_picnic_first(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """exit_to_overworld：截到的是野餐画面（出错后接着跑）：先结束野餐（Y、A），不是按 B。"""
    world = make_world(party=EMPTY_PARTY)
    world.mode = "picnic"
    sw = make_egg(world.render)
    exit_to_overworld(sw)
    assert controller.pressed == ["Y", "A"]
    assert world.mode == "overworld"


def test_exit_to_overworld_presses_b_in_unknown_picnic_screens_then_leaves(
    load_image: Callable[[str], bytes], make_egg: EggFactory, controller: Any
) -> None:
    """exit_to_overworld：在食谱这种认不出是什么的画面：按 B 回到野餐（假画面里按 B 就回野餐），
    再结束野餐（Y、A）。
    """

    def scene() -> bytes:
        pressed = controller.pressed
        if "A" in pressed:
            return load_image("野外.jpg")
        if "Y" in pressed:
            return load_image("结束野餐确认.jpg")
        return load_image("野餐.jpg" if "B" in pressed else "食谱-17.jpg")

    sw = make_egg(scene)
    exit_to_overworld(sw)
    assert controller.pressed == ["B", "Y", "A"]


# ---------- 读面板 ----------


def test_read_name_returns_name_when_two_frames_agree(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_name：连续两帧读到一样的名字就返回（爱吃豚）。"""
    image = box_image(("party", 1), "parent3")
    sw = make_egg(list_scene([image, image]))
    assert read_name(sw) == "爱吃豚"


def test_read_name_waits_until_two_frames_agree(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_name：第一帧是爱吃豚、后两帧是蛋（换格子的动画期间）：返回「蛋」，不是第一帧的名字。"""
    first = box_image(("party", 1), "parent3")
    later = box_image(("party", 1), "egg")
    sw = make_egg(list_scene([first, later, later]))
    assert read_name(sw) == "蛋"


def test_read_name_never_stable_returns_last_reading(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_name：每一帧都不一样：读 read_tries 次后返回最后一次读到的，不死循环。"""
    parent = box_image(("party", 1), "parent3")
    egg = box_image(("party", 1), "egg")
    sw = make_egg(list_scene([parent, egg] * 20))
    assert read_name(sw) in ("爱吃豚", "蛋")


def test_read_shiny_true_when_second_frame_is_shiny(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_shiny：第一帧不是闪光、第二帧是：任何一帧是就算，返回 True。"""
    plain = box_image(("party", 1), "parent4")
    shiny = box_image(("party", 1), "shiny")
    sw = make_egg(list_scene([plain, shiny]))
    assert read_shiny(sw) is True


def test_read_shiny_true_when_first_frame_is_shiny(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_shiny：第一帧是闪光、第二帧不是：返回 True。"""
    plain = box_image(("party", 1), "parent4")
    shiny = box_image(("party", 1), "shiny")
    sw = make_egg(list_scene([shiny, plain]))
    assert read_shiny(sw) is True


def test_read_shiny_false_when_no_frame_is_shiny(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """read_shiny：两帧都不是闪光：返回 False。"""
    plain = box_image(("party", 1), "parent4")
    sw = make_egg(list_scene([plain, plain]))
    assert read_shiny(sw) is False


# ---------- ensure_judge ----------


def test_ensure_judge_returns_without_pressing_when_already_on_judge_page(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """ensure_judge：面板已经在判定页（六项能力有判定词）：不按键，返回这张截图。"""
    world = make_world(party=["ditto", "parent3", None, None, None, None], cursor=("party", 1))
    open_box(world)
    sw = make_egg(world.render)
    image = ensure_judge(sw)
    assert controller.pressed == []
    assert image is not None


def test_ensure_judge_presses_plus_when_panel_is_on_another_page(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """ensure_judge：面板不在判定页（六项能力读不出判定词）：按 PLUS 切换，切到判定页就返回。"""
    world = make_world(
        party=["ditto", "parent3", None, None, None, None], cursor=("party", 1), judge_page=False
    )
    open_box(world)
    sw = make_egg(world.render)
    ensure_judge(sw)
    assert controller.events.count(("click", "PLUS")) == 1
    assert world.judge_page is True


def test_ensure_judge_stuck_raises_runtime_error_after_10_plus(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """ensure_judge：按了 10 次 PLUS 面板还是不在判定页：抛 RuntimeError。"""
    world = make_world(
        party=["ditto", "parent3", None, None, None, None],
        cursor=("party", 1),
        judge_page=False,
        judge_stuck=True,
    )
    open_box(world)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError):
        ensure_judge(sw)
    assert controller.pressed.count("PLUS") == 10


# ---------- pick_up、put_down ----------


def test_pick_up_presses_y_until_holding(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """pick_up：光标在蛋上，按 Y 之后画面显示拿着：只按一次。"""
    world = make_world(party=EMPTY_PARTY, box={(0, 0): "egg"}, cursor=("box", 0, 0))
    open_box(world)
    sw = make_egg(world.render)
    pick_up(sw)
    assert controller.pressed == ["Y"]
    assert world.holding == "egg"


def test_pick_up_presses_y_again_when_first_press_is_swallowed(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """pick_up：第一次按 Y 被吞掉（画面还是没拿着）：隔 pick_interval 秒再按一次。"""
    world = make_world(
        party=EMPTY_PARTY, box={(0, 0): "egg"}, cursor=("box", 0, 0), swallow={"Y": 1}
    )
    open_box(world)
    sw = make_egg(world.render)
    pick_up(sw)
    assert controller.pressed == ["Y", "Y"]
    assert world.holding == "egg"


def test_pick_up_on_empty_cell_raises_timeout_error_after_10_seconds(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """pick_up：光标在空格上，Y 拿不起来：10 秒后抛 TimeoutError。"""
    world = make_world(party=EMPTY_PARTY, cursor=("box", 0, 0))
    open_box(world)
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        pick_up(sw)


def test_put_down_presses_a_until_not_holding(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """put_down：拿着蛋，光标在空的队伍格上：按 A，画面显示没拿着，只按一次。"""
    world = make_world(party=EMPTY_PARTY, cursor=("party", 1))
    open_box(world)
    world.holding = "egg"
    world.origin = ("box", 0, 0)
    sw = make_egg(world.render)
    put_down(sw)
    assert controller.pressed == ["A"]
    assert world.party[1] == "egg"


def test_put_down_presses_a_again_when_first_press_is_swallowed(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """put_down：第一次按 A 被吞掉（还拿着）：再按一次。"""
    world = make_world(party=EMPTY_PARTY, cursor=("party", 1), swallow={"A": 1})
    open_box(world)
    world.holding = "egg"
    world.origin = ("box", 0, 0)
    sw = make_egg(world.render)
    put_down(sw)
    assert controller.pressed == ["A", "A"]


def test_put_down_always_holding_raises_timeout_error(
    make_world: WorldFactory, make_egg: EggFactory
) -> None:
    """put_down：A 一直放不下（一直显示拿着）：抛 TimeoutError。"""
    world = make_world(party=EMPTY_PARTY, cursor=("party", 1), swallow={"A": 10**6})
    open_box(world)
    world.holding = "egg"
    world.origin = ("box", 0, 0)
    sw = make_egg(world.render)
    with pytest.raises(TimeoutError):
        put_down(sw)


# ---------- select_box ----------


def test_select_box_turns_forward_with_r_to_reach_the_box(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """select_box：从盒子 21 到盒子 23：往近的方向按 R 两下；到了之后读两次确认。"""
    world = make_world(party=EMPTY_PARTY, box_number=21)
    open_box(world)
    sw = make_egg(world.render)
    select_box(sw, 23)
    assert controller.pressed == ["R", "R"]
    assert world.box_number == 23


def test_select_box_turns_backward_with_l_when_that_is_closer(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """select_box：从盒子 23 到盒子 21：按 L 两下（不绕一圈按 R）。"""
    world = make_world(party=EMPTY_PARTY, box_number=23)
    open_box(world)
    sw = make_egg(world.render)
    select_box(sw, 21)
    assert controller.pressed == ["L", "L"]
    assert world.box_number == 21


def test_select_box_already_there_presses_nothing(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """select_box：已经在这个盒子：不按键。"""
    world = make_world(party=EMPTY_PARTY, box_number=22)
    open_box(world)
    sw = make_egg(world.render)
    select_box(sw, 22)
    assert controller.pressed == []


def test_select_box_waits_for_box_animation_after_arriving(
    make_world: WorldFactory, make_egg: EggFactory, clock: Any
) -> None:
    """select_box：到位之后等 box_settle_wait（0.8 秒，换盒子的动画）。"""
    world = make_world(party=EMPTY_PARTY, box_number=22)
    open_box(world)
    sw = make_egg(world.render)
    start = clock.now
    select_box(sw, 22)
    assert clock.now - start >= sw.config.box_settle_wait


def test_select_box_gives_up_after_5_rounds_with_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """select_box：R 一直按不动盒子：5 轮之后抛 RuntimeError，每轮按了一次 R。"""
    world = make_world(party=EMPTY_PARTY, box_number=21, swallow={"R": 10**6})
    open_box(world)
    sw = make_egg(world.render)
    with pytest.raises(RuntimeError, match="22"):
        select_box(sw, 22)
    assert controller.pressed == ["R"] * 5


def test_select_box_title_never_readable_raises_timeout_error(
    load_image: Callable[[str], bytes], make_egg: EggFactory
) -> None:
    """select_box：盒子编号一直读不出来（不在盒子画面）：抛 TimeoutError。"""
    sw = make_egg(lambda: load_image("野外.jpg"))
    with pytest.raises(TimeoutError):
        select_box(sw, 21)


# ---------- stable_egg_cells ----------


def test_stable_egg_cells_returns_cells_when_two_frames_agree(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """stable_egg_cells：连续两帧认出的蛋一样：返回这些格子，按行列排好。"""
    image = box_image(("box", 0, 0), "empty", 21, frozenset({(2, 3), (0, 1)}))
    sw = make_egg(list_scene([image, image]))
    assert stable_egg_cells(sw) == [(0, 1), (2, 3)]


def test_stable_egg_cells_waits_until_two_frames_agree(
    box_image: Callable[..., bytes], make_egg: EggFactory
) -> None:
    """stable_egg_cells：第一帧（换盒子的动画）认出的蛋和后面不一样：用连续两帧一样的那个结果，不用第一帧的。"""
    animating = box_image(("box", 0, 0), "empty", 21, frozenset({(4, 4)}))
    settled = box_image(("box", 0, 0), "empty", 21, frozenset({(1, 1), (1, 2)}))
    sw = make_egg(list_scene([animating, settled, settled]))
    assert stable_egg_cells(sw) == [(1, 1), (1, 2)]


# ---------- release_current ----------


def test_release_current_releases_pokemon_and_logs_it_gone(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """release_current：光标在队伍第 4 格的宝可梦上：A 出操作菜单，DDOWN×4 选中「放生」，A，
    确认框 DUP、A，再按 A 关掉对话；这一格变空。
    """
    world = make_world(party=["ditto", "parent3", None, "other", None, None], cursor=("party", 3))
    open_box(world)
    sw = make_egg(world.render)
    release_current(sw)
    assert controller.pressed == ["A", "DDOWN", "DDOWN", "DDOWN", "DDOWN", "A", "DUP", "A", "A"]
    assert world.party[3] is None


def test_release_current_presses_a_again_when_operation_menu_does_not_show(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """release_current：第一次按 A 没出操作菜单（被吞掉）：再按一次 A，之后照常。"""
    world = make_world(
        party=["ditto", "parent3", None, "other", None, None], cursor=("party", 3), swallow={"A": 1}
    )
    open_box(world)
    sw = make_egg(world.render)
    release_current(sw)
    assert controller.pressed[:2] == ["A", "A"]
    assert world.party[3] is None


def test_release_current_selected_row_is_not_release_raises_runtime_error(
    make_world: WorldFactory, make_egg: EggFactory, controller: Any
) -> None:
    """release_current：DDOWN 之后菜单里选中的不是「放生」（这里只按了 3 次）：抛 RuntimeError，
    报错里写出选中的是什么，不按 A 选下去。
    """
    world = make_world(party=["ditto", "parent3", None, "other", None, None], cursor=("party", 3))
    open_box(world)
    sw = make_egg(world.render)
    sw.config.release_downs = 3
    with pytest.raises(RuntimeError, match="放生"):
        release_current(sw)
    assert controller.pressed == ["A", "DDOWN", "DDOWN", "DDOWN"]
    assert world.party[3] == "other"
