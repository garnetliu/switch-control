"""control_switch.vision.ImageChecker：截图检查。

期望值取自搬迁前 libs.check_image 的运行结果。真机截图放在 tests/images/，其余用生成的图。
"""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from control_switch.types import Hsv, Rect
from control_switch.vision import ImageChecker

IMAGES = Path(__file__).resolve().parents[1] / "images"
ROUTE = IMAGES / "路线上的界面-要走哪条路.jpg"
RESEARCHER = IMAGES / "研究员问换不换.jpg"

# 「要走哪条路？」所在的那一行、整个对话框
DIALOG_LINE: Rect = ((0.27, 0.81), (0.6, 0.88))
DIALOG: Rect = ((0.25, 0.80), (0.75, 0.95))
FULL: Rect = ((0.0, 0.0), (1.0, 1.0))
WHITE_LOWER: Hsv = (0, 0, 220)
WHITE_UPPER: Hsv = (180, 30, 255)
RED_LOWER: Hsv = (0, 100, 100)
RED_UPPER: Hsv = (10, 255, 255)


def encode(image: np.ndarray, ext: str = ".png") -> bytes:
    ok, buffer = cv2.imencode(ext, image)
    assert ok
    return buffer.tobytes()


def black_checker(height: int = 720, width: int = 1280) -> ImageChecker:
    return ImageChecker(encode(np.zeros((height, width, 3), np.uint8)))


def white_checker(height: int = 100, width: int = 200) -> ImageChecker:
    return ImageChecker(encode(np.full((height, width, 3), 255, np.uint8)))


@pytest.fixture(scope="module")
def route_bytes() -> bytes:
    return ROUTE.read_bytes()


@pytest.fixture(scope="module")
def route(route_bytes: bytes) -> ImageChecker:
    return ImageChecker(route_bytes)


@pytest.fixture(scope="module")
def researcher() -> ImageChecker:
    return ImageChecker(RESEARCHER.read_bytes())


# ---- 构造、bgr、crop ----


def test_init_non_image_bytes_raises_value_error() -> None:
    """非空但不是图片的字节：抛 ValueError。"""
    with pytest.raises(ValueError):
        ImageChecker(b"not an image")


def test_bgr_keeps_original_size(route: ImageChecker) -> None:
    """bgr 是原始大小的彩色图（720x1280，三通道）。"""
    assert route.bgr.shape == (720, 1280, 3)


def test_crop_size_follows_ratio(route: ImageChecker) -> None:
    """crop 按比例裁剪：((0.25, 0.5), (0.75, 1.0)) 在 1280x720 上是 640 宽、360 高。"""
    assert route.crop(((0.25, 0.5), (0.75, 1.0))).shape == (360, 640, 3)


def test_crop_bgr_and_hsv_are_three_channels() -> None:
    """channel 取 bgr、hsv：三通道。"""
    checker = white_checker()
    rect: Rect = ((0.0, 0.0), (0.5, 0.5))
    assert checker.crop(rect, "bgr").shape == (50, 100, 3)
    assert checker.crop(rect, "hsv").shape == (50, 100, 3)


def test_crop_gray_is_two_dimensional() -> None:
    """channel 取 gray：二维。"""
    assert white_checker().crop(((0.0, 0.0), (0.5, 0.5)), "gray").shape == (50, 100)


def test_crop_unknown_channel_raises_key_error() -> None:
    """channel 取不认识的值：抛 KeyError。"""
    with pytest.raises(KeyError):
        white_checker().crop(FULL, "rgb")


# ---- save ----


def test_save_jpg_to_jpg_writes_original_bytes(
    route: ImageChecker, route_bytes: bytes, tmp_path: Path
) -> None:
    """原图是 jpg、存成 .jpg：写出的文件和原始字节完全一样。"""
    target = tmp_path / "out.jpg"
    route.save(str(target))
    assert target.read_bytes() == route_bytes


