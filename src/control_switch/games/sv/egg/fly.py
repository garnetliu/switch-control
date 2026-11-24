"""在地图上找到零区闸口，飞过去。

照 PokemonAutomation 的做法，野餐和孵蛋都在零区闸口进行：那里地方平、野生宝可梦少，
每次孵蛋前飞回去，人不会越绕越偏（reset_position_at_zero_gate、picnic_at_zero_gate）。
PokemonAutomation 是把地图光标往下推一小段对准飞行点；这里改成在地图截图里找飞行点的图标，
把光标推过去，直到光标上方的提示是「零区闸口」，不依赖人站的位置和地图缩放。
"""

import logging
import math
import time
from typing import cast

import cv2
import numpy as np

from control_switch.flow import act_until, capture
from control_switch.session import Session
from control_switch.vision import ImageChecker

from . import screens
from .box import exit_to_overworld
from .config import EggConfig


def _config(sw: Session) -> EggConfig:
    return cast(EggConfig, sw.config)


def is_map(image: ImageChecker, config: EggConfig) -> bool:
    """地图画面：左上角有「地图」两个字。"""
    return image.has_text(config.map_title, config.map_title_text)


def _fly_icons(image: ImageChecker, config: EggConfig) -> list[tuple[float, float]]:
    """地图上所有飞行点图标的中心，按占画面宽高的比例。"""
    template = cv2.imread(str(config.fly_icon))
    if template is None:
        raise RuntimeError(f"读不到飞行点的图标 {config.fly_icon}")
    height, width = image.bgr.shape[:2]
    scores = cv2.matchTemplate(image.bgr, template, cv2.TM_CCOEFF_NORMED)
    points: list[tuple[float, float]] = []
    ys, xs = np.where(scores >= config.fly_icon_score)
    th, tw = template.shape[:2]
    for x, y in sorted(zip(xs, ys), key=lambda p: -scores[p[1], p[0]]):
        cx, cy = (x + tw / 2) / width, (y + th / 2) / height
        if any(abs(cx - px) < 0.02 and abs(cy - py) < 0.03 for px, py in points):
            continue
        (left, top), (right, bottom) = config.map_area
        if left <= cx <= right and top <= cy <= bottom:
            points.append((cx, cy))
    return points


def _menu_options(image: ImageChecker, config: EggConfig) -> list[str]:
    """地图上按 A 出的菜单里的选项文字；没有菜单返回空列表。"""
    found = image.find_menu(config.fly_menu_area)
    return [text for text, _ in found[1]] if found else []


def open_map(sw: Session) -> ImageChecker:
    """在野外按 Y 打开地图，没反应就再按。"""
    config = _config(sw)
    return act_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: is_map(s, config),
        "地图",
        interval=config.map_retry,
        timeout=config.timeout,
    )


def fly_to_gate(sw: Session) -> None:
    """飞到零区闸口，回到野外为止。"""
    config = _config(sw)
    exit_to_overworld(sw)
    image = open_map(sw)
    probes = 0
    for _ in range(config.map_moves):
        if image.has_text(config.map_tooltip, config.gate_name):
            break
        icons = _fly_icons(image, config)
        if not icons:
            # 人在零区闸口附近时，飞行点的图标被人的头像挡住了。照 PokemonAutomation 把光标往下轻推一点，
            # 光标就会停到飞行点上、显示地点名（真机上试过）；不行再往别的方向轻推
            if probes >= len(config.map_probes):
                raise RuntimeError("地图上看不到飞行点，轻推光标也没对准零区闸口")
            px, py = config.map_probes[probes]
            probes += 1
            sw.stick(
                "LEFT",
                round(config.stick_max * config.map_probe_tilt * px),
                round(config.stick_max * config.map_probe_tilt * py),
                config.map_probe_time,
            )
            time.sleep(config.map_move_wait)
            image = capture(sw, "地图上找零区闸口")
            continue
        cx, cy = config.map_cursor
        target = min(icons, key=lambda p: math.dist(p, (cx, cy)))
        dx, dy = target[0] - cx, target[1] - cy
        distance = math.hypot(dx, dy)
        seconds = min(max(distance / config.map_cursor_speed, config.map_move_min), 1.0)
        stick = config.stick_max
        sw.stick("LEFT", round(stick * dx / distance), round(-stick * dy / distance), seconds)
        time.sleep(config.map_move_wait)
        image = capture(sw, "地图上找零区闸口")
    else:
        raise RuntimeError(f"地图光标移了 {config.map_moves} 次，还是没对准「{config.gate_name}」")
    # A 出菜单（飞翔、设置为目的地、取消），光标不在飞行点上时没有「飞翔」
    menu = act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: any(config.cancel_text in text for text in _menu_options(s, config)),
        "地图上的菜单",
        interval=config.map_retry,
        timeout=config.timeout,
    )
    options = _menu_options(menu, config)
    if not any(config.fly_text in text for text in options):
        sw.click("B", config.map_move_wait)
        raise RuntimeError(f"地图光标不在飞行点上，菜单里是 {options}，没有「{config.fly_text}」")
    # A 选「飞翔」，出「要使用飞翔移动至这个地方吗？」，再 A 选「是」
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_prompt(s, config),
        "飞翔的确认",
        interval=config.map_retry,
        timeout=config.timeout,
    )
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not is_map(s, config) and not screens.is_prompt(s, config),
        "飞走",
        interval=config.map_retry,
        timeout=config.timeout,
    )
    act_until(
        sw,
        lambda: None,
        lambda s: screens.is_overworld(s, config),
        "飞到零区闸口",
        interval=config.map_retry,
        timeout=config.fly_timeout,
    )
    logging.info(f"飞到了{config.gate_name}")
