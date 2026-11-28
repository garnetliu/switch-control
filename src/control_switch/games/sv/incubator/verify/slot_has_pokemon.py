from control_switch.flow import read_stable
from control_switch.vision import ImageChecker

from ..session import IncubatorSession


def _panel_present(image: ImageChecker) -> bool:
    """右边的面板上有宝可梦：顶上的名字栏是黄色，黄色占比超过 0.5。光标在空格上时没有面板。"""
    return image.color_ratio(((0.70, 0.01), (0.99, 0.06)), (20, 150, 180), (35, 255, 255)) > 0.5


def slot_has_pokemon(sw: IncubatorSession) -> bool:
    """光标所在的格子里有没有宝可梦：连着 3 帧看右边的面板，结果一样才算（光标刚到时面板还没换）。"""
    return read_stable(sw, _panel_present, "格子里有没有宝可梦")
