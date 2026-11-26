"""收蛋：在零区闸口开野餐、做三明治、走到篮子前反复查篮子收蛋、收野餐、飞回闸口、换成孵蛋队伍。

照 PokemonAutomation 的 fetch_eggs_full_routine：picnic_at_zero_gate、eat_egg_sandwich_at_picnic
（enter_sandwich_recipe_list、select_sandwich_recipe、run_sandwich_maker、finish_sandwich_eating）、
collect_eggs_after_sandwich、check_basket_to_collect_eggs、clear_mons_in_front。
"""

import logging
import math
import time
from collections.abc import Callable
from typing import Literal

from control_switch.flow import capture, press_until, wait_until
from control_switch.games.sv import actions
from control_switch.types import Rect
from control_switch.vision import ImageChecker

from .. import box, fly, screens
from ..config import EggConfig
from ..session import EggSession

# 整个画面
FULL_SCREEN: Rect = ((0.0, 0.0), (1.0, 1.0))

BasketState = Literal["prompt", "dialog", "none", "unknown"]
SandwichState = Literal["picnic", "menu", "recipes", "dialog", "unknown"]


def fetch(sw: EggSession) -> str:
    """开野餐、做三明治、收蛋、换成孵蛋队伍，返回下一步 "hatch"。"""
    _picnic_at_zero_gate(sw)
    if not _eat_egg_sandwich(sw):
        raise RuntimeError(
            f"做不了三明治：没有食谱 {sw.config.recipe_number}（超级花生酱三明治）或者材料不够"
        )
    _collect_eggs_after_sandwich(sw)
    actions.close_picnic(sw)
    fly.fly_to_gate(sw)
    sw.eggs_in_party = box.to_hatch_party(sw)
    logging.info(f"队伍里有 {sw.eggs_in_party} 个蛋")
    return "hatch"


def _picnic_at_zero_gate(sw: EggSession) -> None:
    """在零区闸口开野餐。

    先按 L 让镜头对准人面对的方向（读档之后镜头会重置），往右前方走一点让人背对观测站，再按 L、往前走，开野餐。
    """
    sw.picnics += 1
    logging.info(f"第 {sw.picnics} 次开野餐")
    sw.follow(sw.config.picnic_route)
    actions.open_picnic(sw)


