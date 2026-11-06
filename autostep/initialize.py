from config.layout import DIALOG_RECT
from lib import switch
from lib.dialog import advance_until, menu_last_item, press_until


def initialize() -> str:
    """确认前台是剑/盾，并且游戏停在科学家面前、没有对话框，返回下一步的名字 "join"。

    在科学家面前一直按 A，直到开场白旁边的「现在就出发 / 我想听讲解 / 还是先算了」出来：
    前面中途退出的罚款（「是 / 否」光标默认在「是」上，按 A 就是付）、提醒都用 A 过掉，不认文字。
    再按 B 直到对话框消失。使用全局连接，需要先调用 switch.connect。
    前台不是剑/盾、按了 B 对话框还在会抛 RuntimeError。
    """
    # 《宝可梦 剑》《宝可梦 盾》的 Title ID
    sword, shield = "0100ABF008968000", "01008DB008C2C000"
    # 退出对话最多按几次 B
    max_b = 30

    title_id = switch.get().title_id().upper()
    if title_id not in (sword, shield):
        raise RuntimeError(f"前台不是剑/盾（Title ID {title_id}）")
    press_until(lambda screen: menu_last_item(screen) == "还是先算了", "开场白的菜单")
    advance_until(
        lambda screen: not screen.read_text(DIALOG_RECT),
        "对话框消失",
        button="B",
        max_presses=max_b,
    )
    return "join"
