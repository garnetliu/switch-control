from config.layout import DIALOG_RECT
from config.timing import DEFAULT_TIMEOUT
from lib import switch
from lib.dialog import advance_until, menu_items
from lib.scientist import open_start_dialog
from lib.wait import wait_for


def initialize() -> str:
    """确认前台是剑/盾，并且游戏停在科学家面前、没有对话框，返回下一步的名字 "join"。

    和科学家说话直到出现开场白（有中途退出的罚款就先付掉，见 lib/scientist.py），
    再按 B 直到对话框消失。使用全局连接，需要先调用 switch.connect。
    前台不是剑/盾、按了 B 对话框还在会抛 RuntimeError，一直等不到开场白会抛 TimeoutError。
    """
    # 《宝可梦 剑》《宝可梦 盾》的 Title ID
    sword, shield = "0100ABF008968000", "01008DB008C2C000"
    # 退出对话最多按几次 B
    max_b = 30

    title_id = switch.get().title_id().upper()
    if title_id not in (sword, shield):
        raise RuntimeError(f"前台不是剑/盾（Title ID {title_id}）")
    open_start_dialog()
    # 开场白出来时旁边的菜单不一定画好了：这时按 B 只是把菜单叫出来，对话文字不变（真机上遇到过），
    # 所以先等菜单出来或者对话框消失，菜单在就再按 B 退出
    switch.get().click("B", 0)
    wait_for(
        lambda screen: "还是先算了" in menu_items(screen) or not screen.read_text(DIALOG_RECT),
        DEFAULT_TIMEOUT,
        "开场白旁边的菜单或者对话框消失",
    )
    advance_until(
        lambda screen: not screen.read_text(DIALOG_RECT),
        "对话框消失",
        button="B",
        max_presses=max_b,
    )
    return "join"
