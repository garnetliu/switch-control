"""一场极巨大冒险对战。"""

import logging
import time
from dataclasses import replace

from libs import ImageChecker
from swsh.field import Field
from swsh.lair.switch import LairSwitch
from swsh.lair.war import War
from swsh.pokemon import Pokemon
from tools import act_until, capture, wait_for
from type import Rect


def battle(sw: LairSwitch) -> str:
    """打到出现要不要抓的界面返回 "catch"，命数扣到 0 或者认到战败返回 "select_pokemon"。"""
    war = _create_war(sw)

    while True:
        image = capture(sw, "战斗")
        state = _battle_state(sw, image)

        if state == "fight":
            _choose_move(sw, war)
        elif state == "cheer":
            war.faint()
            _cheer(sw)
        elif state == "field":
            war.update(image.read_text(sw.config.rects.black_full_line1))
        elif state == "storm":
            if _storm(sw, war):
                _record_faints(sw, war)
                return "select_pokemon"
        elif state == "catch":
            _record_faints(sw, war)
            return "catch"
        elif state == "loss":
            _loss(sw, war)
            return "select_pokemon"
        else:
            # 出招动画、战斗文字这些都不用处理，隔一会儿再看
            time.sleep(sw.config.interval)


def _create_war(sw: LairSwitch) -> War:
    """建这场对战的场上状态：自己、队友和对手。自己的 PP 用内存里读到的剩余值。"""
    own_pp = _read_team(sw)
    own_name, own_hp = sw.game.team[0]
    return War(
        own=replace(sw.data.pokemon_object(own_name), hp=own_hp, pp=own_pp),
        teammates=[replace(sw.data.pokemon_object(name), hp=hp) for name, hp in sw.game.team[1:]],
        opponent=_read_opponent(sw),
    )


def _read_team(sw: LairSwitch) -> list[int]:
    """重新读队伍内存，算出每只的血量比例。返回自己 4 个招式的剩余 PP。

    当前血量用内存里的值。内存记录里的最大血量不对，改用内存里的等级、个体值、努力值算；
    数据文件里的个体值是统一写的 15，和游戏里的不一样，不能直接用。
    """
    records = sw.pkhex.read_pk8(sw.config.addresses.party)
    team = []
    hps = []
    for record in records:
        name = sw.data.name_id(record["species"], record["form"])
        pokemon = replace(
            sw.data.pokemon_object(name),
            level=record["level"],
            ivs=tuple(record["ivs"]),
            evs=tuple(record["evs"]),
        )
        max_hp = pokemon.stats[0]
        team.append((name, record["hp"] / max_hp if max_hp else 1.0))
        hps.append(f"{pokemon.name(sw.config.language)} {record['hp']}/{max_hp}")
    sw.game.team = team
    logging.info(f"队伍血量: {'，'.join(hps)}")
    sw.game.save()
    own_pp = list(records[0]["pp"])
    logging.info(f"队伍: {sw.game.team}，自己的 PP: {own_pp}")
    return own_pp


def _read_opponent(sw: LairSwitch) -> Pokemon:
    """第 4 场是首领，直接用这一局的首领；其他场从对手内存记录识别。"""
    if sw.game.num_caught == 3:
        return replace(sw.data.pokemon_object(sw.game.boss))
    record = sw.pkhex.read_pk8([sw.config.addresses.opponent])[0]
    return replace(sw.data.pokemon_object(sw.data.name_id(record["species"], record["form"])))


def _choose_move(sw: LairSwitch, war: War) -> None:
    """算出这回合用哪个招式、要不要极巨化，然后出招。

    极巨招式经常重名，所以按序号移光标，不按名字找。
    """
    war.start_turn()
    image = act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: _move_cursor(sw, screen) >= 0,
        "招式列表",
    )
    best, score, dynamax = war.best_move(_dynamax_available(sw, image))
    if dynamax:
        image = _dynamax(sw)
        war.dynamax()
    own = war.own
    move = own.max_moves[best] if own.dynamax else own.moves[best]
    logging.info(f"用第 {best + 1} 个招式 {move.name()}，得分 {score:.2f}")

    _move_cursor_to(sw, image, best)
    _use_move(sw)
    war.use_move(best)


