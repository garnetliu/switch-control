"""拿蛋：开野餐、做三明治、在篮子前收蛋，收够了退回野外去孵蛋。

做三明治和收蛋照 PokemonAutomation 的 eat_egg_sandwich_at_picnic、collect_eggs_after_sandwich，
从 egg 脚本搬过来。
"""

import logging
import math
import re
import time
from collections.abc import Callable
from functools import cache
from importlib.resources import files
from typing import Literal

import cv2
import numpy as np

from control_switch.flow import capture, press_until, wait_until
from control_switch.games.sv import actions
from control_switch.games.sv import verify as sv_verify
from control_switch.types import Press, Push, Rect
from control_switch.vision import ImageChecker

from ..session import IncubatorSession
from ..types import TeamType

# 整个画面
FULL_SCREEN: Rect = ((0.0, 0.0), (1.0, 1.0))

BasketState = Literal["prompt", "dialog", "none", "unknown"]
SandwichState = Literal["picnic", "menu", "recipes", "dialog", "unknown"]


def fetch(sw: IncubatorSession) -> str:
    """还要拿 max_eggs 减 eggs 个蛋：0 个直接去孵蛋；不是 0 就退回野外、开野餐、做三明治、收蛋，收够了退回野外去孵蛋。"""
    need = sw.config.max_eggs - sw.eggs
    logging.info(f"已经有 {sw.eggs} 个蛋，还要拿 {need} 个")
    if need <= 0:
        return TeamType.HATCH
    actions.exit_to_overworld(sw)
    actions.open_picnic(sw)
    if not _eat_egg_sandwich(sw):
        raise RuntimeError(
            f"做不了三明治：没有食谱 {sw.config.recipe_number}（超级花生酱三明治）或者材料不够"
        )
    collected = _collect_eggs(sw, need)
    sw.eggs += collected
    logging.info(f"拿到 {collected} 个蛋，现在一共 {sw.eggs} 个")
    actions.exit_to_overworld(sw)
    return TeamType.HATCH


def _watch(
    sw: IncubatorSession, condition: Callable[[ImageChecker], bool], seconds: float, what: str
) -> ImageChecker | None:
    """看画面最多 seconds 秒，condition 满足就返回那张截图；一直没满足返回 None，不报错。"""
    deadline = time.monotonic() + seconds
    while True:
        image = capture(sw, what)
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            return None
        time.sleep(sw.config.wait.interval)


# ---- 桌子前和食谱 ----


def _eat_egg_sandwich(sw: IncubatorSession) -> bool:
    """走到桌子前做超级花生酱三明治，做完吃掉。没有食谱、材料不够时返回 False。"""
    # 开了野餐，往前走到桌子前
    sw.follow((Push(0.0, 1.0, 0.24, 0.32),))
    _clear_mons_in_front(sw)
    if not _enter_recipe_list(sw):
        return False
    if not _select_recipe(sw, sw.config.recipe_number):
        return False
    _run_sandwich_maker(sw)
    return True


def _is_table_menu_arrow(image: ImageChecker, sw: IncubatorSession) -> bool:
    """桌子的菜单（做料理、更改配置……）里，选中第一项「做料理」的箭头。"""
    return sv_verify.gradient_arrow(image, ((0.7161, 0.3213), (0.7625, 0.4139)), sw.config)


def _recipe_rect(origin: tuple[float, float], size: tuple[float, float], i: int) -> Rect:
    """食谱列表里第 i 格（两列三行，从左到右、从上到下数）的某个小框；两格之间横向隔 0.26、纵向隔 0.277。"""
    column, row = i % 2, i // 2
    left, top = origin[0] + column * 0.26, origin[1] + row * 0.277
    return ((left, top), (left + size[0], top + size[1]))


