"""在野外按 X 打开主菜单，认到菜单为止。"""

from control_switch.flow import press_until
from control_switch.games.sv import screens
from control_switch.games.sv.session import SvSession


def open_menu(sw: SvSession) -> None:
    """在野外按 X 打开主菜单，认到菜单为止。

    按 X 有时没反应（真机上刚退回野外时按的那次被吞掉过），所以隔 menu.retry 秒没出菜单就再按一次。
    """
    config = sw.config
    press_until(
        sw,
        lambda: sw.click("X", 0),
        lambda s: screens.is_main_menu(s, config),
        sw.config.wait.timeout,
        "主菜单",
        interval=config.menu.retry,
    )
