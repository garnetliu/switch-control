"""跨帧读路线图第 2 层，判断地图类型。"""

from .check_image import ImageChecker
from .switch import Switch


class MapTypeReader:
    """跨帧读第 2 层的四个属性标签，读全后按纵向间距判断地图类型。

    每一帧能认几个就记几个；后面的帧补上缺的，并用重叠的列校准镜头位移。
    同一帧里高度差超过一层的，按高度拆成多组。
    seed 里第 2、3 层每列有哪些属性是已知的，用它判断一组标签属于第几层。
    """

    def __init__(self, sw: Switch):
        self._sw = sw
        self._icons = sw.data.type_icons()
        self._allowed: dict[int, list[set[str]]] = {2: [], 3: []}
        if sw.game.maps is not None:
            rentals = sw.data.rental_pokemon()
            for row in (2, 3):
                nodes = sw.game.maps["rows"].get(str(row), [])
                self._allowed[row] = [
                    set(rentals[node["encounter"]]["type_ids"]) for node in nodes
                ]
        self._merged: dict[int, tuple[str, int]] = {}
        self._pending: list[dict[int, tuple[str, int]]] = []

    def update(self, image: ImageChecker) -> str | None:
        """吃一帧画面；四列都读到时返回地图类型，否则返回 None。"""
        height = image.bgr.shape[0]
        for group in self._split_rows(self._read_frame(image), height):
            if self._row_of(group) == 2:
                self._merge(group)
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

    def _read_frame(self, image: ImageChecker) -> dict[int, tuple[str, int]]:
        """这一帧各列匹配度最高的属性和它的纵坐标。"""
        found: dict[int, tuple[str, int]] = {}
        for col, rect in enumerate(self._sw.config.rects.path_second_row):
            best_type = ""
            best_score = -1.0
            best_y = 0
            for type_id, icon in self._icons.items():
                score, location = image.match_template_position(
                    rect,
                    icon,
                    self._sw.config.label_icon_lower,
                    self._sw.config.label_icon_upper,
                )
                if score > best_score:
                    best_type = type_id
                    best_score = score
                    best_y = location[1]
            if best_score < self._sw.config.label_icon_score:
                continue
            found[col] = (best_type, best_y)
        return found

    def _split_rows(
            self, frame: dict[int, tuple[str, int]], height: int
    ) -> list[dict[int, tuple[str, int]]]:
        """同一帧里高度差太大的标签拆成多组，每组是一排。"""
        groups: list[dict[int, tuple[str, int]]] = []
        last_y = None
        gap = self._sw.config.row_max_spread * height
        for col, (type_id, y) in sorted(frame.items(), key=lambda item: item[1][1]):
            if last_y is None or y - last_y > gap:
                groups.append({})
            groups[-1][col] = (type_id, y)
            last_y = y
        return groups

    def _row_of(self, group: dict[int, tuple[str, int]]) -> int | None:
        """用 seed 里各列已知的属性判断这组标签属于第几层。"""
        possible = {2, 3}
        for col, (type_id, _) in group.items():
            possible &= {
                row
                for row in (2, 3)
                if col < len(self._allowed[row]) and type_id in self._allowed[row][col]
            }
            if not possible:
                return None
        return possible.pop() if len(possible) == 1 else None

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
                offsets = sorted(
                    self._merged[col][1] - frame[col][1] for col in shared
                )
                offset = offsets[len(offsets) // 2]
                for col, (type_id, y) in frame.items():
                    self._merged[col] = (type_id, y + offset)
                merged = True
