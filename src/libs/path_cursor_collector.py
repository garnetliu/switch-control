"""岔路口光标坐标：缺坐标时逐列采样，写回 game_config.py 并保存截图。

地图类型和层号决定路线图上节点的位置，所以坐标按 (地图类型, 层号) 记录，
一局里量到一次之后写回源码，下次直接使用。采样时用属性标签定位每一列：
seed 里每个节点的遭遇宝可梦决定了这一列可能出现的属性，标签正下方的白色箭头就是光标。
"""

import logging
import os
import time
from itertools import product
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

from type import Rect

from .check_image import ImageChecker
from .switch import Switch

# 第 1 层只有两列，x 区间沿用旧流程的实测值（config/layout.py 的 PATH_RECTS[1]）
_FIRST_ROW_COLUMNS = ((0.28, 0.45), (0.67, 0.84))
# 岔路口找属性标签的纵向范围，和旧流程的 FORK_LABEL_RECT 一致，避开底部文字框
_LABEL_TOP = 0.05
_LABEL_BOTTOM = 0.80
# 光标区域相对属性图标左上角（x, y）的偏移，旧流程真机实测：光标在图标下方 60 到 180 像素
_CURSOR_LEFT = -60
_CURSOR_TOP = 60
_CURSOR_RIGHT = 160
_CURSOR_BOTTOM = 180
# 截图统一缩放到这个尺寸，偏移量按它量出来
_SCREEN_WIDTH = 1920
_SCREEN_HEIGHT = 1080
# 同一个图标被几个属性模板匹配上时，这个像素距离内只留分数最高的
_HIT_DISTANCE = 40
# 镜头稳定：连续两帧标签位置相差不超过这么多像素
_STABLE_PIXELS = 4
# 开始采样前先等这么久，排除切界面瞬间的坏帧
_SETTLE_TIMEOUT = 1.5
# 推一次摇杆后等列号变化的最长时间，没变化就当作输入被吞，重推
_MOVE_TIMEOUT = 1.5
# 截图目录，和 logs/catches 同级
_LOG_DIRECTORY = "path_cursors"


class _Hit(NamedTuple):
    """一列里的一个属性标签候选。"""

    type_id: str
    score: float
    # 图标左上角在整张截图上的像素坐标
    x: int
    y: int
    # 图标下方光标区域的白色占比
    white: float


class _Frame(NamedTuple):
    """一帧的检测结果：每列一个标签、光标列和每列的光标区域。"""

    image: ImageChecker
    hits: tuple[_Hit, ...]
    index: int
    rects: tuple[Rect, ...]


