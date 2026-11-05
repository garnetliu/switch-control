import time

from config.game import (
    BASE_BALL,
    LEGENDARY_BALL,
    LOCK_MAX_FAINTS,
    LOCK_MAX_MINUTES,
    RECORD_LOCATION,
)
from config.layout import (
    DIALOG_RECT,
    RESULT_MENU_RECT,
    RESULT_ROW_RECTS,
    RESULT_TITLE_RECT,
    SHINY_RECT,
    SUMMARY_NAME_LABEL_RECT,
    SUMMARY_NAME_RECT,
)
from config.paths import CATCH_DIR
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, TICK_SECONDS
from lib import run, switch
from lib.dialog import advance_until
from lib.game import restart
from lib.log import log
from lib.scientist import START_TEXT
from lib.wait import capture, wait_for
from tool.check_image import ImageChecker
from tool.image import save, text_lines

# 带走界面的标题
RESULT_TEXT = "选1只要带回去的宝可梦"
# 打赢之后科学家问要不要记录位置。待实测
RECORD_TEXT = "记录"


def select_pokemon() -> str | None:
    """一局结束：一只只查抓到的宝可梦是不是闪光，有闪光就带走，然后按 keep path 收尾。照搬上游。

    开始时游戏在 catch 或 battle 结束之后。使用全局连接，需要先调用 switch.connect。
    要不要 keep path 在这里按这一局的结果决定，见 _update_keep_path。
    - 一只都没抓到：keep path 重启游戏，否则回到科学家面前。
    - 有闪光：带走，回到科学家面前继续刷。
    - 没有闪光：keep path 重启游戏；否则不带走，打赢了按配置记录位置。
    返回 "join" 接着刷；球不够下一局、或者要等人决定记不记录位置时返回 None，脚本停下。
    """
    current = run.get()
    if current.num_caught == 0:
        log("一只都没抓到")
        if _update_keep_path():
            _restart_same_seed()
            return "join"
        run.save()
        return "join" if _back_to_scientist() else None

    image = wait_for(
        lambda screen: screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT), 60, "带走宝可梦的界面"
    )
    _save_screenshot(image, "list")
    shiny = _find_shiny()
    if shiny is not None:
        _take(shiny)
        # 带走了，这张图就打完了，下一局是新的图
        current.keep_path = False
    elif _update_keep_path():
        _restart_same_seed()
        return "join"
    else:
        _leave()
    if shiny == 3:
        # 闪光的神兽带走了，这只刷完了，清掉所有状态
        log("带走了闪光的神兽，清掉所有状态")
        run.clear()
    else:
        run.save()
    if not _back_to_scientist():
        return None

    # 下一局要 3 个普通球和 1 个首领球，两种是同一种球时要 4 个
    balls = current.balls
    enough = (
        balls.get(BASE_BALL, 4) >= 4
        if BASE_BALL == LEGENDARY_BALL
        else balls.get(BASE_BALL, 3) >= 3 and balls.get(LEGENDARY_BALL, 1) >= 1
    )
    if not enough:
        log(f"球不够下一局了: {balls}", "WARNING")
        return None
    return "join"


def _find_shiny() -> int | None:
    """打开资料页，从最后抓到的那只（打赢了就是首领）开始一只只往前查闪光，
    返回第一只闪光在列表上的位置（从 0 开始，和抓到的顺序一致），都不是返回 None。

    列表上光标在第一只，往上推一下绕到最后一只；按 A 弹出「选择 / 查看能力 / 取消」，
    往下推一下到「查看能力」再按 A 进资料页；资料页上往上推一下就是前一只（真机实测）。
    """
    current = run.get()
    sw = switch.get()
    last = current.num_caught - 1
    sw.stick("LEFT", 0, switch.STICK_MAX, TICK_SECONDS)
    wait_for(
        lambda screen: screen.selected(list(RESULT_ROW_RECTS[: last + 1])) == last,
        DEFAULT_TIMEOUT,
        "列表光标移到最后一只",
    )
    sw.click("A", 0)
    wait_for(lambda screen: _menu_selected(screen) == 0, DEFAULT_TIMEOUT, "选择 / 查看能力 / 取消")
    sw.stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
    wait_for(lambda screen: _menu_selected(screen) == 1, DEFAULT_TIMEOUT, "光标移到「查看能力」")
    sw.click("A", 0)
    image = wait_for(
        lambda screen: screen.has_text(SUMMARY_NAME_LABEL_RECT, "名字"), LOAD_TIMEOUT, "资料页"
    )

    for index in range(last, -1, -1):
        name = image.read_text(SUMMARY_NAME_RECT).strip()
        if index == last:
            _save_screenshot(image, "summary")
        if _is_shiny():
            log(
                f"闪光！第 {index + 1} 只 {current.caught[index]}（资料页上是「{name}」）",
                "WARNING",
            )
            return index
        log(f"第 {index + 1} 只「{name}」不是闪光")
        if index > 0:
            sw.stick("LEFT", 0, switch.STICK_MAX, TICK_SECONDS)
            image = wait_for(
                lambda screen, before=name: (
                    screen.read_text(SUMMARY_NAME_RECT).strip() not in ("", before)
                ),
                DEFAULT_TIMEOUT,
                "资料页换到前一只",
            )
    return None


