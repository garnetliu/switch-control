"""检查截图内容。

区域用比例坐标 ((左, 上), (右, 下))，数值是占图片宽高的比例，和分辨率无关。
截图保持原始大小，不去黑边、不缩放，直接按比例裁剪。
要用像素数的地方（图标匹配、连通区域大小）都写成占画面高度的比例，用的时候再乘上这张图的高度。
颜色用 OpenCV 的 HSV：H 取 0 到 180，S、V 取 0 到 255。
"""

import re
from difflib import SequenceMatcher
from functools import lru_cache

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from type import Hsv, Rect


def _clean(text: str) -> str:
    """去掉空白和标点，OCR 经常在这些地方不一致。"""
    return re.sub(r"[\s，。！？、,.!?…：:]", "", text)


@lru_cache(maxsize=1)
def _shared_ocr() -> RapidOCR:
    """整个程序共用一个识别器。创建一次要 0.11 秒，不能每张截图都创建。"""
    return RapidOCR()


class ImageChecker:
    """对一张截图做各种检查。截图只解码一次，同一张图的多次检查共用。"""

    def __init__(self, image: bytes):
        """image: 截图的 JPEG 或 PNG 字节。解码失败会抛 ValueError。"""
        self._ocr = _shared_ocr()
        # Switch 的截图本身没有黑边，不去黑边：整屏很暗的画面（比如战败时黑屏上只有一条对话框）
        # 去黑边会把画面内容裁掉，按比例找的范围就全错位了
        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("无法解码图片")
        self._bgr = img
        self._hsv = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2HSV)
        self._gray = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2GRAY)

    @property
    def bgr(self) -> np.ndarray:
        """截图的彩色图（BGR），原始大小。"""
        return self._bgr

    def save(self, path: str) -> None:
        """把截图存成图片文件，格式按扩展名。"""
        cv2.imwrite(path, self.bgr)

    def crop(self, rect: Rect, channel: str = "bgr") -> np.ndarray:
        """按比例裁剪截图。channel: bgr（彩色）、gray（灰度）或 hsv。"""
        image = {"bgr": self._bgr, "gray": self._gray, "hsv": self._hsv}[channel]
        return self._crop(image, rect)

    def _crop(self, img: np.ndarray, rect: Rect) -> np.ndarray:
        h, w = img.shape[:2]
        (left, top), (right, bottom) = rect
        return img[round(top * h) : round(bottom * h), round(left * w) : round(right * w)]

    # ---- 文字 ----

    def read_text(self, rect: Rect) -> str:
        """识别区域内的一行文字，没有文字返回空字符串。

        区域里要正好是一行字：只识别、不先检测文字在哪里，比检测加识别快几十倍
        （真机截图上 0.01 秒对 0.5 秒）。识别结果的置信度低于 0.5 时当作没有字，
        所以空的区域也能直接用来判断「有没有字」。要读多行的区域用 text_lines。
        """
        min_text_score = 0.5
        result, _ = self._ocr(
            self._crop(self._bgr, rect), use_det=False, use_cls=False, use_rec=True
        )
        if not result:
            return ""
        text = str(result[0][0])
        score = float(result[0][1])
        return text.strip() if score >= min_text_score else ""

    def read_line(self, rect: Rect) -> str:
        """只识别、不检测文字位置：rect 里要正好是一行字。读不出返回空字符串。"""
        result, _ = self._ocr(self.crop(rect), use_det=False, use_cls=False, use_rec=True)
        return result[0][0].strip() if result else ""

    def text_lines(self, rect: Rect) -> list[tuple[str, Rect]]:
        """识别区域内的每一行文字，返回 (文字, 这一行文字所在的区域)，从上到下排列。

        返回的区域是整张截图上的比例坐标，可以直接交给 ImageChecker 的其他方法。
        """
        height, width = self.bgr.shape[:2]
        (left, top), _ = rect
        x0, y0 = round(left * width), round(top * height)
        result, _ = self._ocr(self.crop(rect))
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

    def find_options(self, area: Rect) -> list[tuple[str, Rect]]:
        """找出区域里的选项：每一行文字和它在整张截图上的位置。"""
        return self.text_lines(area)

    def find_menu(self, area: Rect) -> tuple[Rect, list[tuple[str, Rect]]] | None:
        """在 area 里找菜单，返回菜单外框和里面的选项；找不到返回 None。

        菜单是画面右侧的白色框：在 area 里找最大的白色连通区域。
        """
        height, width = self.bgr.shape[:2]
        (left, top), (right, bottom) = area
        x0, y0 = round(left * width), round(top * height)
        x1, y1 = min(round(right * width), width), min(round(bottom * height), height)
        mask = cv2.inRange(
            self._hsv[y0:y1, x0:x1],
            (0, 0, 220),
            (180, 30, 255),
        )
        # 文字是深色的，会把白底分开；闭运算把文字的空洞填掉，留下整块菜单。
        # 闭运算的大小是画面高度的 0.023（1080 行的画面上是 25 像素）
        size = max(round(height * 0.023), 3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((size, size), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        x, y, w, h = max((cv2.boundingRect(c) for c in contours), key=lambda r: r[2] * r[3])
        menu = (
            ((x0 + x) / width, (y0 + y) / height),
            ((x0 + x + w) / width, (y0 + y + h) / height),
        )
        return menu, self.find_options(menu)

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
        min_highlight_gap = 40
        brightness = [self.brightness(rect) for rect in rects]
        darkest = int(np.argmin(brightness))
        others = [b for i, b in enumerate(brightness) if i != darkest]
        if not others or min(others) - brightness[darkest] < min_highlight_gap:
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
        # 亮度不超过 50 的像素占比至少 98%，并且亮度的标准差不超过 10
        dark_value, dark_ratio, dark_std = 50, 0.98, 10
        value = self._hsv[:, :, 2]
        return float((value <= dark_value).mean()) >= dark_ratio and float(value.std()) <= dark_std

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
        score, _ = self.match_template_position(rect, template, lower, upper)
        return score

    def match_template_position(
        self,
        rect: Rect,
        template: np.ndarray,
        lower: Hsv | None = None,
        upper: Hsv | None = None,
    ) -> tuple[float, tuple[int, int]]:
        """在区域里找模板，返回最高匹配度和模板左上角相对区域的像素位置。"""
        if lower is not None and upper is not None:
            area = cv2.inRange(self._crop(self._hsv, rect), lower, upper)
        else:
            area = self._crop(self._bgr, rect)
        if area.shape[0] < template.shape[0] or area.shape[1] < template.shape[1]:
            return 0.0, (0, 0)
        result = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        return float(score), (int(location[0]), int(location[1]))

    def match_sprite(self, rect: Rect, sprite: np.ndarray) -> float:
        """区域里的图在 sprite 模板里的最高匹配度。

        用在截图里的小图标和完整精灵图之间比较，区域必须不大于模板。
        """
        area = self.crop(rect)
        if area.shape[0] > sprite.shape[0] or area.shape[1] > sprite.shape[1]:
            return 0.0
        result = cv2.matchTemplate(sprite, area, cv2.TM_CCOEFF_NORMED)
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
