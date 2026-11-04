"""检查截图内容。

区域用比例坐标 ((左, 上), (右, 下))，数值是占图片宽高的比例，和分辨率无关。
截图会先去掉黑边、缩放到 1920x1080，再按比例裁剪，见 docs/实测-分辨率定位.md。
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

Rect = tuple[tuple[float, float], tuple[float, float]]

BASE_SIZE = (1920, 1080)
# 行或列的平均亮度不超过这个值，当作黑边
BLACK_BAR = 8
# 选中项比其他项至少暗这么多，才认为有明确的选中项
MIN_HIGHLIGHT_GAP = 40


@lru_cache(maxsize=1)
def _ocr() -> RapidOCR:
    return RapidOCR()


def _prepare(image: bytes) -> np.ndarray:
    """解码截图，去掉上下左右的黑边，缩放到 1920x1080。"""
    img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rows = np.where(gray.mean(axis=1) > BLACK_BAR)[0]
    cols = np.where(gray.mean(axis=0) > BLACK_BAR)[0]
    if rows.size and cols.size:
        img = img[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    interpolation = cv2.INTER_AREA if img.shape[1] > BASE_SIZE[0] else cv2.INTER_CUBIC
    return cv2.resize(img, BASE_SIZE, interpolation=interpolation)


def _crop(img: np.ndarray, rect: Rect) -> np.ndarray:
    h, w = img.shape[:2]
    (left, top), (right, bottom) = rect
    return img[round(top * h) : round(bottom * h), round(left * w) : round(right * w)]


def _clean(text: str) -> str:
    """去掉空白和标点，OCR 经常在这些地方不一致。"""
    return re.sub(r"[\s，。！？、,.!?…：:]", "", text)


def read_text(image: bytes, rect: Rect) -> str:
    """识别区域内的文字，多行按从上到下的顺序拼接，没有文字返回空字符串。"""
    result, _ = _ocr()(_crop(_prepare(image), rect))
    return "".join(line[1] for line in result or [])


def check_image(image: bytes, rect: Rect, text: str, min_similarity: float = 0.8) -> bool:
    """区域内识别到的文字里，有没有 text。

    OCR 偶尔会错字，所以不要求完全相等：在识别结果里滑动一个和 text 等长的窗口，
    任何一处的相似度达到 min_similarity 就算有。
    """
    found, text = _clean(read_text(image, rect)), _clean(text)
    window = len(text)
    for start in range(max(1, len(found) - window + 1)):
        if SequenceMatcher(None, found[start : start + window], text).ratio() >= min_similarity:
            return True
    return False


def check_selected(image: bytes, rects: list[Rect]) -> int:
    """多个选项里，当前选中的是第几个（从 0 开始）。

    选中项是深色底，其他是白底，所以取平均亮度最低的那个区域。
    没有哪一项明显更暗时返回 -1。
    """
    img = cv2.cvtColor(_prepare(image), cv2.COLOR_BGR2GRAY)
    brightness = [float(_crop(img, rect).mean()) for rect in rects]
    darkest = int(np.argmin(brightness))
    others = [b for i, b in enumerate(brightness) if i != darkest]
    if not others or min(others) - brightness[darkest] < MIN_HIGHLIGHT_GAP:
        return -1
    return darkest
