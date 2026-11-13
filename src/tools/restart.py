"""重启游戏。"""

import logging

from libs import ImageChecker, Switch
from tools.wait import capture, press_until, wait_for


def restart(sw: Switch) -> None:
    """关掉游戏再重新打开，直到开场画面变黑并停止按键。"""
    restart_to_title(sw)
    enter_game(sw)
    logging.info("游戏已重启")


def restart_to_title(sw: Switch) -> None:
    """关掉游戏再重新打开，等到开场的彩色画面出现为止，不按键进游戏。

    做法：HOME 菜单上按 Y 切换用户，要先关掉正在运行的软件，确认框默认选中「关闭」，按 A；
    关掉之后出现选用户的界面，按 A 用默认选中的用户，游戏就直接重新启动了。
    """
    rects = sw.config.rects
    # 已经在 HOME 上就不能再按 HOME：HOME 上按 HOME 是回到游戏（真机上因此重启失败过）
    if not _home_shown(sw, capture(sw, "是不是在 HOME 菜单")):
        sw.click("HOME", 0)
        wait_for(sw, lambda screen: _home_shown(sw, screen), sw.config.timeout, "HOME 菜单")
    # HOME 菜单刚出来时按的 Y 会被吞掉（真机上出现过，画面停在 HOME），所以一直按到确认框出来
    press_until(
        sw,
        lambda screen: screen.has_text(rects.close_dialog, "将关闭软件"),
        "切换用户前关闭软件的确认框",
        button="Y",
    )
    sw.click("A", 0)
    wait_for(
        sw,
        lambda screen: screen.has_text(rects.user_picker, "由谁来游玩软件"),
        sw.config.load_timeout,
        "选用户的界面",
    )
    sw.click("A", 0)
    logging.info("游戏已关闭，重新启动")
    wait_for(
        sw,
        lambda screen: _game_running(sw) and _colorful(sw, screen),
        sw.config.boot_timeout,
        "开场的彩色画面",
    )


def enter_game(sw: Switch) -> None:
    """开场彩色画面出现之后用：持续按 A，每次截图检查，画面变黑就停止。"""
    screen = capture(sw, "进游戏")
    presses = 0
    while not screen.is_black():
        sw.click("A", 0)
        presses += 1
        screen = capture(sw, "进游戏")
    logging.info(f"画面变黑，停止按 A（共按 {presses} 次）")


def _home_shown(sw: Switch, screen: ImageChecker) -> bool:
    """HOME 菜单：游戏图标下面有「切换用户」的提示。"""
    return screen.has_text(sw.config.rects.home_hint, "切换用户")


def _game_running(sw: Switch) -> bool:
    """前台正在运行的是这个脚本的游戏。"""
    return sw.title_id().strip().upper() in sw.config.game_title_ids


def _colorful(sw: Switch, screen: ImageChecker) -> bool:
    """画面是彩色的：开机 logo 和黑屏 0，选用户的界面 0.08，HOME 0.21，开场动画、标题画面和游戏里都在 0.32 以上。"""
    return (
        screen.color_ratio(((0, 0), (1, 1)), sw.config.colorful_lower, sw.config.colorful_upper)
        >= sw.config.colorful_ratio
    )
