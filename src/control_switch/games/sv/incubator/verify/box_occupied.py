import numpy as np

from control_switch.vision import ImageChecker

from ..config import IncubatorConfig
from ..types import Cursor


def box_occupied(image: ImageChecker, config: IncubatorConfig) -> list[Cursor]:
    """盒子里哪些格子有宝可梦或蛋，返回 ("slots", 行, 列)，偶数行从左到右、奇数行从右到左。

    看每一格中间一块（避开上方光标箭头的位置）三个通道的标准差之和：空格是一片纯色，不超过 7；
    有宝可梦或蛋的至少 77。超过 30 算有。光标停着的格子会变黄，调用前先把光标移到格子外面。
    """
    occupied: list[Cursor] = []
    for row in range(config.box_rows):
        columns = range(config.box_columns)
        for col in columns if row % 2 == 0 else reversed(columns):
            # 第 0 行第 0 列格子中间那一块，相邻两格横向隔 0.0656、纵向隔 0.1167
            left, top = 0.242 + 0.0656 * col, 0.213 + 0.1167 * row
            cell = image.crop(((left, top), (left + 0.046, top + 0.07)))
            if float(np.std(cell, axis=(0, 1)).sum()) > 30:
                occupied.append(("slots", row, col))
    return occupied
