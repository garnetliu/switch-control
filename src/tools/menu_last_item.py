"""和游戏里的人对话：认出菜单。"""

from libs import ImageChecker, Switch
from type import Rect


def menu_last_item(
    sw: Switch,
    screen: ImageChecker,
    index: int = -1,
    area: Rect | None = None,
) -> str:
    """读菜单里第 index 项的文本，默认最后一项；没有菜单返回空字符串。

    用默认的对话菜单范围时，先确认下方有对话文字（菜单只跟着对话出现）；
    传其它 area（比如大厅菜单）时不检查对话框。
    """
    if area is None:
        area = sw.config.rects.menu_search
    if area == sw.config.rects.menu_search and not screen.read_text(
        sw.config.rects.white_center_line1
    ):
        return ""
    found = screen.find_menu(area)
    if found is None:
        return ""
    _, options = found
    return options[index][0] if options else ""