def _is_shiny() -> bool:
    """资料页上的闪光标志：照搬上游，闪光框里高饱和像素的占比（0 到 255）超过 10。

    沿用旧项目的两条保护：连看几帧，任何一帧是闪光就算（漏掉闪光无法挽回，误报只是停下来）；
    占比超过 100 说明画面根本不是资料页（真闪光约 27），这一帧不算。
    """
    # 连看几帧
    frames = 3
    # 闪光的最低占比、不是资料页的最高占比（0 到 255）
    threshold, invalid = 10, 100

    for _ in range(frames):
        value = capture().color_ratio(SHINY_RECT, (0, 100, 20), (180, 255, 255)) * 255
        log(f"闪光框的占比 {value:.1f}", "DEBUG")
        if threshold < value <= invalid:
            return True
    return False


def _take(index: int) -> None:
    """带走第 index 只：资料页按 B 回到列表，A 弹出菜单，在「选择」上按 A，把确认的对话推进完。

    待实测：还没遇到过闪光，带走的对话怎么走没见过。
    """
    current = run.get()
    sw = switch.get()
    sw.click("B", 0)
    wait_for(
        lambda screen: screen.selected(list(RESULT_ROW_RECTS[: current.num_caught])) == index,
        DEFAULT_TIMEOUT,
        "回到列表，光标在要带走的那只上",
    )
    sw.click("A", 0)
    wait_for(lambda screen: _menu_selected(screen) == 0, DEFAULT_TIMEOUT, "光标在「选择」上")
    sw.click("A", 0)
    wait_for(
        lambda screen: not screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT),
        DEFAULT_TIMEOUT,
        "带走界面消失",
    )
    log(f"带走了 {current.caught[index]}")


def _leave() -> None:
    """不带走：资料页按 B 回到列表，再按 B 退出。照搬上游。待实测"""
    sw = switch.get()
    sw.click("B", 0)
    wait_for(
        lambda screen: not screen.has_text(SUMMARY_NAME_LABEL_RECT, "名字"),
        DEFAULT_TIMEOUT,
        "回到列表",
    )
    sw.click("B", 0)
    wait_for(
        lambda screen: not screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT),
        DEFAULT_TIMEOUT,
        "带走界面消失",
    )
    log("一只都不带走")


def _back_to_scientist() -> bool:
    """按 A 推进结算的对话，直到科学家的开场白出现，再按 B 退出对话。照搬上游。

    打赢之后中途会问要不要记录位置：RECORD_LOCATION 为 True 时按 A 记录；
    为 False 时停在这一步，返回 False。待实测：结算的对话还没在真机上走过。
    """
    image = advance_until(
        lambda screen: (
            screen.has_text(DIALOG_RECT, START_TEXT)
            or (not RECORD_LOCATION and screen.has_text(DIALOG_RECT, RECORD_TEXT))
        ),
        "科学家的开场白",
        max_presses=30,
        timeout=LOAD_TIMEOUT,
    )
    if not image.has_text(DIALOG_RECT, START_TEXT):
        log("科学家问要不要记录位置，配置是不自动记录，停下来等人决定", "WARNING")
        return False
    advance_until(
        lambda screen: not screen.read_text(DIALOG_RECT), "对话框消失", button="B", max_presses=5
    )
    return True


def _update_keep_path() -> bool:
    """查完闪光、没有可带走的之后，决定下一局要不要 keep path，记到这一局里，返回决定。

    这一局已经是 keep path（在锁定的图上开局）就不用再判断，继续锁定。
    否则照旧项目的规则：打赢、倒下不超过 LOCK_MAX_FAINTS 次、用时不超过 LOCK_MAX_MINUTES 分钟，
    就锁定这张图。
    """
    current = run.get()
    if current.plan is not None:
        current.keep_path = True
        return True
    won = current.num_caught == 4
    faints = 4 - current.lives
    minutes = (time.time() - current.started) / 60
    current.keep_path = won and faints <= LOCK_MAX_FAINTS and minutes <= LOCK_MAX_MINUTES
    log(
        f"这一局 {current.path_name()}：{'赢' if won else '输'}，倒下 {faints} 次，"
        f"用时 {minutes:.1f} 分钟，{'锁定这张图' if current.keep_path else '不锁定'}"
    )
    return current.keep_path


def _restart_same_seed() -> None:
    """keep path：把这一局写进状态文件（下一局沿用），然后重启游戏，回到存档里同一张路线图。"""
    run.save()
    log("keep path，重启游戏回到同一张路线图")
    restart()


def _menu_selected(screen: ImageChecker) -> int:
    """「选择 / 查看能力 / 取消」菜单上光标在第几项（从 0 开始），菜单不在返回 -1。

    菜单跟着列表上选中的那一行出现，位置不固定，所以先在列表区域里找到这三项的文字，再比亮度。
    """
    lines = {text: rect for text, rect in text_lines(screen, RESULT_MENU_RECT)}
    if not all(item in lines for item in ("选择", "查看能力", "取消")):
        return -1
    return screen.selected([lines["选择"], lines["查看能力"], lines["取消"]])


def _save_screenshot(image: ImageChecker, kind: str) -> None:
    """把战果截图存进 CATCH_DIR，文件名带时间。只留最新的一些，旧的删掉。"""
    # 最多留几张
    keep = 200

    CATCH_DIR.mkdir(parents=True, exist_ok=True)
    path = CATCH_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.jpg"
    save(image, str(path))
    for old in sorted(CATCH_DIR.glob("*.jpg"))[:-keep]:
        old.unlink()
    log(f"战果截图: {path}", "DEBUG")