def _use_move(sw: LairSwitch) -> None:
    """光标已经在要用的招式上：按 A 出招，一直到战斗文字出现「×××使出了」。

    按 A 到招式列表消失。之后要是出了选目标的界面，先看光标所在的卡片能不能选：
    能选就一直按 A；不能选（比如花瓣舞，光标默认在对手上，但只能选自己）就把光标移到能选的卡片上再按 A。
    """

    # 选目标界面上我方卡片的名牌正好落在招式列表第一行的光标框里，会被当成招式光标，
    # 所以认到选目标的光标也算招式列表消失了
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: _target_cursor(sw, screen) >= 0 or _move_cursor(sw, screen) == -1,
        "招式列表消失",
    )
    wait_for(
        sw,
        lambda screen: _target_cursor(sw, screen) >= 0,
        sw.config.timeout,
        "选目标的界面或者出招",
    )
    _move_target_cursor(sw)
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: screen.has_text(sw.config.rects.black_full_line1, "使出了"),
        "出招",
    )


def _target_cursor(sw: LairSwitch, image: ImageChecker) -> int:
    """选目标界面的光标在哪张卡片上：0 是对手，1 到 4 是我方四张；不在选目标界面返回 -1。"""
    rects = (sw.config.rects.target_cursor, *sw.config.rects.ally_target_cursor_rects)
    marks = [_marker_shown(sw, image, rect) for rect in rects]
    return marks.index(True) if marks.count(True) == 1 else -1


def _target_selectable(sw: LairSwitch, image: ImageChecker, index: int) -> bool:
    """选目标界面第 index 张卡片能不能选：能选的是不透明的白底或黑底，不能选的是半透明的灰底。"""
    rect = (sw.config.rects.target_card, *sw.config.rects.ally_target_card_rects)[index]
    white = image.color_ratio(
        rect, sw.config.target_card_white_lower, sw.config.target_card_white_upper
    )
    dark = image.color_ratio(rect, sw.config.marker_dark_lower, sw.config.marker_dark_upper)
    return max(white, dark) > sw.config.target_card_ratio


def _target_blocked(sw: LairSwitch) -> bool:
    """光标停在一张不能选的卡片上返回 True。

    界面刚出来时卡片还在淡入，所以连着看 3 张：有一张能选，或者已经不在选目标界面了，就返回 False。
    """
    for _ in range(3):
        image = capture(sw, "选目标的光标能不能选")
        index = _target_cursor(sw, image)
        if index == -1 or _target_selectable(sw, image, index):
            return False
        time.sleep(sw.config.interval)
    return True


def _move_target_cursor(sw: LairSwitch) -> None:
    """光标所在的卡片不能选：先按下移到我方那一排，再一张一张往右，停在第一张能选的卡片上。"""
    for button in ("DDOWN", "DRIGHT", "DRIGHT", "DRIGHT"):
        if not _target_blocked(sw):
            logging.info("选目标的光标在能选的卡片上")
            return
        before = _target_cursor(sw, capture(sw, "选目标的光标"))
        act_until(
            sw,
            lambda: sw.click(button, 0),
            lambda screen: _target_cursor(sw, screen) not in (before, -1),
            "选目标的光标移动",
        )


def _dynamax(sw: LairSwitch) -> ImageChecker:
    """招式列表上把光标移到「极巨化」按钮上按 A，等列表换成极巨招式，返回换好后的画面。"""
    sw.stick("LEFT", -sw.config.stick_max, 0, sw.config.stick_tick)
    wait_for(
        sw,
        lambda screen: _marker_shown(sw, screen, sw.config.rects.dynamax_cursor),
        sw.config.timeout,
        "光标移到极巨化按钮上",
    )
    sw.click("A", 0)
    # 极巨化之后按钮消失，光标回到招式列表上
    image = wait_for(
        sw,
        lambda screen: not _dynamax_available(sw, screen) and _move_cursor(sw, screen) >= 0,
        sw.config.timeout,
        "换成极巨招式",
    )
    logging.info("极巨化")
    return image


