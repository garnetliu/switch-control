"""control_switch.flow.menu：认出菜单选项、把光标移到目标。

期望值取自搬迁前 menu_last_item、move_menu_option 在真机截图上的运行结果。
研究员那张图 OCR 读出两项 ['>是', '定否']（和画面上的字不一样），光标在第 0 项。
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from control_switch.device.botbase import Switch
from control_switch.flow.menu import menu_last_item, move_menu_option
from control_switch.flow.wait import wait_for
from control_switch.types import Rect
from control_switch.vision import ImageChecker

IMAGES = Path(__file__).resolve().parents[1] / "images"
RESEARCHER = (IMAGES / "研究员问换不换.jpg").read_bytes()
BACKPACKER = (IMAGES / "路线上的界面-遇到了背包客.jpg").read_bytes()

MENU_AREA: Rect = ((0.60, 0.45), (0.90, 0.79))
EMPTY_DIALOG: Rect = ((0.0, 0.0), (0.2, 0.1))

SwitchFactory = Callable[..., Any]

ARROW_ROW_RECT: Rect = ((0.67, 0.50), (0.70, 0.55))
ARROW_MENU: tuple[Rect, list[tuple[str, Rect]]] = (
    ((0.66, 0.49), (0.83, 0.80)),
    [
        (">", ARROW_ROW_RECT),
        ("是", ((0.67, 0.60), (0.72, 0.65))),
        ("否", ((0.67, 0.70), (0.72, 0.75))),
    ],
)


def nothing() -> None:
    """不移动光标。"""


def test_menu_last_item_returns_last_option_text() -> None:
    """有菜单的图：默认返回最后一项的文字。"""
    assert menu_last_item(ImageChecker(RESEARCHER), MENU_AREA) == "定否"


def test_menu_last_item_returns_option_at_given_index() -> None:
    """指定序号时返回那一项。"""
    assert menu_last_item(ImageChecker(RESEARCHER), MENU_AREA, 0) == ">是"


def test_menu_last_item_returns_empty_string_without_menu() -> None:
    """没有菜单的图：返回空字符串。"""
    assert menu_last_item(ImageChecker(BACKPACKER), MENU_AREA) == ""


def test_menu_last_item_returns_empty_string_when_dialog_has_no_text() -> None:
    """传了对话区域而那里没有文字：即使有菜单也返回空字符串。"""
    screen = ImageChecker(RESEARCHER)
    assert screen.read_text(EMPTY_DIALOG) == ""
    assert menu_last_item(screen, MENU_AREA, dialog=EMPTY_DIALOG) == ""


def test_move_menu_option_index_target_already_selected_does_not_move(
    make_switch: SwitchFactory,
) -> None:
    """目标是序号 0 且光标已经在第 0 项：返回 0，不移动。"""
    fake = make_switch([RESEARCHER])
    moves: list[int] = []
    result = move_menu_option(
        cast(Switch, fake),
        ImageChecker(RESEARCHER),
        0,
        lambda: moves.append(1),
        "研究员的菜单",
        MENU_AREA,
    )
    assert result == 0
    assert moves == []
    assert fake.pressed == []


def test_move_menu_option_text_target_already_selected_does_not_move(
    make_switch: SwitchFactory,
) -> None:
    """目标是文字 ">是"（OCR 读出来的原样）且光标已经在这项：返回 0，不移动。"""
    fake = make_switch([RESEARCHER])
    moves: list[int] = []
    result = move_menu_option(
        cast(Switch, fake),
        ImageChecker(RESEARCHER),
        ">是",
        lambda: moves.append(1),
        "研究员的菜单",
        MENU_AREA,
    )
    assert result == 0
    assert moves == []


def test_move_menu_option_text_target_off_by_one_character_still_matches(
    make_switch: SwitchFactory,
) -> None:
    """目标文字 ">是吗" 和读出的 ">是" 差一个字，3 个字允许差 1：能对上第 0 项。"""
    fake = make_switch([RESEARCHER])
    result = move_menu_option(
        cast(Switch, fake), ImageChecker(RESEARCHER), ">是吗", nothing, "研究员的菜单", MENU_AREA
    )
    assert result == 0


def test_move_menu_option_text_target_not_in_menu_raises_runtime_error(
    make_switch: SwitchFactory,
) -> None:
    """目标文字和所有选项都差得远：抛 RuntimeError，报错里有目标文字和读到的选项。"""
    fake = make_switch([RESEARCHER])
    with pytest.raises(RuntimeError, match="找不到「完全不相干的文字」.*定否"):
        move_menu_option(
            cast(Switch, fake),
            ImageChecker(RESEARCHER),
            "完全不相干的文字",
            nothing,
            "研究员的菜单",
            MENU_AREA,
        )


def test_move_menu_option_without_menu_raises_runtime_error(make_switch: SwitchFactory) -> None:
    """图里没有菜单：抛 RuntimeError，报错里有传进去的说明。"""
    fake = make_switch([BACKPACKER])
    with pytest.raises(RuntimeError, match="背包客的画面里找不到菜单"):
        move_menu_option(
            cast(Switch, fake),
            ImageChecker(BACKPACKER),
            0,
            nothing,
            "背包客的画面",
            MENU_AREA,
        )


@pytest.mark.parametrize("arrow", [">", "＞", " > ", "›", "》", "〉"])
def test_move_menu_option_arrow_only_row_is_not_an_option_for_text_target(
    make_switch: SwitchFactory, monkeypatch: pytest.MonkeyPatch, arrow: str
) -> None:
    """光标的箭头被单独认成一行时不算选项：目标「否」是第 1 项，不是第 2 项。"""
    menu = (ARROW_MENU[0], [(arrow, ARROW_ROW_RECT), *ARROW_MENU[1][1:]])
    monkeypatch.setattr(ImageChecker, "find_menu", lambda self, area: menu)
    seen: list[list[Rect]] = []

    def fake_selected(self: ImageChecker, rects: list[Rect]) -> int:
        seen.append(rects)
        return 1

    monkeypatch.setattr(ImageChecker, "selected", fake_selected)
    fake = make_switch([RESEARCHER])
    result = move_menu_option(
        cast(Switch, fake), ImageChecker(RESEARCHER), "否", nothing, "带箭头行的菜单", MENU_AREA
    )
    assert result == 1
    assert seen == [[menu[1][1][1], menu[1][2][1]]]


def test_move_menu_option_arrow_only_row_is_not_counted_in_option_count(
    make_switch: SwitchFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """箭头单独一行时，选项个数是 2（不是 3）：移满 2 次没到目标就报错。"""
    monkeypatch.setattr(ImageChecker, "find_menu", lambda self, area: ARROW_MENU)
    results = iter([0, 1] * 4)
    monkeypatch.setattr(ImageChecker, "selected", lambda self, rects: next(results))
    fake = make_switch([RESEARCHER])
    with pytest.raises(RuntimeError, match="移了 2 次"):
        move_menu_option(
            cast(Switch, fake), ImageChecker(RESEARCHER), 9, nothing, "带箭头行的菜单", MENU_AREA
        )


def test_move_menu_option_keeps_regular_option_starting_with_arrow_symbol(
    make_switch: SwitchFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'>是' 去掉符号后不是空的，照常算选项：研究员那张图有 2 个选项，移满 2 次报错。"""
    results = iter([0, 1] * 4)
    monkeypatch.setattr(ImageChecker, "selected", lambda self, rects: next(results))
    fake = make_switch([RESEARCHER])
    with pytest.raises(RuntimeError, match="移了 2 次"):
        move_menu_option(
            cast(Switch, fake), ImageChecker(RESEARCHER), 9, nothing, "研究员的菜单", MENU_AREA
        )


