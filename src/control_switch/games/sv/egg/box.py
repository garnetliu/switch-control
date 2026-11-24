"""主菜单和盒子里的操作。"""

import logging
import time
from typing import cast

from control_switch.flow import act_until, capture, wait_for
from control_switch.session import Session
from control_switch.vision import ImageChecker

from . import screens
from .config import EggConfig
from .screens import Cursor


def _config(sw: Session) -> EggConfig:
    return cast(EggConfig, sw.config)


def open_menu(sw: Session) -> ImageChecker:
    """按 X 打开主菜单，等到认出菜单，返回那张截图。

    按 X 有时没反应（真机上刚退回野外时按的那次被吞掉过），所以隔 menu_retry 秒没出菜单就再按一次。
    """
    config = _config(sw)
    return act_until(
        sw,
        lambda: sw.click("X", 0),
        lambda s: screens.menu_row(s, config) != -1,
        "主菜单",
        interval=config.menu_retry,
        timeout=config.timeout,
    )


def menu_to_row(sw: Session, row: int) -> None:
    """主菜单光标移到第 row 行，按 A。"""
    config = _config(sw)
    image = wait_for(sw, lambda s: screens.menu_row(s, config) != -1, config.timeout, "主菜单")
    current = screens.menu_row(image, config)
    while current != row:
        button = "DDOWN" if row > current else "DUP"
        before = current
        image = act_until(
            sw,
            lambda button=button: sw.click(button, 0),
            lambda s, before=before: screens.menu_row(s, config) not in (before, -1),
            "主菜单的光标移一格",
        )
        current = screens.menu_row(image, config)
    # A 有时被吞掉（菜单还在），隔一会儿没进去就再按一次
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.menu_row(s, config) == -1,
        "进主菜单的这一行",
        interval=config.menu_enter_interval,
        timeout=config.timeout,
    )


def leave_picnic(sw: Session) -> None:
    """结束野餐：按 Y 直到出确认框，按 A 直到回到野外，最后再等一会儿。"""
    config = _config(sw)
    act_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: screens.is_prompt(s, config),
        "结束野餐的确认",
        interval=config.leave_prompt_interval,
        timeout=config.leave_prompt_timeout,
    )
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_overworld(s, config),
        "回到野外",
        interval=config.leave_overworld_interval,
        timeout=config.leave_overworld_timeout,
    )
    time.sleep(config.leave_final_wait)


def exit_to_overworld(sw: Session) -> None:
    """按 B 退出菜单或盒子，直到回到野外。"""
    config = _config(sw)
    presses = 0
    while True:
        image = capture(sw, "退出到野外")
        if screens.is_overworld(image, config):
            return
        if screens.is_picnic(image, config):
            # 在野餐里（出错后接着跑）：先结束野餐。食谱、三明治的画面认不出是什么，按 B 会回到野餐
            leave_picnic(sw)
            continue
        if presses >= config.exit_presses:
            break
        sw.click("B", config.exit_wait)
        presses += 1
    raise RuntimeError(f"按了 {config.exit_presses} 次 B，还是回不到野外")


def set_riding(sw: Session, want: bool) -> None:
    """骑上或下来：状态不对就关菜单按 PLUS，再开菜单确认一次；最后关菜单。"""
    config = _config(sw)
    image = open_menu(sw)
    if screens.is_riding(image, config) != want:
        exit_to_overworld(sw)
        sw.click("PLUS", config.ride_wait)
        image = open_menu(sw)
        if screens.is_riding(image, config) != want:
            raise RuntimeError(f"按了 PLUS，坐骑状态还是不对（要{'骑上' if want else '下来'}）")
    exit_to_overworld(sw)


def open_box(sw: Session) -> None:
    """从野外打开盒子（主菜单第 1 行）。"""
    config = _config(sw)
    open_menu(sw)
    menu_to_row(sw, 1)
    wait_for(sw, lambda s: screens.box_title(s, config) is not None, config.timeout, "盒子画面")