def _selected_recipe_cell(image: ImageChecker, sw: IncubatorSession) -> int:
    """食谱列表里选中的是这一页第几格（0 到 5）；没有选中的箭头，或者不止一个，返回 -1。"""
    found = [
        i
        for i in range(6)
        if sv_verify.gradient_arrow(
            image, _recipe_rect((0.112, 0.0731), (0.0521, 0.0825), i), sw.config
        )
    ]
    return found[0] if len(found) == 1 else -1


def _is_pick_arrow(image: ImageChecker, sw: IncubatorSession) -> bool:
    """选三明治签子的界面：选中第一根签子的箭头。"""
    return sv_verify.gradient_arrow(image, ((0.0208, 0.1611), (0.0672, 0.2537)), sw.config)


def _read_recipe_number(image: ImageChecker, rect: Rect) -> int:
    """读食谱左下角的编号，认不出是 0。编号是白色的粗体数字：白色变黑、其余变白，放大 3 倍、加白边再认。"""
    gray = image.crop(rect, "gray")
    black_on_white = np.where(gray >= 180, 0, 255).astype(np.uint8)
    enlarged = cv2.resize(black_on_white, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    padded = cv2.copyMakeBorder(enlarged, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    ok, encoded = cv2.imencode(".png", padded)
    if not ok:
        return 0
    digits = re.sub(r"\D", "", ImageChecker(encoded.tobytes()).read_text(FULL_SCREEN))
    number = int(digits) if digits else 0
    # 食谱一共 151 个
    return number if 0 < number <= 151 else 0


def _recipe_numbers(image: ImageChecker) -> list[int]:
    """食谱列表这一页六格的编号，认不出（没有食谱、材料不够是半透明的）是 0。"""
    numbers = [
        _read_recipe_number(image, _recipe_rect((0.015, 0.240), (0.042, 0.048), i))
        for i in range(6)
    ]
    # 个别认错的：前后两格差 2，中间这格就是前一格加 1
    for i in range(1, len(numbers) - 1):
        before, after = numbers[i - 1], numbers[i + 1]
        if before > 0 and after > 0 and before + 2 == after:
            numbers[i] = before + 1
    return numbers


def _sandwich_state(sw: IncubatorSession) -> SandwichState:
    """看桌子前现在是什么画面，最多看 30 秒：回到了野餐、桌子菜单、食谱列表、对话，或者认不出。"""
    config = sw.config
    deadline = time.monotonic() + 30.0
    while True:
        image = capture(sw, "桌子前")
        if sv_verify.is_picnic(image, config):
            return "picnic"
        if _is_table_menu_arrow(image, sw):
            return "menu"
        if _selected_recipe_cell(image, sw) != -1:
            return "recipes"
        if sv_verify.is_dialog(image, config):
            return "dialog"
        if time.monotonic() >= deadline:
            return "unknown"
        time.sleep(config.wait.interval)


def _enter_recipe_list(sw: IncubatorSession) -> bool:
    """在桌子前打开食谱列表，打开了返回 True；选了「做料理」之后出了对话（没有材料）返回 False。

    按 A 之后等 0.8 秒；最多 60 秒。
    """
    logging.info("在桌子前打开食谱列表")
    sw.click("A", 0.8)
    start = time.monotonic()
    opened_menu = False
    while True:
        if time.monotonic() - start > 60.0:
            raise TimeoutError("60 秒了还是没打开食谱列表")
        state = _sandwich_state(sw)
        if state == "picnic":
            logging.info("回到了野餐的画面，第一下 A 可能被吞了，往前走一点再按 A")
            sw.follow((Push(0.0, 1.0, 0.8, 0.32),))
            sw.click("A", 0.8)
        elif state == "menu":
            logging.info("看到「做料理」的选择箭头，按 A 进食谱列表")
            opened_menu = True
            sw.click("A", 0.8)
        elif state == "recipes":
            logging.info("看到食谱列表")
            # 等列表画完
            time.sleep(1.0)
            return True
        elif state == "dialog":
            if opened_menu:
                logging.warning("选了「做料理」之后出了对话，没有材料")
                return False
            sw.click("A", 0.8)
        else:
            raise RuntimeError("30 秒了还是认不出桌子前是什么画面，进不了食谱列表")


def _select_recipe(sw: IncubatorSession, target: int) -> bool:
    """在食谱列表里选中编号 target 的食谱，按 A 进选签子的界面、再按 A 开始做。

    找到了返回 True；目标应该在这一页却没有（材料不够，食谱是半透明的）、往下翻 100 次也没有，返回 False。
    """
    logging.info(f"在食谱列表里找食谱 {target}")
    for _ in range(100):
        # 翻页之后等画面稳定
        time.sleep(0.2)
        numbers = _recipe_numbers(capture(sw, "食谱的编号"))
        logging.info(f"这一页的食谱编号：{numbers}")
        shown = [number for number in numbers if number > 0]
        low = min(shown, default=0)
        if 0 < low <= target <= max(numbers):
            if target not in numbers:
                logging.warning(f"食谱 {target} 不在这一页，应该是材料不够")
                return False
            target_cell = numbers.index(target)
            selected_cell = _wait_selected_recipe_cell(sw)
            if target_cell == selected_cell:
                logging.info(f"选中了食谱 {target}")
                _start_sandwich(sw)
                return True
            if target_cell == selected_cell + 1:
                sw.click("DRIGHT", 0.48)
                continue
        sw.click("DDOWN", 0.48)
    logging.warning(f"翻了 100 次，还是没找到食谱 {target}")
    return False


def _wait_selected_recipe_cell(sw: IncubatorSession) -> int:
    """食谱列表里选中的是这一页第几格，最多等 10 秒，看不到选中的箭头就报错。"""
    try:
        image = wait_until(
            sw,
            lambda s: _selected_recipe_cell(s, sw) >= 0,
            "食谱列表里选中的箭头",
            timeout=10.0,
        )
    except TimeoutError as error:
        raise RuntimeError("食谱列表里看不到选中食谱的箭头") from error
    return _selected_recipe_cell(image, sw)


def _start_sandwich(sw: IncubatorSession) -> None:
    """选中食谱之后：按 A 进选签子的界面，再按 A 开始做；画面 3 秒还在原处就是那一下被吞了，再按。"""
    sw.click("A", 1.04)
    while (
        _watch(
            sw,
            lambda s: _selected_recipe_cell(s, sw) >= 0 or _is_pick_arrow(s, sw),
            3.0,
            "选食谱之后的画面",
        )
        is not None
    ):
        sw.click("A", 1.04)
    logging.info("进了做三明治的画面")


# ---- 做三明治 ----


@cache
def _hand_template(kind: str) -> np.ndarray:
    """手的模板：白色的部分是 1，其余是 0。kind 是 "free"（空手）或 "grabbing"（抓着东西）。"""
    path = files("control_switch.games.sv") / "data" / f"sandwich_hand_{kind}.png"
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"读不到手的模板 {path}")
    return (template > 0).astype(np.uint8)


def _hand_in_image(image: ImageChecker, kind: str, area: Rect) -> tuple[float, float] | None:
    """在 area 里找做三明治的手，返回手的中心（占画面宽高的比例）；没有返回 None。

    手是白色的、有黑边：找白色的连通区域，大小、宽高比、白色占外框的比例、形状都和模板差不多的就是手
    （上游 SandwichHandMatcher）。空手至少占画面的 0.00193，抓着东西的至少 0.00174；
    宽高比和白色比例的误差不超过 15%，和模板形状不一样的像素不超过 10%。
    """
    template = _hand_template(kind)
    min_ratio = 0.00193 if kind == "free" else 0.00174
    image.mark(area)
    bgr = image.bgr
    height, width = bgr.shape[:2]
    (left, top), (right, bottom) = area
    x0, y0 = round(left * width), round(top * height)
    x1, y1 = round(right * width), round(bottom * height)
    mask = cv2.inRange(bgr[y0:y1, x0:x1], (150, 150, 150), (255, 255, 255))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    template_aspect = template.shape[1] / template.shape[0]
    template_fill = float(template.mean())
    best: tuple[float, tuple[float, float]] | None = None
    for i in range(1, count):
        x, y, w, h, size = (int(value) for value in stats[i])
        if size < min_ratio * height * width:
            continue
        if abs(w / h / template_aspect - 1) > 0.15:
            continue
        if abs(size / (w * h) / template_fill - 1) > 0.15:
            continue
        piece = (labels[y : y + h, x : x + w] == i).astype(np.uint8)
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_NEAREST)
        mismatch = float(np.abs(resized.astype(float) - piece.astype(float)).mean())
        if mismatch > 0.1:
            continue
        center = ((x0 + float(centroids[i][0])) / width, (y0 + float(centroids[i][1])) / height)
        if best is None or mismatch < best[0]:
            best = (mismatch, center)
    return None if best is None else best[1]


