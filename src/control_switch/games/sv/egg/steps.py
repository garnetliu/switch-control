"""孵蛋刷闪的步骤。

人站在野外空地，队伍第 3 格是亲代，第 4–6 格空着。循环：开野餐、做三明治、去篮子收蛋，
收够了把蛋三个一组放进队伍，骑着坐骑绕圈孵化，看孵出来的：闪光就推送并停下，
个体比亲代好的换掉亲代，其余放生。
"""

import logging
import time
from typing import cast

from control_switch.flow import act_until, capture, wait_for
from control_switch.log import new_log
from control_switch.session import Session
from control_switch.vision import ImageChecker

from . import screens
from .box import (
    describe_cursor,
    ensure_judge,
    exit_to_overworld,
    leave_picnic,
    menu_to_row,
    move_cursor,
    open_box,
    open_menu,
    pick_up,
    put_down,
    read_name,
    read_shiny,
    release_current,
    select_box,
    set_riding,
    stable_egg_cells,
)
from .config import EggConfig
from .fly import fly_to_gate
from .screens import Cursor
from .session import EggSession

# 摇杆推满时每个方向的 (x, y)，y 正数向上
_STICK = 0x7FFF
_DIRECTIONS = {"U": (0, _STICK), "D": (0, -_STICK), "L": (-_STICK, 0), "R": (_STICK, 0)}
# 队伍的两种组法（照 PokemonAutomation EggAutonomous 的文档）：
# 野餐收蛋时只有能配对的两只：第 1 格百变怪，第 2 格亲代；
# 孵蛋时第 1 格火焰之躯，第 2–6 格放蛋。不在队伍里的放在 flame_box 第 1 行：
# 野餐时火焰之躯在第 1 列；孵蛋时百变怪在第 1 列、亲代在第 2 列
_EGG_SLOTS = (1, 2, 3, 4, 5)
_PARENT_SLOT = 1
_LEAD_SLOT = 0
_STORE_LEAD: Cursor = ("box", 0, 0)
_STORE_PARENT: Cursor = ("box", 0, 1)


def _push(sw: Session, side: str, direction: str, seconds: float) -> None:
    x, y = _DIRECTIONS[direction]
    sw.stick(side, x, y, seconds)


def _slot_name(sw: EggSession, cursor: Cursor) -> str:
    move_cursor(sw, cursor)
    return read_name(sw)


def _party_state(sw: EggSession) -> str:
    """看队伍第 1、2 格和 flame_box 第 1 行第 1、2 列四个位置的名字，认出现在是哪种组法。盒子要已经打开。

    picnic：（百变怪，亲代，火焰之躯，空）；hatch：（火焰之躯，蛋或空，百变怪，亲代）；
    to_hatch_mid：换到一半（火焰之躯，亲代，百变怪，空），还差把亲代放进盒子；
    to_picnic_mid：换到一半（百变怪，蛋或空，火焰之躯，亲代），还差把亲代放回队伍。
    认不出抛 RuntimeError。读完光标停在 flame_box。
    """
    config = sw.config
    lead = _slot_name(sw, ("party", _LEAD_SLOT))
    second = _slot_name(sw, ("party", _PARENT_SLOT))
    select_box(sw, config.flame_box)
    stored_lead = _slot_name(sw, _STORE_LEAD)
    stored_parent = _slot_name(sw, _STORE_PARENT)
    flame, ditto, parent = config.flame_name, config.ditto_name, config.parent_name
    if ditto in lead and parent in second and flame in stored_lead and not stored_parent:
        return "picnic"
    if flame in lead and ditto in stored_lead and parent in stored_parent:
        return "hatch"
    if flame in lead and parent in second and ditto in stored_lead and not stored_parent:
        return "to_hatch_mid"
    if ditto in lead and flame in stored_lead and parent in stored_parent:
        return "to_picnic_mid"
    raise RuntimeError(
        "队伍认不出是哪种组法："
        f"队伍第 1 格「{lead}」，队伍第 2 格「{second}」，"
        f"盒子 {config.flame_box} 第 1 行第 1 列「{stored_lead}」，第 2 列「{stored_parent}」"
    )


