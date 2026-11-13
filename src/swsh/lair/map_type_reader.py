"""读路线图第 2 层，判断地图类型。"""

import cv2

from libs import ImageChecker
from type import Rect

from .switch import LairSwitch


class MapTypeReader:
    """在一帧里读全第 2 层的四个属性标签，按纵向间距判断地图类型。

    镜头移动很快，一帧识别得越久截到的帧越少，所以分两步找：
    先只在最左一列找标签，上下找满整个画面；找到了，再以它的高度为准，
    在往上 label_rise、往下 label_drop（占画面高度的比例）的一条里找另外三列。四列都是第 2 层的才算数，只看这一帧，不跨帧累计。
    seed 里第 2、3 层每列有哪些属性是已知的，用它逐个判断标签属于第几层。
    """

    # 一列里最多找几个标签：第 1、2、3 层
    MAX_LABELS_PER_COLUMN = 3

    def __init__(self, sw: LairSwitch):
        self._sw = sw
        self._icons = sw.data.type_icons()
        self._icon_height = max(int(icon.shape[0]) for icon in self._icons.values())
        self._allowed: dict[int, list[set[str]]] = {2: [], 3: []}
        if sw.game.maps is not None:
            rentals = sw.data.rental_pokemon()
            for row in (2, 3):
                nodes = sw.game.maps["rows"].get(str(row), [])
                self._allowed[row] = [set(rentals[node["encounter"]]["type_ids"]) for node in nodes]
        # 读出地图类型的那一帧实际找标签的范围：最左一列，加上另外三列的窄条；存判定截图时画出来
        self.rects: tuple[Rect, ...] = ()

    def update(self, image: ImageChecker) -> str | None:
        """吃一帧画面；这一帧里第 2 层四列都读到时返回地图类型，否则返回 None。"""
        config = self._sw.config
        height = image.bgr.shape[0]
        columns = config.rects.path_columns
        rise = round(config.label_rise * height)
        drop = round(config.label_drop * height)
        left, right = config.rects.path_first_column
        first: Rect = ((left, 0.0), (right, 1.0))
        for type_id, y in self._find_labels(image, first):
            top = max(y - rise, 0)
            bottom = min(y + drop + self._icon_height, height)
            labels = [(0, type_id, y)]
            strips: list[Rect] = []
            for col, (left, right) in enumerate(columns[1:], start=1):
                rect = ((left, top / height), (right, bottom / height))
                strips.append(rect)
                labels.extend(
                    (col, other, top + y2) for other, y2 in self._find_labels(image, rect)
                )
            second = self._second_row(labels, height)
            if len(second) < 4:
                continue
            self.rects = (first, *strips)
            ys = [y for _, y in second.values()]
            spread = (max(ys) - min(ys)) / height
            closest = min(config.path_types, key=lambda standard: abs(standard - spread))
            return config.path_types[closest]
        return None

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
