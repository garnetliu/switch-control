"""control_switch.games.sv.actions：存档、开主菜单、主菜单选行、开野餐、收野餐（sv/egg、sv/outbreak 共用）。

每一步按完都看画面：用一个游戏画面模型（按键让它变化，时间也会让它变化），
control_switch.games.sv.screens 里的识别函数换成读这个模型的函数。
"""

import importlib
from types import ModuleType
from typing import Any

import pytest

actions: ModuleType = importlib.import_module("control_switch.games.sv.actions")


class SaveWorld:
    """存档的画面：野外、主菜单、确认框、存档中（菜单还在）、字没出完的对话、存完的对话。

    野外按 X 开菜单；菜单按 R 出确认框（存完之后按 B 回到野外）；确认框按 A 开始存档，
    存档中菜单还在画面上，saving 秒之后出现字没出完的对话，再过 typing 秒字出完；
    存完的对话按 B 回到菜单。swallow_x：前几次 X 被游戏吞了。
    """

    def __init__(
        self, stage: Any, saving: list[float] | None = None, typing: float = 2.0, swallow_x: int = 0
    ) -> None:
        self.stage = stage
        self.phase = "overworld"
        self.saved = False
        # 每次进入存档中状态时用掉第一项（用完了用 5 秒）
        self.savings = list(saving or [])
        self.saving = 5.0
        self.typing = typing
        self.swallow_x = swallow_x
        self.since = stage.clock.now
        stage.on_click = self.press
        stage.set_sv_screens(
            is_overworld=lambda: self.now() == "overworld",
            is_main_menu=lambda: self.now() in ("menu", "saving"),
            is_prompt=lambda: self.now() == "prompt",
            is_dialog=lambda: self.now() == "dialog",
            has_dialog_box=lambda: self.now() in ("prompt", "typing", "dialog"),
        )

    def now(self) -> str:
        elapsed = self.stage.clock.now - self.since
        if self.phase == "saving" and elapsed >= self.saving:
            self.go("typing")
        if self.phase == "typing" and elapsed >= self.typing:
            self.go("dialog")
        return self.phase

    def go(self, phase: str) -> None:
        self.phase = phase
        self.since = self.stage.clock.now

    def press(self, button: str) -> None:
        phase = self.now()
        if phase == "overworld" and button == "X":
            if self.swallow_x:
                self.swallow_x -= 1
            else:
                self.go("menu")
        elif phase == "menu" and button == "R" and not self.saved:
            self.go("prompt")
        elif phase == "menu" and button == "B" and self.saved:
            self.go("overworld")
        elif phase == "prompt" and button == "A":
            self.saving = self.savings.pop(0) if self.savings else 5.0
            self.go("saving")
        elif phase == "saving" and button == "R":
            self.go("prompt")
        elif phase == "dialog" and button == "B":
            self.saved = True
            self.go("menu")


def test_save_game_presses_x_r_a_b_b_through_the_states(stage: Any) -> None:
    """存档：野外按 X，主菜单按 R，确认框按 A，存完的对话按 B，菜单再按 B；按键依次是 X、R、A、B、B，正常返回。
    存档中菜单还在画面上（5 秒）也不重按 R，字没出完的对话框也不按键，只等。
    """
    SaveWorld(stage)
    actions.save_game(stage.sw)
    assert stage.clicks() == ["X", "R", "A", "B", "B"]


def test_save_game_presses_x_again_when_first_x_is_swallowed(stage: Any) -> None:
    """野外按 X 没反应（被游戏吞了）：还在野外就再按 X，之后照常存完。"""
    SaveWorld(stage, swallow_x=1)
    actions.save_game(stage.sw)
    assert stage.clicks() == ["X", "X", "R", "A", "B", "B"]


def test_save_game_presses_r_again_when_confirmation_never_leads_to_dialog(stage: Any) -> None:
    """按了确认之后菜单一直在（超过 10 秒还没出存完的对话）：认为确认没按上，回到菜单按 R 再来，
    按键依次是 X、R、A、R、A、B、B。
    """
    SaveWorld(stage, saving=[15.0, 5.0])
    actions.save_game(stage.sw)
    assert stage.clicks() == ["X", "R", "A", "R", "A", "B", "B"]


