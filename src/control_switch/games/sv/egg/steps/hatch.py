"""孵蛋：一列一批，下坡、绕圈孵、飞回闸口、开盒子逐只检查、装下一列；整盒孵完收尾。

照 PokemonAutomation 的 hatch_eggs_full_routine、hatch_eggs_at_zero_gate、do_egg_cycle_motion、
handle_egg_hatching、process_one_baby，加上 program 里一轮结束的部分。
"""

import logging
import time

from control_switch import flow
from control_switch.flow import capture, press_until, wait_until
from control_switch.games.sv import actions

from .. import box, fly, screens
from ..session import EggSession


def hatch(sw: EggSession) -> str:
    """孵完队伍里的蛋，一列一批，整盒孵完收尾，返回下一步 "fetch"；右边的盒子满了返回 "done"。

    整盒孵完：一只都没留下就重启游戏回档（孵出来的放回盒子，不放生）；留下过就放生整盒、
    换回野餐队伍、存档。留下东西（闪光、换下来的亲代）的那一批孵完之后要先存档才孵下一批。
    """
    sw.kept_in_box = False
    sw.save_pending = False
    count = sw.eggs_in_party
    # 下一个要装进队伍的蛋在盒子的第几列（从 0 数）。第 0 列在 fetch 里已经装好了，所以从 1 开始
    next_col = 1
    while True:
        if sw.save_pending:
            logging.info("留下了东西，先存档")
            actions.save_game(sw)
            sw.save_pending = False
        _hatch_eggs_at_zero_gate(sw, count)
        fly.fly_to_gate(sw)
        box.open_box(sw)
        for index in range(count):
            if not _process_baby(sw, index, count):
                logging.warning("右边的盒子满了，没地方放留下的了，结束")
                return "done"
        # 孵出来的放回刚装蛋的那一列，这一盒孵完要是一只都没留下，重启游戏就回档，不用放生
        box.unload_column(sw, next_col - 1)
        while next_col < sw.config.box_columns:
            box.move_cursor(sw, "slots", 0, next_col)
            if box.slot_has_pokemon(sw):
                break
            next_col += 1
        if next_col < sw.config.box_columns:
            logging.info(f"装第 {next_col} 列的蛋")
            box.load_column(sw, next_col)
            box.move_cursor(sw, "party", 0, 0)
            count = box.count_party_eggs(sw)
            actions.exit_to_overworld(sw)
            next_col += 1
            continue
        break

    if not sw.kept_in_box:
        logging.info("这一盒什么都没留下，重启游戏回档")
        flow.restart(sw)
        # restart 在黑屏时就返回了，看画面等游戏加载完回到野外，再等一会儿让人能动
        wait_until(
            sw,
            lambda s: screens.is_overworld(s, sw.config),
            sw.config.restart_timeout,
            "重启之后回到野外",
        )
        time.sleep(sw.config.restart_settle_wait)
        # 这一盒的截图用不着了，不清的话列表会一直变大
        sw.frames.clear()
        return "fetch"
    logging.info("这一盒留下过东西，放生整盒，换回野餐队伍，存档")
    box.release_box(sw)
    box.to_picnic_party(sw)
    actions.exit_to_overworld(sw)
    actions.save_game(sw)
    sw.frames.clear()
    return "fetch"


def _process_baby(sw: EggSession, index: int, count: int) -> bool:
    """在盒子里查队伍里第 index 只孵出来的（从下往上查），返回 False 表示右边的盒子满了。

    闪光：推送并存到右边盒子的第一个空格。和亲代同种、「最棒」项数比亲代多：和亲代交换。
    其余不留：什么都不做，孵出来的留在队伍里，等一会儿放回盒子。
    """
    row = count - index
    box.move_cursor(sw, "party", row, 0)
    mon = box.read_mon(sw)
    logging.info(f"第 {index + 1}/{count} 只：{mon}")
    if mon.shiny:
        logging.info("孵出闪光了！")
        _send_shiny(sw, mon)
        return _keep_shiny(sw, row)
    if (
        sw.judge_unlocked
        and mon.best is not None
        and mon.name == sw.parent_name
        and mon.best > sw.parent_best
    ):
        _replace_parent(sw, row, mon.best)
    return True


