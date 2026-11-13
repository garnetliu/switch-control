import logging
import shutil

from swsh.lair.switch import LairSwitch
from tools import menu_last_item, press_until
from tools.log import new_log


def initialize(sw: LairSwitch) -> str:
    """确认前台是剑/盾，把游戏带到科学家面前、没有对话框的状态，返回下一步 "join"。

    游戏要停在科学家面前。一直按 A，把中途退出的罚款提醒（「是 / 否」光标默认在「是」上，
    按 A 就是付）和其它提示都过掉，直到开场白的菜单「现在就出发 / 我想听讲解 / 还是先算了」出现；
    再一直按 B，直到对话框消失。前台不是剑/盾抛 RuntimeError；按键超时抛 TimeoutError。
    """
    # 每一局一个日志文件：新的一局从这里开始，换一个新文件
    new_log(sw, "start")
    # 上一局没出错，截图丢掉
    sw.frames.clear()

    rects = sw.config.rects
    title_id = sw.title_id().upper()
    if title_id not in sw.config.game_title_ids:
        raise RuntimeError(f"前台不是剑/盾（Title ID {title_id}）")
    press_until(
        sw,
        lambda screen: (
            menu_last_item(screen, rects.menu_search, dialog=rects.white_center_line1)
            == "还是先算了"
        ),
        "开场白的菜单",
    )
    press_until(
        sw,
        lambda screen: not screen.read_text(rects.white_center_line1),
        "对话框消失",
        button="B",
    )
    _clean_logs(sw)
    return "join"


def _clean_logs(sw: LairSwitch) -> None:
    """清空这个脚本的日志目录，直接删除，不进回收站。

    留下 start（运行日志）和 failed（出错时存下的截图）。
    """
    removed = 0
    for path in sw.config.log_dir.iterdir():
        if path.name in ("start", sw.config.failed_dir.name):
            continue
        if path.is_dir():
            removed += sum(1 for item in path.rglob("*") if item.is_file())
            shutil.rmtree(path)
        else:
            path.unlink()
            removed += 1
    logging.info(f"清空 {sw.config.log_dir.name} 的日志，删掉 {removed} 个文件")
