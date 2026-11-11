"""跨帧读路线图第 2 层，判断地图类型。"""

import cv2

from type import Rect

from .check_image import ImageChecker
from .switch import Switch


class MapTypeReader:
    """跨帧读第 2 层的四个属性标签，读全后按纵向间距判断地图类型。

    每一帧能认几个就记几个；后面的帧补上缺的，并用重叠的列校准镜头位移。
    每一列的区域里同时能看到第 2、3 层的标签，所以一列里所有过线的标签都要找出来。
    seed 里第 2、3 层每列有哪些属性是已知的，用它逐个判断标签属于第几层。
    """

    # 一列里最多找几个标签：第 1、2、3 层
    MAX_LABELS_PER_COLUMN = 3

    def __init__(self, sw: Switch):
        self._sw = sw
        self._icons = sw.data.type_icons()
        self._allowed: dict[int, list[set[str]]] = {2: [], 3: []}
        if sw.game.maps is not None:
            rentals = sw.data.rental_pokemon()
            for row in (2, 3):
                nodes = sw.game.maps["rows"].get(str(row), [])
                self._allowed[row] = [set(rentals[node["encounter"]]["type_ids"]) for node in nodes]
        self._merged: dict[int, tuple[str, int]] = {}
        self._pending: list[dict[int, tuple[str, int]]] = []

    def update(self, image: ImageChecker) -> str | None:
        """吃一帧画面；四列都读到时返回地图类型，否则返回 None。"""
        height = image.bgr.shape[0]
        self._merge(self._second_row(self._read_frame(image), height))
        if len(self._merged) < 4:
            return None
        ys = [y for _, y in self._merged.values()]
        if max(ys) - min(ys) > self._sw.config.row_max_spread * height:
            return None
        spread = max(ys) - min(ys)
        closest = min(
            self._sw.config.path_types,
            key=lambda standard: abs(standard - spread),
        )
        return self._sw.config.path_types[closest]

    def _read_frame(self, image: ImageChecker) -> list[tuple[int, str, int]]:
        """这一帧每一列里所有过线的标签：(列, 属性, 纵坐标)。

        纵坐标是相对列区域顶边的像素，四列的区域顶边一样，可以直接比较。
        """
        labels = []
        for col, rect in enumerate(self._sw.config.rects.path_second_row):
            for type_id, y in self._find_labels(image, rect):
                labels.append((col, type_id, y))
        return labels

    def _find_labels(self, image: ImageChecker, rect: Rect) -> list[tuple[str, int]]:
        """区域里所有过线的标签：(属性, 相对区域顶边的纵坐标)，按匹配度从高到低。

        每个属性图标只匹配一次，从匹配结果里取出多个峰值：取一个最高点，把它上下一个图标高度内
        的结果清掉，再取下一个。不同属性在同一高度上都过线时，留匹配度高的那个。
        """
        config = self._sw.config
        area = cv2.inRange(
            image.crop(rect, "hsv"), config.label_icon_lower, config.label_icon_upper
        )
        candidates: list[tuple[float, str, int, int]] = []
        for type_id, icon in self._icons.items():
            icon_height = icon.shape[0]
            if area.shape[0] < icon_height or area.shape[1] < icon.shape[1]:
                continue
            result = cv2.matchTemplate(area, icon, cv2.TM_CCOEFF_NORMED)
            for _ in range(self.MAX_LABELS_PER_COLUMN):
                _, score, _, location = cv2.minMaxLoc(result)
                if score < config.label_icon_score:
                    break
                y = int(location[1])
                candidates.append((float(score), type_id, y, icon_height))
                result[max(0, y - icon_height) : y + icon_height + 1, :] = -1.0
        found: list[tuple[str, int, int]] = []
        for _, type_id, y, icon_height in sorted(candidates, reverse=True):
            if all(abs(y - other) > icon_height for _, other, _ in found):
                found.append((type_id, y, icon_height))
            if len(found) == self.MAX_LABELS_PER_COLUMN:
                break
        return [(type_id, y) for type_id, y, _ in found]

    def _second_row(
        self, labels: list[tuple[int, str, int]], height: int
    ) -> dict[int, tuple[str, int]]:
        """从这一帧的标签里挑出第 2 层的：{列: (属性, 纵坐标)}。

        先按 seed 里这一列第 2、3 层允许的属性逐个判断层号；两层都可能的，
        看它离已经确定的哪一层更近（同一层的高度差不超过 row_max_spread）；
        哪层都不可能或者判断不了的，只丢这一个标签。
        """
        gap = self._sw.config.row_max_spread * height
        known: dict[int, list[int]] = {2: [], 3: []}
        unsure: list[tuple[int, str, int]] = []
        rows: list[tuple[int, int, str, int]] = []
        for col, type_id, y in labels:
            possible = {
                row
                for row in (2, 3)
                if col < len(self._allowed[row]) and type_id in self._allowed[row][col]
            }
            if len(possible) == 1:
                row = possible.pop()
                known[row].append(y)
                rows.append((row, col, type_id, y))
            elif possible:
                unsure.append((col, type_id, y))
        for col, type_id, y in unsure:
            near = [
                row
                for row in (2, 3)
                if known[row] and abs(y - sorted(known[row])[len(known[row]) // 2]) <= gap
            ]
            if len(near) == 1:
                rows.append((near[0], col, type_id, y))
        second = [(col, type_id, y) for row, col, type_id, y in rows if row == 2]
        if not second:
            return {}
        # 同一列有两个都判成第 2 层时，留离第 2 层中间高度最近的
        ys = sorted(y for _, _, y in second)
        middle = ys[len(ys) // 2]
        frame: dict[int, tuple[str, int]] = {}
        for col, type_id, y in second:
            # 离第 2 层中间高度太远的，多半是别的层读错了属性，不要
            if abs(y - middle) > gap:
                continue
            if col not in frame or abs(y - middle) < abs(frame[col][1] - middle):
                frame[col] = (type_id, y)
        return frame

    def _merge(self, frame: dict[int, tuple[str, int]]) -> None:
        """把这一帧并进累计结果，用重叠的列计算镜头移动的偏移。"""
        if not frame:
            return
        if not self._merged:
            self._merged = dict(frame)
            self._merge_pending()
            return
        shared = set(frame) & set(self._merged)
        if not shared:
            self._pending.append(frame)
            return
        offsets = sorted(self._merged[col][1] - frame[col][1] for col in shared)
        offset = offsets[len(offsets) // 2]
        for col, (type_id, y) in frame.items():
            self._merged[col] = (type_id, y + offset)
        self._merge_pending()

    def _merge_pending(self) -> None:
        """累计结果更新后，把能和它对齐的待合并帧并进来。"""
        merged = True
        while merged:
            merged = False
            for frame in list(self._pending):
                shared = set(frame) & set(self._merged)
                if not shared:
                    continue
                self._pending.remove(frame)
                offsets = sorted(self._merged[col][1] - frame[col][1] for col in shared)
                offset = offsets[len(offsets) // 2]
                for col, (type_id, y) in frame.items():
                    self._merged[col] = (type_id, y + offset)
                merged = True