def _swap(sw: EggSession, first: Cursor, second: Cursor) -> None:
    """first 和 second 交换：从有宝可梦的那一格拿起，放到另一格。

    在空格上按 Y 也会进入替换模式（画面变紫），看起来像拿着东西，其实什么都没拿（真机上出过），
    所以先确认拿起的那一格不是空的。两格都空抛 RuntimeError。
    """
    move_cursor(sw, first)
    if not read_name(sw):
        first, second = second, first
        move_cursor(sw, first)
        if not read_name(sw):
            raise RuntimeError(
                f"{describe_cursor(first)}和{describe_cursor(second)}都是空的，没东西可换"
            )
    pick_up(sw)
    move_cursor(sw, second)
    put_down(sw)


def _swap_lead(sw: EggSession) -> None:
    """队伍第 1 格和 flame_box 第 1 行第 1 列交换。"""
    select_box(sw, sw.config.flame_box)
    _swap(sw, _STORE_LEAD, ("party", _LEAD_SLOT))


def _swap_parent(sw: EggSession) -> None:
    """队伍第 2 格和 flame_box 第 1 行第 2 列交换。"""
    select_box(sw, sw.config.flame_box)
    _swap(sw, _STORE_PARENT, ("party", _PARENT_SLOT))


def _to_picnic_party(sw: EggSession) -> None:
    """换成野餐的队伍：火焰之躯和盒子里的百变怪交换，亲代放回队伍第 2 格。

    盒子要已经打开，队伍第 2–6 格要已经空了（孵出来的都看完了）。按实际位置补完剩下的搬动。
    最后盒子停在 egg_boxes[0]，篮子里的蛋从这个盒子开始放。
    """
    config = sw.config
    state = _party_state(sw)
    if state == "hatch":
        _swap_lead(sw)
        _swap_parent(sw)
    elif state == "to_picnic_mid":
        _swap_parent(sw)
    elif state == "to_hatch_mid":
        _swap_lead(sw)
    if state != "picnic":
        if _party_state(sw) != "picnic":
            raise RuntimeError("换完之后队伍第 2 格不是亲代")
        logging.info("换成野餐的队伍：百变怪和亲代")
    select_box(sw, config.egg_boxes[0])


def _to_hatch_party(sw: EggSession) -> None:
    """换成孵蛋的队伍：盒子里的火焰之躯和百变怪交换，亲代放进盒子。盒子要已经打开。"""
    state = _party_state(sw)
    if state == "hatch":
        return
    if state == "to_picnic_mid":
        _swap_parent(sw)
        state = "picnic"
    if state == "picnic":
        _swap_lead(sw)
    _swap_parent(sw)
    if _party_state(sw) != "hatch":
        raise RuntimeError("换完之后亲代没有放进盒子")
    logging.info("换成孵蛋的队伍：火焰之躯")


def _read_parent(sw: EggSession, state: str) -> None:
    """读亲代有几项最棒：野餐的队伍在队伍第 2 格，孵蛋的队伍在 flame_box 第 1 行第 2 列。"""
    config = sw.config
    where: Cursor = _STORE_PARENT if state in ("hatch", "to_picnic_mid") else ("party", 1)
    move_cursor(sw, where)
    name = read_name(sw)
    if config.parent_name not in name:
        raise RuntimeError(
            f"{describe_cursor(where)}是「{name}」，不是亲代「{config.parent_name}」"
        )
    image = ensure_judge(sw)
    sw.parent_best = screens.panel_best_count(image, config)
    logging.info(f"亲代{name}，{sw.parent_best} 项最棒")


