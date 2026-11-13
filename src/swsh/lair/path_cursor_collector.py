"""岔路口光标坐标：缺坐标时逐列采样，写回 game_config.py 并保存截图。

镜头跟着玩家移动，所以坐标按 (地图类型, 出发节点) 记录：每个出发节点只记它能走到的那几列，
顺序和 next_columns 返回的列一致。量到一次之后写回源码，下次直接使用；还没采的是 ((0, 0), (0, 0))。
采样时用属性标签定位每一列：seed 里每个节点的遭遇宝可梦决定了这一列可能出现的属性。
光标是标签附近的白色箭头，有的列在标签左下、有的在右下，所以光标停在这一列时找出箭头本身，
用它的外框加上边距作为这一列的坐标。

每到岔路口还顺手收集属性图标：这一层可能出现的属性里有还没换成真机抠图的，就从截图上抠下来存好。
"""

import logging
import os
import time
from itertools import product
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

from libs import ImageChecker
from type import Rect

from .switch import LairSwitch

# 第 1 层只有两列，x 区间沿用旧流程的实测值（config/layout.py 的 PATH_RECTS[1]）
_FIRST_ROW_COLUMNS = ((0.28, 0.45), (0.67, 0.84))
# 岔路口找属性标签的纵向范围，和旧流程的 FORK_LABEL_RECT 一致，避开底部文字框
_LABEL_TOP = 0.05
_LABEL_BOTTOM = 0.80
# 下面带「比例」的长度都是占画面高度的比例，横向的也按高度算，用的时候乘上这张图的高度。
# 括号里是 1080 行的画面上量到的像素数。
# 找光标箭头的范围，相对属性图标左上角（x, y）的偏移。真机上箭头在图标左下或右下，
# 离图标左上角横向 -90 到 +150、纵向 +85 到 +160 像素，外框约 64×64 像素
_SEARCH_LEFT = -0.185  # -200
_SEARCH_TOP = 0.037  # 40
_SEARCH_RIGHT = 0.231  # 250
_SEARCH_BOTTOM = 0.213  # 230
# 箭头的白色面积至少是画面高度平方的这么多（500 像素），小的白点不算；
# 宽、高都不超过这么多（110 像素），大块的白色不是箭头
_ARROW_MIN_AREA = 0.00043
_ARROW_MAX_SIZE = 0.102
# 左侧白色的队伍面板右边缘，占画面宽度的比例（260 像素）。找箭头时不看这左边的部分
# （面板和里面的对话气泡都是白色）
_PANEL_RIGHT = 0.135
# 箭头会上下晃动，外框四周再放这么多（20 像素）
_ARROW_MARGIN = 0.0185
# 还没采样的列
_MISSING: Rect = ((0, 0), (0, 0))
# 同一个图标被几个属性模板匹配上时，这个距离内只留分数最高的（40 像素）
_HIT_DISTANCE = 0.037
# 镜头稳定：连续两帧标签位置相差不超过这么多（4 像素）
_STABLE = 0.0037
# 开始采样前先等这么久，排除切界面瞬间的坏帧
_SETTLE_TIMEOUT = 1.5
# 推一次摇杆后等列号变化的最长时间，没变化就当作输入被吞，重推
_MOVE_TIMEOUT = 1.5
# 收集属性图标：最多等这么久认出稳定的一帧；匹配度至少这么高才抠，免得把认错的存下来
_COLLECT_TIMEOUT = 3.0
_COLLECT_SCORE = 0.85


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
    """一帧的检测结果：每列一个标签和光标所在的列。"""

    image: ImageChecker
    hits: tuple[_Hit, ...]
    index: int


