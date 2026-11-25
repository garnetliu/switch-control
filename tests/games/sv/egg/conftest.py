"""sv/egg 测试共用的图片、假时钟、假取图和一个会跟着按键变化的游戏画面模型。

测试文件里不能 from conftest import，这里的东西都通过 fixture 给测试用，类型标成 Any 或 Callable。

- load_image(名字)：读 tests/images/sv/egg/ 下的真机截图，返回 JPEG 字节。
- checker(名字)：同上，返回 ImageChecker（解码和 OCR 的结果按图片缓存）。
- box_image(光标, 面板)：合成盒子画面。左边的格子用「盒子-空格.jpg」，原来的光标涂暗，
  在指定的格子涂满黄色；右边的面板用 panel 指定的那张图的右边。
- fake_time：time.sleep、time.monotonic 换成假时钟，按键的 delay 也让假时钟往前走。
- make_egg(scene)：建一个 EggSession，scene 是每次截图时返回图片字节的函数。
- make_world(...)：游戏画面模型 World，截图（world.render）和按键（controller 的记录）联动。
"""

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from control_switch.device import Devices
from control_switch.games.sv.egg.config import EggConfig
from control_switch.games.sv.egg.session import EggSession
from control_switch.settings import load_settings
from control_switch.vision import ImageChecker

IMAGE_DIR = Path(__file__).resolve().parents[3] / "images" / "sv" / "egg"

# 面板用的图（只取右边的面板部分）
PANELS = {
    "parent3": "盒子-爱吃豚-3V.jpg",
    "parent4": "盒子-爱吃豚-4V.jpg",
    "ditto": "盒子-百变怪-6V.jpg",
    "other": "盒子-打开.jpg",
    "egg": "盒子-拿着蛋.jpg",
    "empty": "盒子-空格.jpg",
}
# 面板和格子的分界：面板在画面右边，x 大于这个比例
PANEL_LEFT = 0.67
# 闪光星星的区域
SHINY_RECT = ((0.878, 0.081), (0.906, 0.127))
# 同一个步骤里最多允许按多少次键、截多少次图，超过说明实现停不下来，测试直接报错
MAX_CLICKS = 3000
MAX_PEEKS = 20000

# 光标在 HSV 的 H=27、S、V 满格时的 BGR，在 box_cursor 要求的黄色（H 20–35，S≥150，V≥200）里
YELLOW = (0, 230, 255)

Cursor = tuple[Any, ...]

_bytes_cache: dict[str, bytes] = {}
_checker_cache: dict[str, ImageChecker] = {}
_box_cache: dict[tuple[Any, ...], bytes] = {}


def _load(name: str) -> bytes:
    if name not in _bytes_cache:
        _bytes_cache[name] = (IMAGE_DIR / name).read_bytes()
    return _bytes_cache[name]