def initialize(sw: EggSession) -> str:
    """读亲代，看队伍里有没有蛋。"""
    sw.frames.clear()
    new_log(sw, "start")
    # 开始时可能停在菜单或盒子里，先退回野外
    exit_to_overworld(sw)
    open_box(sw)
    state = _party_state(sw)
    _read_parent(sw, state)
    if state != "hatch":
        # 野餐的队伍里没有蛋，直接去找盒子里的蛋（hatch_load 会补完换到一半的队伍）
        exit_to_overworld(sw)
        return "hatch_load"
    eggs = 0
    hatched = 0
    for slot in _EGG_SLOTS:
        move_cursor(sw, ("party", slot))
        name = read_name(sw)
        if screens.is_egg_name(name):
            eggs += 1
        elif name:
            hatched += 1
    exit_to_overworld(sw)
    if hatched:
        # 上次孵出来还没看过的，先去看
        logging.info(f"队伍第 2–6 格有 {hatched} 只孵出来的，先去看")
        return "check"
    if eggs:
        sw.eggs_in_box = 0
        sw.eggs_in_party = eggs
        return "hatch_walk"
    # 盒子里可能还有上次没孵的蛋，先去找；一个都没有时 hatch_load 会去开野餐
    return "hatch_load"


def picnic(sw: EggSession) -> str:
    """没骑坐骑，转镜头，开野餐。"""
    sw.frames.clear()
    config = sw.config
    open_box(sw)
    _to_picnic_party(sw)
    exit_to_overworld(sw)
    # 照 PokemonAutomation picnic_at_zero_gate：飞到零区闸口，背对观测站往外走一段再开野餐
    fly_to_gate(sw)
    set_riding(sw, False)
    _leave_gate(sw, config.picnic_walk)
    open_menu(sw)
    menu_to_row(sw, 2)
    wait_for(sw, lambda s: screens.is_picnic(s, config), config.picnic_timeout, "野餐画面")
    # 刚开野餐时人在丢精灵球，这段动画里不能动
    time.sleep(config.picnic_settle_wait)
    sw.picnics += 1
    logging.info(f"开了第 {sw.picnics} 次野餐")
    return "sandwich"


def _is_making(image: ImageChecker, config: EggConfig) -> bool:
    """已经在做三明治：底下有「长按以抓起」的提示。"""
    return image.has_text(config.making_hint, config.making_hint_text)


def _reach_table(sw: Session) -> None:
    """走到桌子前按 A，等对话框；前面有宝可梦挡着就吹口哨再试。"""
    config = cast(EggConfig, sw.config)
    for attempt in range(config.table_attempts):
        if attempt:
            sw.click("R", config.whistle_wait)
        _push(sw, "LEFT", "U", config.walk_to_table)
        sw.click("A", config.press_wait)
        try:
            wait_for(sw, lambda s: screens.is_dialog(s, config), config.dialog_wait, "桌子的对话")
            return
        except TimeoutError:
            continue
    raise RuntimeError("走到桌子前按 A，一直没有对话框，可能前面有宝可梦挡着")


def _fill(sw: Session) -> None:
    """放 3 片香蕉。"""
    config = cast(EggConfig, sw.config)
    for action, seconds in config.filling_moves:
        if action in _DIRECTIONS:
            _push(sw, "LEFT", action, seconds)
        elif action == "A+":
            sw.press("A")
            time.sleep(seconds)
        elif action == "A-":
            sw.release("A")
            time.sleep(seconds)
        elif action.startswith("A+") and action[2:] in _DIRECTIONS:
            _push(sw, "LEFT", action[2:], seconds)
        else:
            raise ValueError(f"不认识的动作：{action}")