def _is_plate_label_yellow(image: ImageChecker) -> bool:
    """盘子的标签是黄色：从盘子里抓着东西时标签会变黄，没抓着（盘子空了）不变。黄色至少占画面的 0.0000965。"""
    yellow = cv2.inRange(
        image.crop(((0.397, 0.268), (0.600, 0.312))), (0, 161, 180), (100, 255, 255)
    )
    height, width = image.bgr.shape[:2]
    return int(np.count_nonzero(yellow)) >= 0.0000965 * height * width


def _run_sandwich_maker(sw: IncubatorSession) -> None:
    """做三明治：把盘子里的香蕉一片一片放到面包上，放完加上面包、插签子，吃掉。

    照上游 run_sandwich_maker，只做一种材料（香蕉）、一个盘子（正中间）：
    每一片都是空手找到盘子上方、按住 A 抓起、抓着移到目标框、松开 A 放下。
    """
    # 最开始手所在的框；中间的盘子（上面的标签）的框；三片香蕉要放的框
    initial: Rect = ((0.440, 0.455), (0.552, 0.634))
    plate: Rect = ((0.455, 0.130), (0.545, 0.160))
    targets: tuple[Rect, ...] = (
        ((0.386, 0.507), (0.446, 0.562)),
        ((0.470, 0.507), (0.530, 0.562)),
        ((0.554, 0.507), (0.614, 0.562)),
    )
    logging.info("开始做三明治")
    try:
        wait_until(
            sw,
            lambda s: _hand_in_image(s, "free", initial) is not None,
            "做三明治时最开始的手",
            timeout=30.0,
        )
    except TimeoutError as error:
        raise RuntimeError("做三明治一开始就没找到手") from error
    # 等盘子的标签出来
    time.sleep(2.4)
    _move_hand(sw, "free", False, initial, initial)
    _move_hand(sw, "grabbing", True, FULL_SCREEN, initial)

    placed = 0
    while placed < len(targets):
        end, _ = _move_hand(sw, "free", False, FULL_SCREEN, plate)
        end, plate_yellow = _move_hand(
            sw, "grabbing", True, _expand_box(end), targets[placed], check_label=True
        )
        if not plate_yellow:
            logging.warning("抓着的时候盘子的标签没变黄，当作盘子空了")
            break
        placed += 1
        logging.info(f"放好了第 {placed} 片香蕉")

    # 放完香蕉等面包出来
    time.sleep(0.5)
    image = _watch(
        sw,
        lambda s: _hand_in_image(s, "grabbing", FULL_SCREEN) is not None,
        30.0,
        "上面的面包",
    )
    if image is None:
        raise RuntimeError("放完香蕉之后没看到抓着上面面包的手")
    location = _hand_in_image(image, "grabbing", FULL_SCREEN)
    assert location is not None
    _move_hand(sw, "grabbing", False, _expand_box(_hand_box(location)), plate)
    # 加了面包之后连按 A 5 秒插签子
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        sw.click("A", 0.2)
    logging.info("三明治做好了")
    _finish_eating(sw)