def test_save_game_does_not_press_anything_while_dialog_text_is_still_appearing(
    stage: Any,
) -> None:
    """字没出完的对话框（有对话框、没有翻页的小三角）：不按键，只等；字出完（出现小三角）才按 B。"""
    start = stage.clock.now
    done = [False]

    def press(button: str) -> None:
        done[0] = True

    stage.on_click = press
    stage.set_sv_screens(
        is_overworld=lambda: done[0],
        is_main_menu=lambda: False,
        is_prompt=lambda: False,
        is_dialog=lambda: not done[0] and stage.clock.now - start >= 3.0,
        has_dialog_box=lambda: not done[0],
    )
    actions.save_game(stage.sw)
    assert stage.clicks() == ["B"]
    assert stage.clock.now - start >= 3.0


def test_save_game_raises_timeout_error_when_screen_never_changes(stage: Any) -> None:
    """画面一直是野外、按 X 没有任何反应：一直按 X，超时后抛 TimeoutError。"""
    stage.set_sv_screens(
        is_overworld=lambda: True,
        is_main_menu=lambda: False,
        is_prompt=lambda: False,
        is_dialog=lambda: False,
        has_dialog_box=lambda: False,
    )
    with pytest.raises(TimeoutError):
        actions.save_game(stage.sw)
    assert set(stage.clicks()) == {"X"}


def test_save_game_raises_timeout_error_when_nothing_is_recognized(stage: Any) -> None:
    """画面什么都认不出来：不按键，超时后抛 TimeoutError。"""
    stage.set_sv_screens(
        is_overworld=lambda: False,
        is_main_menu=lambda: False,
        is_prompt=lambda: False,
        is_dialog=lambda: False,
        has_dialog_box=lambda: False,
    )
    with pytest.raises(TimeoutError):
        actions.save_game(stage.sw)
    assert stage.clicks() == []


def test_open_menu_presses_x_again_when_first_press_is_swallowed(stage: Any) -> None:
    """开主菜单：第一次 X 被吞了，隔几秒没出菜单就再按一次 X，菜单出来就停。"""
    presses: list[str] = []
    stage.on_click = presses.append
    stage.set_sv_screens(is_main_menu=lambda: len(presses) >= 2)
    actions.open_menu(stage.sw)
    assert stage.clicks() == ["X", "X"]


class MenuWorld:
    """主菜单：光标在右边第 row 行（-1 是在左边队伍栏上）；DRIGHT 从左边到右边，DDOWN、DUP 上下移，
    A 进这一行（菜单消失）。swallow_a：前几次 A 被吞了。
    """

    def __init__(self, stage: Any, row: int, swallow_a: int = 0) -> None:
        self.row = row
        self.open = True
        self.swallow_a = swallow_a
        stage.on_click = self.press
        stage.set_sv_screens(
            menu_row=lambda: self.row if self.open else -1,
            is_main_menu=lambda: self.open,
        )

    def press(self, button: str) -> None:
        if button == "DRIGHT" and self.row == -1:
            self.row = 0
        elif button == "DDOWN" and self.row >= 0:
            self.row = min(self.row + 1, 5)
        elif button == "DUP" and self.row > 0:
            self.row -= 1
        elif button == "A":
            if self.swallow_a:
                self.swallow_a -= 1
            else:
                self.open = False


def test_menu_to_row_moves_down_then_presses_a(stage: Any) -> None:
    """主菜单光标在第 0 行、要进第 2 行：按 DDOWN 两下，再按 A。"""
    world = MenuWorld(stage, 0)
    actions.menu_to_row(stage.sw, 2)
    assert stage.clicks() == ["DDOWN", "DDOWN", "A"]
    assert world.row == 2
    assert not world.open


