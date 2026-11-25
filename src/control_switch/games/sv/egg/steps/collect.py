"""collect：隔一会儿查一次篮子领蛋，收够了或三明治快失效就收野餐。"""

import logging
import time
from typing import cast

from control_switch.flow import capture, wait_for
from control_switch.session import Session

from .. import screens
from ..box import (
    leave_picnic,
)
from ..config import EggConfig
from ..session import EggSession


def _open_basket(sw: Session) -> None:
    """按 A 查篮子，等对话框；没有就吹口哨再试，试几次后转镜头。"""
    config = cast(EggConfig, sw.config)
    for attempt in range(config.collect_attempts):
        if attempt:
            sw.click("R", config.whistle_wait)
            if attempt % config.camera_turn_every == 0:
                sw.stick("RIGHT", -sw.controller.STICK_MAX, 0, config.camera_turn_hold)
        sw.click("A", config.collect_wait)
        try:
            wait_for(sw, lambda s: screens.is_dialog(s, config), config.dialog_wait, "篮子的对话")
            return
        except TimeoutError:
            continue
    raise RuntimeError(f"按了 {config.collect_attempts} 次 A，一直没有对话框，可能没走到篮子前")


def _wait_with_keepalive(sw: Session, seconds: float) -> None:
    """等 seconds 秒，期间隔一会儿按一下键，不让 Switch 休眠。"""
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        sw.click(config.keepalive_button, 0)
        time.sleep(min(config.keepalive_gap, max(deadline - time.monotonic(), 0)))


def _quiet(sw: Session) -> bool:
    """篮子的对话结束了：连续 quiet_frames 帧都没有对话框，并且回到了野餐画面。"""
    config = cast(EggConfig, sw.config)
    for frame in range(config.quiet_frames):
        if frame:
            time.sleep(config.quiet_gap)
        image = capture(sw, "篮子的对话结束了吗")
        if screens.is_dialog(image, config) or not screens.is_picnic(image, config):
            return False
    return True


def collect(sw: EggSession) -> str:
    """查一次篮子，领蛋；收够了或者时间到了就收野餐。"""
    sw.frames.clear()
    config = sw.config
    before = sw.eggs_in_box
    _open_basket(sw)
    deadline = time.monotonic() + config.collect_timeout
    # 拒绝领蛋之后会再出一个是/否，要选「是」
    refusing = False
    while not _quiet(sw):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"查篮子等了 {config.collect_timeout} 秒还没结束")
        image = capture(sw, "篮子")
        if screens.is_prompt(image, config):
            if refusing:
                sw.click("A", config.collect_wait)
                refusing = False
            elif sw.eggs_in_box < config.max_eggs:
                sw.click("A", config.collect_wait)
                sw.eggs_in_box += 1
            else:
                sw.click("B", config.collect_wait)
                refusing = True
        elif screens.is_dialog(image, config):
            # 普通对话按 B 推进，免得把没认出的是/否按成「是」
            sw.click("B", config.collect_wait)
    logging.info(f"这次收了 {sw.eggs_in_box - before} 个蛋，一共 {sw.eggs_in_box} 个")
    started = time.monotonic() if sw.sandwich_at is None else sw.sandwich_at
    minutes = (time.monotonic() - started) / 60
    if sw.eggs_in_box < config.max_eggs and minutes < config.picnic_minutes:
        _wait_with_keepalive(sw, config.basket_interval)
        return "collect"
    leave_picnic(sw)
    return "hatch_load"
