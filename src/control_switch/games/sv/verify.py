"""朱紫几个脚本共用的画面判断：只看传进来的截图，不按键、不截图。区域和阈值在 SvConfig 里。"""

import re
import unicodedata
from functools import cache
from importlib.resources import files

import cv2
import numpy as np

from control_switch.types import Hsv, Rect
from control_switch.vision import ImageChecker

from .config import SvConfig


def has_dialog_box(image: ImageChecker, config: SvConfig) -> bool:
    """下方有对话框：左上角是黄色，框里大部分是暗色。"""
    lower, upper = config.dialog.yellow
    if image.color_ratio(config.dialog.corner, lower, upper) <= config.dialog.corner_ratio:
        return False
    body = image.crop(config.dialog.body)
    dark = body.max(axis=2) < config.dialog.dark_max
    return float(dark.mean()) > config.dialog.dark_ratio


def is_dialog(image: ImageChecker, config: SvConfig) -> bool:
    """有对话框，并且右下角有翻页的小三角：按 A 或 B 能往下翻。"""
    if not has_dialog_box(image, config):
        return False
    lower, upper = config.dialog.arrow_white
    return image.color_ratio(config.dialog.arrow, lower, upper) > config.dialog.arrow_ratio


def gradient_arrow(image: ImageChecker, area: Rect, config: SvConfig) -> bool:
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


def is_prompt(image: ImageChecker, config: SvConfig) -> bool:
    """对话框带选择框（「是 / 否」）：选择框里有选中的箭头。"""
    return has_dialog_box(image, config) and gradient_arrow(
        image, config.dialog.prompt_area, config
    )


def is_overworld(image: ImageChecker, config: SvConfig) -> bool:
    """野外：右下角有小地图。小地图圆心有人位置的黄色圆点，外圈上青、绿、黄、红四种颜色都有。

    小地图跟着镜头转，圆点一直在圆心；外圈的色段跟着镜头转，所以只看每种颜色在圈上占多少，不看在哪。
    只看一种颜色不行：盒子画面那里是青色，野餐画面是绿色，沙漠地形孵化动画时整片地面都是土黄色。
    """
    # 人位置的黄色圆点（720p 下圆心 (1160, 598) 上下左右 6 像素），黄色占比超过 0.8。
    # 亮度下限 245：画面完全亮起来时圆点亮度是 252 到 255，飞行落地、读档后画面从黑慢慢变亮，
    # 没亮完时人还不能动，不算野外（见 docs/实测-野外判定.md）
    if (
        image.color_ratio(((0.9016, 0.8222), (0.9109, 0.8389)), (20, 150, 245), (35, 255, 255))
        <= 0.8
    ):
        return False
    # 小地图外圈：圆心和两个半径（按画面高度的比例，正好落在外圈的细边上，取两圈防止偏一两个像素）
    center_x, center_y = 0.90625, 0.8333
    radii = (0.124, 0.128)
    # 青、绿、黄、红，每种可以有几段 HSV 范围；红色的 H 跨在 0 和 180 两头，分两段
    colors: tuple[tuple[tuple[Hsv, Hsv], ...], ...] = (
        (((80, 100, 150), (105, 255, 255)),),
        (((40, 100, 150), (80, 255, 255)),),
        (((20, 100, 150), (35, 255, 255)),),
        (((0, 80, 150), (10, 255, 255)), ((170, 80, 150), (180, 255, 255))),
    )
    bgr = image.bgr
    height, width = bgr.shape[:2]
    outer = max(radii)
    image.mark(
        (
            (center_x - outer * height / width, center_y - outer),
            (center_x + outer * height / width, center_y + outer),
        )
    )
    angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    cx, cy = center_x * width, center_y * height
    points = []
    for radius in radii:
        xs = np.clip((cx + radius * height * np.cos(angles)).astype(int), 0, width - 1)
        ys = np.clip((cy + radius * height * np.sin(angles)).astype(int), 0, height - 1)
        points.append(bgr[ys, xs])
    hsv = cv2.cvtColor(np.concatenate(points)[np.newaxis], cv2.COLOR_BGR2HSV)
    # 每种颜色在圈上至少占 10%
    for ranges in colors:
        hit = np.any([cv2.inRange(hsv, low, high) > 0 for low, high in ranges], axis=0)
        if float(np.mean(hit)) < 0.1:
            return False
    return True


@cache
def _picnic_icon(name: str) -> np.ndarray:
    """野餐按键图标的白色模板（720p 下 20×20）：白色的部分是 True。"""
    path = files("control_switch.games.sv") / "data" / f"picnic_{name}.png"
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"读不到野餐按键图标的模板 {path}")
    return template > 0


def is_picnic(image: ImageChecker, config: SvConfig) -> bool:
    """野餐中：左下角 B、减号、Y 三个按键图标都在，并且没有对话框。

    每个图标框住白色的圆，按白色转成黑白图，缩到模板大小，和模板逐个像素比，一样的超过 90% 才算。
    圆里的字母是深色的，只有形状对上才行，桌布上白色的餐巾、碗沿凑不出这个图案。
    """
    # 三个图标白色圆的位置（720p 下 x 38 到 58，y 分别从 513、629、667 开始，各 20 像素）
    icons: tuple[tuple[str, Rect], ...] = (
        ("b", ((0.0297, 0.7125), (0.0453, 0.7403))),
        ("minus", ((0.0297, 0.8736), (0.0453, 0.9014))),
        ("y", ((0.0297, 0.9264), (0.0453, 0.9542))),
    )
    for name, rect in icons:
        template = _picnic_icon(name)
        white = cv2.inRange(image.crop(rect, "hsv"), (0, 0, 200), (180, 40, 255))
        white = cv2.resize(white, template.shape[::-1], interpolation=cv2.INTER_NEAREST) > 0
        if float(np.mean(white == template)) < 0.9:
            return False
    return not has_dialog_box(image, config)


def menu_row(image: ImageChecker, config: SvConfig) -> int:
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


def is_main_menu(image: ImageChecker, config: SvConfig) -> bool:
    """主菜单：光标在右边的某一行上，或者在左边队伍栏的第一格上。"""
    if menu_row(image, config) != -1:
        return True
    lower, upper = config.menu.yellow
    return image.color_ratio(config.menu.party, lower, upper) > config.menu.ratio


def box_title(image: ImageChecker, config: SvConfig) -> int | None:
    """盒子画面的盒子编号，读不到返回 None。"""
    text = unicodedata.normalize("NFKC", image.read_text(config.box.title_area))
    match = re.search(r"盒子\s*(\d+)", text)
    return int(match.group(1)) if match else None
