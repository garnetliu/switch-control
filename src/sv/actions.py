"""朱紫里几个脚本都会用到的操作：存档、开野餐、收野餐。

按键和等待时间照 Eppin/Sysbot.NET 的 SaveGame、DoPicnicResetting，每个键按完固定等一会儿。
每一步等完都留一张截图（keep_image），以后照着截图改成看画面判断。
"""

import logging

from libs import Switch
from tools import capture, keep_image


def save_game(sw: Switch) -> None:
    """在野外存档，存完回到野外。"""
    config = sw.config
    logging.info("存档")
    sw.click("X", config.save_menu_wait)
    keep_image(sw, capture(sw), "菜单")
    sw.click("R", config.save_prompt_wait)
    keep_image(sw, capture(sw), "存档的确认框")
    sw.click("A", config.save_done_wait)
    keep_image(sw, capture(sw), "存档完成")
    for _ in range(config.save_back):
        sw.click("B", config.save_back_wait)
    keep_image(sw, capture(sw), "野外")


def open_picnic(sw: Switch) -> None:
    """在野外开野餐。菜单的光标要事先停在「野餐」上。"""
    config = sw.config
    logging.info("开野餐")
    sw.click("X", config.picnic_menu_wait)
    sw.click("A", config.picnic_open_wait)
    keep_image(sw, capture(sw), "野餐")


def close_picnic(sw: Switch) -> None:
    """收起野餐，回到野外。"""
    config = sw.config
    logging.info("收起野餐")
    sw.click("Y", config.picnic_close_prompt_wait)
    keep_image(sw, capture(sw), "收起野餐的确认框")
    sw.click("A", config.picnic_close_wait)