def sandwich(sw: EggSession) -> str:
    """做超级花生酱三明治。"""
    sw.frames.clear()
    config = sw.config
    _reach_table(sw)
    # 桌子的菜单第一项是「做料理」，按 A 直到出食谱画面
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: s.has_text(config.recipe_title, "食谱"),
        "食谱画面",
        interval=config.table_interval,
        timeout=config.table_timeout,
    )
    time.sleep(config.recipe_wait)
    for _ in range(config.recipe_downs):
        sw.click("DDOWN", config.recipe_down_wait)
    if not capture(sw, "食谱 17").has_text(config.recipe_name, config.recipe_name_text):
        raise RuntimeError(f"食谱 17 不是{config.recipe_name_text}，可能没解锁或者材料不够")
    # 进选签子的界面，再按 A 开始做，每一步都认画面
    # 选签子的界面有时一闪而过（按 A 太快会直接开始做），所以等「选签子」或者「已经在做」任一个
    image = act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda s: screens.is_pick_screen(s, config) or _is_making(s, config),
        "选签子的界面",
        interval=config.pick_press_interval,
    )
    if not _is_making(image, config):
        act_until(
            sw,
            lambda: sw.click("A", 0),
            lambda s: _is_making(s, config),
            "开始做三明治",
            interval=config.make_press_interval,
        )
    time.sleep(config.start_wait)
    try:
        _fill(sw)
    except BaseException:
        sw.release("A")
        sw.release_stick("LEFT")
        raise
    _push(sw, "LEFT", "L", config.bread_left)
    sw.click("A", config.bread_wait)
    sw.click("A", config.skewer_wait)
    deadline = time.monotonic() + config.eat_timeout
    while not screens.is_picnic(capture(sw, "吃三明治"), config):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.eat_timeout} 秒，三明治还没吃完")
        sw.click("A", config.eat_wait)
    sw.sandwich_at = time.monotonic()
    logging.info("三明治做好了")
    return "to_basket"


def to_basket(sw: EggSession) -> str:
    """收回坐骑，走到篮子前。"""
    sw.frames.clear()
    config = sw.config
    sw.click("PLUS", config.unride_wait)
    for action, seconds in config.basket_route:
        if action == "btn:L":
            sw.click("L", seconds)
        else:
            _push(sw, "LEFT", action, seconds)
            time.sleep(config.basket_step_wait)
    sw.eggs_in_box = 0
    return "collect"


def _open_basket(sw: Session) -> None:
    """按 A 查篮子，等对话框；没有就吹口哨再试，试几次后转镜头。"""
    config = cast(EggConfig, sw.config)
    for attempt in range(config.collect_attempts):
        if attempt:
            sw.click("R", config.whistle_wait)
            if attempt % config.camera_turn_every == 0:
                sw.stick("RIGHT", -_STICK, 0, config.camera_turn_hold)
        sw.click("A", config.collect_wait)
        try:
            wait_for(sw, lambda s: screens.is_dialog(s, config), config.dialog_wait, "篮子的对话")
            return
        except TimeoutError:
            continue
    raise RuntimeError(f"按了 {config.collect_attempts} 次 A，一直没有对话框，可能没走到篮子前")


def _wait_with_keepalive(sw: Session, seconds: float) -> None:
    """等 seconds 秒，期间隔一会儿按一下键，不让 Switch 休眠。"""
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        sw.click(config.keepalive_button, 0)
        time.sleep(min(config.keepalive_gap, max(deadline - time.monotonic(), 0)))


def _quiet(sw: Session) -> bool:
    """篮子的对话结束了：连续 quiet_frames 帧都没有对话框，并且回到了野餐画面。"""
    config = cast(EggConfig, sw.config)
    for frame in range(config.quiet_frames):
        if frame:
            time.sleep(config.quiet_gap)
        image = capture(sw, "篮子的对话结束了吗")
        if screens.is_dialog(image, config) or not screens.is_picnic(image, config):
            return False
    return True


def collect(sw: EggSession) -> str:
    """查一次篮子，领蛋；收够了或者时间到了就收野餐。"""
    sw.frames.clear()
    config = sw.config
    before = sw.eggs_in_box
    _open_basket(sw)
    deadline = time.monotonic() + config.collect_timeout
    # 拒绝领蛋之后会再出一个是/否，要选「是」
    refusing = False
    while not _quiet(sw):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"查篮子等了 {config.collect_timeout} 秒还没结束")
        image = capture(sw, "篮子")
        if screens.is_prompt(image, config):
            if refusing:
                sw.click("A", config.collect_wait)
                refusing = False
            elif sw.eggs_in_box < config.max_eggs:
                sw.click("A", config.collect_wait)
                sw.eggs_in_box += 1
            else:
                sw.click("B", config.collect_wait)
                refusing = True
        elif screens.is_dialog(image, config):
            # 普通对话按 B 推进，免得把没认出的是/否按成「是」
            sw.click("B", config.collect_wait)
    logging.info(f"这次收了 {sw.eggs_in_box - before} 个蛋，一共 {sw.eggs_in_box} 个")
    started = time.monotonic() if sw.sandwich_at is None else sw.sandwich_at
    minutes = (time.monotonic() - started) / 60
    if sw.eggs_in_box < config.max_eggs and minutes < config.picnic_minutes:
        _wait_with_keepalive(sw, config.basket_interval)
        return "collect"
    leave_picnic(sw)
    return "hatch_load"


