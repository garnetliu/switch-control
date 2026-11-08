from config.layout import DIALOG_RECT
from lib import switch
from lib.dialog import menu_last_item, press_until
from lib.game_state import GameState


def initialize(game: GameState) -> str:
    """确认前台是剑/盾，把游戏带到科学家面前、没有对话框的状态，返回下一步 "join"。

    游戏要停在科学家面前。一直按 A，把中途退出的罚款提醒（「是 / 否」光标默认在「是」上，
    按 A 就是付）和其它提示都过掉，直到开场白的菜单「现在就出发 / 我想听讲解 / 还是先算了」出现；
    再一直按 B，直到对话框消失。使用全局连接，需要先调用 switch.connect。
    前台不是剑/盾抛 RuntimeError；按键超时抛 TimeoutError。
    """
    # 《宝可梦 剑》《宝可梦 盾》的 Title ID
    sword, shield = "0100ABF008968000", "01008DB008C2C000"

    title_id = switch.get().title_id().upper()
    if title_id not in (sword, shield):
        raise RuntimeError(f"前台不是剑/盾（Title ID {title_id}）")
    press_until(lambda screen: menu_last_item(screen) == "还是先算了", "开场白的菜单")
    press_until(
        lambda screen: not screen.read_text(DIALOG_RECT),
        "对话框消失",
        button="B",
    )
    return "join"