def _dynamax_available(sw: LairSwitch, image: ImageChecker) -> bool:
    """招式列表左边有「极巨化」按钮：按钮上白色标志的占比超过阈值。"""
    return (
        image.color_ratio(
            sw.config.rects.dynamax_button,
            sw.config.dynamax_lower,
            sw.config.dynamax_upper,
        )
        > sw.config.dynamax_ratio
    )


def _move_cursor_to(sw: LairSwitch, image: ImageChecker, target: int) -> None:
    """把招式列表光标移到第 target 行。光标会记住上回合的位置，按到目标为止。"""
    for _ in range(len(sw.config.rects.move_cursor_rects)):
        current = _move_cursor(sw, image)
        if current == target:
            return
        image = act_until(
            sw,
            lambda: sw.stick("LEFT", 0, -sw.config.stick_max, sw.config.stick_tick),
            lambda screen, before=current: _move_cursor(sw, screen) not in (before, -1),
            "招式光标移动",
        )
    raise RuntimeError(f"招式光标移了 4 次，还是没到第 {target + 1} 行")


def _storm(sw: LairSwitch, war: War) -> bool:
    """有宝可梦倒下：这一场倒下次数加 1，等「倒下了」这行字消失。命数扣到 0 就是输了，返回 True。

    输了之后的带走宝可梦界面由 select_pokemon 去等。
    """
    war.faints += 1
    lives = sw.game.lives - war.faints
    logging.info(f"有一只倒下了，这一场倒下 {war.faints} 次，还剩 {lives} 条命")
    wait_for(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_full_line1, "倒下了"),
        sw.config.timeout,
        "「倒下了」消失",
    )
    return lives <= 0


def _loss(sw: LairSwitch, war: War) -> None:
    """认到战败（「被风刮到巢穴外了」）：这一场到此结束，倒下次数按已经记下的写进去。"""
    logging.info(f"战败，这一场倒下 {war.faints} 次")
    _record_faints(sw, war)


def _record_faints(sw: LairSwitch, war: War) -> None:
    """这一场打完：倒下次数写进 game.faints，每场固定加一项。"""
    sw.game.faints.append(war.faints)
    sw.game.save()


def _cheer(sw: LairSwitch) -> None:
    """助威：按 A，等助威菜单消失。"""
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.battle_menu_text, "助威"),
        "助威菜单消失",
    )


def _marker_shown(sw: LairSwitch, image: ImageChecker, rect: Rect) -> bool:
    """区域里有菜单光标「>」：白色描边加黑色填充。"""
    white = image.color_ratio(rect, sw.config.marker_white_lower, sw.config.marker_white_upper)
    dark = image.color_ratio(rect, sw.config.marker_dark_lower, sw.config.marker_dark_upper)
    return white > sw.config.marker_white_ratio and dark > sw.config.marker_dark_ratio


def _battle_state(sw: LairSwitch, image: ImageChecker) -> str:
    """当前战斗界面是哪个状态：fight、cheer、catch、loss（战败，被风刮到巢穴外）、
    storm（有宝可梦倒下）、field（天气、场地变化的提示）；都不是返回 none。"""
    if image.has_text(sw.config.rects.battle_menu_text, "战斗"):
        return "fight"
    if image.has_text(sw.config.rects.battle_menu_text, "助威"):
        return "cheer"
    if image.has_text(sw.config.rects.black_full_line2, "使用精灵球的好机会"):
        return "catch"
    # 战败时黑屏上出两行字：「×××他们」「被风刮到巢穴外了……」
    if image.has_text(sw.config.rects.black_full_line2, "巢穴外"):
        return "loss"
    if image.has_text(sw.config.rects.black_full_line1, "倒下了"):
        return "storm"
    if Field.change(image.read_text(sw.config.rects.black_full_line1)) is not None:
        return "field"
    return "none"


def _move_cursor(sw: LairSwitch, image: ImageChecker) -> int:
    """招式列表光标在第几行，不在招式列表上返回 -1。"""
    marks = [_marker_shown(sw, image, rect) for rect in sw.config.rects.move_cursor_rects]
    return marks.index(True) if marks.count(True) == 1 else -1