def _finish_eating(sw: IncubatorSession) -> None:
    """吃三明治：一直按 A，直到回到野餐的画面；认到之后等 1 秒再看一次，还在才算。最多 80 秒。"""
    config = sw.config
    deadline = time.monotonic() + 80.0
    while True:
        press_until(
            sw,
            lambda: sw.click("A", 0),
            lambda s: sv_verify.is_picnic(s, config),
            "吃完三明治回到野餐",
            timeout=max(deadline - time.monotonic(), 0.0),
        )
        time.sleep(1.0)
        if sv_verify.is_picnic(capture(sw, "吃完了吗"), config):
            logging.info("吃完了，回到野餐")
            return


def _hand_box(location: tuple[float, float]) -> Rect:
    """以手的中心为中心、手那么大（宽 0.071、高 0.106）的框（上游 hand_location_to_box）。"""
    x, y = location
    return ((x - 0.0355, y - 0.053), (x + 0.0355, y + 0.053))


def _expand_box(area: Rect) -> Rect:
    """把手的框往外扩，下一次在这里找手（上游 expand_box）：左上角往外扩 1.5 倍宽高，宽高变成 4 倍。"""
    (left, top), (right, bottom) = area
    width, height = right - left, bottom - top
    x = max(0.0, left - width * 1.5)
    y = max(0.0, top - height * 1.5)
    return ((x, y), (x + min(width * 4, 1.0 - x), y + min(height * 4, 1.0 - y)))