def test_save_jpg_to_png_reencodes_pixels(route: ImageChecker, tmp_path: Path) -> None:
    """原图是 jpg、存成 .png：重新编码，读回来的像素和 bgr 一样。"""
    target = tmp_path / "out.png"
    route.save(str(target))
    loaded = cv2.imread(str(target))
    assert loaded is not None
    assert np.array_equal(loaded, route.bgr)


def test_save_png_to_jpg_reencodes(tmp_path: Path) -> None:
    """原图是 png、存成 .jpg：重新编码，写出的文件和原始字节不一样。"""
    raw = encode(np.full((50, 50, 3), 120, np.uint8), ".png")
    target = tmp_path / "out.jpg"
    ImageChecker(raw).save(str(target))
    written = target.read_bytes()
    assert written != raw
    assert written[:2] == b"\xff\xd8"


# ---- 文字 ----


def test_read_text_black_region_returns_empty_string() -> None:
    """全黑图片上的区域没有文字：返回空字符串。"""
    assert black_checker().read_text(((0.1, 0.1), (0.5, 0.2))) == ""


def test_read_text_on_dialog_line_returns_route_question(route: ImageChecker) -> None:
    """对话框那一行读出「要走哪条路？」。"""
    assert route.read_text(DIALOG_LINE) == "要走哪条路？"


def test_read_text_low_confidence_returns_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """识别结果的置信度 0.4 低于 0.5：当作没有字，返回空字符串。"""
    checker = black_checker()

    def fake_ocr(*args: Any, **kwargs: Any) -> tuple[list[list[Any]], None]:
        return [["字", 0.4]], None

    monkeypatch.setattr(checker, "_ocr", fake_ocr)
    assert checker.read_text(((0.1, 0.1), (0.5, 0.2))) == ""


def test_read_text_confidence_at_threshold_returns_stripped_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """置信度正好 0.5：保留识别结果，并去掉首尾空白。"""
    checker = black_checker()

    def fake_ocr(*args: Any, **kwargs: Any) -> tuple[list[list[Any]], None]:
        return [[" 字 ", 0.5]], None

    monkeypatch.setattr(checker, "_ocr", fake_ocr)
    assert checker.read_text(((0.1, 0.1), (0.5, 0.2))) == "字"


def test_read_text_no_result_returns_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """识别没有结果时 read_text 返回空字符串。"""
    checker = black_checker()

    def fake_ocr(*args: Any, **kwargs: Any) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(checker, "_ocr", fake_ocr)
    assert checker.read_text(((0.1, 0.1), (0.5, 0.2))) == ""


def test_read_line_on_dialog_line_returns_route_question(route: ImageChecker) -> None:
    """read_line 在对话框那一行读出「要走哪条路？」。"""
    assert route.read_line(DIALOG_LINE) == "要走哪条路？"


def test_read_line_no_result_returns_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """识别没有结果时 read_line 返回空字符串。"""
    checker = black_checker()

    def fake_ocr(*args: Any, **kwargs: Any) -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(checker, "_ocr", fake_ocr)
    assert checker.read_line(((0.1, 0.1), (0.5, 0.2))) == ""


def test_has_text_finds_route_question_in_dialog_line(route: ImageChecker) -> None:
    """对话框那一行能找到「要走哪条路」。"""
    assert route.has_text(DIALOG_LINE, "要走哪条路") is True


def test_has_text_does_not_find_unrelated_sentence(route: ImageChecker) -> None:
    """对话框那一行找不到无关的话。"""
    assert route.has_text(DIALOG_LINE, "今天天气真好") is False


def test_text_lines_returns_dialog_line_with_page_ratio_rect(route: ImageChecker) -> None:
    """text_lines 返回对话框里的一行文字，区域是整张图上的比例坐标。"""
    lines = route.text_lines(DIALOG)
    assert len(lines) == 1
    text, ((left, top), (right, bottom)) = lines[0]
    assert text == "要走哪条路？"
    assert (left, top) == pytest.approx((0.27734375, 0.8138888888888889))
    assert (right, bottom) == pytest.approx((0.40546875, 0.8666666666666667))


