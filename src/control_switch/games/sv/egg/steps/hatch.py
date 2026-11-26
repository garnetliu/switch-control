"""孵蛋：飞到零区闸口走到空地，换成孵蛋队伍，绕圈孵，队伍里的孵完就在盒子里换下一列蛋。

照 PokemonAutomation 的 hatch_eggs_at_zero_gate、do_egg_cycle_motion、handle_egg_hatching。
只在开始时飞一次闸口，之后一直在空地上孵。
"""

import logging

from control_switch.flow import capture, press_until, wait_until
from control_switch.games.sv import actions

from .. import box, fly, screens
from ..session import EggSession


def hatch(sw: EggSession) -> str:
    """飞到闸口走到空地，换成孵蛋队伍，绕圈孵完队伍里的蛋就换下一列，一直孵到盒子和队伍里都没有蛋，返回 "release"。"""
    config = sw.config
    fly.fly_to_gate(sw)
    sw.follow(config.ramp_route)
    box.open_box(sw)
    _to_hatch_party(sw)
    while True:
        has_eggs = _refill_party(sw)
        actions.exit_to_overworld(sw)
        if not has_eggs:
            logging.info("盒子和队伍里都没有蛋了，去放生")
            return "release"
        while sw.eggs_in_party > 0:
            logging.info(f"孵蛋，队伍里还有 {sw.eggs_in_party} 个")
            # 每个蛋之前都把镜头转到人面对的方向
            sw.click("L", config.camera_wait)
            _do_egg_cycle_motion(sw)
            _handle_egg_hatching(sw)
            sw.eggs_in_party -= 1
        box.open_box(sw)


# ---- 换队伍、换蛋 ----


def _to_hatch_party(sw: EggSession) -> None:
    """队伍还是野餐队伍（第 2 格是百变怪）时，换成孵蛋队伍：到放亲代和带队的盒子，带队的和队伍第一只交换，
    队伍里其余的卸到那个盒子第 1 列，再回到放蛋的盒子。已经是孵蛋队伍就什么都不做。"""
    box.move_cursor(sw, "party", 1, 0)
    if not (box.slot_has_pokemon(sw) and box.read_name(sw) == sw.config.ditto_name):
        return
    logging.info("换成孵蛋队伍")
    box.turn_box(sw, "L")
    box.swap_slots(sw, ("slots", 0, 0), ("party", 0, 0))
    box.unload_column(sw, 1)
    box.turn_box(sw, "R")


def _party_slots(sw: EggSession) -> list[str]:
    """队伍第 1 到 5 格各是什么："empty"、"egg"、"mon"。"""
    config = sw.config
    box.move_cursor(sw, "party", 0, 0)
    image = capture(sw, "队伍里的蛋")
    return [screens.party_slot(image, row, config) for row in range(1, config.party_rows)]


def _refill_party(sw: EggSession) -> bool:
    """在放蛋的盒子里：队伍里有蛋就不换；没有蛋就把孵出来的放进第一个空的列，再装第一个有蛋的列。

    队伍里的蛋数记在 sw.eggs_in_party。盒子和队伍里都没有蛋了返回 False。
    """
    slots = _party_slots(sw)
    if "egg" not in slots:
        if "mon" in slots:
            column = _first_column(sw, empty=True)
            if column is None:
                raise RuntimeError("放蛋的盒子里没有空的一列，孵出来的放不回去")
            box.unload_column(sw, column)
        column = _first_column(sw, empty=False)
        if column is None:
            return False
        box.load_column(sw, column)
        slots = _party_slots(sw)
    sw.eggs_in_party = slots.count("egg")
    return True


def _first_column(sw: EggSession, empty: bool) -> int | None:
    """放蛋的盒子里第一个第 0 行是空格（empty=True）或者是蛋（empty=False）的列；没有返回 None。"""
    for col in range(sw.config.box_columns):
        box.move_cursor(sw, "slots", 0, col)
        has_pokemon = box.slot_has_pokemon(sw)
        if empty and not has_pokemon:
            return col
        if not empty and has_pokemon and box.read_name(sw).startswith("蛋"):
            return col
    return None


# ---- 绕圈、孵化 ----


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


def _handle_egg_hatching(sw: EggSession) -> None:
    """蛋孵出来了：把镜头往左转一下，一直按 A 过孵化的动画和对话，直到回到野外。"""
    config = sw.config
    logging.info("孵出了一个")
    sw.push("RIGHT", -1.0, 0.0, config.hatch_turn_seconds)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_overworld(s, config),
        config.hatch_end_timeout,
        "孵化结束回到野外",
        interval=sw.config.wait.press_interval,
    )