def hatch_load(sw: EggSession) -> str:
    """按 egg_boxes 的顺序，在盒子画面里找蛋，放进队伍第 2–6 格里的空格。"""
    sw.frames.clear()
    config = sw.config
    open_box(sw)
    _to_hatch_party(sw)
    # 队伍第 2–6 格里可能还留着蛋（上次没孵完），只往空格里放
    waiting = 0
    free: list[int] = []
    for slot in _EGG_SLOTS:
        name = _slot_name(sw, ("party", slot))
        if screens.is_egg_name(name):
            waiting += 1
        elif not name:
            free.append(slot)
        else:
            raise RuntimeError(f"拿蛋前队伍第 {slot + 1} 格是「{name}」，应该是空的或者蛋")
    free = free[: config.eggs_per_load]
    taken = 0
    for number in config.egg_boxes:
        if taken >= len(free):
            break
        select_box(sw, number)
        for row, col in stable_egg_cells(sw):
            if taken >= len(free):
                break
            name = _slot_name(sw, ("box", row, col))
            if not screens.is_egg_name(name):
                raise RuntimeError(
                    f"盒子 {number} 第 {row + 1} 行第 {col + 1} 列不是蛋，读到「{name}」"
                )
            slot = free[taken]
            _swap(sw, ("box", row, col), ("party", slot))
            name = read_name(sw)
            if not screens.is_egg_name(name):
                raise RuntimeError(f"蛋放进队伍第 {slot + 1} 格之后，那一格是「{name}」")
            taken += 1
    if not taken + waiting:
        select_box(sw, config.egg_boxes[0])
        exit_to_overworld(sw)
        return "picnic"
    sw.eggs_in_party = taken + waiting
    exit_to_overworld(sw)
    return "hatch_walk"


def _start_circle(sw: Session) -> None:
    sw.press("LSTICK")
    sw.press_stick("LEFT", 0, _STICK)
    sw.press_stick("RIGHT", _STICK, 0)


def _stop_circle(sw: Session) -> None:
    sw.release_stick("LEFT")
    sw.release_stick("RIGHT")
    sw.release("LSTICK")


def _escaped(sw: Session) -> bool:
    """按完「逃走」之后看结果：野外连续 flee_stable_frames 帧算逃掉了；中途有对话框按 B；
    又看到战斗菜单、或者等了 flee_timeout 秒还没结果算没逃掉。
    """
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + config.flee_timeout
    consecutive = 0
    while time.monotonic() < deadline:
        image = capture(sw, "逃走之后")
        if screens.is_overworld(image, config) and not screens.is_dialog(image, config):
            consecutive += 1
            if consecutive >= config.flee_stable_frames:
                return True
        elif screens.is_dialog(image, config):
            consecutive = 0
            sw.click("B", 0)
        elif screens.is_battle(image, config):
            return False
        else:
            consecutive = 0
        time.sleep(config.flee_gap)
    return False


def _flee(sw: Session) -> None:
    """战斗菜单里把光标移到「逃走」（第 4 行）按 A，没逃掉就重来。"""
    config = cast(EggConfig, sw.config)
    for _ in range(config.flee_attempts):
        # 误进了包包、宝可梦这些子菜单时按 B 退回战斗菜单
        image = act_until(
            sw,
            lambda: sw.click("B", 0),
            lambda s: screens.battle_row(s, config) != -1,
            "战斗菜单",
            interval=config.flee_move_interval * 3,
            timeout=config.wait.timeout,
        )
        row = screens.battle_row(image, config)
        while row != config.flee_row:
            button = "DDOWN" if row < config.flee_row else "DUP"
            image = act_until(
                sw,
                lambda button=button: sw.click(button, 0),
                lambda s, before=row: screens.battle_row(s, config) not in (before, -1),
                "战斗菜单的光标移一格",
                interval=config.flee_move_interval,
            )
            row = screens.battle_row(image, config)
        sw.click("A", 0)
        if _escaped(sw):
            return
    raise RuntimeError(f"逃了 {config.flee_attempts} 次，还是在战斗")