def test_text_lines_black_image_returns_empty_list() -> None:
    """没有文字的图上 text_lines 返回空列表。"""
    assert black_checker().text_lines(FULL) == []


def test_text_lines_sorted_top_to_bottom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OCR 结果乱序时，text_lines 按区域的上边从上到下排列。"""
    checker = black_checker(100, 200)
    low = [[0, 60], [20, 60], [20, 80], [0, 80]]
    high = [[0, 10], [20, 10], [20, 30], [0, 30]]

    def fake_ocr(*args: Any, **kwargs: Any) -> tuple[list[list[Any]], None]:
        return [[low, "下", 0.9], [high, "上", 0.9]], None

    monkeypatch.setattr(checker, "_ocr", fake_ocr)
    lines = checker.text_lines(FULL)
    assert [text for text, _ in lines] == ["上", "下"]
    assert lines[0][1] == ((0.0, 0.1), (0.1, 0.3))
    assert lines[1][1] == ((0.0, 0.6), (0.1, 0.8))


def test_find_options_returns_same_as_text_lines(route: ImageChecker) -> None:
    """find_options 返回区域内每一行文字和它在整张图上的位置，结果和旧代码一样。"""
    options = route.find_options(DIALOG)
    assert [text for text, _ in options] == ["要走哪条路？"]
    assert options == route.text_lines(DIALOG)


# ---- find_menu ----


def test_find_menu_returns_frame_and_options(researcher: ImageChecker) -> None:
    """研究员问换不换：在右半边能找到菜单，菜单外框和两个选项和旧代码一样。"""
    found = researcher.find_menu(((0.5, 0.0), (1.0, 1.0)))
    assert found is not None
    menu, options = found
    (left, top), (right, bottom) = menu
    assert (left, top) == pytest.approx((0.67109375, 0.625))
    assert (right, bottom) == pytest.approx((0.828125, 0.7805555555555556))
    assert [text for text, _ in options] == [">是", "足否"]
    assert options[0][1][0] == pytest.approx((0.67109375, 0.6430555555555556))
    assert options[0][1][1] == pytest.approx((0.72265625, 0.7069444444444445))
    assert options[1][1][0] == pytest.approx((0.69140625, 0.6777777777777778))
    assert options[1][1][1] == pytest.approx((0.72109375, 0.7569444444444444))


def test_find_menu_black_image_returns_none() -> None:
    """全黑的图上找不到菜单：返回 None。"""
    assert black_checker().find_menu(((0.5, 0.0), (1.0, 1.0))) is None


# ---- 颜色和亮度 ----


def test_brightness_white_image_is_255() -> None:
    """全白的图亮度是 255。"""
    assert white_checker().brightness(FULL) == 255.0


def test_brightness_black_image_is_0() -> None:
    """全黑的图亮度是 0。"""
    assert black_checker(10, 10).brightness(FULL) == 0.0


def test_edge_ratio_white_image_is_0() -> None:
    """全白的图没有边缘，edge_ratio 是 0。"""
    assert white_checker().edge_ratio(FULL) == 0.0


def test_edge_ratio_image_with_outline_is_positive() -> None:
    """有轮廓的图 edge_ratio 大于 0。"""
    image = np.zeros((100, 200, 3), np.uint8)
    image[:, 100:] = 255
    assert ImageChecker(encode(image)).edge_ratio(FULL) > 0.0


def _half_red_checker() -> ImageChecker:
    image = np.full((100, 200, 3), 255, np.uint8)
    image[:, :100] = (0, 0, 255)  # BGR 红色
    return ImageChecker(encode(image))


def test_color_ratio_half_red_half_white_is_half() -> None:
    """左半红、右半白：红色的 color_ratio 是 0.5。"""
    assert _half_red_checker().color_ratio(FULL, RED_LOWER, RED_UPPER) == 0.5


def test_has_color_ratio_equal_to_min_ratio_is_false() -> None:
    """占比正好等于 min_ratio：has_color 是 False（要超过才算）。"""
    assert _half_red_checker().has_color(FULL, RED_LOWER, RED_UPPER, 0.5) is False


def test_has_color_ratio_above_min_ratio_is_true() -> None:
    """占比 0.5 超过 min_ratio 0.4：has_color 是 True。"""
    assert _half_red_checker().has_color(FULL, RED_LOWER, RED_UPPER, 0.4) is True


def test_is_black_generated_black_image_is_true() -> None:
    """自己生成的全黑图：is_black 是 True。"""
    assert black_checker().is_black() is True


def test_is_black_real_screenshot_is_false(route: ImageChecker) -> None:
    """真机截图：is_black 是 False。"""
    assert route.is_black() is False


# ---- selected ----


def _blocks_checker(values: list[int]) -> tuple[ImageChecker, list[Rect]]:
    """宽 300、高 100 的图，横向分成 3 块，每块填一个灰度。"""
    image = np.full((100, 300, 3), 255, np.uint8)
    for index, value in enumerate(values):
        image[:, index * 100 : (index + 1) * 100] = value
    rects: list[Rect] = [((i / 3, 0.0), ((i + 1) / 3, 1.0)) for i in range(3)]
    return ImageChecker(encode(image)), rects


def test_selected_returns_index_of_darkest_block() -> None:
    """一块深色、其余白色：返回深色那一块的序号。"""
    checker, rects = _blocks_checker([255, 20, 255])
    assert checker.selected(rects) == 1


def test_selected_gap_below_40_returns_minus_one() -> None:
    """几块亮度差不到 40（230 对 255，差 25）：返回 -1。"""
    checker, rects = _blocks_checker([255, 230, 255])
    assert checker.selected(rects) == -1


def test_selected_single_rect_returns_minus_one() -> None:
    """只给一个区域：返回 -1。"""
    checker, rects = _blocks_checker([0, 255, 255])
    assert checker.selected(rects[:1]) == -1


# ---- 模板匹配 ----

# 截图里一块白色箭头所在的像素范围，模板从这里裁，区域包含它
TEMPLATE_REGION: Rect = ((0.3, 0.35), (0.6, 0.65))
TEMPLATE_BOX = (slice(290, 340), slice(490, 545))
# 模板左上角在区域里的位置：区域左上角是 (384, 252)，模板左上角是 (490, 290)
TEMPLATE_POSITION = (106, 38)


def _template(route: ImageChecker) -> np.ndarray:
    return route.bgr[TEMPLATE_BOX].copy()


def _mask_template(route: ImageChecker) -> np.ndarray:
    hsv = cv2.cvtColor(route.bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv[TEMPLATE_BOX], WHITE_LOWER, WHITE_UPPER)


def test_match_template_cropped_from_region_scores_near_one(route: ImageChecker) -> None:
    """从截图里裁一块当模板，在包含它的区域里匹配度接近 1。"""
    assert route.match_template(TEMPLATE_REGION, _template(route)) == pytest.approx(1.0, abs=1e-3)


def test_match_template_position_is_top_left_relative_to_region(route: ImageChecker) -> None:
    """返回的位置是模板左上角相对区域的像素位置。"""
    score, position = route.match_template_position(TEMPLATE_REGION, _template(route))
    assert score == pytest.approx(1.0, abs=1e-3)
    assert position == TEMPLATE_POSITION


def test_match_template_region_smaller_than_template_returns_zero(route: ImageChecker) -> None:
    """区域比模板小：match_template 返回 0。"""
    assert route.match_template(((0.1, 0.1), (0.12, 0.12)), _template(route)) == 0.0


def test_match_template_position_region_smaller_than_template_returns_zero_origin(
    route: ImageChecker,
) -> None:
    """区域比模板小：match_template_position 返回 0 和 (0, 0)。"""
    result = route.match_template_position(((0.1, 0.1), (0.12, 0.12)), _template(route))
    assert result == (0.0, (0, 0))


def test_match_template_with_color_range_matches_binary_template(route: ImageChecker) -> None:
    """给了 lower、upper：区域按颜色转成黑白图再匹配，同样处理过的单通道模板匹配度接近 1。"""
    template = _mask_template(route)
    assert template.ndim == 2
    score = route.match_template(TEMPLATE_REGION, template, WHITE_LOWER, WHITE_UPPER)
    assert score == pytest.approx(1.0, abs=1e-3)


def test_match_template_position_with_color_range_returns_position(route: ImageChecker) -> None:
    """给了 lower、upper：返回的位置同样是模板左上角相对区域的像素位置。"""
    template = _mask_template(route)
    score, position = route.match_template_position(
        TEMPLATE_REGION, template, WHITE_LOWER, WHITE_UPPER
    )
    assert score == pytest.approx(1.0, abs=1e-3)
    assert position == TEMPLATE_POSITION


def test_has_template_min_score_below_score_is_true(route: ImageChecker) -> None:
    """min_score 比匹配度低：has_template 是 True。"""
    assert route.has_template(TEMPLATE_REGION, _template(route), min_score=0.9) is True


def test_has_template_min_score_above_score_is_false(route: ImageChecker) -> None:
    """min_score 比匹配度高（匹配度不超过 1，门槛取 1.1）：has_template 是 False。"""
    assert route.has_template(TEMPLATE_REGION, _template(route), min_score=1.1) is False


def test_has_template_default_min_score_matches_cropped_template(route: ImageChecker) -> None:
    """不给 min_score（默认 0.85）：裁出来的模板能匹配到。"""
    assert route.has_template(TEMPLATE_REGION, _template(route)) is True


def test_has_template_with_color_range(route: ImageChecker) -> None:
    """给了 lower、upper 的 has_template：黑白模板能匹配到。"""
    template = _mask_template(route)
    assert route.has_template(TEMPLATE_REGION, template, 0.9, WHITE_LOWER, WHITE_UPPER) is True


def test_match_sprite_small_region_inside_sprite_scores_near_one(route: ImageChecker) -> None:
    """截图一大块当模板，区域取这一块里面的一小块：匹配度接近 1。"""
    sprite = route.bgr[100:400, 100:500].copy()
    small: Rect = ((200 / 1280, 200 / 720), (300 / 1280, 300 / 720))
    assert route.match_sprite(small, sprite) == pytest.approx(1.0, abs=1e-3)


def test_match_sprite_region_larger_than_sprite_returns_zero(route: ImageChecker) -> None:
    """区域比模板大：match_sprite 返回 0。"""
    sprite = route.bgr[100:400, 100:500].copy()
    assert route.match_sprite(FULL, sprite) == 0.0


# ---- 找到的问题 ----


def test_init_empty_bytes_raises_value_error() -> None:
    """空字节也是解码失败，要和 docstring 说的一样抛 ValueError。

    防的是：ImageChecker(b"") 现在抛的是 cv2.error（不是 ValueError 的子类），
    按文档写 `except ValueError` 的调用方接不住。原来就有的问题。
    """
    with pytest.raises(ValueError):
        ImageChecker(b"")


def test_save_reencoded_to_missing_directory_does_not_fail_silently(tmp_path: Path) -> None:
    """重新编码存图写不出文件时要报错，不能悄悄返回。

    防的是：save 走 cv2.imwrite 的分支（png 原图，或存成 .png）时，目录不存在、没权限等
    写失败只返回 False，save 不检查，文件没写出来也不报错；同样的情况走 jpg 原字节分支
    会抛 FileNotFoundError。原来就有的问题。
    """
    checker = ImageChecker(encode(np.full((20, 20, 3), 120, np.uint8), ".png"))
    target = tmp_path / "missing" / "out.png"
    try:
        checker.save(str(target))
    except Exception:
        return
    assert target.exists(), "save 没有报错，但文件没有写出来"