def _read_title(sw: Session) -> int:
    """读盒子编号，连续两次一样才算。读不出时每隔 title_retry 秒往下按一格，让开挡住盒子名的格子名字。"""
    config = _config(sw)

    # 光标停在盒子第 1 行时，格子上方弹出的名字会挡住盒子名，往下按一格让开
    def unblock_title() -> None:
        cursor = screens.box_cursor(capture(sw, "盒子名被挡住了吗"), config)
        if cursor is not None and len(cursor) == 3 and cursor[1] == 0:
            sw.click("DDOWN", 0)

    previous: int | None = None
    for _ in range(config.box_title_tries):
        image = act_until(
            sw,
            unblock_title,
            lambda s: screens.box_title(s, config) is not None,
            "盒子画面",
            interval=config.title_retry,
            timeout=config.timeout,
        )
        title = screens.box_title(image, config)
        if title is not None and title == previous:
            return title
        previous = title
        time.sleep(config.box_frame_gap)
    raise RuntimeError("盒子编号一直读不稳")


def select_box(sw: Session, number: int) -> None:
    """用 R、L 把盒子转到第 number 个。

    先连续读两次一样的盒子编号，算出往近的方向按几下，按完再读两次确认，不对就重算，最多 box_rounds 轮。
    """
    config = _config(sw)
    for _ in range(config.box_rounds):
        current = _read_title(sw)
        if current == number:
            time.sleep(config.box_settle_wait)
            return
        forward = (number - current) % config.box_count
        backward = config.box_count - forward
        button, count = ("R", forward) if forward <= backward else ("L", backward)
        for _ in range(count):
            sw.click(button, config.box_turn_wait)
        time.sleep(config.box_settle_wait)
    raise RuntimeError(f"转了 {config.box_rounds} 轮，还是没转到盒子 {number}")


def stable_egg_cells(sw: Session) -> list[tuple[int, int]]:
    """盒子里蛋的位置，连续两帧一样才用（换盒子的动画期间画面在变）。"""
    config = _config(sw)
    previous = screens.egg_cells(capture(sw, "盒子里的蛋"), config)
    for _ in range(config.read_tries):
        time.sleep(config.box_frame_gap)
        cells = screens.egg_cells(capture(sw, "盒子里的蛋"), config)
        if cells == previous:
            return cells
        previous = cells
    return previous


def describe_cursor(cursor: Cursor | None) -> str:
    """光标位置写给人看，行、列、格子都从 1 数。"""
    if cursor is None:
        return "格子外面"
    if len(cursor) == 2:
        return f"队伍第 {cursor[1] + 1} 格"
    return f"盒子第 {cursor[1] + 1} 行第 {cursor[2] + 1} 列"


def _next_button(current: Cursor, target: Cursor) -> str:
    """往目标靠近要按的方向键：先换列（队伍和盒子之间、盒子里左右），再上下。"""
    if len(current) == 2:
        if len(target) == 3:
            # 队伍第 6 格往右是盒子下面的「搜寻」按钮，不是盒子，要先往上一格（真机上出过）
            return "DUP" if current[1] >= 5 else "DRIGHT"
        return "DDOWN" if target[1] > current[1] else "DUP"
    if len(target) == 2:
        return "DLEFT"
    if target[2] != current[2]:
        return "DRIGHT" if target[2] > current[2] else "DLEFT"
    return "DDOWN" if target[1] > current[1] else "DUP"


def _wait_cursor_change(sw: Session, current: Cursor) -> Cursor | None:
    """等光标变化，最多 cursor_wait 秒；没变返回原来的。

    光标跑到格子外面（盒子下面的「一览」「搜寻」按钮）时认不出格子，返回 None。
    """
    config = _config(sw)
    deadline = time.monotonic() + config.cursor_wait
    cursor: Cursor | None = current
    while True:
        cursor = screens.box_cursor(capture(sw, "盒子的光标"), config)
        if cursor is not None and cursor != current:
            return cursor
        if time.monotonic() >= deadline:
            return cursor
        time.sleep(config.interval)


def move_cursor(sw: Session, target: Cursor) -> None:
    """盒子画面里把光标移到队伍或盒子的某一格，最多按 cursor_max_presses 下。"""
    config = _config(sw)
    # 光标可能停在格子外面的「一览」「搜寻」按钮上，认不出格子时按 DUP 回来
    image = act_until(
        sw,
        lambda: sw.click("DUP", 0),
        lambda s: screens.box_cursor(s, config) is not None,
        "盒子的光标",
        interval=config.title_retry,
        timeout=config.timeout,
    )
    cursor = screens.box_cursor(image, config)
    assert cursor is not None
    current: Cursor | None = cursor
    for _ in range(config.cursor_max_presses):
        if current == target:
            time.sleep(config.cursor_settle_wait)
            return
        if current is None:
            # 在格子外面的按钮上，往上回到格子里
            sw.click("DUP", 0)
            current = _wait_cursor_change(sw, cursor)
            continue
        cursor = current
        sw.click(_next_button(cursor, target), 0)
        current = _wait_cursor_change(sw, cursor)
    cursor = current
    if cursor == target:
        time.sleep(config.cursor_settle_wait)
        return
    raise RuntimeError(
        f"光标按了 {config.cursor_max_presses} 下，还是没到{describe_cursor(target)}，"
        f"现在在{describe_cursor(cursor)}"
    )


