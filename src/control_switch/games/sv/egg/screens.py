"""孵蛋脚本的画面判断：只看传进来的截图，不按键、不截图。阈值和坐标在 EggConfig 里。

对话框、选择框、野外、野餐、主菜单这些几个脚本都用的判断在 control_switch.games.sv.screens，这里引进来，
步骤里统一写 screens.xxx。
"""

import re
from functools import cache

import cv2
import numpy as np

from control_switch.games.sv.verify import (
    gradient_arrow,
    has_dialog_box,
    is_dialog,
    is_main_menu,
    is_overworld,
    is_picnic,
    is_prompt,
)
from control_switch.types import Rect
from control_switch.vision import ImageChecker

from .config import EggConfig

# 从 sv.screens 引进来的，步骤里统一写 screens.xxx 调用
__all__ = [
    "gradient_arrow",
    "has_dialog_box",
    "is_dialog",
    "is_main_menu",
    "is_overworld",
    "is_picnic",
    "is_prompt",
]

DEFAULT = EggConfig()

# 盒子里光标的位置：("party", 队伍第几行, 0) 或 ("slots", 行, 列)
Cursor = tuple[str, int, int]


# ---- 野餐和三明治 ----


def has_a_hint(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """野餐时左边有 A 按钮的提示（「聊天」）：身边有宝可梦在跟前，A 按下去是和它说话。"""
    lower, upper = config.a_hint_white
    return image.color_ratio(config.a_hint_area, lower, upper) > config.a_hint_ratio


def is_table_menu_arrow(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """桌子的菜单（做料理、更改配置……）里，选中第一项的箭头。"""
    return gradient_arrow(image, config.table_arrow_area, config)


def _recipe_rect(
    config: EggConfig, origin: tuple[float, float], size: tuple[float, float], i: int
) -> Rect:
    """食谱列表里第 i 格（两列三行，从左到右、从上到下数）的某个小框。"""
    column, row = i % config.recipe_columns, i // config.recipe_columns
    left = origin[0] + column * config.recipe_step[0]
    top = origin[1] + row * config.recipe_step[1]
    return ((left, top), (left + size[0], top + size[1]))


def selected_recipe_cell(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """食谱列表里选中的是这一页第几格（0 到 5）；没有选中的箭头，或者不止一个，返回 -1。"""
    found = [
        i
        for i in range(config.recipe_columns * config.recipe_rows)
        if gradient_arrow(
            image,
            _recipe_rect(config, config.recipe_arrow_origin, config.recipe_arrow_size, i),
            config,
        )
    ]
    return found[0] if len(found) == 1 else -1


def is_recipe_list(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """食谱列表：有选中的箭头。"""
    return selected_recipe_cell(image, config) != -1


def is_pick_arrow(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """选三明治签子的界面：选中第一根签子的箭头。"""
    return gradient_arrow(image, config.pick_arrow_area, config)


def recipe_numbers(image: ImageChecker, config: EggConfig = DEFAULT) -> list[int]:
    """食谱列表这一页六格左下角的编号，认不出（没有食谱、材料不够是半透明的）是 0。

    编号是白色的粗体数字：把白色变成黑色、其余变成白色，放大，再认。
    """
    numbers = [
        _read_number(
            image, _recipe_rect(config, config.recipe_id_origin, config.recipe_id_size, i), config
        )
        for i in range(config.recipe_columns * config.recipe_rows)
    ]
    # 个别认错的：前后两格差 2，中间这格就是前一格加 1
    for i in range(1, len(numbers) - 1):
        before, after = numbers[i - 1], numbers[i + 1]
        if before > 0 and after > 0 and before + 2 == after:
            numbers[i] = before + 1
    return numbers


def _read_number(image: ImageChecker, rect: Rect, config: EggConfig) -> int:
    gray = image.crop(rect, "gray")
    black_on_white = np.where(gray >= config.recipe_id_white, 0, 255).astype(np.uint8)
    enlarged = cv2.resize(
        black_on_white,
        None,
        fx=config.recipe_id_scale,
        fy=config.recipe_id_scale,
        interpolation=cv2.INTER_CUBIC,
    )
    border = config.recipe_id_border
    padded = cv2.copyMakeBorder(
        enlarged, border, border, border, border, cv2.BORDER_CONSTANT, value=255
    )
    ok, encoded = cv2.imencode(".png", padded)
    if not ok:
        return 0
    text = ImageChecker(encoded.tobytes()).read_text(((0.0, 0.0), (1.0, 1.0)))
    digits = re.sub(r"\D", "", text)
    number = int(digits) if digits else 0
    return number if 0 < number <= config.recipe_max else 0


@cache
def _hand_template(path: str) -> np.ndarray:
    """手的模板：白色的部分是 1，其余是 0。"""
    template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"读不到手的模板 {path}")
    return (template > 0).astype(np.uint8)


def find_hand(
    image: ImageChecker, kind: str, area: Rect, config: EggConfig = DEFAULT
) -> tuple[float, float] | None:
    """在 area 里找做三明治的手，返回手的中心（占画面宽高的比例）；没有返回 None。

    kind 是 "free"（空手）或 "grabbing"（抓着东西的拳头）。手是白色的、有黑边：找白色的连通区域，
    大小、宽高比、白色占外框的比例、形状都和模板差不多的就是手（上游 SandwichHandMatcher）。
    """
    if kind == "free":
        path, base_area = config.hand_template_free, config.hand_min_area_free
    else:
        path, base_area = config.hand_template_grabbing, config.hand_min_area_grabbing
    template = _hand_template(str(path))
    image.mark(area)
    bgr = image.bgr
    height, width = bgr.shape[:2]
    (left, top), (right, bottom) = area
    x0, y0 = round(left * width), round(top * height)
    x1, y1 = round(right * width), round(bottom * height)
    lower, upper = config.hand_white
    mask = cv2.inRange(bgr[y0:y1, x0:x1], lower, upper)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = base_area * (height / config.hand_base_height) ** 2
    template_aspect = template.shape[1] / template.shape[0]
    template_fill = float(template.mean())
    best: tuple[float, tuple[float, float]] | None = None
    for i in range(1, count):
        x, y, w, h, size = (int(value) for value in stats[i])
        if size < min_area:
            continue
        if abs(w / h / template_aspect - 1) > config.hand_tolerance:
            continue
        if abs(size / (w * h) / template_fill - 1) > config.hand_tolerance:
            continue
        piece = (labels[y : y + h, x : x + w] == i).astype(np.uint8)
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_NEAREST)
        mismatch = float(np.abs(resized.astype(float) - piece.astype(float)).mean())
        if mismatch > config.hand_max_mismatch:
            continue
        center = (
            (x0 + float(centroids[i][0])) / width,
            (y0 + float(centroids[i][1])) / height,
        )
        if best is None or mismatch < best[0]:
            best = (mismatch, center)
    return None if best is None else best[1]


def is_plate_label_yellow(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """盘子的标签是黄色：从盘子里抓着东西时标签会变黄，没抓着（盘子空了）不变。"""
    lower, upper = config.plate_label_yellow
    size = cv2.inRange(image.crop(config.plate_label_area), lower, upper)
    height = image.bgr.shape[0]
    return (
        int(np.count_nonzero(size))
        >= config.plate_yellow_min * (height / config.hand_base_height) ** 2
    )


# ---- 盒子 ----


def is_box_selecting(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """盒子里的选择模式（按过减号、Y，或者拿起了一整列）：底栏中间那些按键提示都没有了，只剩右边的「返回」。"""
    lower, upper = config.bar_white
    return image.color_ratio(config.bar_area, lower, upper) < config.bar_ratio


def box_cursor(image: ImageChecker, config: EggConfig = DEFAULT) -> Cursor | None:
    """盒子画面里光标在哪一格；光标在格子外面（盒子名、「一览」「搜寻」）或者认不出返回 None。

    光标是格子上方一个黄绿色渐变的向下箭头。格子本身的黄色会一闪一闪，不能用来认。
    箭头黄绿色的那一段是一个扁扁的长方块，位置在格子上边中间。
    """
    image.mark(config.cursor_search)
    bgr = image.bgr
    height, width = bgr.shape[:2]
    lower, upper = config.cursor_yellow
    mask = cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), lower, upper)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = config.cursor_min_area * (height / config.hand_base_height) ** 2
    best: tuple[int, float, float] | None = None
    for i in range(1, count):
        _, _, w, h, size = (int(value) for value in stats[i])
        if size < min_area or not config.cursor_aspect[0] <= w / h <= config.cursor_aspect[1]:
            continue
        cx, cy = float(centroids[i][0]) / width, float(centroids[i][1]) / height
        if not config.cursor_search[0][0] <= cx <= config.cursor_search[1][0]:
            continue
        if not config.cursor_search[0][1] <= cy <= config.cursor_search[1][1]:
            continue
        if best is None or size > best[0]:
            best = (size, cx, cy)
    if best is None:
        return None
    _, cx, cy = best
    row = round((cy - config.cursor_origin[1]) / config.cell_step[1])
    if cx < config.party_limit:
        return ("party", row, 0) if 0 <= row < config.party_rows else None
    col = round((cx - config.cursor_origin[0]) / config.cell_step[0])
    if 0 <= row < config.box_rows and 0 <= col < config.box_columns:
        return ("slots", row, col)
    return None


def panel_present(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """右边的面板上有宝可梦：顶上的名字栏是黄色。光标在空格上时没有面板。"""
    lower, upper = config.panel_header_yellow
    return image.color_ratio(config.panel_header, lower, upper) > config.panel_header_ratio


def panel_name(image: ImageChecker, config: EggConfig = DEFAULT) -> str:
    """右侧面板顶上的名字：宝可梦名、「蛋」，空格是空字符串。"""
    return image.read_text(config.panel_name_area)


def panel_shiny(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """右侧面板上有闪光的星星：星星区域三个通道标准差之和超过阈值。"""
    area = image.crop(config.shiny_area).reshape(-1, 3)
    return float(np.std(area, axis=0).sum()) > config.shiny_std


def panel_stats(image: ImageChecker, config: EggConfig = DEFAULT) -> list[str]:
    """面板上六项能力的文字：在评定页是「最棒」「非常好」这些判定词，在能力页是数值。"""
    return [image.read_text(rect) for rect in config.panel_stats]


def is_judge_page(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """右侧面板在评定页：六项能力里至少 judge_min 项读到「最棒」「非常好」这些判定词。"""
    texts = panel_stats(image, config)
    return (
        sum(any(word in text for word in config.judge_words) for text in texts) >= config.judge_min
    )


def is_stats_page(image: ImageChecker, config: EggConfig = DEFAULT) -> bool:
    """右侧面板在能力页：特性那一行的标签是「特性」（评定页这里是「性格」）。"""
    return config.ability_label in image.read_text(config.ability_label_area)


def panel_ability(image: ImageChecker, config: EggConfig = DEFAULT) -> str:
    """右侧面板能力页上的特性。"""
    return image.read_text(config.ability_area)


@cache
def _egg_template(path: str) -> np.ndarray:
    """盒子格子里蛋的模板。"""
    template = cv2.imread(path)
    if template is None:
        raise RuntimeError(f"读不到蛋的模板 {path}")
    return template


def box_eggs(image: ImageChecker, config: EggConfig = DEFAULT) -> list[tuple[int, int]]:
    """盒子里哪些格子是蛋，返回 (行, 列)：每一格和蛋的模板比，匹配度超过 egg_score 的是蛋。"""
    template = _egg_template(str(config.egg_template))
    scale = image.bgr.shape[0] / config.egg_template_height
    if scale != 1:
        template = cv2.resize(template, None, fx=scale, fy=scale)
    (left, top), (right, bottom) = config.box_cell
    eggs = []
    for row in range(config.box_rows):
        for col in range(config.box_columns):
            dx, dy = config.cell_step[0] * col, config.cell_step[1] * row
            cell = image.crop(((left + dx, top + dy), (right + dx, bottom + dy)))
            score = float(cv2.matchTemplate(cell, template, cv2.TM_CCOEFF_NORMED).max())
            if score > config.egg_score:
                eggs.append((row, col))
    return eggs


def party_slot(image: ImageChecker, row: int, config: EggConfig = DEFAULT) -> str:
    """队伍第 row 行是什么："empty"（空格）、"egg"（蛋）、"mon"（宝可梦）。"""
    (left, top), (right, bottom) = config.party_cell
    step = config.cell_step[1] * row
    rect: Rect = ((left, top + step), (right, bottom + step))
    if float(np.std(image.crop(rect), axis=(0, 1)).sum()) < config.empty_slot_std:
        return "empty"
    name_rect: Rect = (
        (config.party_name[0][0], config.party_name[0][1] + step),
        (config.party_name[1][0], config.party_name[1][1] + step),
    )
    return "egg" if image.read_text(name_rect).startswith("蛋") else "mon"


def operation_row(image: ImageChecker, config: EggConfig = DEFAULT) -> int:
    """盒子里按 A 出来的操作菜单（移动、查看能力、携带持有物、标记、放生、取消）选中的是第几行；认不出返回 -1。

    选中那行左边有个向右的渐变箭头，黄绿色那一段是又窄又高的长条。菜单在格子右边，横向位置跟着格子变，
    所以只看箭头在哪一行。
    """
    image.mark(config.operation_area)
    bgr = image.bgr
    height, width = bgr.shape[:2]
    lower, upper = config.cursor_yellow
    (left, top), (right, bottom) = config.operation_area
    x0, y0, x1, y1 = (
        round(left * width),
        round(top * height),
        round(right * width),
        round(bottom * height),
    )
    mask = cv2.inRange(cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV), lower, upper)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = config.cursor_min_area * (height / config.hand_base_height) ** 2
    best: tuple[int, float] | None = None
    for i in range(1, count):
        _, _, w, h, size = (int(value) for value in stats[i])
        if size < min_area or w / h > config.operation_aspect:
            continue
        if best is None or size > best[0]:
            best = (size, (y0 + float(centroids[i][1])) / height)
    if best is None:
        return -1
    row = round((best[1] - config.operation_first_row) / config.operation_step)
    return row if 0 <= row < config.operation_rows else -1