def _stable_overworld(sw: Session, first: ImageChecker) -> bool:
    """野外要连续 stable_frames 帧（每帧间隔 stable_gap 秒），期间没有对话框，才算孵完。"""
    config = cast(EggConfig, sw.config)
    image = first
    for frame in range(config.stable_frames):
        if frame:
            time.sleep(config.stable_gap)
            image = capture(sw, "孵化结束了吗")
        if not screens.is_overworld(image, config) or screens.is_dialog(image, config):
            return False
    return True


def _finish_hatch(sw: Session) -> None:
    """一直按 A 看完孵化；回到野外并且稳定了才算完。按 A 的时候遇到战斗就逃走。"""
    config = cast(EggConfig, sw.config)
    deadline = time.monotonic() + config.hatch_timeout
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {config.hatch_timeout} 秒，孵化一直没有结束")
        image = capture(sw, "孵化结束")
        if screens.is_battle(image, config):
            _flee(sw)
        elif screens.is_overworld(image, config) and not screens.is_dialog(image, config):
            if _stable_overworld(sw, image):
                return
        else:
            sw.click("A", config.hatch_press_wait)


def _leave_gate(sw: Session, walk: float) -> None:
    """在零区闸口的飞行点上：转镜头，往右前方走，让人背对观测站，再转镜头、往前走 walk 秒。"""
    config = cast(EggConfig, sw.config)
    sw.click("L", config.camera_wait)
    sw.stick(
        "LEFT", config.stick.max, round(config.stick.max * config.gate_turn_y), config.gate_turn
    )
    sw.click("L", config.camera_wait)
    _push(sw, "LEFT", "U", walk)


def _to_hatch_ground(sw: EggSession) -> None:
    """飞回零区闸口，骑上坐骑，下坡到空地上（PokemonAutomation hatch_eggs_at_zero_gate）。"""
    config = sw.config
    fly_to_gate(sw)
    set_riding(sw, True)
    _leave_gate(sw, config.ramp_walk)
    sw.click("L", config.ride_circle_wait)


def hatch_walk(sw: EggSession) -> str:
    """骑上坐骑原地绕圈，孵出队伍里所有的蛋。"""
    sw.frames.clear()
    config = sw.config
    _to_hatch_ground(sw)
    done = 0
    last_progress = time.monotonic()
    circling = False
    try:
        while done < sw.eggs_in_party:
            if not circling:
                _start_circle(sw)
                circling = True
            image = capture(sw, "绕圈")
            if screens.is_dialog(image, config):
                _stop_circle(sw)
                circling = False
                _finish_hatch(sw)
                done += 1
                sw.hatched += 1
                last_progress = time.monotonic()
                logging.info(f"孵出了第 {sw.hatched} 只")
            elif screens.is_battle(image, config):
                _stop_circle(sw)
                circling = False
                _flee(sw)
                # 逃走后照 PokemonAutomation 飞回零区闸口重新开始绕圈
                _to_hatch_ground(sw)
            elif time.monotonic() - last_progress >= config.circle_timeout:
                raise RuntimeError(f"绕圈超过 {config.circle_timeout} 秒，一个蛋也没孵出来")
            else:
                time.sleep(config.circle_interval)
    finally:
        _stop_circle(sw)
    return "check"


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
    move_cursor(sw, _STORE_PARENT)
    put_down(sw)
    move_cursor(sw, _STORE_PARENT)
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
    for slot in reversed(_EGG_SLOTS):
        name = _slot_name(sw, ("party", slot))
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