class PathCursorCollector:
    """岔路口的光标区域：还没收集时移动光标逐列采样。"""

    def __init__(self, sw: LairSwitch):
        self._sw = sw
        self._icons = sw.data.type_icons()
        self._maps = sw.game.maps
        self._stamp = time.strftime("%Y%m%d-%H%M%S")
        self._first: ImageChecker | None = None
        self._last: ImageChecker | None = None
        self._failed = False
        self._directory = sw.config.keep_dir
        self._map_type = ""
        self._row = 0
        self._allowed: list[set[str]] = []
        self._bands: list[Rect] = []

    def ensure(self, start: tuple[int, int], columns: tuple[int, ...]) -> tuple[Rect, ...]:
        """从 start 节点出发、能走到的 columns 这几列的光标区域，顺序和 columns 一致。

        还没采样的列现场采样，写回 game_config.py。
        """
        maps = self._maps
        if maps is None or maps["type"] is None:
            raise RuntimeError("还没读出地图类型，没法收集岔路口光标坐标")
        map_type = maps["type"]
        row = start[0] + 1
        nodes = maps["rows"].get(str(row), [])
        if not nodes:
            raise RuntimeError(f"seed 里没有第 {row} 层的节点")
        self._map_type, self._row = map_type, row
        self._allowed = self._allowed_types(nodes)
        self._bands = self._column_bands(row, len(nodes))
        self._collect_icons()
        known = list(self._sw.config.rects.path_cursors[map_type][start])
        missing = tuple(column for column, rect in zip(columns, known) if rect == _MISSING)
        if missing:
            logging.info(
                f"岔路口 {map_type} 从 {start} 出发，第 {row} 层第 {[c + 1 for c in missing]} 列"
                "的光标坐标还没收集，开始采样"
            )
            try:
                collected = self._collect(missing)
            except TimeoutError:
                raise
            except Exception:
                self._save_failure("error")
                raise
            for index, column in enumerate(columns):
                if column in collected:
                    known[index] = collected[column]
            self._sw.config.rects.path_cursors[map_type][start] = tuple(known)
            self._save_source()
            logging.info(f"岔路口 {map_type} 从 {start} 出发的光标坐标: {tuple(known)}")
        return tuple(known)

    def _collect_icons(self) -> None:
        """这一层可能出现的属性里还有没换成真机抠图的，就趁岔路口画面静止时从截图上抠下来。

        认不出稳定的一帧就算了，下次到岔路口再收集，不影响后面移动光标。
        """
        data = self._sw.data
        wanted = set().union(*self._allowed) - data.collected_type_icons()
        if not wanted:
            return
        frame = self._steady_frame(_COLLECT_TIMEOUT)
        if frame is None:
            logging.info(f"岔路口没认出稳定的一帧，这次不收集属性图标（还缺 {sorted(wanted)}）")
            return
        for hit in frame.hits:
            if hit.type_id not in wanted or hit.score < _COLLECT_SCORE:
                continue
            height, width = self._icons[hit.type_id].shape[:2]
            area = frame.image.bgr[hit.y : hit.y + height, hit.x : hit.x + width]
            icon = cv2.inRange(
                cv2.cvtColor(area, cv2.COLOR_BGR2HSV),
                self._sw.config.label_icon_lower,
                self._sw.config.label_icon_upper,
            )
            data.save_type_icon(hit.type_id, icon)
            wanted.discard(hit.type_id)
            logging.info(
                f"收集到 {hit.type_id} 的属性图标（匹配度 {hit.score:.3f}），"
                f"已有 {len(data.collected_type_icons())}/{len(self._icons)}"
            )

    def _steady_frame(self, timeout: float) -> _Frame | None:
        """在 timeout 秒里等连续两帧的标签类型和位置都一致，返回后一帧；等不到返回 None。"""
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            frame = self._read_frame(self._capture())
            if frame is not None and previous is not None and _same(previous, frame):
                return frame
            previous = frame
            time.sleep(self._sw.config.interval)
        return None

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
            columns = self._sw.config.rects.path_columns
        if len(columns) != count:
            raise RuntimeError(f"第 {row} 层有 {count} 个节点，但标签搜索区间是 {len(columns)} 列")
        return [((left, _LABEL_TOP), (right, _LABEL_BOTTOM)) for left, right in columns]

    def _collect(self, columns: tuple[int, ...]) -> dict[int, Rect]:
        """光标逐个移到 columns 里的列，每列找出箭头的外框。"""
        frame = self._prepare()
        rects = {}
        for target in columns:
            frame = self._move_to(target, frame)
            self._save_column(frame.image, target)
            hit = frame.hits[target]
            rect = self._cursor_rect(frame.image, hit)
            if rect is None:
                raise RuntimeError(f"第 {target + 1} 列的光标在，但找不到箭头的外框")
            rects[target] = rect
            logging.info(
                f"岔路口 {self._map_type} 第 {self._row} 层第 {target + 1} 列:"
                f" {hit.type_id}，白色 {hit.white:.3f}，光标 {rect}"
            )
        return rects

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
            marked = [index for index, hit in enumerate(combo) if hit.white > 0]
            if len(marked) != 1:
                continue
            key = (spread, -sum(hit.score for hit in combo))
            if best is None or key < best[0]:
                best = (key, combo, marked[0])
        if best is None:
            return None
        _, combo, index = best
        return _Frame(image, tuple(combo), index)

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
        distance = _HIT_DISTANCE * height
        hits: list[_Hit] = []
        for score, x, y, type_id in sorted(candidates, reverse=True):
            if any(abs(x - hit.x) <= distance and abs(y - hit.y) <= distance for hit in hits):
                continue
            hits.append(_Hit(type_id, score, x, y, self._white(image, x, y)))
        return hits

    def _white(self, image: ImageChecker, x: int, y: int) -> float:
        """属性图标附近箭头的白色占比；没有箭头时是 0。"""
        arrow = self._arrow(image, x, y)
        if arrow is None:
            return 0.0
        height, width = image.bgr.shape[:2]
        (left, top), (right, bottom) = _search_region(x, y, width, height)
        area = (right - left) * width * (bottom - top) * height
        return float(arrow[4]) / area

    def _cursor_rect(self, image: ImageChecker, hit: _Hit) -> Rect | None:
        """属性图标附近的箭头外框加边距，比例坐标；找不到箭头返回 None。"""
        arrow = self._arrow(image, hit.x, hit.y)
        if arrow is None:
            return None
        left, top, width, height, _ = arrow
        screen_height, screen_width = image.bgr.shape[:2]
        margin = round(_ARROW_MARGIN * screen_height)
        return _pixel_rect(
            left - margin,
            top - margin,
            left + width + margin,
            top + height + margin,
            screen_width,
            screen_height,
        )

    def _arrow(self, image: ImageChecker, x: int, y: int) -> tuple[int, int, int, int, int] | None:
        """属性图标附近箭头大小的白块里面积最大的一块：(左, 上, 宽, 高, 面积)，像素坐标。"""
        screen_height, screen_width = image.bgr.shape[:2]
        region = _search_region(x, y, screen_width, screen_height)
        mask = cv2.inRange(
            image.crop(region, "hsv"),
            self._sw.config.cursor_white_lower,
            self._sw.config.cursor_white_upper,
        )
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        blobs = [
            stats[i]
            for i in range(1, count)
            if stats[i][4] >= _ARROW_MIN_AREA * screen_height**2
            and stats[i][2] <= _ARROW_MAX_SIZE * screen_height
            and stats[i][3] <= _ARROW_MAX_SIZE * screen_height
        ]
        if not blobs:
            return None
        left, top, width, height, area = (int(v) for v in max(blobs, key=lambda blob: blob[4]))
        x0 = round(region[0][0] * screen_width)
        y0 = round(region[0][1] * screen_height)
        return x0 + left, y0 + top, width, height, area

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
        """按 game_config.py 里的缩进生成 path_cursors 的源码，行尾注释写这一组是第几排的哪几列。"""
        from .next_columns import next_columns

        lines = ["    path_cursors: ClassVar[dict[str, PathCursors]] = {\n"]
        for map_type, starts in self._sw.config.rects.path_cursors.items():
            lines.append(f'        "{map_type}": PathCursors({{\n')
            for start, rects in starts.items():
                columns = ", ".join(str(c) for c in next_columns(map_type, *start))
                lines.append(f"            {start}: (  # 第 {start[0] + 1} 排第 {columns} 列\n")
                lines.extend(f"                {rect!r},\n" for rect in rects)
                lines.append("            ),\n")
            lines.append("        }),\n")
        lines.append("    }\n")
        return lines


