import logging
import shutil

from libs import Switch
from tools import menu_last_item, press_until
from tools.log import new_log


def initialize(sw: Switch) -> str:
    """确认前台是剑/盾，把游戏带到科学家面前、没有对话框的状态，返回下一步 "join"。

    游戏要停在科学家面前。一直按 A，把中途退出的罚款提醒（「是 / 否」光标默认在「是」上，
    按 A 就是付）和其它提示都过掉，直到开场白的菜单「现在就出发 / 我想听讲解 / 还是先算了」出现；
    再一直按 B，直到对话框消失。前台不是剑/盾抛 RuntimeError；按键超时抛 TimeoutError。
    """
    # 每一局一个日志文件：新的一局从这里开始，换一个新文件
    new_log(sw, "start")
    # 《宝可梦 剑》《宝可梦 盾》的 Title ID
    sword, shield = "0100ABF008968000", "01008DB008C2C000"

    title_id = sw.title_id().upper()
    if title_id not in (sword, shield):
        raise RuntimeError(f"前台不是剑/盾（Title ID {title_id}）")
    press_until(sw, lambda screen: menu_last_item(sw, screen) == "还是先算了", "开场白的菜单")
    press_until(
        sw,
        lambda screen: not screen.read_text(sw.config.rects.white_center_line1),
        "对话框消失",
        button="B",
    )
    _clean_logs(sw)
    return "join"


def _clean_logs(sw: Switch) -> None:
    """清空 logs，直接删除，不进回收站。

    留下 start（运行日志）和 keep（长期留着的截图）。
    """
    removed = 0
    for path in sw.config.log_dir.iterdir():
        if path.name in ("start", sw.config.keep_dir.name):
            continue
        if path.is_dir():
            removed += sum(1 for item in path.rglob("*") if item.is_file())
            shutil.rmtree(path)
        else:
            path.unlink()
            removed += 1
    logging.info(f"清空 logs，删掉 {removed} 个文件")
