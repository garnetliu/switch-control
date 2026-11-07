"""游戏软件本身的操作：重启游戏。"""

from config.layout import (
    CLOSE_DIALOG_RECT,
    HOME_HINT_RECT,
    USER_PICKER_RECT,
    Y_COMM_RECT,
)
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT
from lib import data, switch
from lib.dialog import press_until
from lib.log import log
from lib.wait import capture, wait_for
from tool.check_image import ImageChecker

# 《宝可梦 剑》《宝可梦 盾》的 Title ID
GAME_TITLE_IDS = ("0100ABF008968000", "01008DB008C2C000")


def restart() -> None:
    """关掉游戏再重新打开，直到开场画面变黑并停止按键。

    做法：HOME 菜单上按 Y 切换用户，要先关掉正在运行的软件，确认框默认选中「关闭」，按 A；
    关掉之后出现选用户的界面，按 A 用默认选中的用户，游戏就直接重新启动了。
    冒险途中重启会放弃这一局，下次和科学家说话时要付极矿石作为罚款。
    使用全局连接，需要先调用 switch.connect。
    """
    sw = switch.get()
    # 已经在 HOME 上就不能再按 HOME：HOME 上按 HOME 是回到游戏（真机上因此重启失败过）
    if not _home_shown(capture()):
        sw.click("HOME", 0)
        wait_for(_home_shown, DEFAULT_TIMEOUT, "HOME 菜单")
    # HOME 菜单刚出来时按的 Y 会被吞掉（真机上出现过，画面停在 HOME），所以一直按到确认框出来
    press_until(
        lambda screen: screen.has_text(CLOSE_DIALOG_RECT, "将关闭软件"),
        "切换用户前关闭软件的确认框",
        button="Y",
    )
    sw.click("A", 0)
    wait_for(
        lambda screen: screen.has_text(USER_PICKER_RECT, "由谁来游玩软件"),
        LOAD_TIMEOUT,
        "选用户的界面",
    )
    sw.click("A", 0)
    log("游戏已关闭，重新启动")
    _enter_game()
    log("游戏已重启")


def _enter_game() -> None:
    """等开场彩色画面出现后持续按 A，每次截图检查，画面变黑就停止。"""
    # 从开始启动到出现彩色画面，最多等几秒（不跳过开场动画时实测约 15 秒）
    boot_timeout = 60.0
    screen = wait_for(
        lambda screen: _game_running() and _colorful(screen), boot_timeout, "开场的彩色画面"
    )
    presses = 0
    while not screen.is_black():
        switch.get().click("A", 0)
        presses += 1
        screen = capture()
    log(f"画面变黑，停止按 A（共按 {presses} 次）")


def _home_shown(screen: ImageChecker) -> bool:
    """HOME 菜单：游戏图标下面有「切换用户」的提示。"""
    return screen.has_text(HOME_HINT_RECT, "切换用户")


def _game_running() -> bool:
    """前台正在运行的是剑或盾。"""
    return switch.get().title_id().strip().upper() in GAME_TITLE_IDS


def _colorful(screen: ImageChecker) -> bool:
    """画面是彩色的：鲜艳的像素（饱和度、亮度都不低）至少占三成。

    真机截图上：开机 logo 和黑屏 0，选用户的界面 0.08，HOME 0.21，
    开场动画、标题画面和游戏里都在 0.32 以上。
    """
    return screen.color_ratio(((0, 0), (1, 1)), (0, 100, 60), (180, 255, 255)) >= 0.3


def _in_game(screen: ImageChecker) -> bool:
    """站在场景里、没有对话框：左下角有 Y 通信图标。"""
    return screen.match_template(Y_COMM_RECT, data.misc_icons()["y_comm"]) >= 0.85