def _send_shiny(sw: EggSession, mon: box.Mon) -> None:
    """闪光：存一张截图，推送给所有人。"""
    directory = sw.config.shiny_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}-shiny-{mon.name}.jpg"
    capture(sw, "闪光").save(str(path))
    sw.notifier.send_everyone(f"孵出闪光{mon.name}了！", [path])


def _keep_shiny(sw: EggSession, row: int) -> bool:
    """把队伍第 row 行的闪光放到右边盒子的第一个空格，再回到放蛋的盒子。没有空格返回 False。"""
    box.turn_box(sw, "R")
    for slot_row in range(sw.config.box_rows):
        for col in range(sw.config.box_columns):
            box.move_cursor(sw, "slots", slot_row, col)
            if not box.slot_has_pokemon(sw):
                box.swap_slots(sw, ("party", row, 0), ("slots", slot_row, col))
                box.turn_box(sw, "L")
                sw.kept_in_box = True
                sw.save_pending = True
                return True
    return False


def _replace_parent(sw: EggSession, row: int, best: int) -> None:
    """孵出来的和亲代同种、「最棒」项数比亲代多：和左边盒子里的亲代交换，换下来的旧亲代按不留处理。

    亲代是野餐队伍第 0 只时放在左边盒子的第 0 行第 0 列，是第 i 只时放在第 1 列第 i - 1 行。
    """
    parent_row, parent_col = (0, 0) if sw.parent_index == 0 else (sw.parent_index - 1, 1)
    logging.info(f"比亲代好（{best} 项对 {sw.parent_best} 项），换亲代")
    box.turn_box(sw, "L")
    box.swap_slots(sw, ("party", row, 0), ("slots", parent_row, parent_col))
    box.turn_box(sw, "R")
    sw.parent_best = best
    sw.kept_in_box = True
    sw.save_pending = True


# ---- 下坡、绕圈、孵化 ----


def _hatch_eggs_at_zero_gate(sw: EggSession, count: int) -> None:
    """在零区闸口孵 count 个蛋：先骑上坐骑下坡到空地，再一个一个绕圈孵。"""
    config = sw.config
    got_off_ramp = False
    for index in range(count):
        logging.info(f"孵第 {index + 1}/{count} 个蛋")
        # 读档之后镜头会重置，每个蛋之前都把镜头转到人面对的方向
        sw.click("L", config.camera_wait)
        if not got_off_ramp:
            if index == 0 and _leave_ramp(sw):
                # 下坡的路上就孵了：处理完飞回闸口重新来
                _handle_egg_hatching(sw, index, count)
                fly.fly_to_gate(sw)
                continue
            got_off_ramp = True
        _do_egg_cycle_motion(sw)
        _handle_egg_hatching(sw, index, count)


def _leave_ramp(sw: EggSession) -> bool:
    """骑上坐骑，往右前方走让人背对观测站，转镜头，往前走下坡。

    每个动作之前看有没有出现孵化的对话，有就马上返回 True（下坡的路上就孵了）；做完返回 False。
    """
    config = sw.config
    for step in config.ramp_route:
        if screens.is_dialog(capture(sw, "下坡"), config):
            return True
        sw.follow([step])
    return False


def _do_egg_cycle_motion(sw: EggSession) -> None:
    """骑着坐骑转圈：左摇杆往前推满、右摇杆往右推满、按住左摇杆，直到出现孵化的对话。

    等了 cycle_timeout 秒还没孵出来抛 TimeoutError。不管怎样最后都把摇杆和按键松开。
    """
    config = sw.config
    full = sw.controller.STICK_MAX
    sw.press_stick("LEFT", 0, full)
    sw.press_stick("RIGHT", full, 0)
    sw.press("LSTICK")
    try:
        wait_until(
            sw,
            lambda s: screens.is_dialog(s, config),
            config.cycle_timeout,
            "孵化的对话",
            interval=config.cycle_interval,
        )
    finally:
        sw.release("LSTICK")
        sw.release_stick("RIGHT")
        sw.release_stick("LEFT")


def _handle_egg_hatching(sw: EggSession, index: int, count: int) -> None:
    """蛋孵出来了：把镜头往左转一下，一直按 A 过孵化的动画和对话，直到回到野外。"""
    config = sw.config
    logging.info(f"孵出了第 {index + 1}/{count} 个")
    sw.push("RIGHT", -1.0, 0.0, config.hatch_turn_seconds)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_overworld(s, config),
        config.hatch_end_timeout,
        "孵化结束回到野外",
        interval=sw.config.wait.press_interval,
    )