def test_move_menu_option_raises_when_cursor_moves_every_time_but_never_reaches_target(
    make_switch: SwitchFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """光标每次都换了位置（轮流 0、1），移满选项个数那么多次还没到目标：抛 RuntimeError，有「还是没到」。"""
    results = iter([0, 1] * 4)
    monkeypatch.setattr(ImageChecker, "selected", lambda self, rects: next(results))
    fake = make_switch([RESEARCHER])
    with pytest.raises(RuntimeError, match="还是没到第 6 项"):
        move_menu_option(
            cast(Switch, fake), ImageChecker(RESEARCHER), 5, nothing, "研究员的菜单", MENU_AREA
        )


def test_menu_last_item_with_index_beyond_options_does_not_break_wait_for(
    make_switch: SwitchFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """防的是：菜单只读出一项（还没出全、或者范围里是别的白框）时，menu_last_item(..., 1) 抛 IndexError。

    join.py 在 wait_for 的条件里写 menu_last_item(screen, rects.lobby_menu, 1) == solo，
    IndexError 会直接穿出 wait_for 让整局出错，而不是接着等菜单出全、到时间抛 TimeoutError。
    文档写的是「没有菜单返回空字符串」，读不到第 index 项也应该当作没有。
    """
    one_option: tuple[Rect, list[tuple[str, Rect]]] = (
        ((0.66, 0.49), (0.83, 0.80)),
        [("发起挑战", ((0.67, 0.50), (0.80, 0.55)))],
    )
    monkeypatch.setattr(ImageChecker, "find_menu", lambda self, area: one_option)
    fake = make_switch([RESEARCHER])
    with pytest.raises(TimeoutError, match="大厅的菜单"):
        wait_for(
            cast(Switch, fake),
            lambda screen: menu_last_item(screen, MENU_AREA, 1) == "发起单人挑战！",
            0.3,
            "大厅的菜单",
        )