def _decode_bytes(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


def _decode(name: str) -> np.ndarray:
    return _decode_bytes(_load(name))


def _encode(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def _cell(cursor: Cursor) -> tuple[tuple[float, float], tuple[float, float]]:
    """盒子画面里光标所在格子的范围（和 box_cursor 用的一样）。"""
    if cursor[0] == "party":
        i = cursor[1]
        return ((0.021, 0.185 + 0.1167 * i), (0.208, 0.296 + 0.1167 * i))
    _, r, c = cursor
    return (
        (0.234 + 0.0656 * c, 0.185 + 0.1167 * r),
        (0.2965 + 0.0656 * c, 0.296 + 0.1167 * r),
    )


def _fill(
    image: np.ndarray, rect: tuple[tuple[float, float], tuple[float, float]], color: Any
) -> None:
    height, width = image.shape[:2]
    (left, top), (right, bottom) = rect
    image[
        round(top * height) : round(bottom * height), round(left * width) : round(right * width)
    ] = color


def shiny_panel_image() -> bytes:
    """「盒子-爱吃豚-4V.jpg」，闪光星星的区域画上红白相间的方格（棋盘格）。"""
    image = _decode("盒子-爱吃豚-4V.jpg")
    height, width = image.shape[:2]
    (left, top), (right, bottom) = SHINY_RECT
    x0, x1, y0, y1 = (
        round(left * width),
        round(right * width),
        round(top * height),
        round(bottom * height),
    )
    for y in range(y0, y1):
        for x in range(x0, x1):
            image[y, x] = (0, 0, 255) if ((x - x0) // 4 + (y - y0) // 4) % 2 else (255, 255, 255)
    return _encode(image)


# 盒子编号的标题区域；22、23 的标题从对应的真机截图里取
TITLE_AREA = ((0.34, 0.11), (0.56, 0.165))
TITLE_SOURCES = {22: "盒子-22-蛋和宝可梦.jpg", 23: "盒子-23-两个蛋.jpg"}
# 蛋的样子取自这张图第 3 行第 2 列的格子（那一格是蛋，光标不在它上面）
EGG_SOURCE = ("盒子-21-蛋和宝可梦.jpg", (3, 2))


def _egg_part(cell: tuple[tuple[float, float], tuple[float, float]]) -> tuple[Any, Any]:
    """egg_cells 看的那一块：格子下 3/4、横向中间一半。"""
    (left, top), (right, bottom) = cell
    width, height = right - left, bottom - top
    return (
        (left + width * 0.25, top + height * 0.25),
        (left + width * 0.75, bottom),
    )


def _paste(image: np.ndarray, source: np.ndarray, rect: Any, target: Any | None = None) -> None:
    """把 source 里 rect 这块贴到 image 里 target（不给就是同一个位置）。"""
    height, width = image.shape[:2]
    (left, top), (right, bottom) = rect
    (tl, tt), _ = target or rect
    y0, y1 = round(top * height), round(bottom * height)
    x0, x1 = round(left * width), round(right * width)
    ty, tx = round(tt * height), round(tl * width)
    image[ty : ty + (y1 - y0), tx : tx + (x1 - x0)] = source[y0:y1, x0:x1]


def _box_image(
    cursor: Cursor,
    panel: str,
    number: int = 21,
    eggs: frozenset[tuple[int, int]] = frozenset(),
    holding: bool = False,
    judge: bool = True,
) -> bytes:
    key = (cursor, panel, number, eggs, holding, judge)
    if key not in _box_cache:
        image = _decode("盒子-空格.jpg")
        width = image.shape[1]
        # 原图的光标在盒子第 3 行第 0 列，涂暗
        _fill(image, _cell(("box", 3, 0)), (40, 40, 40))
        # 原图的格子里有宝可梦和蛋，把 egg_cells 看的那一块都涂暗，蛋按 eggs 再贴上去
        for r in range(5):
            for c in range(6):
                _fill(image, _egg_part(_cell(("box", r, c))), (40, 40, 40))
        if number != 21:
            _paste(image, _decode(TITLE_SOURCES[number]), TITLE_AREA)
        if panel == "shiny":
            panel_source = _decode_bytes(shiny_panel_image())
        else:
            panel_source = _decode(PANELS[panel])
        image[:, round(PANEL_LEFT * width) :] = panel_source[:, round(PANEL_LEFT * width) :]
        if cursor[0] != "out":
            _fill(image, _cell(cursor), YELLOW)
        egg_name, (egg_r, egg_c) = EGG_SOURCE
        egg_source = _decode(egg_name)
        for r, c in eggs:
            _paste(
                image,
                egg_source,
                _egg_part(_cell(("box", egg_r, egg_c))),
                _egg_part(_cell(("box", r, c))),
            )
        # 底栏：没拿着时有「替换」，拿着时只剩「显示宝可梦」「返回」
        bar_source = _decode("盒子-拿着蛋.jpg" if holding else "盒子-打开.jpg")
        _paste(image, bar_source, HOLDING_AREA)
        if not judge:
            # 面板在别的页（六项能力不是判定词）：六项能力的位置涂暗
            for rect in EggConfig().panel_stats:
                _fill(image, rect, (40, 40, 40))
        _box_cache[key] = _encode(image)
    return _box_cache[key]


_battle_cache: dict[int, bytes] = {}


def _battle_image(row: int) -> bytes:
    """战斗菜单，黄色光标在第 row 行（真机只有第 0 行的截图，其他行是把按钮位置涂成黄色）。"""
    if row not in _battle_cache:
        config = EggConfig()
        image = _decode("战斗菜单.jpg")
        (left, top), (right, bottom) = config.battle_button

        def rect(i: int) -> Any:
            shift = config.battle_row_step * i
            return ((left, top + shift), (right, bottom + shift))

        if row != 0:
            # 第 0 行的按钮不选中时的样子，取第 1 行的
            _paste(image, image, rect(1), rect(0))
            _fill(image, rect(row), YELLOW)
        _battle_cache[row] = _encode(image)
    return _battle_cache[row]


RIDING_AREA = ((0.11, 0.935), (0.23, 0.99))
HOLDING_AREA = ((0.30, 0.94), (0.70, 0.99))
_menu_cache: dict[tuple[int, bool], bytes] = {}


def _menu_image(row: int, riding: bool) -> bytes:
    """主菜单：光标在第 row 行（1 是盒子、2 是野餐），坐骑那一栏按 riding 写「下来」或「骑上」。"""
    key = (row, riding)
    if key not in _menu_cache:
        image = _decode("主菜单-盒子-骑着.jpg" if row == 1 else "主菜单-野餐.jpg")
        source = _decode("主菜单-盒子-骑着.jpg" if riding else "主菜单-野餐.jpg")
        _paste(image, source, RIDING_AREA)
        _menu_cache[key] = _encode(image)
    return _menu_cache[key]


class Clock:
    """假时钟：sleep 只让时间往前走。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        """假的 time.monotonic。"""
        return self.now

    def sleep(self, seconds: float) -> None:
        """假的 time.sleep。"""
        self.now += seconds


class SceneScreen:
    """假 Screen：每次截图调用 scene 取图片字节；截得太多说明实现停不下来。"""

    def __init__(self, scene: Callable[[], bytes]) -> None:
        self._scene = scene
        self.peeks = 0
        self.close_calls = 0

    def pixel_peek(self) -> bytes:
        """调用 scene。"""
        self.peeks += 1
        assert self.peeks <= MAX_PEEKS, "截图太多次，实现停不下来"
        return self._scene()

    def close(self) -> None:
        """记下调用次数。"""
        self.close_calls += 1


class World:
    """游戏画面模型：按 controller.events 里的按键更新状态，render() 返回当前状态对应的真机截图。

    状态（mode）：overworld 野外、menu 主菜单、box 盒子、operation 盒子里的操作菜单、
    confirm 放生确认、released 放生后的对话、picnic 野餐中、battle 战斗菜单、
    hatch_dialog 蛋要孵了的对话、hatch_anim 孵化动画。

    主菜单：骑着的时候显示「盒子」那一行（A 进盒子），没骑的时候显示「野餐」那一行（A 开野餐）。
    盒子：光标在队伍第 i 格 ("party", i) 或盒子 ("box", r, c)；Y 拿起，A 放下或和那一格交换
    （换下来的放回拿起的地方）。操作菜单里按 4 次 DDOWN 再 A 是放生，确认框里 DUP 选「是」。
    放生之后队伍下面的格子往上补。
    绕圈（按住 LSTICK、左右摇杆都推着）时每截一次图记一次，记满 circle_ticks 次发生下一个事件：
    events 里依次是 "battle"（战斗菜单，DDOWN 三次再 A 逃走）或 "hatch"（孵化的对话，按 A 两次回到野外）。
    """

    def __init__(
        self,
        controller: Any,
        *,
        party: Sequence[str | None],
        box: dict[tuple[int, int], str] | None = None,
        boxes: dict[int, dict[tuple[int, int], str]] | None = None,
        box_number: int = 21,
        cursor: Cursor = ("box", 0, 0),
        riding: bool = True,
        events: Sequence[str] = (),
        circle_ticks: int = 3,
        escape_fails: bool = False,
        picnic_fails: bool = False,
        paint_eggs: frozenset[tuple[int, int]] = frozenset(),
        frozen: bool = False,
        drop_moves: int = 0,
        out_on_first_move: bool = False,
        menu_row: int | None = None,
        swallow: dict[str, int] | None = None,
        judge_page: bool = True,
        judge_stuck: bool = False,
        save_fails: bool = False,
        flee_dialog: bool = False,
        late_dialog: bool = False,
        swap_stores: str | None = None,
    ) -> None:
        assert len(party) == 6
        self.controller = controller
        self.party: list[str | None] = list(party)
        # 每个盒子里的内容；box 是当前盒子的
        self.boxes: dict[int, dict[tuple[int, int], str]] = {
            number: dict(content) for number, content in (boxes or {}).items()
        }
        self.box_number = box_number
        if box is not None:
            self.boxes[box_number] = dict(box)
        self.origin_box = box_number
        self.cursor: Cursor = cursor
        self.riding = riding
        # 主菜单的光标在第几行：1 是盒子、2 是野餐；不给就是骑着停在盒子、没骑停在野餐
        self.menu_row = menu_row if menu_row is not None else (1 if riding else 2)
        self.mode = "overworld"
        self.holding: str | None = None
        self.origin: Cursor | None = None
        self.held: set[str] = set()
        self.sticks: dict[str, tuple[int, int]] = {}
        self.pending = list(events)
        self.circle_ticks = circle_ticks
        self.escape_fails = escape_fails
        self.picnic_fails = picnic_fails
        self.paint_eggs = paint_eggs
        self.frozen = frozen
        self.drop_moves = drop_moves
        self.out_on_first_move = out_on_first_move
        self.back: Cursor = cursor
        # 前几次按这些键会被游戏吞掉（按键 -> 还要吞几次）
        self.swallow = dict(swallow or {})
        self.judge_page = judge_page
        self.judge_stuck = judge_stuck
        self.save_fails = save_fails
        self.flee_dialog = flee_dialog
        self.late_dialog = late_dialog
        self.late_countdown = 0
        self.hatch_battle = False
        self.swap_stores = swap_stores
        self.battle_row = 0
        self.ticks = 0
        self.downs = 0
        self.yes = False
        self.escapes = 0
        self.hatched = 0
        self._seen = 0

    # ---- 格子里的内容 ----

    @property
    def box(self) -> dict[tuple[int, int], str]:
        """当前盒子里的内容。"""
        return self.boxes.setdefault(self.box_number, {})

    @box.setter
    def box(self, value: dict[tuple[int, int], str]) -> None:
        self.boxes[self.box_number] = dict(value)

    def content(self, pos: Cursor) -> str | None:
        """pos 这一格里的宝可梦（面板的名字），没有是 None。"""
        if pos[0] == "out":
            return None
        if pos[0] == "party":
            return self.party[pos[1]]
        return self.box.get((pos[1], pos[2]))

    def set_content(self, pos: Cursor, value: str | None, number: int | None = None) -> None:
        """改 pos 这一格里的内容（盒子里的格子默认是当前盒子，也可以指定盒子编号）。"""
        if pos[0] == "party":
            self.party[pos[1]] = value
            return
        content = self.boxes.setdefault(self.box_number if number is None else number, {})
        if value is None:
            content.pop((pos[1], pos[2]), None)
        else:
            content[(pos[1], pos[2])] = value

    # ---- 按键 ----

    def sync(self) -> None:
        """把 controller.events 里还没处理的操作都处理掉。"""
        events = self.controller.events
        while self._seen < len(events):
            event = events[self._seen]
            self._seen += 1
            kind = event[0]
            if kind == "click":
                self._click(event[1])
            elif kind == "press":
                self.held.add(event[1])
            elif kind == "release":
                self.held.discard(event[1])
            elif kind == "press_stick":
                self.sticks[event[1]] = (event[2], event[3])
            elif kind == "release_stick":
                self.sticks.pop(event[1], None)

    def _move(self, button: str) -> None:
        if self.frozen:
            return
        if self.drop_moves > 0:
            self.drop_moves -= 1
            return
        kind = self.cursor[0]
        if kind == "out":
            if button == "DUP":
                self.cursor = self.back
            return
        if self.out_on_first_move:
            # 第一下就跑到格子外面去了（盒子下面的按钮）
            self.out_on_first_move = False
            self.back = self.cursor
            self.cursor = ("out",)
            return
        if kind == "party":
            i = self.cursor[1]
            if button == "DUP":
                self.cursor = ("party", max(i - 1, 0))
            elif button == "DDOWN":
                self.cursor = ("party", min(i + 1, 5))
            elif button == "DRIGHT":
                if i == 5:
                    # 队伍第 6 格往右是「搜寻」按钮，不是盒子
                    self.back = self.cursor
                    self.cursor = ("out",)
                else:
                    self.cursor = ("box", i, 0)
            return
        r, c = self.cursor[1], self.cursor[2]
        if button == "DUP":
            self.cursor = ("box", max(r - 1, 0), c)
        elif button == "DDOWN":
            self.cursor = ("box", min(r + 1, 4), c)
        elif button == "DRIGHT":
            self.cursor = ("box", r, min(c + 1, 5))
        elif button == "DLEFT":
            self.cursor = ("party", r) if c == 0 else ("box", r, c - 1)

    def _click(self, button: str) -> None:
        if self.swallow.get(button, 0) > 0:
            self.swallow[button] -= 1
            return
        mode = self.mode
        if mode == "overworld":
            if button == "X":
                self.mode = "menu"
            elif button == "PLUS":
                self.riding = not self.riding
        elif mode == "menu":
            if button == "B":
                self.mode = "overworld"
            elif button == "R" and not self.save_fails:
                self.mode = "save_confirm"
            elif button == "DUP":
                self.menu_row = max(self.menu_row - 1, 1)
            elif button == "DDOWN":
                self.menu_row = min(self.menu_row + 1, 2)
            elif button == "A":
                if self.menu_row == 1:
                    self.mode = "box"
                elif not self.picnic_fails:
                    self.mode = "picnic"
        elif mode == "picnic":
            if button == "Y":
                self.mode = "leave_confirm"
        elif mode == "leave_confirm":
            if button == "A":
                self.mode = "overworld"
            elif button == "B":
                self.mode = "picnic"
        elif mode == "save_confirm":
            if button == "A":
                self.mode = "save_done"
            elif button == "B":
                self.mode = "menu"
        elif mode == "save_done" or mode == "flee_dialog":
            if button == "B":
                self.mode = "overworld"
        elif mode == "box":
            if button == "PLUS":
                if not self.judge_stuck:
                    self.judge_page = not self.judge_page
            elif button in ("DUP", "DDOWN", "DLEFT", "DRIGHT"):
                self._move(button)
            elif button in ("R", "L"):
                step = 1 if button == "R" else -1
                self.box_number = (self.box_number - 1 + step) % 32 + 1
            elif button == "B":
                self.mode = "menu"
            elif button == "Y" and self.holding is None and self.content(self.cursor) is not None:
                self.holding = self.content(self.cursor)
                self.origin = self.cursor
                self.origin_box = self.box_number
                self.set_content(self.cursor, None)
            elif button == "A" and self.holding is not None:
                assert self.origin is not None
                self.set_content(self.origin, self.content(self.cursor), self.origin_box)
                self.set_content(self.cursor, self.holding)
                if (
                    self.swap_stores is not None
                    and self.cursor[0] == "box"
                    and self.cursor[1:] == (0, 1)
                ):
                    self.set_content(self.cursor, self.swap_stores)
                self.holding = None
            elif button == "A" and self.content(self.cursor) is not None:
                self.mode = "operation"
                self.downs = 0
        elif mode == "operation":
            if button == "DDOWN":
                self.downs += 1
            elif button == "DUP":
                self.downs -= 1
            elif button == "B":
                self.mode = "box"
            elif button == "A":
                if self.downs == 4:
                    self.mode = "confirm"
                    self.yes = False
                else:
                    self.mode = "box"
        elif mode == "confirm":
            if button == "DUP":
                self.yes = True
            elif button == "DDOWN":
                self.yes = False
            elif button == "A":
                if self.yes:
                    self._release_pokemon()
                    self.mode = "released"
                else:
                    self.mode = "box"
        elif mode == "released":
            if button == "A":
                self.mode = "box"
        elif mode == "battle":
            if button == "DDOWN":
                self.battle_row = min(self.battle_row + 1, 3)
            elif button == "DUP":
                self.battle_row = max(self.battle_row - 1, 0)
            elif button == "A":
                if self.battle_row == 3 and not self.escape_fails:
                    self.escapes += 1
                    self.mode = "flee_dialog" if self.flee_dialog else "overworld"
                self.battle_row = 0
        elif mode == "hatch_dialog":
            if button == "A":
                self.mode = "hatch_anim"
        elif mode == "hatch_anim" and button == "A":
            self.hatched += 1
            if self.hatch_battle:
                self.hatch_battle = False
                self.battle_row = 0
                self.mode = "battle"
            else:
                self.mode = "overworld"
                if self.late_dialog:
                    self.late_countdown = 2

    def _release_pokemon(self) -> None:
        """放生光标所在的格子；队伍里下面的格子往上补。"""
        if self.cursor[0] == "party":
            i = self.cursor[1]
            self.party[i:] = [*self.party[i + 1 :], None]
        else:
            self.set_content(self.cursor, None)

    # ---- 截图 ----

    def render(self) -> bytes:
        """先处理按键，再返回当前状态的截图。"""
        self.sync()
        if self.mode == "overworld":
            circling = "LSTICK" in self.held and "LEFT" in self.sticks and "RIGHT" in self.sticks
            if circling and self.pending:
                self.ticks += 1
                if self.ticks >= self.circle_ticks:
                    self.ticks = 0
                    self.downs = 0
                    event = self.pending.pop(0)
                    self.battle_row = 0
                    self.hatch_battle = event == "hatch_battle"
                    self.mode = "battle" if event == "battle" else "hatch_dialog"
        if self.mode == "overworld":
            if self.late_countdown > 0:
                self.late_countdown -= 1
                if self.late_countdown == 0:
                    return _load("孵化-哦.jpg")
            return _load("野外-骑着.jpg" if self.riding else "野外.jpg")
        if self.mode == "menu":
            return _menu_image(self.menu_row, self.riding)
        if self.mode == "box":
            panel = self.holding if self.holding is not None else self.content(self.cursor)
            eggs = self.paint_eggs | {pos for pos, value in self.box.items() if value == "egg"}
            eggs = frozenset(eggs)
            return _box_image(
                self.cursor,
                panel or "empty",
                self.box_number,
                eggs,
                self.holding is not None,
                self.judge_page,
            )
        if self.mode == "operation":
            return _load("盒子-菜单选中放生.jpg" if self.downs >= 4 else "盒子-操作菜单.jpg")
        if self.mode == "confirm":
            return _load("盒子-放生确认.jpg")
        if self.mode == "released":
            return _load("篮子-没有蛋.jpg")
        if self.mode == "picnic":
            return _load("野餐.jpg")
        if self.mode == "battle":
            return _battle_image(self.battle_row)
        if self.mode in ("save_confirm", "leave_confirm"):
            return _load("结束野餐确认.jpg")
        if self.mode in ("save_done", "flee_dialog"):
            return _load("篮子-没有蛋.jpg")
        if self.mode == "hatch_dialog":
            return _load("孵化-哦.jpg")
        return _load("孵化动画.jpg")


@pytest.fixture
def load_image() -> Callable[[str], bytes]:
    """返回一个函数：传入图片名，返回 tests/images/sv/egg/ 下这张图的 JPEG 字节。"""
    return _load


@pytest.fixture
def checker() -> Callable[[str], ImageChecker]:
    """返回一个函数：传入图片名，返回这张图的 ImageChecker（同一张图只解码一次）。"""

    def make(name: str) -> ImageChecker:
        if name not in _checker_cache:
            _checker_cache[name] = ImageChecker(_load(name))
        return _checker_cache[name]

    return make


@pytest.fixture
def shiny_image() -> bytes:
    """「盒子-爱吃豚-4V.jpg」，闪光区域画了红白相间的棋盘格。"""
    return shiny_panel_image()


@pytest.fixture
def box_image() -> Callable[..., bytes]:
    """返回一个函数：传入光标 ("party", i) 或 ("box", r, c)，和面板的名字
    （parent3、parent4、ditto、other、egg、empty、shiny），可以再传盒子编号（21、22、23）
    和有蛋的格子 (行, 列) 的集合，返回合成的盒子画面。
    """
    return _box_image


@pytest.fixture
def battle_image() -> Callable[[int], bytes]:
    """返回一个函数：传入黄色光标所在的行（0–3），返回战斗菜单的画面。"""
    return _battle_image


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """time.sleep、time.monotonic 换成假的，测试不真的等待。"""
    fake = Clock()
    monkeypatch.setattr(time, "sleep", fake.sleep)
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    return fake


@pytest.fixture
def make_egg(
    tmp_path: Path,
    controller: Any,
    clock: Clock,
    clean_root_logger: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[], bytes]], EggSession]:
    """返回一个函数：传入「每次截图返回图片字节」的函数，返回用假设备建的 EggSession。

    没有内存设备。config 的 log_dir、shiny_dir 指到临时目录，egg_boxes 设成 (21, 22)、flame_box 设成 23、flame_name 设成「啪嘧海胆」，
    interval 改成 0.5 秒（少截几次图）。controller.click 会让假时钟往前走 delay 秒，
    按键超过 MAX_CLICKS 次抛 AssertionError。
    """

    def click(button: str, delay: float = 0.15) -> None:
        controller.pressed.append(button)
        controller.delays.append(delay)
        controller.events.append(("click", button))
        clock.sleep(delay)
        assert len(controller.pressed) <= MAX_CLICKS, "按键太多次，实现停不下来"

    monkeypatch.setattr(controller, "click", click)

    def factory(scene: Callable[[], bytes]) -> EggSession:
        devices = Devices(SceneScreen(scene), controller, None)
        sw = EggSession(load_settings({}), devices)
        sw.config.log_dir = tmp_path / "logs"
        sw.config.shiny_dir = tmp_path / "shinys"
        sw.config.shiny_dir.mkdir()
        # 测试用的盒子编号只有 21、22、23 有真机的标题图片
        sw.config.egg_boxes = (21, 22)
        sw.config.flame_box = 23
        # 真机截图里没有鸭嘴火兽的面板，用啪嘧海胆（盒子-打开.jpg 的面板）当火焰之躯
        sw.config.flame_name = "啪嘧海胆"
        sw.config.wait.interval = 0.5
        return sw

    return factory


@pytest.fixture
def make_world(controller: Any) -> Callable[..., World]:
    """返回一个函数：传入 World 的参数（party 必填），返回和 controller 联动的游戏画面模型。"""

    def factory(**kwargs: Any) -> World:
        return World(controller, **kwargs)

    return factory
