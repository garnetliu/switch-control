"""check：看孵出来的，闪光推送并存档停下，个体好的换亲代，其余放生。"""

import logging
import time

from control_switch.flow import capture, wait_for

from .. import screens
from ..box import (
    describe_cursor,
    ensure_judge,
    exit_to_overworld,
    move_cursor,
    open_box,
    open_menu,
    pick_up,
    put_down,
    read_name,
    read_shiny,
    release_current,
    select_box,
)
from ..session import EggSession
from .party import EGG_SLOTS, STORE_PARENT, slot_name


def _save_game(sw: EggSession) -> bool:
    """存档：开菜单，按 R 等确认框，按 A 等「记录」的对话，再退回野外。没存上返回 False。"""
    config = sw.config
    try:
        open_menu(sw)
        sw.click("R", config.save_click_wait)
        wait_for(sw, lambda s: screens.is_prompt(s, config), config.save_prompt_timeout, "存档确认")
        sw.click("A", config.save_click_wait)
        wait_for(sw, lambda s: screens.is_dialog(s, config), config.save_dialog_timeout, "存档对话")
        exit_to_overworld(sw)
    except (TimeoutError, RuntimeError) as error:
        logging.warning(f"存档失败：{error}")
        return False
    return True


def _announce_shiny(sw: EggSession, name: str, slot: int) -> str:
    """闪光：截图、推送、退出盒子存档。存档失败再推送一次，提醒手动存档。"""
    logging.info(f"队伍第 {slot + 1} 格是闪光{name}")
    sw.config.shiny_dir.mkdir(parents=True, exist_ok=True)
    path = sw.config.shiny_dir / f"shiny-{time.strftime('%Y%m%d-%H%M%S')}-sv-egg.jpg"
    capture(sw, "闪光").save(str(path))
    sw.notifier.send_everyone(f"孵蛋刷到闪光{name}，在队伍第 {slot + 1} 格", [path])
    exit_to_overworld(sw)
    if not _save_game(sw):
        sw.notifier.send_everyone("没存上档，请手动存档")
    return "done"


def _release(sw: EggSession) -> bool:
    """放生光标所在的这一格。放生前再看一次闪光，是闪光就不放生，返回 True。"""
    if read_shiny(sw):
        return True
    release_current(sw)
    return False


def _swap_parent_in(sw: EggSession, slot: int, best: int) -> None:
    """队伍 slot 这一格比亲代好：和 flame_box 的亲代交换，确认两边都对了才继续。"""
    config = sw.config
    old_best = sw.parent_best
    pick_up(sw)
    select_box(sw, config.flame_box)
    move_cursor(sw, STORE_PARENT)
    put_down(sw)
    move_cursor(sw, STORE_PARENT)
    stored = screens.panel_best_count(ensure_judge(sw), config)
    if stored != best:
        raise RuntimeError(f"换亲代之后盒子里的亲代有 {stored} 项最棒，应该是 {best} 项")
    move_cursor(sw, ("party", slot))
    name = read_name(sw)
    image = ensure_judge(sw)
    old = screens.panel_best_count(image, config)
    if config.parent_name not in name or old != old_best or screens.is_holding(image, config):
        raise RuntimeError(
            f"换亲代之后{describe_cursor(('party', slot))}是「{name}」，{old} 项最棒，应该是原来的亲代（{old_best} 项）"
        )


def check(sw: EggSession) -> str:
    """从队伍第 6 格往上看孵出来的（到第 2 格）：闪光停下，比亲代好换亲代，其余放生。"""
    sw.frames.clear()
    config = sw.config
    open_box(sw)
    for slot in reversed(EGG_SLOTS):
        name = slot_name(sw, ("party", slot))
        if not name or screens.is_egg_name(name):
            # 空格，或者还没孵的蛋（上次绕圈多算了一次孵化时会留下），跳过
            continue
        # 亲代已经 6 项最棒时不可能更好，不用再读能力，只看闪光
        maxed = sw.parent_best >= config.best_max
        image = None if maxed else ensure_judge(sw)
        if read_shiny(sw):
            return _announce_shiny(sw, name, slot)
        if config.parent_name not in name:
            # 盒子里以前留下的别的宝可梦的蛋孵出来的：不是闪光就放生
            logging.info(f"队伍第 {slot + 1} 格是{name}，不是{config.parent_name}，放生")
            if _release(sw):
                return _announce_shiny(sw, name, slot)
            continue
        best = 0 if image is None else screens.panel_best_count(image, config)
        if best > sw.parent_best:
            # 亲代在 flame_box 第 1 行第 2 列：和它交换，原来的亲代到了这一格，确认之后放生
            _swap_parent_in(sw, slot, best)
            if _release(sw):
                return _announce_shiny(sw, name, slot)
            sw.parent_best = best
            logging.info(f"亲代换成 {best} 项最棒的")
        elif _release(sw):
            return _announce_shiny(sw, name, slot)
    exit_to_overworld(sw)
    return "hatch_load"
