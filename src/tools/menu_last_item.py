"""和游戏里的人对话：认出菜单。"""

from libs import ImageChecker
from type import Rect


def menu_last_item(
    screen: ImageChecker,
    area: Rect,
    index: int = -1,
    dialog: Rect | None = None,
) -> str:
    """读 area 里的菜单第 index 项的文本，默认最后一项；没有菜单返回空字符串。

    菜单只跟着对话出现时传 dialog（对话文字的范围）：那里没有文字就当作没有菜单。
    """
    if dialog is not None and not screen.read_text(dialog):
        return ""
    found = screen.find_menu(area)
    if found is None:
        return ""
    _, options = found
    return options[index][0] if options else ""
