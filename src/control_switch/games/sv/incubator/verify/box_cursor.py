from collections.abc import Sequence

import cv2
import numpy as np

from control_switch.types import Rect
from control_switch.vision import ImageChecker

from ..config import IncubatorConfig
from ..types import Cursor


def box_cursor(image: ImageChecker, config: IncubatorConfig) -> Cursor:
    """盒子画面里光标在哪：队伍返回 ("party", 行, 0)，盒子返回 ("slots", 行, 列)，
    格子外面返回 ("other", 第几个, 0)（0 盒子名、1「一览」、2「搜寻」）。盒子画面里一定有箭头，找不到抛 RuntimeError。

    光标是一个黄绿色渐变到青色的向下箭头，所有能停的位置都是固定的。每个位置框住箭头上下晃动的整个范围，
    看哪个框里箭头黄绿色那一段的像素最多。格子本身选中时的黄色色相比箭头低，不算进去。
    箭头下半截是青色，框里也要有青色才算，野外画面上的黄绿色没有青色；
    而且青色要在黄绿色下面，盒子操作菜单里向右的箭头（黄绿在左、青在右）落在格子上时不算。
    """
    # 坐标都是占画面宽高的比例。每个框包住箭头上下晃动的整个范围；
    # 盒子相邻两格横向隔 0.0656、纵向隔 0.1167，队伍每一行和盒子每一行一样高
    party: Sequence[Rect] = [
        ((0.1461, 0.1722 + 0.1167 * row), (0.1836, 0.2403 + 0.1167 * row))
        for row in range(config.party_rows)
    ]
    slots: Sequence[Sequence[Rect]] = [
        [
            (
                (0.2469 + 0.0656 * col, 0.1722 + 0.1167 * row),
                (0.2844 + 0.0656 * col, 0.2403 + 0.1167 * row),
            )
            for col in range(config.box_columns)
        ]
        for row in range(config.box_rows)
    ]
    # 盒子名、「一览」、「搜寻」
    others: Sequence[Rect] = [
        ((0.4102, 0.0792), (0.4477, 0.1472)),
        ((0.3031, 0.7931), (0.3406, 0.8611)),
        ((0.5164, 0.7931), (0.5539, 0.8611)),
    ]
    candidates: Sequence[tuple[Cursor, Rect]] = [
        *((("party", row, 0), rect) for row, rect in enumerate(party)),
        *(
            (("slots", row, col), rect)
            for row, cells in enumerate(slots)
            for col, rect in enumerate(cells)
        ),
        *((("other", index, 0), rect) for index, rect in enumerate(others)),
    ]
    hsv = cv2.cvtColor(image.bgr, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (29, 100, 200), (60, 255, 255))
    cyan = cv2.inRange(hsv, (80, 150, 200), (100, 255, 255))
    height, width = yellow.shape
    best: tuple[float, Cursor] | None = None
    for cursor, rect in candidates:
        (left, top), (right, bottom) = rect
        rows = slice(round(top * height), round(bottom * height))
        cols = slice(round(left * width), round(right * width))
        yellow_ys = np.nonzero(yellow[rows, cols])[0]
        cyan_ys = np.nonzero(cyan[rows, cols])[0]
        size = yellow[rows, cols].size
        # 箭头黄绿色那一段占框的比例超过 0.1、青色超过 0.03，并且青色的平均高度在黄绿色下面才算
        if len(yellow_ys) / size < 0.1 or len(cyan_ys) / size < 0.03:
            continue
        if cyan_ys.mean() <= yellow_ys.mean():
            continue
        if best is None or len(yellow_ys) / size > best[0]:
            best = (len(yellow_ys) / size, cursor)
    if best is None:
        raise RuntimeError("盒子画面里找不到光标的箭头")
    return best[1]