class PathCursorCollector:
    """岔路口的光标区域：还没收集时移动光标逐列采样。"""

    def __init__(self, sw: Switch):
        self._sw = sw
        self._icons = sw.data.type_icons()
        self._maps = sw.game.maps
        self._stamp = time.strftime("%Y%m%d-%H%M%S")
        self._first: ImageChecker | None = None
        self._last: ImageChecker | None = None
        self._failed = False
        self._directory = sw.config.log_dir / _LOG_DIRECTORY
        self._map_type = ""
        self._row = 0
        self._allowed: list[set[str]] = []
        self._bands: list[Rect] = []

    def ensure(self, row: int) -> tuple[Rect, ...]:
        """返回这一层各列的光标区域；还没收集就现场采样并写回 game_config.py。"""
        maps = self._maps
        if maps is None or maps["type"] is None:
            raise RuntimeError("还没读出地图类型，没法收集岔路口光标坐标")
        map_type = maps["type"]
        nodes = maps["rows"].get(str(row), [])
        if not nodes:
            raise RuntimeError(f"seed 里没有第 {row} 层的节点")
        rects = self._sw.config.rects.path_cursors[map_type][row]
        if rects:
            return rects

        self._map_type, self._row = map_type, row
        self._allowed = self._allowed_types(nodes)
        self._bands = self._column_bands(row, len(nodes))
        logging.info(f"岔路口 {map_type} 第 {row} 层的光标坐标还没收集，开始逐列采样")
        try:
            rects = self._collect()
        except TimeoutError:
            raise
        except Exception:
            self._save_failure("error")
            raise
        self._sw.config.rects.path_cursors[map_type][row] = rects
        self._save_source()
        logging.info(f"岔路口 {map_type} 第 {row} 层的光标坐标: {rects}")
        return rects

    def _allowed_types(self, nodes: list) -> list[set[str]]:
        """每列可能出现的属性。双属性宝可梦在地图上显示哪个属性不确定，所以用集合。"""
        rentals = self._sw.data.rental_pokemon()
        allowed = []
        for node in nodes:
            rental = rentals.get(node["encounter"])
            types = set(rental["type_ids"]) if rental is not None else set()
            if not types:
                logging.warning(f"数据里没有 {node['encounter']}，按 {node['type']} 认标签")
                types = {node["type"]}
            allowed.append(types)
        return allowed

    def _column_bands(self, row: int, count: int) -> list[Rect]:
        """每一列找属性标签的范围。"""
        if row == 1:
            columns = _FIRST_ROW_COLUMNS
        else:
            columns = [(rect[0][0], rect[1][0]) for rect in self._sw.config.rects.path_second_row]
        if len(columns) != count:
            raise RuntimeError(f"第 {row} 层有 {count} 个节点，但标签搜索区间是 {len(columns)} 列")
        return [((left, _LABEL_TOP), (right, _LABEL_BOTTOM)) for left, right in columns]

    def _collect(self) -> tuple[Rect, ...]:
        """从左到右逐列采样，返回最终那一帧的每列光标区域。"""
        frame = self._prepare()
        for target in range(len(self._allowed)):
            frame = self._move_to(target, frame)
            self._save_column(frame.image, target)
            hit = frame.hits[target]
            logging.info(
                f"岔路口 {self._map_type} 第 {self._row} 层第 {target + 1} 列:"
                f" {hit.type_id}，白色 {hit.white:.3f}"
            )
        final = self._wait_stable(frame)
        return _round_rects(final.rects)

    def _prepare(self) -> _Frame:
        """等出一帧能认全标签和光标的画面；看不到标签时推右摇杆把镜头带回岔路口。"""
        deadline = time.monotonic() + _SETTLE_TIMEOUT
        frame = None
        while time.monotonic() < deadline:
            frame = self._read_frame(self._capture())
            if frame is not None:
                break
            time.sleep(self._sw.config.interval)
        if frame is None:
            logging.info("岔路口看不到这一层的属性标签，右摇杆往下推")
            self._sw.press_stick("RIGHT", 0, -self._sw.config.stick_max)
            try:
                frame = self._wait_frame(
                    self._sw.config.timeout,
                    f"岔路口 {self._map_type} 第 {self._row} 层的属性标签和光标",
                )
            finally:
                self._sw.release_stick("RIGHT")
        return self._wait_stable(frame)

    def _move_to(self, target: int, frame: _Frame) -> _Frame:
        """把光标移到 target 列，返回目标列稳定后的一帧。"""
        deadline = time.monotonic() + self._sw.config.timeout
        while True:
            if frame.index == target:
                stable = self._wait_stable(frame)
                if stable.index == target:
                    return stable
                frame = stable
                continue
            direction = 1 if target > frame.index else -1
            self._sw.stick(
                "LEFT", direction * self._sw.config.stick_max, 0, self._sw.config.stick_tick
            )
            moved = self._wait_change(frame.index, _MOVE_TIMEOUT)
            if moved is not None:
                frame = moved
                continue
            if time.monotonic() >= deadline:
                self._save_failure("timeout")
                raise TimeoutError(f"岔路口光标从第 {frame.index + 1} 列移到第 {target + 1} 列超时")

    def _read_frame(self, image: ImageChecker) -> _Frame | None:
        """这一帧每列的属性标签和光标列；认不全或者不唯一时返回 None。"""
        columns = [
            self._hits(image, band, allowed) for band, allowed in zip(self._bands, self._allowed)
        ]
        if any(not column for column in columns):
            return None
        height = image.bgr.shape[0]
        max_spread = self._sw.config.row_max_spread * height
        best: tuple[tuple[float, float], tuple[_Hit, ...], int] | None = None
        for combo in product(*columns):
            ys = [hit.y for hit in combo]
            spread = max(ys) - min(ys)
            if spread > max_spread:
                continue
            marked = [
                index
                for index, hit in enumerate(combo)
                if hit.white > self._sw.config.cursor_white_ratio
            ]
            if len(marked) != 1:
                continue
            key = (spread, -sum(hit.score for hit in combo))
            if best is None or key < best[0]:
                best = (key, combo, marked[0])
        if best is None:
            return None
        _, combo, index = best
        return _Frame(
            image,
            tuple(combo),
            index,
            tuple(_below_label(hit.x, hit.y) for hit in combo),
        )

    def _hits(self, image: ImageChecker, band: Rect, allowed: set[str]) -> list[_Hit]:
        """这一列里所有可能的属性标签，每个都算上光标区域的白色占比。"""
        mask = cv2.inRange(
            image.crop(band, "hsv"),
            self._sw.config.label_icon_lower,
            self._sw.config.label_icon_upper,
        )
        height, width = image.bgr.shape[:2]
        x0, y0 = round(band[0][0] * width), round(band[0][1] * height)
        candidates = []
        for type_id in sorted(allowed):
            icon = self._icons.get(type_id)
            if icon is None:
                continue
            if mask.shape[0] < icon.shape[0] or mask.shape[1] < icon.shape[1]:
                continue
            result = cv2.matchTemplate(mask, icon, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(result >= self._sw.config.label_icon_score)
            candidates.extend(
                (float(result[y, x]), x0 + int(x), y0 + int(y), type_id) for y, x in zip(ys, xs)
            )
        # 同一位置被几个属性模板匹配上时只留分数最高的
        hits: list[_Hit] = []
        for score, x, y, type_id in sorted(candidates, reverse=True):
            if any(
                abs(x - hit.x) <= _HIT_DISTANCE and abs(y - hit.y) <= _HIT_DISTANCE for hit in hits
            ):
                continue
            hits.append(_Hit(type_id, score, x, y, self._white(image, x, y)))
        return hits

    def _white(self, image: ImageChecker, x: int, y: int) -> float:
        """属性图标正下方区域的白色占比，有光标时明显超过阈值。"""
        return image.color_ratio(
            _below_label(x, y),
            self._sw.config.cursor_white_lower,
            self._sw.config.cursor_white_upper,
        )

    def _capture(self) -> ImageChecker:
        image = ImageChecker(self._sw.pixel_peek())
        self._first = self._first or image
        self._last = image
        return image

    def _wait_frame(self, timeout: float, what: str) -> _Frame:
        """反复截图直到认出一帧，超时存下首末帧并抛 TimeoutError。"""
        deadline = time.monotonic() + timeout
        while True:
            frame = self._read_frame(self._capture())
            if frame is not None:
                return frame
            if time.monotonic() >= deadline:
                self._save_failure("timeout")
                raise TimeoutError(f"等了 {timeout} 秒，{what}")
            time.sleep(self._sw.config.interval)

    def _wait_stable(self, frame: _Frame) -> _Frame:
        """等连续两帧的标签类型和位置都一致，返回后一帧。"""
        deadline = time.monotonic() + self._sw.config.timeout
        while True:
            current = self._read_frame(self._capture())
            if current is not None:
                if _same(frame, current):
                    return current
                frame = current
            if time.monotonic() >= deadline:
                self._save_failure("timeout")
                raise TimeoutError(f"等了 {self._sw.config.timeout} 秒，岔路口标签的位置还不稳定")
            time.sleep(self._sw.config.interval)

    def _wait_change(self, before: int, timeout: float) -> _Frame | None:
        """等光标离开 before 列；超时还在原来那一列时返回 None。"""
        deadline = time.monotonic() + timeout
        while True:
            frame = self._read_frame(self._capture())
            if frame is not None and frame.index != before:
                return frame
            if time.monotonic() >= deadline:
                return None
            time.sleep(self._sw.config.interval)

    def _save_column(self, image: ImageChecker, column: int) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / (f"{self._stamp}-{self._map_type}-row{self._row}-col{column}.jpg")
        image.save(str(path))
        logging.info(f"岔路口光标截图: {path}")

    def _save_failure(self, kind: str) -> None:
        """超时或出错时把开始和最后一帧存下来，同一组截图只存一次。"""
        if self._failed or self._first is None or self._last is None:
            return
        self._failed = True
        self._directory.mkdir(parents=True, exist_ok=True)
        for name, image in (("first", self._first), ("last", self._last)):
            path = self._directory / (
                f"{self._stamp}-{self._map_type}-row{self._row}-{kind}-{name}.jpg"
            )
            image.save(str(path))
            logging.warning(f"{kind} 截图: {path}")

    def _save_source(self) -> None:
        """把 path_cursors 写回 game_config.py，下次启动直接读出来。"""
        path = Path(__file__).with_name("game_config.py")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if line.startswith("    path_cursors: ClassVar[")
            ),
            None,
        )
        end = next(
            (
                index
                for index in range((start or 0) + 1, len(lines))
                if lines[index].rstrip("\n") == "    }"
            ),
            None,
        )
        if start is None or end is None:
            logging.warning(f"{path} 里找不到 path_cursors，坐标没有写回文件")
            return
        lines[start : end + 1] = self._format_cursors()
        temp = path.with_suffix(".tmp")
        temp.write_text("".join(lines), encoding="utf-8")
        os.replace(temp, path)
        logging.info(f"光标坐标已写回 {path}")

    def _format_cursors(self) -> list[str]:
        """按 game_config.py 里的缩进生成 path_cursors 的源码。"""
        lines = ["    path_cursors: ClassVar[dict[str, dict[int, tuple[Rect, ...]]]] = {\n"]
        for map_type, rows in self._sw.config.rects.path_cursors.items():
            lines.append(f'        "{map_type}": {{\n')
            for row in sorted(rows):
                rects = rows[row]
                if not rects:
                    lines.append(f"            {row}: _EMPTY_CURSORS,\n")
                    continue
                lines.append(f"            {row}: (\n")
                lines.extend(f"                {rect!r},\n" for rect in rects)
                lines.append("            ),\n")
            lines.append("        },\n")
        lines.append("    }\n")
        return lines