def _search_region(x: int, y: int, width: int, height: int) -> Rect:
    """属性图标左上角附近找光标箭头的范围，比例坐标。左边不超过队伍面板。width、height 是截图的大小。"""
    return _pixel_rect(
        max(x + round(_SEARCH_LEFT * height), round(_PANEL_RIGHT * width)),
        y + round(_SEARCH_TOP * height),
        x + round(_SEARCH_RIGHT * height),
        y + round(_SEARCH_BOTTOM * height),
        width,
        height,
    )


def _pixel_rect(left: int, top: int, right: int, bottom: int, width: int, height: int) -> Rect:
    """像素坐标转成比例坐标，超出画面的部分截掉，保留 4 位小数。width、height 是截图的大小。"""
    return (
        (round(max(left, 0) / width, 4), round(max(top, 0) / height, 4)),
        (round(min(right, width) / width, 4), round(min(bottom, height) / height, 4)),
    )


def _same(first: _Frame, second: _Frame) -> bool:
    """两帧的标签类型顺序和位置都几乎一样。"""
    if first.index != second.index or len(first.hits) != len(second.hits):
        return False
    stable = max(round(_STABLE * second.image.bgr.shape[0]), 1)
    return all(
        before.type_id == after.type_id
        and abs(before.x - after.x) <= stable
        and abs(before.y - after.y) <= stable
        for before, after in zip(first.hits, second.hits)
    )
