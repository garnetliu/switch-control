"""在野外存档，存完回到野外。"""

import logging
import time

from control_switch.flow import capture
from control_switch.games.sv import screens
from control_switch.games.sv.session import SvSession


def save_game(sw: SvSession) -> None:
    """在野外存档，存完回到野外。

    状态：野外按 X 开菜单；菜单按 R 出存档的确认框；确认框按 A；存完的对话按 B，菜单再按 B 回到野外。
    """
    config = sw.config
    logging.info("存档")
    deadline = time.monotonic() + config.save.timeout
    saved = False
    # 按了「是」之后，存档的过程中菜单还在，不能再按 R；存完的对话一直没出来才重来
    confirmed_at: float | None = None
    while True:
        image = capture(sw, "存档")
        now = time.monotonic()
        if confirmed_at is not None and now - confirmed_at > config.save.confirm_timeout:
            confirmed_at = None
        if screens.is_overworld(image, config):
            if saved:
                return
            sw.click("X", config.save.press_wait)
        elif screens.is_prompt(image, config):
            sw.click("A", config.save.press_wait)
            confirmed_at = now
        elif screens.is_dialog(image, config):
            sw.click("B", config.save.press_wait)
            saved = True
            confirmed_at = None
        elif screens.has_dialog_box(image, config):
            # 字还在一个个出来，等它出完
            time.sleep(config.wait.interval)
        elif screens.is_main_menu(image, config):
            if confirmed_at is None:
                sw.click("B" if saved else "R", config.save.press_wait)
            else:
                time.sleep(config.wait.interval)
        else:
            time.sleep(config.wait.interval)
        if now >= deadline:
            raise TimeoutError(f"等了 {config.save.timeout} 秒，还是没存完档")