def read_name(sw: Session) -> str:
    """读面板上的名字，连续两帧一样才算，最多读 read_tries 次。"""
    config = _config(sw)
    previous = screens.panel_name(capture(sw, "面板的名字"), config)
    for _ in range(config.read_tries):
        time.sleep(config.read_gap)
        name = screens.panel_name(capture(sw, "面板的名字"), config)
        if name == previous:
            return name
        previous = name
    return previous


def read_shiny(sw: Session) -> bool:
    """面板上有没有闪光星星：连续两帧里任何一帧有就算。"""
    config = _config(sw)
    first = screens.panel_shiny(capture(sw, "闪光星星"), config)
    time.sleep(config.read_gap)
    second = screens.panel_shiny(capture(sw, "闪光星星"), config)
    return first or second


def ensure_judge(sw: Session) -> ImageChecker:
    """面板要在能力判定页（六项能力是「最棒」「一般般」这些词）；不是就按 PLUS 切换。返回判定页的截图。"""
    config = _config(sw)
    for _ in range(config.judge_tries):
        image = capture(sw, "能力判定页")
        if screens.judge_count(image, config) >= config.judge_min:
            return image
        sw.click("PLUS", config.judge_wait)
    raise RuntimeError(f"按了 {config.judge_tries} 次 PLUS，面板还是不在能力判定页")


def pick_up(sw: Session) -> None:
    """按 Y 拿起光标上的宝可梦，直到画面显示拿着；没反应就隔 pick_interval 秒重按。"""
    config = _config(sw)
    act_until(
        sw,
        lambda: sw.click("Y", 0),
        lambda s: screens.is_holding(s, config),
        "拿起宝可梦",
        interval=config.pick_interval,
        timeout=config.pick_timeout,
    )


def put_down(sw: Session) -> None:
    """按 A 把手里的宝可梦放下（格子里有的话就交换），直到画面显示没拿着。"""
    config = _config(sw)
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_holding(s, config),
        "放下宝可梦",
        interval=config.pick_interval,
        timeout=config.pick_timeout,
    )
    time.sleep(config.swap_wait)


def release_current(sw: Session) -> None:
    """放生光标所在的这一格，放生后确认这一格的名字变了。"""
    config = _config(sw)
    before = read_name(sw)
    # 按 A 出操作菜单（底下有「要拿……怎么办？」的对话框），没出来就再按
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_dialog(s, config),
        "盒子的操作菜单",
        interval=config.operation_interval,
        timeout=config.timeout,
    )
    # 按 DDOWN 移到「放生」，每按一下读一次选中的是哪项；按键偶尔会被吞（真机上停在过「标记」），所以不按固定次数
    selected = ""
    for _ in range(config.release_downs * 2):
        selected = screens.operation_selected(capture(sw, "操作菜单选中的一项"), config)
        if config.release_text in selected:
            break
        sw.click("DDOWN", config.release_down_wait)
    else:
        raise RuntimeError(f"操作菜单选中的是「{selected}」，移不到「{config.release_text}」")
    sw.click("A", config.box_click_wait)
    wait_for(sw, lambda s: screens.is_prompt(s, config), config.timeout, "放生确认")
    sw.click("DUP", config.release_down_wait)
    sw.click("A", config.box_click_wait)
    wait_for(sw, lambda s: screens.is_dialog(s, config), config.timeout, "放生后的对话")
    # 「已将……放生了。再见……」有两句，字还在一个个出来时按 A 只会把字显示完，所以一直按到对话框消失
    # 「已将……放生了」的对话出现过就是放生成功了。放生后面板会晚一点刷新，不再拿名字比较（真机上读到过旧的名字）。
    # 放生的是队伍最后一只时，光标停在变空的那一格上，这一格不会变黄，认不出光标，所以只等对话框消失
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: not screens.is_dialog(s, config),
        "放生后的盒子",
        interval=config.dialog_retry,
        timeout=config.timeout,
    )
    logging.info(f"放生了{before}")