def _watch(
    sw: EggSession, condition: Callable[[ImageChecker], bool], seconds: float, what: str
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


# ---- 做三明治 ----


def _eat_egg_sandwich(sw: EggSession) -> bool:
    """走到桌子前做超级花生酱三明治，做完吃掉。没有食谱、材料不够时返回 False。"""
    config = sw.config
    sw.follow(config.table_route)
    _clear_mons_in_front(sw)
    if not _enter_sandwich_recipe_list(sw):
        return False
    if not _select_sandwich_recipe(sw, config.recipe_number):
        return False
    _run_sandwich_maker(sw)
    return True


def _sandwich_state(sw: EggSession) -> SandwichState:
    """看桌子前现在是什么画面，最多看 sandwich_state_timeout 秒。

    返回 "picnic"（回到了野餐）、"menu"（桌子菜单的箭头）、"recipes"（食谱列表）、"dialog"（对话）、
    "unknown"（什么都没认出来）。
    """
    config = sw.config
    deadline = time.monotonic() + config.sandwich_state_timeout
    while True:
        image = capture(sw, "桌子前")
        if screens.is_picnic(image, config):
            return "picnic"
        if screens.is_table_menu_arrow(image, config):
            return "menu"
        if screens.is_recipe_list(image, config):
            return "recipes"
        if screens.is_dialog(image, config):
            return "dialog"
        if time.monotonic() >= deadline:
            return "unknown"
        time.sleep(config.wait.interval)


def _enter_sandwich_recipe_list(sw: EggSession) -> bool:
    """在桌子前打开食谱列表，打开了返回 True；桌子菜单之后出了对话（没有材料）返回 False。"""
    config = sw.config
    logging.info("在桌子前打开食谱列表")
    # 先按 A 试试能不能打开桌子的菜单
    sw.click("A", config.table_press_wait)
    start = time.monotonic()
    opened_menu = False
    while True:
        if time.monotonic() - start > config.recipe_enter_timeout:
            raise TimeoutError(f"{config.recipe_enter_timeout} 秒了还是没打开食谱列表")
        state = _sandwich_state(sw)
        if state == "picnic":
            logging.info("回到了野餐的画面，第一下 A 可能被吞了，往前走一点再按 A")
            sw.follow(config.table_retry_route)
            sw.click("A", config.table_press_wait)
        elif state == "menu":
            logging.info("看到「做料理」的选择箭头，按 A 进食谱列表")
            opened_menu = True
            sw.click("A", config.table_press_wait)
        elif state == "recipes":
            logging.info("看到食谱列表")
            time.sleep(config.recipe_settle_wait)
            return True
        elif state == "dialog":
            if opened_menu:
                logging.warning("选了「做料理」之后出了对话，没有材料")
                return False
            sw.click("A", config.table_press_wait)
        else:
            raise RuntimeError(
                f"{config.sandwich_state_timeout} 秒了还是认不出桌子前是什么画面，进不了食谱列表"
            )


def _select_sandwich_recipe(sw: EggSession, target: int) -> bool:
    """在食谱列表里选中编号 target 的食谱，按 A 进选签子的界面、再按 A 开始做。

    找到了返回 True；目标应该在这一页却没有（材料不够，食谱是半透明的）、整个列表翻完也没有，返回 False。
    """
    config = sw.config
    logging.info(f"在食谱列表里找食谱 {target}")
    for _ in range(config.recipe_scroll_limit):
        time.sleep(config.recipe_look_wait)
        numbers = screens.recipe_numbers(capture(sw, "食谱的编号"), config)
        logging.info(f"这一页的食谱编号：{numbers}")
        shown = [number for number in numbers if number > 0]
        low = min(shown, default=0)
        if 0 < low <= target <= max(numbers):
            if target not in numbers:
                logging.warning(f"食谱 {target} 不在这一页，应该是材料不够")
                return False
            target_cell = numbers.index(target)
            selected_cell = _selected_recipe_cell(sw)
            if target_cell == selected_cell:
                logging.info(f"选中了食谱 {target}")
                _start_sandwich(sw)
                return True
            if target_cell == selected_cell + 1:
                sw.click("DRIGHT", config.recipe_move_wait)
                continue
        sw.click("DDOWN", config.recipe_move_wait)
    logging.warning(f"翻了 {config.recipe_scroll_limit} 次，还是没找到食谱 {target}")
    return False


def _selected_recipe_cell(sw: EggSession) -> int:
    """食谱列表里选中的是这一页第几格，最多等 recipe_arrow_timeout 秒，看不到选中的箭头就报错。"""
    config = sw.config
    try:
        image = wait_until(
            sw,
            lambda s: screens.selected_recipe_cell(s, config) >= 0,
            config.recipe_arrow_timeout,
            "食谱列表里选中的箭头",
        )
    except TimeoutError as error:
        raise RuntimeError("食谱列表里看不到选中食谱的箭头") from error
    return screens.selected_recipe_cell(image, config)


def _start_sandwich(sw: EggSession) -> None:
    """选中食谱之后：按 A 进选签子的界面，再按 A 开始做；哪一下被吞了画面还在原处，就再按一下。"""
    config = sw.config
    sw.click("A", config.recipe_press_wait)
    while (
        _watch(
            sw,
            lambda s: (
                screens.selected_recipe_cell(s, config) >= 0 or screens.is_pick_arrow(s, config)
            ),
            config.recipe_start_look,
            "选食谱之后的画面",
        )
        is not None
    ):
        sw.click("A", config.recipe_press_wait)
    logging.info("进了做三明治的画面")


def _run_sandwich_maker(sw: EggSession) -> None:
    """做三明治：把盘子里的香蕉一片一片放到面包上，放完加上面包、插签子，吃掉。

    照上游 run_sandwich_maker，只做一种材料（香蕉）、一个盘子（正中间）：
    每一片都是空手找到盘子上方、按住 A 抓起、抓着移到目标框、松开 A 放下。
    """
    config = sw.config
    logging.info("开始做三明治")
    try:
        wait_until(
            sw,
            lambda s: screens.find_hand(s, "free", config.hand_initial_box, config) is not None,
            config.hand_first_timeout,
            "做三明治时最开始的手",
        )
    except TimeoutError as error:
        raise RuntimeError("做三明治一开始就没找到手") from error
    # 等盘子的标签出来
    time.sleep(config.plate_label_wait)
    end = _move_sandwich_hand(sw, "free", False, config.hand_initial_box, config.hand_initial_box)
    _move_sandwich_hand(sw, "grabbing", True, FULL_SCREEN, config.hand_initial_box)

    placed = 0
    while placed < len(config.banana_targets):
        end = _move_sandwich_hand(sw, "free", False, FULL_SCREEN, config.plate_box)
        end, plate_yellow = _move_hand(
            sw,
            "grabbing",
            True,
            _expand_box(end, config),
            config.banana_targets[placed],
            check_label=True,
        )
        if not plate_yellow:
            logging.warning("抓着的时候盘子的标签没变黄，当作盘子空了")
            break
        placed += 1
        logging.info(f"放好了第 {placed} 片香蕉")

    time.sleep(config.top_bread_wait)
    image = _watch(
        sw,
        lambda s: screens.find_hand(s, "grabbing", FULL_SCREEN, config) is not None,
        config.hand_first_timeout,
        "上面的面包",
    )
    if image is None:
        raise RuntimeError("放完香蕉之后没看到抓着上面面包的手")
    location = screens.find_hand(image, "grabbing", FULL_SCREEN, config)
    assert location is not None
    _move_sandwich_hand(
        sw, "grabbing", False, _expand_box(_hand_box(location, config), config), config.plate_box
    )
    deadline = time.monotonic() + config.mash_seconds
    while time.monotonic() < deadline:
        sw.click("A", config.mash_gap)
    logging.info("三明治做好了")
    _finish_sandwich_eating(sw)


def _finish_sandwich_eating(sw: EggSession) -> None:
    """吃三明治：一直按 A，直到回到野餐的画面；认到之后等一会儿再看一次，还在才算。"""
    config = sw.config
    deadline = time.monotonic() + config.eat_timeout
    while True:
        press_until(
            sw,
            lambda: sw.click("A", 0),
            lambda s: screens.is_picnic(s, config),
            max(deadline - time.monotonic(), 0.0),
            "吃完三明治回到野餐",
            interval=config.eat_press_interval,
        )
        time.sleep(config.eat_settle_wait)
        if screens.is_picnic(capture(sw, "吃完了吗"), config):
            logging.info("吃完了，回到野餐")
            return


def _hand_box(location: tuple[float, float], config: EggConfig) -> Rect:
    """以手的中心为中心的框（上游 hand_location_to_box）。"""
    x, y = location
    half_width, half_height = config.hand_width / 2, config.hand_height / 2
    return ((x - half_width, y - half_height), (x + half_width, y + half_height))


def _expand_box(area: Rect, config: EggConfig) -> Rect:
    """把手的框往外扩，下一次在这里找手（上游 expand_box）：左上角往外扩 1.5 倍宽高，宽高变成 4 倍。"""
    (left, top), (right, bottom) = area
    width, height = right - left, bottom - top
    x = max(0.0, left - width * config.hand_expand_margin)
    y = max(0.0, top - height * config.hand_expand_margin)
    return (
        (x, y),
        (
            x + min(width * config.hand_expand_scale, 1.0 - x),
            y + min(height * config.hand_expand_scale, 1.0 - y),
        ),
    )


def _find_hand(
    sw: EggSession, kind: str, area: Rect, seconds: float
) -> tuple[tuple[float, float], ImageChecker] | None:
    """在 area 里找手，最多找 seconds 秒；area 里没有就再在整个画面里找一次（上游是这样）。

    返回手的中心和那张截图，一直没找到返回 None。
    """
    config = sw.config
    deadline = time.monotonic() + seconds
    while True:
        image = capture(sw, "找手")
        location = screens.find_hand(image, kind, area, config)
        if location is None and area != FULL_SCREEN:
            location = screens.find_hand(image, kind, FULL_SCREEN, config)
        if location is not None:
            return location, image
        if time.monotonic() >= deadline:
            return None
        time.sleep(config.wait.interval)


def _recover_hand(
    sw: EggSession, kind: str, pressing_a: bool
) -> tuple[tuple[float, float], ImageChecker]:
    """5 秒没找到手：手可能在屏幕边上。把手往右下推到头，再往左推一点，然后在整个画面里找。找不到抛 RuntimeError。"""
    config = sw.config
    logging.info("没找到手，把它移到画面中间再在整个画面里找")
    for x, y, seconds in config.hand_recover_route:
        sw.push("LEFT", x, y, seconds)
        time.sleep(config.hand_recover_wait)
    found = _find_hand(sw, kind, FULL_SCREEN, config.hand_recover_look)
    if found is None:
        raise RuntimeError(f"移到画面中间之后还是没找到{'抓着东西的' if pressing_a else ''}手")
    return found


def _move_hand(
    sw: EggSession,
    kind: str,
    pressing_a: bool,
    start: Rect,
    end: Rect,
    check_label: bool = False,
) -> tuple[Rect, bool]:
    """把手从 start 里移到 end（上游 move_sandwich_hand_and_check_if_plates_empty）。

    每一轮找到手的位置，按距离推一下摇杆：离得越远推得越满，手的中心进了 end 的框就算到了。
    pressing_a 为真时一直按着 A，到了松开。check_label 为真时，到了的那一刻看盘子的标签是不是黄色。
    返回手最后所在的框，和盘子的标签是不是黄色（没看就是 False）。
    """
    config = sw.config
    target = ((end[0][0] + end[1][0]) / 2, (end[0][1] + end[1][1]) / 2)
    half_width = (end[1][0] - end[0][0]) / 2
    half_height = (end[1][1] - end[0][1]) / 2
    area = start
    deadline = time.monotonic() + config.hand_move_timeout
    if pressing_a:
        sw.press("A")
    try:
        while True:
            found = _find_hand(sw, kind, area, config.hand_look_timeout) or _recover_hand(
                sw, kind, pressing_a
            )
            location, image = found
            box_around_hand = _hand_box(location, config)
            area = _expand_box(box_around_hand, config)
            dx, dy = target[0] - location[0], target[1] - location[1]
            if abs(dx) < half_width and abs(dy) < half_height:
                logging.info(f"手到了目标框里 {location}")
                return box_around_hand, check_label and screens.is_plate_label_yellow(image, config)
            if time.monotonic() > deadline:
                raise TimeoutError(f"{config.hand_move_timeout} 秒了，手还是没移到目标框里")
            # 按 16:9 算屏幕上的距离，4 格以内按距离推，再远就满推
            real_x, real_y = dx * config.screen_width_units, dy * config.screen_height_units
            distance = math.hypot(real_x, real_y)
            push = min(distance * config.hand_gain, 1.0)
            sw.push(
                "LEFT",
                real_x * push / distance,
                -real_y * push / distance,
                config.hand_push_seconds,
            )
            time.sleep(config.hand_move_wait)
    finally:
        if pressing_a:
            sw.release("A")
            if kind == "grabbing":
                # 等手把东西放下
                time.sleep(config.hand_release_wait)


def _move_sandwich_hand(
    sw: EggSession, kind: str, pressing_a: bool, start: Rect, end: Rect
) -> Rect:
    """把手从 start 里移到 end，返回手最后所在的框。"""
    return _move_hand(sw, kind, pressing_a, start, end)[0]


# ---- 走到篮子前收蛋 ----


def _walk_to_basket(sw: EggSession) -> None:
    """从桌子前走到篮子前：先收起坐骑，绕过桌子，转向篮子，靠近。路线和时间照上游，镜头辅助开着也关着都能用。"""
    sw.follow(sw.config.basket_route)


def _clear_mons_in_front(sw: EggSession) -> None:
    """桌子前、篮子前有宝可梦挡着时（左边出现 A 的提示），吹口哨等它们让开：每 30 秒吹一次，最多 40 次。"""
    config = sw.config
    for _ in range(config.whistle_rounds):
        deadline = time.monotonic() + config.whistle_wait
        while True:
            if not screens.has_a_hint(capture(sw, "前面有没有宝可梦挡着"), config):
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(config.wait.interval)
        logging.info("有宝可梦挡在前面，吹口哨等 30 秒")
        sw.click("R", 0)
    raise TimeoutError(
        f"{config.whistle_rounds * config.whistle_wait / 60} 分钟了，前面的宝可梦还是没让开"
    )


def _look_at_basket(sw: EggSession) -> BasketState:
    """看篮子前现在是什么画面，最多看 basket_look_timeout 秒。

    返回 "prompt"（选择框）、"dialog"（要按键往下翻的对话）、"none"（没有对话框）、"unknown"（什么都没认出来）。
    没有对话框要连着看 basket_none_hold 秒都没有才算，对话切换时框可能闪一下。
    """
    config = sw.config
    deadline = time.monotonic() + config.basket_look_timeout
    none_since: float | None = None
    while True:
        image = capture(sw, "篮子前")
        if screens.is_prompt(image, config):
            return "prompt"
        if screens.is_dialog(image, config):
            return "dialog"
        now = time.monotonic()
        if not screens.has_dialog_box(image, config):
            if none_since is None:
                none_since = now
            if now - none_since >= config.basket_none_hold:
                return "none"
        else:
            none_since = None
            if now >= deadline:
                return "unknown"
        time.sleep(config.wait.interval)


def _check_basket(sw: EggSession, max_eggs: int, collected: int) -> int:
    """和篮子说话收蛋，返回收完之后一共收到的蛋数（上游 check_basket_to_collect_eggs）。

    没有对话框：还没说过话就按 A 去说话，说过了就结束；连着 10 次都没有对话框报错，找不到篮子。
    普通对话按 B；选择框蛋没收满按 A 收下，收满了按 B 拒绝、之后再出现的确认选择框按 A；
    5 秒什么都没认出来就转一下视角。
    """
    config = sw.config
    checked = False
    nothing = 0
    last_prompt: str | None = None
    pending_refuse = False
    start = time.monotonic()
    while True:
        if time.monotonic() - start > config.basket_check_timeout:
            raise TimeoutError(f"{config.basket_check_timeout} 秒了还在收篮子里的蛋")
        state = _look_at_basket(sw)
        if state != "none":
            nothing = 0
        if state == "none":
            logging.info("没有对话框")
            nothing += 1
            last_prompt = None
            if nothing >= config.basket_none_limit:
                raise RuntimeError(
                    f"连着 {config.basket_none_limit} 次都没有对话框，找不到篮子，"
                    "请确认游戏设置里「镜头辅助」是开的"
                )
            if checked:
                logging.info("和篮子说完话了")
                return collected
            logging.info("去和篮子说话")
            sw.click("A", config.basket_talk_wait)
        elif state == "dialog":
            last_prompt = None
            sw.click("B", config.basket_talk_wait)
            checked = True
        elif state == "prompt":
            if last_prompt is not None:
                logging.warning("连着出了两次选择框，重复上一次按的键")
                sw.click(last_prompt, config.basket_prompt_wait)
            elif pending_refuse:
                logging.info("确认不要这个蛋")
                sw.click("A", config.basket_prompt_wait)
                pending_refuse = False
            elif collected < max_eggs:
                collected += 1
                logging.info(f"收下一个蛋 {collected}/{max_eggs}")
                sw.click("A", config.basket_prompt_wait)
                last_prompt = "A"
            else:
                logging.info("蛋已经够了，不要这个蛋")
                sw.click("B", config.basket_prompt_wait)
                last_prompt = "B"
                pending_refuse = True
        else:
            logging.warning("没认出画面，转一下视角再看")
            sw.push("RIGHT", -1.0, 0.0, config.basket_turn_seconds)


def _basket_wait_seconds(default: int, remaining: int, average: float) -> int:
    """下一次查篮子前等几秒：剩下的蛋比平均每次收到的还少时，按比例缩短，最少 30 秒。"""
    if remaining >= average:
        return default
    return max(int(remaining * default / average), 30)


def _wait_for_basket(sw: EggSession, seconds: int) -> None:
    """等 seconds 秒，期间每隔 keepalive_gap 秒按一下键，不让 Switch 休眠。"""
    config = sw.config
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        sw.click(config.keepalive_button, 0)
        time.sleep(min(config.keepalive_gap, remaining))


def _collect_eggs_after_sandwich(sw: EggSession) -> int:
    """走到篮子前，隔一会儿查一次篮子，收够 30 个或者过了 30 分钟为止，返回收到的蛋数。"""
    config = sw.config
    _walk_to_basket(sw)
    start = time.monotonic()
    collected = 0
    checks = 0
    while True:
        _clear_mons_in_front(sw)
        collected = _check_basket(sw, config.max_eggs, collected)
        checks += 1
        if collected >= config.max_eggs:
            logging.info(f"收够了 {config.max_eggs} 个蛋")
            break
        if time.monotonic() - start > config.fetch_limit:
            logging.info("等了太久，不等了")
            break
        average = collected / checks
        seconds = _basket_wait_seconds(config.basket_interval, config.max_eggs - collected, average)
        logging.info(f"收到 {collected} 个蛋，平均每次 {average:.1f} 个，等 {seconds} 秒再查")
        _wait_for_basket(sw, seconds)
    return collected
