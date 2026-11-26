"""朱紫几个脚本共用的画面判断：只看传进来的截图，不按键、不截图。区域和阈值在 SvConfig 里。"""

import re
import unicodedata

import cv2
import numpy as np

from control_switch.types import Rect
from control_switch.vision import ImageChecker

from .config import SvConfig

DEFAULT = SvConfig()


def has_dialog_box(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """下方有对话框：左上角是黄色，框里大部分是暗色。"""
    lower, upper = config.dialog.yellow
    if image.color_ratio(config.dialog.corner, lower, upper) <= config.dialog.corner_ratio:
        return False
    body = image.crop(config.dialog.body)
    dark = body.max(axis=2) < config.dialog.dark_max
    return float(dark.mean()) > config.dialog.dark_ratio


def is_dialog(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """有对话框，并且右下角有翻页的小三角：按 A 或 B 能往下翻。"""
    if not has_dialog_box(image, config):
        return False
    lower, upper = config.dialog.arrow_white
    return image.color_ratio(config.dialog.arrow, lower, upper) > config.dialog.arrow_ratio


def gradient_arrow(image: ImageChecker, area: Rect, config: SvConfig = DEFAULT) -> bool:
    """区域里有选中用的渐变箭头：黄绿色和青色的像素都够多。"""
    (left, top), (right, bottom) = area
    size = (right - left) * (bottom - top)
    yellow_lower, yellow_upper = config.gradient_arrow.yellow
    cyan_lower, cyan_upper = config.gradient_arrow.cyan
    return (
        image.color_ratio(area, yellow_lower, yellow_upper) * size
        > config.gradient_arrow.yellow_min
        and image.color_ratio(area, cyan_lower, cyan_upper) * size > config.gradient_arrow.cyan_min
    )


def is_prompt(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """对话框带选择框（「是 / 否」）：选择框里有选中的箭头。"""
    return has_dialog_box(image, config) and gradient_arrow(
        image, config.dialog.prompt_area, config
    )


def is_overworld(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """野外：右下角有小地图。看小地图外圈上青、绿、黄三种颜色是不是都有。"""
    bgr = image.bgr
    height, width = bgr.shape[:2]
    center_x, center_y = config.overworld.minimap_center
    radius = max(config.overworld.minimap_radii)
    image.mark(
        (
            (center_x - radius * height / width, center_y - radius),
            (center_x + radius * height / width, center_y + radius),
        )
    )
    angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    cx, cy = config.overworld.minimap_center[0] * width, config.overworld.minimap_center[1] * height
    points = []
    for radius in config.overworld.minimap_radii:
        xs = np.clip((cx + radius * height * np.cos(angles)).astype(int), 0, width - 1)
        ys = np.clip((cy + radius * height * np.sin(angles)).astype(int), 0, height - 1)
        points.append(bgr[ys, xs])
    hsv = cv2.cvtColor(np.concatenate(points)[np.newaxis], cv2.COLOR_BGR2HSV)
    return all(
        float(cv2.inRange(hsv, lower, upper).mean()) / 255 >= config.overworld.minimap_ratio
        for lower, upper in config.overworld.minimap_colors
    )


def is_picnic(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """野餐中：左下角三个按键图标（白色的圆、暗色的底）都在，并且没有对话框。"""
    white_lower, white_upper = config.picnic.white
    dark_lower, dark_upper = config.picnic.dark
    for icon in config.picnic.icons:
        if image.color_ratio(icon, white_lower, white_upper) <= config.picnic.ratio:
            return False
        if image.color_ratio(icon, dark_lower, dark_upper) <= config.picnic.dark_ratio:
            return False
    return not has_dialog_box(image, config)


def menu_row(image: ImageChecker, config: SvConfig = DEFAULT) -> int:
    """主菜单光标在右边第几行（从 0 数）；光标不在右边的菜单上返回 -1。"""
    lower, upper = config.menu.yellow
    ratios = []
    for i in range(config.menu.rows):
        top = config.menu.top + config.menu.row_height * i
        rect: Rect = (
            (config.menu.left, top),
            (config.menu.right, top + config.menu.row_height),
        )
        ratios.append(image.color_ratio(rect, lower, upper))
    best = max(range(config.menu.rows), key=lambda i: ratios[i])
    return best if ratios[best] > config.menu.ratio else -1


def is_main_menu(image: ImageChecker, config: SvConfig = DEFAULT) -> bool:
    """主菜单：光标在右边的某一行上，或者在左边队伍栏的第一格上。"""
    if menu_row(image, config) != -1:
        return True
    lower, upper = config.menu.yellow
    return image.color_ratio(config.menu.party, lower, upper) > config.menu.ratio


def box_title(image: ImageChecker, config: SvConfig = DEFAULT) -> int | None:
    """盒子画面的盒子编号，读不到返回 None。"""
    text = unicodedata.normalize("NFKC", image.read_text(config.box.title_area))
    match = re.search(r"盒子\s*(\d+)", text)
    return int(match.group(1)) if match else None
