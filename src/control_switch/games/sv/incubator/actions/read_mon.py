from control_switch.flow import capture, press_until, read_stable

from .. import verify
from ..session import IncubatorSession
from ..types import Mon
from .read_name import read_name


def read_mon(sw: IncubatorSession, read_best: bool = True) -> Mon:
    """读光标所在格子里的宝可梦：名字、「最棒」的项数、是不是闪光。

    read_best 是 False 时不切评定页读「最棒」的项数（不用换亲代时用不到）。蛋、不读、读不到都是 -1。
    """
    name = read_name(sw)
    shiny = _read_shiny(sw)
    best = _read_best(sw) if read_best and not name.startswith("蛋") else -1
    return Mon(name, best, shiny)


def _read_shiny(sw: IncubatorSession) -> bool:
    """面板上有没有闪光的星星，连着几帧一样才算。"""
    return read_stable(sw, verify.panel_shiny, "闪光的星星")


def _read_best(sw: IncubatorSession) -> int:
    """切到评定页读「最棒」的项数：不在评定页就按 PLUS 切过去。

    按了 3 秒还切不到评定页，说明游戏里评定功能没解锁，返回 -1。
    """
    image = capture(sw, "评定页")
    if not verify.is_judge_page(image):
        try:
            image = press_until(
                sw,
                lambda: sw.click("PLUS", 0),
                verify.is_judge_page,
                "评定页",
                timeout=3.0,
            )
        except TimeoutError:
            return -1
    return sum("最棒" in text for text in verify.panel_stats(image))