def _find_hand(
    sw: IncubatorSession, kind: str, area: Rect, seconds: float
) -> tuple[tuple[float, float], ImageChecker] | None:
    """在 area 里找手，最多找 seconds 秒；area 里没有就再在整个画面里找一次。返回手的中心和那张截图。"""
    deadline = time.monotonic() + seconds
    while True:
        image = capture(sw, "找手")
        location = _hand_in_image(image, kind, area)
        if location is None and area != FULL_SCREEN:
            location = _hand_in_image(image, kind, FULL_SCREEN)
        if location is not None:
            return location, image
        if time.monotonic() >= deadline:
            return None
        time.sleep(sw.config.wait.interval)


def _recover_hand(
    sw: IncubatorSession, kind: str, pressing_a: bool
) -> tuple[tuple[float, float], ImageChecker]:
    """5 秒没找到手：手可能在屏幕边上。往右下推到头（4 秒）再往左推一点（0.8 秒），每次推完等 0.8 秒，
    然后在整个画面里找 1 秒。找不到抛 RuntimeError。"""
    logging.info("没找到手，把它移到画面中间再在整个画面里找")
    for x, y, seconds in ((1.0, -1.0, 4.0), (-1.0, 0.0, 0.8)):
        sw.push("LEFT", x, y, seconds)
        time.sleep(0.8)
    found = _find_hand(sw, kind, FULL_SCREEN, 1.0)
    if found is None:
        raise RuntimeError(f"移到画面中间之后还是没找到{'抓着东西的' if pressing_a else ''}手")
    return found


