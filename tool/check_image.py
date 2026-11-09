"""检查截图内容。

区域用比例坐标 ((左, 上), (右, 下))，数值是占图片宽高的比例，和分辨率无关。
截图会先去掉黑边、缩放到 1920x1080，再按比例裁剪，见 docs/实测-分辨率定位.md。
颜色用 OpenCV 的 HSV：H 取 0 到 180，S、V 取 0 到 255。
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from typedefs.image import Hsv, Rect

BASE_SIZE = (1920, 1080)
# 行或列的平均亮度不超过这个值，当作黑边
BLACK_BAR = 8
# 只识别一行字时，置信度低于这个值就当作区域里没有字
MIN_TEXT_SCORE = 0.5
# 选中项比其他项至少暗这么多，才认为有明确的选中项
MIN_HIGHLIGHT_GAP = 40
# 黑屏：亮度（V）不超过 DARK_VALUE 的像素占比至少这么多，并且亮度的标准差不超过 DARK_STD
DARK_VALUE = 50
DARK_RATIO = 0.98
DARK_STD = 10


@lru_cache(maxsize=1)
def _ocr() -> RapidOCR:
    return RapidOCR()


def load_template(path: str | Path) -> np.ndarray:
    """读取模板图片，找不到文件会抛 FileNotFoundError。"""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(path)
    return img


def _clean(text: str) -> str:
    """去掉空白和标点，OCR 经常在这些地方不一致。"""
    return re.sub(r"[\s，。！？、,.!?…：:]", "", text)


class ImageChecker:
    """对一张截图做各种检查。截图只解码和缩放一次，同一张图的多次检查共用。"""

    def __init__(self, image: bytes):
        """image: 截图的 JPEG 或 PNG 字节。解码失败会抛 ValueError。"""
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("无法解码图片")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        rows = np.flatnonzero(gray.mean(axis=1) > BLACK_BAR)
        cols = np.flatnonzero(gray.mean(axis=0) > BLACK_BAR)
        if rows.size and cols.size:
            img = img[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
        interpolation = cv2.INTER_AREA if img.shape[1] > BASE_SIZE[0] else cv2.INTER_CUBIC
        self._bgr = cv2.resize(img, BASE_SIZE, interpolation=interpolation)
        self._hsv = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2HSV)
        self._gray = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2GRAY)

    @property
    def bgr(self) -> np.ndarray:
        """去黑边、缩放到 1920x1080 之后的彩色图（BGR）。"""
        return self._bgr

    def crop(self, rect: Rect, channel: str = "bgr") -> np.ndarray:
        """按比例裁剪截图。channel: bgr（彩色）、gray（灰度）或 hsv。"""
        image = {"bgr": self._bgr, "gray": self._gray, "hsv": self._hsv}[channel]
        return self._crop(image, rect)

    @staticmethod
    def _crop(img: np.ndarray, rect: Rect) -> np.ndarray:
        h, w = img.shape[:2]
        (left, top), (right, bottom) = rect
        return img[round(top * h) : round(bottom * h), round(left * w) : round(right * w)]

    # ---- 文字 ----

    def read_text(self, rect: Rect) -> str:
        """识别区域内的一行文字，没有文字返回空字符串。

        区域里要正好是一行字：只识别、不先检测文字在哪里，比检测加识别快几十倍
        （真机截图上 0.01 秒对 0.5 秒）。识别结果的置信度低于 MIN_TEXT_SCORE 时当作没有字，
        所以空的区域也能直接用来判断「有没有字」。要读多行的区域用 tool/image.py 的 text_lines。
        """
        result, _ = _ocr()(self._crop(self._bgr, rect), use_det=False, use_cls=False, use_rec=True)
        if not result:
            return ""
        text, score = result[0]
        return text.strip() if score >= MIN_TEXT_SCORE else ""

    def has_text(self, rect: Rect, text: str, min_similarity: float = 0.8) -> bool:
        """区域内识别到的文字里，有没有 text。

        OCR 偶尔会错字，所以不要求完全相等：在识别结果里滑动一个和 text 等长的窗口，
        任何一处的相似度达到 min_similarity 就算有。
        """
        found, text = _clean(self.read_text(rect)), _clean(text)
        window = len(text)
        for start in range(max(1, len(found) - window + 1)):
            if SequenceMatcher(None, found[start : start + window], text).ratio() >= min_similarity:
                return True
        return False

    # ---- 选中项 ----

    def selected(self, rects: list[Rect]) -> int:
        """多个选项里，当前选中的是第几个（从 0 开始）。

        选中项是深色底，其他是白底，所以取平均亮度最低的那个区域。
        没有哪一项明显更暗时返回 -1。
        """
        brightness = [self.brightness(rect) for rect in rects]
        darkest = int(np.argmin(brightness))
        others = [b for i, b in enumerate(brightness) if i != darkest]
        if not others or min(others) - brightness[darkest] < MIN_HIGHLIGHT_GAP:
            return -1
        return darkest

    # ---- 颜色和亮度 ----

    def brightness(self, rect: Rect) -> float:
        """区域的平均亮度，0 到 255。"""
        return float(self._crop(self._gray, rect).mean())

    def color_ratio(self, rect: Rect, lower: Hsv, upper: Hsv) -> float:
        """区域内 HSV 在 lower 到 upper 之间的像素占比，0 到 1。"""
        mask = cv2.inRange(self._crop(self._hsv, rect), lower, upper)
        return float(mask.mean()) / 255

    def has_color(self, rect: Rect, lower: Hsv, upper: Hsv, min_ratio: float) -> bool:
        """区域内指定颜色的像素占比是否超过 min_ratio。"""
        return self.color_ratio(rect, lower, upper) > min_ratio

    def edge_ratio(self, rect: Rect) -> float:
        """区域内 Canny 边缘像素的占比，0 到 1。

        空白、渐变、大块纯色接近 0，有轮廓和细节的地方更高。用来看画面里的东西有没有画出来。
        """
        edges = cv2.Canny(self._crop(self._gray, rect), 50, 150)
        return float((edges > 0).mean())

    def is_black(self) -> bool:
        """是不是黑屏：几乎整张图都很暗，而且亮度很均匀。只看当前这一张。"""
        value = self._hsv[:, :, 2]
        return float((value <= DARK_VALUE).mean()) >= DARK_RATIO and float(value.std()) <= DARK_STD

    # ---- 模板匹配 ----

    def match_template(
        self,
        rect: Rect,
        template: np.ndarray,
        lower: Hsv | None = None,
        upper: Hsv | None = None,
    ) -> float:
        """在区域里找模板，返回最高的匹配度，0 到 1。

        给了 lower 和 upper 时，先把区域按这个颜色范围转成黑白图再匹配，
        这时 template 也要是同样处理过的单通道图。
        区域比模板小时没法匹配，返回 0。
        """
        if lower is not None and upper is not None:
            area = cv2.inRange(self._crop(self._hsv, rect), lower, upper)
        else:
            area = self._crop(self._bgr, rect)
        if area.shape[0] < template.shape[0] or area.shape[1] < template.shape[1]:
            return 0.0
        result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
        return float(result.max())

    def has_template(
        self,
        rect: Rect,
        template: np.ndarray,
        min_score: float = 0.85,
        lower: Hsv | None = None,
        upper: Hsv | None = None,
    ) -> bool:
        """区域里有没有和模板匹配度达到 min_score 的内容。"""
        return self.match_template(rect, template, lower, upper) >= min_score
