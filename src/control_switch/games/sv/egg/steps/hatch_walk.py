"""hatch_walk：骑坐骑绕圈孵蛋，遇到野生宝可梦就逃走。"""

import logging
import time
from typing import cast

from control_switch.flow import act_until, capture
from control_switch.session import Session
from control_switch.vision import ImageChecker

from .. import screens
from ..box import (
    set_riding,
)
from ..config import EggConfig
from ..fly import fly_to_gate
from ..session import EggSession
from .common import leave_gate


def _start_circle(sw: Session) -> None:
    sw.press("LSTICK")
    sw.press_stick("LEFT", 0, sw.controller.STICK_MAX)
    sw.press_stick("RIGHT", sw.controller.STICK_MAX, 0)


def _stop_circle(sw: Session) -> None:
    sw.release_stick("LEFT")
    sw.release_stick("RIGHT")
    sw.release("LSTICK")


def _escaped(sw: Session) -> bool:
    """按完「逃走」之后看结果：野外连续 flee_stable_frames 帧算逃掉了；中途有对话框按 B；
    又看到战斗菜单、或者等了 flee_timeout 秒还没结果算没逃掉。
    """
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + config.flee_timeout
    consecutive = 0
    while time.monotonic() < deadline:
        image = capture(sw, "逃走之后")
        if screens.is_overworld(image, config) and not screens.is_dialog(image, config):
            consecutive += 1
            if consecutive >= config.flee_stable_frames:
                return True
        elif screens.is_dialog(image, config):
            consecutive = 0
            sw.click("B", 0)
        elif screens.is_battle(image, config):
            return False
        else:
            consecutive = 0
        time.sleep(config.flee_gap)
    return False


def _flee(sw: Session) -> None:
    """战斗菜单里把光标移到「逃走」（第 4 行）按 A，没逃掉就重来。"""
    config = cast(EggConfig, sw.config)
    for _ in range(config.flee_attempts):
        # 误进了包包、宝可梦这些子菜单时按 B 退回战斗菜单
        image = act_until(
            sw,
            lambda: sw.click("B", 0),
            lambda s: screens.battle_row(s, config) != -1,
            "战斗菜单",
            interval=config.flee_move_interval * 3,
            timeout=config.wait.timeout,
        )
        row = screens.battle_row(image, config)
        while row != config.flee_row:
            button = "DDOWN" if row < config.flee_row else "DUP"
            image = act_until(
                sw,
                lambda button=button: sw.click(button, 0),
                lambda s, before=row: screens.battle_row(s, config) not in (before, -1),
                "战斗菜单的光标移一格",
                interval=config.flee_move_interval,
            )
            row = screens.battle_row(image, config)
        sw.click("A", 0)
        if _escaped(sw):
            return
    raise RuntimeError(f"逃了 {config.flee_attempts} 次，还是在战斗")


def _stable_overworld(sw: Session, first: ImageChecker) -> bool:
    """野外要连续 stable_frames 帧（每帧间隔 stable_gap 秒），期间没有对话框，才算孵完。"""
    config = cast(EggConfig, sw.config)
    image = first
    for frame in range(config.stable_frames):
        if frame:
            time.sleep(config.stable_gap)
            image = capture(sw, "孵化结束了吗")
        if not screens.is_overworld(image, config) or screens.is_dialog(image, config):
            return False
    return True


def _finish_hatch(sw: Session) -> None:
    """一直按 A 看完孵化；回到野外并且稳定了才算完。按 A 的时候遇到战斗就逃走。"""
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + config.hatch_timeout
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.hatch_timeout} 秒，孵化一直没有结束")
        image = capture(sw, "孵化结束")
        if screens.is_battle(image, config):
            _flee(sw)
        elif screens.is_overworld(image, config) and not screens.is_dialog(image, config):
            if _stable_overworld(sw, image):
                return
        else:
            sw.click("A", config.hatch_press_wait)


def _to_hatch_ground(sw: EggSession) -> None:
    """飞回零区闸口，骑上坐骑，下坡到空地上（PokemonAutomation hatch_eggs_at_zero_gate）。"""
    config = sw.config
    fly_to_gate(sw)
    set_riding(sw, True)
    leave_gate(sw, config.ramp_walk)
    sw.click("L", config.ride_circle_wait)


def hatch_walk(sw: EggSession) -> str:
    """骑上坐骑原地绕圈，孵出队伍里所有的蛋。"""
    sw.frames.clear()
    config = sw.config
    _to_hatch_ground(sw)
    done = 0
    last_progress = time.monotonic()
    circling = False
    try:
        while done < sw.eggs_in_party:
            if not circling:
                _start_circle(sw)
                circling = True
            image = capture(sw, "绕圈")
            if screens.is_dialog(image, config):
                _stop_circle(sw)
                circling = False
                _finish_hatch(sw)
                done += 1
                sw.hatched += 1
                last_progress = time.monotonic()
                logging.info(f"孵出了第 {sw.hatched} 只")
            elif screens.is_battle(image, config):
                _stop_circle(sw)
                circling = False
                _flee(sw)
                # 逃走后照 PokemonAutomation 飞回零区闸口重新开始绕圈
                _to_hatch_ground(sw)
            elif time.monotonic() - last_progress >= config.circle_timeout:
                raise RuntimeError(f"绕圈超过 {config.circle_timeout} 秒，一个蛋也没孵出来")
            else:
                time.sleep(config.circle_interval)
    finally:
        _stop_circle(sw)
    return "check"