def _move_hand(
    sw: IncubatorSession,
    kind: str,
    pressing_a: bool,
    start: Rect,
    end: Rect,
    check_label: bool = False,
) -> tuple[Rect, bool]:
    """把手从 start 里移到 end（上游 move_sandwich_hand_and_check_if_plates_empty）。

    每一轮找到手的位置，按距离推一下摇杆（推 0.16 秒，推完等 0.08 秒）：按 16:9 算屏幕上的距离，
    4 格（宽度的 1/4）以内按距离推，再远满推；手的中心进了 end 的框就算到了，最多 120 秒。
    pressing_a 为真时一直按着 A，到了松开，等 0.1 秒让手把东西放下。check_label 为真时，到了的那一刻看盘子的标签是不是黄色。
    返回手最后所在的框，和盘子的标签是不是黄色（没看就是 False）。
    """
    target = ((end[0][0] + end[1][0]) / 2, (end[0][1] + end[1][1]) / 2)
    half_width = (end[1][0] - end[0][0]) / 2
    half_height = (end[1][1] - end[0][1]) / 2
    area = start
    deadline = time.monotonic() + 120.0
    if pressing_a:
        sw.press("A")
    try:
        while True:
            found = _find_hand(sw, kind, area, 5.0) or _recover_hand(sw, kind, pressing_a)
            location, image = found
            box_around_hand = _hand_box(location)
            area = _expand_box(box_around_hand)
            dx, dy = target[0] - location[0], target[1] - location[1]
            if abs(dx) < half_width and abs(dy) < half_height:
                logging.info(f"手到了目标框里 {location}")
                return box_around_hand, check_label and _is_plate_label_yellow(image)
            if time.monotonic() > deadline:
                raise TimeoutError("120 秒了，手还是没移到目标框里")
            real_x, real_y = dx * 16, dy * 9
            distance = math.hypot(real_x, real_y)
            push = min(distance * 0.25, 1.0)
            sw.push("LEFT", real_x * push / distance, -real_y * push / distance, 0.16)
            time.sleep(0.08)
    finally:
        if pressing_a:
            sw.release("A")
            if kind == "grabbing":
                time.sleep(0.1)


# ---- 走到篮子前收蛋 ----


def _has_a_hint(image: ImageChecker) -> bool:
    """野餐时左边有 A 按钮的提示（「聊天」）：身边有宝可梦在跟前。白色像素占比超过 0.05。"""
    return image.color_ratio(((0.020, 0.590), (0.055, 0.650)), (0, 0, 200), (180, 40, 255)) > 0.05


def _clear_mons_in_front(sw: IncubatorSession) -> None:
    """桌子前、篮子前有宝可梦挡着时（左边出现 A 的提示），吹口哨等它们让开：每 30 秒吹一次，最多 40 次。"""
    for _ in range(40):
        deadline = time.monotonic() + 30.0
        while True:
            if not _has_a_hint(capture(sw, "前面有没有宝可梦挡着")):
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(sw.config.wait.interval)
        logging.info("有宝可梦挡在前面，吹口哨等 30 秒")
        sw.click("R", 0)
    raise TimeoutError("20 分钟了，前面的宝可梦还是没让开")


def _look_at_basket(sw: IncubatorSession) -> BasketState:
    """看篮子前现在是什么画面，最多看 5 秒：选择框、要按键往下翻的对话、没有对话框，或者认不出。

    没有对话框要连着 0.5 秒都没有才算，对话切换时框可能闪一下。
    """
    config = sw.config
    deadline = time.monotonic() + 5.0
    none_since: float | None = None
    while True:
        image = capture(sw, "篮子前")
        if sv_verify.is_prompt(image, config):
            return "prompt"
        if sv_verify.is_dialog(image, config):
            return "dialog"
        now = time.monotonic()
        if not sv_verify.has_dialog_box(image, config):
            if none_since is None:
                none_since = now
            if now - none_since >= 0.5:
                return "none"
        else:
            none_since = None
            if now >= deadline:
                return "unknown"
        time.sleep(config.wait.interval)


