"""截图的通用操作，补充 ImageChecker 没有的读取方式。

ImageChecker 没有对外提供像素数据，这里直接读它内部已经去黑边、缩放到 1920x1080 的图
（_bgr、_gray、_hsv）、裁剪方法 _crop 和文字识别 _ocr。
_crop 通过截图对象调用，lib/debug_checker.py 的子类可以在裁剪时把区域存下来。
所以区域坐标和识别结果都和 ImageChecker 自己的方法完全一致。
"""

import cv2
import numpy as np

from tool.check_image import ImageChecker, _ocr
from type.image import Hsv, Rect


def crop(image: ImageChecker, rect: Rect) -> np.ndarray:
    """区域的彩色（BGR）图片。"""
    return image._crop(image._bgr, rect)


def save(image: ImageChecker, path: str) -> None:
    """把截图（去黑边、缩放到 1920x1080 之后的）存成图片文件，格式按扩展名。"""
    cv2.imwrite(path, image._bgr)


def text_lines(image: ImageChecker, rect: Rect) -> list[tuple[str, Rect]]:
    """识别区域内的每一行文字，返回 (文字, 这一行文字所在的区域)，从上到下排列。

    返回的区域是整张截图上的比例坐标，可以直接交给 ImageChecker 的其他方法。
    """
    height, width = image._bgr.shape[:2]
    (left, top), _ = rect
    x0, y0 = round(left * width), round(top * height)
    result, _ = _ocr()(crop(image, rect))
    lines = []
    for box, text, _score in result or []:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        line_rect = (
            ((x0 + min(xs)) / width, (y0 + min(ys)) / height),
            ((x0 + max(xs)) / width, (y0 + max(ys)) / height),
        )
        lines.append((text, line_rect))
    return sorted(lines, key=lambda line: line[1][0][1])


def difference(a: ImageChecker, b: ImageChecker, rect: Rect) -> float:
    """区域在两张截图之间的差别：灰度逐像素差的绝对值的平均，0 到 255。"""
    gray_a = a._crop(a._gray, rect).astype(np.int16)
    gray_b = b._crop(b._gray, rect).astype(np.int16)
    return float(np.abs(gray_a - gray_b).mean())


def locate_template(
    image: ImageChecker,
    rect: Rect,
    template: np.ndarray,
    lower: Hsv | None = None,
    upper: Hsv | None = None,
) -> tuple[float, tuple[int, int]]:
    """在区域里找模板，返回最高的匹配度（0 到 1）和它的位置 (x, y)。

    位置是模板左上角相对区域左上角的像素坐标。
    给了 lower 和 upper 时，先把区域按这个颜色范围转成黑白图再匹配，
    这时 template 也要是同样处理过的单通道图。
    区域比模板小时没法匹配，返回 (0, (0, 0))。
    """
    if lower is not None and upper is not None:
        area = cv2.inRange(image._crop(image._hsv, rect), lower, upper)
    else:
        area = image._crop(image._bgr, rect)
    if area.shape[0] < template.shape[0] or area.shape[1] < template.shape[1]:
        return 0.0, (0, 0)
    result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return float(score), location


def find_templates(
    image: ImageChecker,
    rect: Rect,
    template: np.ndarray,
    min_score: float,
    lower: Hsv | None = None,
    upper: Hsv | None = None,
) -> list[tuple[float, tuple[int, int]]]:
    """在区域里找出模板出现的所有位置：匹配度至少 min_score，彼此离得太近（重叠）的只留最好的一个。

    返回 (匹配度, 位置) 的列表，按匹配度从高到低；位置是模板左上角相对区域左上角的像素坐标。
    颜色范围和 locate_template 一样。区域比模板小时返回空列表。
    """
    if lower is not None and upper is not None:
        area = cv2.inRange(image._crop(image._hsv, rect), lower, upper)
    else:
        area = image._crop(image._bgr, rect)
    height, width = template.shape[:2]
    if area.shape[0] < height or area.shape[1] < width:
        return []
    result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= min_score)
    candidates = sorted(
        ((float(result[y, x]), (int(x), int(y))) for y, x in zip(ys, xs)), reverse=True
    )
    found: list[tuple[float, tuple[int, int]]] = []
    for score, (x, y) in candidates:
        if all(abs(x - fx) >= width or abs(y - fy) >= height for _, (fx, fy) in found):
            found.append((score, (x, y)))
    return found
