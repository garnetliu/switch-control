"""主菜单里把光标移到右边第 row 行（从 0 数），按 A 进去。"""

from control_switch.flow import capture, press_until
from control_switch.games.sv import screens
from control_switch.games.sv.session import SvSession


def menu_to_row(sw: SvSession, row: int) -> None:
    """主菜单里把光标移到右边第 row 行（从 0 数），按 A 进去。

    光标可能在左边的队伍栏上（上次是从队伍栏退出来的），先按 DRIGHT 到右边。
    """
    config = sw.config
    image = capture(sw, "主菜单")
    if screens.menu_row(image, config) == -1:
        image = press_until(
            sw,
            lambda: sw.click("DRIGHT", 0),
            lambda s: screens.menu_row(s, config) != -1,
            sw.config.wait.timeout,
            "主菜单光标到右边",
            interval=config.menu.move_wait,
        )
    current = screens.menu_row(image, config)
    while current != row:
        button = "DDOWN" if row > current else "DUP"
        before = current
        image = press_until(
            sw,
            lambda key=button: sw.click(key, 0),
            lambda s, last=before: screens.menu_row(s, config) not in (last, -1),
            sw.config.wait.timeout,
            "主菜单的光标移一格",
            interval=config.menu.move_wait,
        )
        current = screens.menu_row(image, config)
    # A 有时被吞掉（菜单还在），隔一会儿没进去就再按一次
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_main_menu(s, config),
        sw.config.wait.timeout,
        "进主菜单的这一行",
        interval=config.menu.enter_interval,
    )