def _check_basket(sw: IncubatorSession, need: int, collected: int) -> int:
    """和篮子说话收蛋，返回收完之后一共收到的蛋数（上游 check_basket_to_collect_eggs）。最多 300 秒。

    没有对话框：还没说过话就按 A 去说话，说过了就结束；连着 10 次都没有对话框报错，找不到篮子。
    普通对话按 B；选择框蛋没收够按 A 收下，收够了按 B 拒绝、之后再出现的确认选择框按 A；
    认不出画面就转一下视角。对话按完等 0.24 秒，选择框按完等 0.64 秒。
    """
    checked = False
    nothing = 0
    last_prompt: str | None = None
    pending_refuse = False
    start = time.monotonic()
    while True:
        if time.monotonic() - start > 300.0:
            raise TimeoutError("300 秒了还在收篮子里的蛋")
        state = _look_at_basket(sw)
        if state != "none":
            nothing = 0
        if state == "none":
            nothing += 1
            last_prompt = None
            if nothing >= 10:
                raise RuntimeError(
                    "连着 10 次都没有对话框，找不到篮子，请确认游戏设置里「镜头辅助」是开的"
                )
            if checked:
                logging.info("和篮子说完话了")
                return collected
            logging.info("去和篮子说话")
            sw.click("A", 0.24)
        elif state == "dialog":
            last_prompt = None
            sw.click("B", 0.24)
            checked = True
        elif state == "prompt":
            if last_prompt is not None:
                logging.warning("连着出了两次选择框，重复上一次按的键")
                sw.click(last_prompt, 0.64)
            elif pending_refuse:
                logging.info("确认不要这个蛋")
                sw.click("A", 0.64)
                pending_refuse = False
            elif collected < need:
                collected += 1
                logging.info(f"收下一个蛋 {collected}/{need}")
                sw.click("A", 0.64)
                last_prompt = "A"
            else:
                logging.info("蛋已经够了，不要这个蛋")
                sw.click("B", 0.64)
                last_prompt = "B"
                pending_refuse = True
        else:
            logging.warning("没认出画面，转一下视角再看")
            sw.push("RIGHT", -1.0, 0.0, 0.24)


def _wait_for_basket(sw: IncubatorSession, seconds: int) -> None:
    """等 seconds 秒，期间每隔 30 秒按一下 L，不让 Switch 休眠。"""
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        sw.click("L", 0)
        time.sleep(min(30.0, remaining))


def _collect_eggs(sw: IncubatorSession, need: int) -> int:
    """从桌子前走到篮子前，隔一会儿查一次篮子，收够 need 个或者过了 fetch_limit 秒为止，返回收到的蛋数。

    每 180 秒查一次（不能超过 180，不然 Switch 会休眠）；剩下的蛋比平均每次收到的还少时按比例缩短，最少 30 秒。
    """
    config = sw.config
    # 先收起坐骑，绕过桌子，转向篮子，靠近，中间按 L 转镜头（上游 collect_eggs_after_sandwich）
    sw.follow(
        (
            Press("PLUS", 0.84),
            Push(0.0, 1.0, 0.32, 0.48),
            Push(-1.0, 0.0, 0.08, 0.48),
            Press("L", 0.48),
            Push(0.0, 1.0, 0.32, 0.48),
            Push(1.0, 0.0, 0.08, 0.48),
            Press("L", 0.48),
            Push(0.0, 1.0, 0.64, 0.48),
            Push(1.0, 0.0, 0.08, 0.48),
            Press("L", 0.48),
            Push(0.0, 1.0, 0.32, 0.48),
            Push(1.0, 0.0, 0.08, 0.48),
            Press("L", 0.48),
            Push(0.0, 1.0, 0.8, 0.48),
            Push(0.0, -1.0, 0.2, 0.48),
            Push(0.0, 1.0, 0.08, 0.48),
            Press("L", 0.48),
        )
    )
    start = time.monotonic()
    collected = 0
    checks = 0
    while True:
        _clear_mons_in_front(sw)
        collected = _check_basket(sw, need, collected)
        checks += 1
        if collected >= need:
            logging.info(f"收够了 {need} 个蛋")
            return collected
        if time.monotonic() - start > config.fetch_limit:
            logging.info("等了太久，不等了")
            return collected
        average = collected / checks
        remaining = need - collected
        seconds = 180 if remaining >= average else max(int(remaining * 180 / average), 30)
        logging.info(f"收到 {collected} 个蛋，平均每次 {average:.1f} 个，等 {seconds} 秒再查")
        _wait_for_basket(sw, seconds)