def _below_label(x: int, y: int) -> Rect:
    """属性图标左上角正下方光标出现的区域，比例坐标。"""
    return (
        (max(x + _CURSOR_LEFT, 0) / _SCREEN_WIDTH, (y + _CURSOR_TOP) / _SCREEN_HEIGHT),
        (
            min(x + _CURSOR_RIGHT, _SCREEN_WIDTH) / _SCREEN_WIDTH,
            (y + _CURSOR_BOTTOM) / _SCREEN_HEIGHT,
        ),
    )


def _same(first: _Frame, second: _Frame) -> bool:
    """两帧的标签类型顺序和位置都几乎一样。"""
    if first.index != second.index or len(first.hits) != len(second.hits):
        return False
    return all(
        before.type_id == after.type_id
        and abs(before.x - after.x) <= _STABLE_PIXELS
        and abs(before.y - after.y) <= _STABLE_PIXELS
        for before, after in zip(first.hits, second.hits)
    )


def _round_rects(rects: tuple[Rect, ...]) -> tuple[Rect, ...]:
    """坐标保留 4 位小数，写回源码时不出现一长串浮点数。"""
    return tuple(
        (
            (round(rect[0][0], 4), round(rect[0][1], 4)),
            (round(rect[1][0], 4), round(rect[1][1], 4)),
        )
        for rect in rects
    )
