"""孵蛋脚本的画面判断：只看传进来的截图，不按键、不截图。阈值和坐标在 EggConfig 里。"""

import re
import unicodedata

import cv2
import numpy as np

from control_switch.types import Rect
from control_switch.vision import ImageChecker

from .config import EggConfig

DEFAULT = EggConfig()

# 光标的位置：("party", 队伍第几格) 或 ("box", 行, 列)
Cursor = tuple[str, int] | tuple[str, int, int]


def is_dialog(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """下方有对话框：左上角是黄色，框里大部分是暗色。"""
    lower, upper = config.dialog_yellow
    if image.color_ratio(config.dialog_corner, lower, upper) <= config.dialog_corner_ratio:
        return False
    body = image.crop(config.dialog_body)
    dark = body.max(axis=2) < config.dialog_dark_max
    return float(dark.mean()) > config.dialog_dark_ratio


def is_battle(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """野外战斗的指令菜单。「真的要放生吗？」那里的按钮位置也是黄色，要排除对话框。"""
    lower, upper = config.dialog_yellow
    if image.color_ratio(config.battle_button, lower, upper) <= config.battle_ratio:
        return False
    return not is_dialog(image, config)


def is_overworld(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
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


def is_picnic(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """野餐中：左下角三个白色按键图标都在，并且没有对话框。"""
    lower, upper = config.picnic_white
    if not all(
        image.color_ratio(icon, lower, upper) > config.picnic_ratio for icon in config.picnic_icons
    ):
        return False
    return not is_dialog(image, config)


def is_prompt(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """对话里有「是/否」选择框。"""
    if not is_dialog(image, config):
        return False
    found = image.find_menu(config.prompt_area)
    if found is None:
        return False
    text = "".join(option for option, _ in found[1])
    return "是" in text and "否" in text


def menu_row(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """主菜单光标在第几行（从 0 数）；不是主菜单返回 -1。"""
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


def is_riding(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """主菜单打开时，左下角写「下来」是骑着，写「骑上」是没骑。"""
    return "下来" in image.read_text(config.riding_text)


def box_title(image: ImageChecker, config: EggConfig = DEFAULT) -> int | None:
    """盒子画面的盒子编号，读不到返回 None。"""
    text = unicodedata.normalize("NFKC", image.read_text(config.box_title_area))
    match = re.search(r"盒子\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _party_cell(config: EggConfig, i: int) -> Rect:
    (left, top), (right, bottom) = config.party_cell
    step = config.cell_step[1]
    return ((left, top + step * i), (right, bottom + step * i))


def _box_cell(config: EggConfig, r: int, c: int) -> Rect:
    (left, top), (right, bottom) = config.box_cell
    step_x, step_y = config.cell_step
    return (
        (left + step_x * c, top + step_y * r),
        (right + step_x * c, bottom + step_y * r),
    )


def box_cursor(image: ImageChecker, config: EggConfig = DEFAULT) -> Cursor | None:
    """盒子画面光标在哪一格：黄色占比最大并且超过阈值的那格。"""
    lower, upper = config.cursor_yellow
    best: Cursor | None = None
    best_ratio = config.cursor_ratio
    for i in range(6):
        ratio = image.color_ratio(_party_cell(config, i), lower, upper)
        if ratio > best_ratio:
            best, best_ratio = ("party", i), ratio
    for r in range(5):
        for c in range(6):
            ratio = image.color_ratio(_box_cell(config, r, c), lower, upper)
            if ratio > best_ratio:
                best, best_ratio = ("box", r, c), ratio
    return best


def egg_cells(image: ImageChecker, config: EggConfig = DEFAULT) -> list[tuple[int, int]]:
    """盒子画面里哪几格是蛋，按行、列排好。

    每格只看下 3/4、横向中间一半：白色占比和浅绿色占比都在范围里就是蛋。
    """
    white_lower, white_upper = config.egg_white
    green_lower, green_upper = config.egg_green
    cells = []
    for r in range(5):
        for c in range(6):
            (left, top), (right, bottom) = _box_cell(config, r, c)
            width, height = right - left, bottom - top
            rect: Rect = (
                (left + width / 4, top + height / 4),
                (right - width / 4, bottom),
            )
            white = image.color_ratio(rect, white_lower, white_upper)
            green = image.color_ratio(rect, green_lower, green_upper)
            if (
                config.egg_white_range[0] <= white <= config.egg_white_range[1]
                and config.egg_green_range[0] <= green <= config.egg_green_range[1]
            ):
                cells.append((r, c))
    return cells


def panel_name(image: ImageChecker, config: EggConfig = DEFAULT) -> str:
    """右侧面板顶上的名字：宝可梦名、「蛋」，空格是空字符串。"""
    return image.read_text(config.panel_name_area)


def panel_best_count(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """六项能力里写「最棒」的有几项。"""
    return sum("最棒" in image.read_text(rect) for rect in config.panel_stats)


def panel_shiny(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """右侧面板上有闪光星星：星星区域三个通道标准差之和超过阈值。"""
    area = image.crop(config.shiny_area).reshape(-1, 3)
    return float(np.std(area, axis=0).sum()) > config.shiny_std


def is_egg_name(name: str) -> bool:
    """panel_name 读到的是不是「蛋」。OCR 会在后面多读出别的字（真机上读成过「蛋麗」），所以只看第一个字。"""
    return name.startswith("蛋")


def is_holding(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """盒子里拿着宝可梦：底栏没有「替换」（只剩「显示宝可梦」「返回」）。"""
    return config.holding_text not in image.read_text(config.holding_area)


def judge_count(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """六项能力里读得出判定词（最棒、了不起……）的有几项。"""
    count = 0
    for rect in config.panel_stats:
        text = image.read_text(rect)
        count += any(word in text for word in config.judge_words)
    return count


def battle_row(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """战斗菜单的黄色光标在第几行（从 0 数），认不出返回 -1。"""
    lower, upper = config.dialog_yellow
    (left, top), (right, bottom) = config.battle_button
    ratios = []
    for i in range(config.battle_rows):
        shift = config.battle_row_step * i
        rect: Rect = ((left, top + shift), (right, bottom + shift))
        ratios.append(image.color_ratio(rect, lower, upper))
    best = max(range(config.battle_rows), key=lambda i: ratios[i])
    return best if ratios[best] > config.battle_ratio else -1


def is_pick_screen(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """选三明治签子的界面：左上「食谱模式」，右上有「签」。"""
    return image.has_text(config.pick_title, config.pick_title_text) and image.has_text(
        config.pick_hint, config.pick_hint_text
    )


def operation_selected(image: ImageChecker, config: EggConfig = DEFAULT) -> str:
    """盒子里的操作菜单选中（黄色）的那一行的文字，认不出返回空字符串。"""
    lower, upper = config.menu_yellow
    (left, top), (right, bottom) = config.operation_rect
    best_ratio = config.operation_ratio
    best: Rect | None = None
    for i in range(config.operation_rows):
        shift = config.operation_step * i
        rect: Rect = ((left, top + shift), (right, bottom + shift))
        ratio = image.color_ratio(rect, lower, upper)
        if ratio > best_ratio:
            best, best_ratio = rect, ratio
    return "" if best is None else image.read_text(best)
