"""朱紫几个脚本共用的画面判断：只看传进来的截图，不按键、不截图。区域和阈值在 SvConfig 里。"""

import cv2
import numpy as np

from control_switch.types import Rect
from control_switch.vision import ImageChecker

from .config import SvConfig

DEFAULT = SvConfig()


def has_dialog_box(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """下方有对话框：左上角是黄色，框里大部分是暗色。"""
    lower, upper = config.dialog_yellow
    if image.color_ratio(config.dialog_corner, lower, upper) <= config.dialog_corner_ratio:
        return False
    body = image.crop(config.dialog_body)
    dark = body.max(axis=2) < config.dialog_dark_max
    return float(dark.mean()) > config.dialog_dark_ratio


def is_dialog(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """有对话框，并且右下角有翻页的小三角：按 A 或 B 能往下翻。"""
    if not has_dialog_box(image, config):
        return False
    lower, upper = config.dialog_arrow_white
    return image.color_ratio(config.dialog_arrow, lower, upper) > config.dialog_arrow_ratio


def gradient_arrow(image: ImageChecker, area: Rect, config: SvConfig = DEFAULT) -> bool:
    """区域里有选中用的渐变箭头：黄绿色和青色的像素都够多。"""
    (left, top), (right, bottom) = area
    size = (right - left) * (bottom - top)
    yellow_lower, yellow_upper = config.arrow_yellow
    cyan_lower, cyan_upper = config.arrow_cyan
    return (
        image.color_ratio(area, yellow_lower, yellow_upper) * size > config.arrow_yellow_min
        and image.color_ratio(area, cyan_lower, cyan_upper) * size > config.arrow_cyan_min
    )


def is_prompt(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """对话框带选择框（「是 / 否」）：选择框里有选中的箭头。"""
    return has_dialog_box(image, config) and gradient_arrow(image, config.prompt_area, config)


def is_overworld(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """野外：右下角有小地图。看小地图外圈上青、绿、黄三种颜色是不是都有。"""
    bgr = image.bgr
    height, width = bgr.shape[:2]
    angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    cx, cy = config.minimap_center[0] * width, config.minimap_center[1] * height
    points = []
    for radius in config.minimap_radii:
        xs = np.clip((cx + radius * height * np.cos(angles)).astype(int), 0, width - 1)
        ys = np.clip((cy + radius * height * np.sin(angles)).astype(int), 0, height - 1)
        points.append(bgr[ys, xs])
    hsv = cv2.cvtColor(np.concatenate(points)[np.newaxis], cv2.COLOR_BGR2HSV)
    return all(
        float(cv2.inRange(hsv, lower, upper).mean()) / 255 >= config.minimap_ratio
        for lower, upper in config.minimap_colors
    )


def is_picnic(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """野餐中：左下角三个按键图标（白色的圆、暗色的底）都在，并且没有对话框。"""
    white_lower, white_upper = config.picnic_white
    dark_lower, dark_upper = config.picnic_dark
    for icon in config.picnic_icons:
        if image.color_ratio(icon, white_lower, white_upper) <= config.picnic_ratio:
            return False
        if image.color_ratio(icon, dark_lower, dark_upper) <= config.picnic_dark_ratio:
            return False
    return not has_dialog_box(image, config)


def menu_row(image: ImageChecker, config: SvConfig = DEFAULT) -> int:
    """主菜单光标在右边第几行（从 0 数）；光标不在右边的菜单上返回 -1。"""
    lower, upper = config.menu_yellow
    ratios = []
    for i in range(config.menu_rows):
        top = config.menu_top + config.menu_row_height * i
        rect: Rect = (
            (config.menu_left, top),
            (config.menu_right, top + config.menu_row_height),
        )
        ratios.append(image.color_ratio(rect, lower, upper))
    best = max(range(config.menu_rows), key=lambda i: ratios[i])
    return best if ratios[best] > config.menu_ratio else -1


def is_main_menu(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """主菜单：光标在右边的某一行上，或者在左边队伍栏的第一格上。"""
    if menu_row(image, config) != -1:
        return True
    lower, upper = config.menu_yellow
    return image.color_ratio(config.menu_party, lower, upper) > config.menu_ratio