def test_menu_to_row_moves_up_when_cursor_is_below(stage: Any) -> None:
    """光标在第 3 行、要进第 1 行：按 DUP 两下，再按 A。"""
    MenuWorld(stage, 3)
    actions.menu_to_row(stage.sw, 1)
    assert stage.clicks() == ["DUP", "DUP", "A"]


def test_menu_to_row_moves_right_first_when_cursor_is_on_party_column(stage: Any) -> None:
    """光标在左边的队伍栏上：先按 DRIGHT 到右边，再往下到第 1 行，按 A。"""
    MenuWorld(stage, -1)
    actions.menu_to_row(stage.sw, 1)
    assert stage.clicks() == ["DRIGHT", "DDOWN", "A"]


def test_menu_to_row_presses_a_again_when_first_a_is_swallowed(stage: Any) -> None:
    """A 被吞了（菜单还在）：隔一会儿再按一次 A，进去为止。"""
    MenuWorld(stage, 1, swallow_a=1)
    actions.menu_to_row(stage.sw, 1)
    assert stage.clicks() == ["A", "A"]


class PicnicWorld:
    """野餐的画面：野外 → X 开菜单 → 选行按 A 进野餐（动画里画面还是野外）→ 野餐；
    野餐里按 Y 出结束的确认框，确认框按 A 回到野外。swallow_y：前几次 Y 被吞了。
    """

    def __init__(self, stage: Any, phase: str, swallow_y: int = 0) -> None:
        self.stage = stage
        self.phase = phase
        self.row = 0
        self.swallow_y = swallow_y
        self.since = stage.clock.now
        stage.on_click = self.press
        stage.set_sv_screens(
            is_overworld=lambda: self.now() in ("overworld", "animation"),
            is_main_menu=lambda: self.now() == "menu",
            menu_row=lambda: self.row if self.now() == "menu" else -1,
            is_picnic=lambda: self.now() == "picnic",
            is_prompt=lambda: self.now() == "prompt",
            has_dialog_box=lambda: self.now() == "prompt",
        )

    def now(self) -> str:
        if self.phase == "animation" and self.stage.clock.now - self.since >= 3.0:
            self.phase = "picnic"
        return self.phase

    def press(self, button: str) -> None:
        phase = self.now()
        if phase == "overworld" and button == "X":
            self.phase = "menu"
        elif phase == "menu" and button == "DDOWN":
            self.row += 1
        elif phase == "menu" and button == "A":
            self.phase = "animation"
            self.since = self.stage.clock.now
        elif phase == "picnic" and button == "Y":
            if self.swallow_y:
                self.swallow_y -= 1
            else:
                self.phase = "prompt"
        elif phase == "prompt" and button == "A":
            self.phase = "overworld"


def test_open_picnic_opens_menu_moves_to_picnic_row_and_waits_for_animation(stage: Any) -> None:
    """开野餐：野外按 X，主菜单里往下移到「野餐」那一行（第 2 行）按 A；进野餐的动画里画面还像野外，
    不能再按 X，等到野餐的画面出来。按键依次是 X、DDOWN、DDOWN、A。
    """
    world = PicnicWorld(stage, "overworld")
    actions.open_picnic(stage.sw)
    assert stage.clicks() == ["X", "DDOWN", "DDOWN", "A"]
    assert world.phase == "picnic"


def test_close_picnic_presses_y_until_prompt_then_a_until_overworld(stage: Any) -> None:
    """收野餐：按 Y 直到出确认框（第一次 Y 被吞了就再按），按 A 直到回到野外。按键依次是 Y、Y、A。"""
    world = PicnicWorld(stage, "picnic", swallow_y=1)
    actions.close_picnic(stage.sw)
    assert stage.clicks() == ["Y", "Y", "A"]
    assert world.phase == "overworld"


def test_close_picnic_raises_timeout_error_when_prompt_never_appears(stage: Any) -> None:
    """按 Y 一直没有确认框：超时（25 秒）抛 TimeoutError，按的都是 Y。"""
    PicnicWorld(stage, "picnic", swallow_y=10**6)
    with pytest.raises(TimeoutError):
        actions.close_picnic(stage.sw)
    assert set(stage.clicks()) == {"Y"}
