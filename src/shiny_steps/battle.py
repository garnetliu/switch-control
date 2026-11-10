"""一场极巨大冒险对战。"""

import logging
import time
from dataclasses import replace

from libs import ImageChecker, Switch, War
from tools import act_until, capture, save_check, wait_for
from type import Field, Pokemon, Rect


def battle(sw: Switch) -> str:
    """打到出现要不要抓的界面返回 "catch"，输掉返回 "select_pokemon"。"""
    war = _create_war(sw)

    while True:
        image = capture(sw)
        state = _battle_state(sw, image)

        if state == "fight":
            _choose_move(sw, war)
        elif state == "cheer":
            war.faint()
            _cheer(sw)
        elif state == "field":
            war.update(image.read_text(sw.config.rects.battle_text))
        elif state == "storm":
            if _storm(sw):
                return "select_pokemon"
        elif state == "catch":
            return "catch"
        else:
            # 出招动画、战斗文字这些都不用处理，隔一会儿再看
            time.sleep(sw.config.interval)


def _create_war(sw: Switch) -> War:
    """建这场对战的场上状态：自己、队友和对手。自己的 PP 用内存里读到的剩余值。"""
    own_pp = _read_team(sw)
    own_name, own_hp = sw.game.team[0]
    return War(
        own=replace(sw.data.pokemon_object(own_name), hp=own_hp, pp=own_pp),
        teammates=[replace(sw.data.pokemon_object(name), hp=hp) for name, hp in sw.game.team[1:]],
        opponent=_read_opponent(sw),
    )


def _read_team(sw: Switch) -> list[int]:
    """重新读队伍内存：位置上的宝可梦没变的沿用原血量，变了的按满血算。返回自己 4 个招式的剩余 PP。"""
    records = sw.pkhex.read_pk8(sw.config.addresses.party)
    names = [sw.data.name_id(record["species"], record["form"]) for record in records]
    old = sw.game.team
    sw.game.team = [
        (name, old[index][1] if index < len(old) and old[index][0] == name else 1.0)
        for index, name in enumerate(names)
    ]
    sw.game.save()
    own_pp = list(records[0]["pp"])
    logging.info(f"队伍: {sw.game.team}，自己的 PP: {own_pp}")
    return own_pp


def _read_opponent(sw: Switch) -> Pokemon:
    """第 4 场是首领，直接用这一局的首领；其他场从对手内存记录识别。"""
    if sw.game.num_caught == 3:
        return replace(sw.data.pokemon_object(sw.game.boss))
    record = sw.pkhex.read_pk8([sw.config.addresses.opponent])[0]
    return replace(sw.data.pokemon_object(sw.data.name_id(record["species"], record["form"])))


def _choose_move(sw: Switch, war: War) -> None:
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
    # 选招式后可能还有选目标的界面，不单独判断，一直按 A，直到战斗文字出现「×××使出了」
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: screen.has_text(sw.config.rects.battle_text, "使出了"),
        "出招",
    )
    war.use_move(best)


def _dynamax(sw: Switch) -> ImageChecker:
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


def _dynamax_available(sw: Switch, image: ImageChecker) -> bool:
    """招式列表左边有「极巨化」按钮：按钮上白色标志的占比超过阈值。"""
    return (
        image.color_ratio(
            sw.config.rects.dynamax_button,
            sw.config.dynamax_lower,
            sw.config.dynamax_upper,
        )
        > sw.config.dynamax_ratio
    )


def _move_cursor_to(sw: Switch, image: ImageChecker, target: int) -> None:
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


def _storm(sw: Switch) -> bool:
    """有宝可梦倒下：扣 1 条命，等「倒下了」这行字消失。命数扣到 0 就是输了，返回 True。

    输了之后的带走宝可梦界面由 select_pokemon 去等。
    """
    sw.game.lives = max(sw.game.lives - 1, 0)
    sw.game.save()
    logging.info(f"有一只倒下了，还剩 {sw.game.lives} 条命")
    wait_for(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.battle_text, "倒下了"),
        sw.config.timeout,
        "「倒下了」消失",
    )
    return sw.game.lives == 0


def _cheer(sw: Switch) -> None:
    """应援：按 A，等应援菜单消失。"""
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.battle_menu_text, "应援"),
        "应援菜单消失",
    )


def _marker_shown(sw: Switch, image: ImageChecker, rect: Rect) -> bool:
    """区域里有菜单光标「>」：白色描边加黑色填充。"""
    white = image.color_ratio(rect, sw.config.marker_white_lower, sw.config.marker_white_upper)
    dark = image.color_ratio(rect, sw.config.marker_dark_lower, sw.config.marker_dark_upper)
    return white > sw.config.marker_white_ratio and dark > sw.config.marker_dark_ratio


def _battle_state(sw: Switch, image: ImageChecker) -> str:
    """当前战斗界面是哪个状态：fight、cheer、catch、storm（有宝可梦倒下）、
    field（天气、场地变化的提示）；都不是返回 none。"""
    if image.has_text(sw.config.rects.battle_menu_text, "战斗"):
        return "fight"
    if image.has_text(sw.config.rects.battle_menu_text, "应援"):
        save_check(sw, image, "cheer", sw.config.rects.battle_menu_text)
        return "cheer"
    if image.has_text(sw.config.rects.battle_line2, "使用精灵球的好机会"):
        save_check(sw, image, "catch", sw.config.rects.battle_line2)
        return "catch"
    if image.has_text(sw.config.rects.battle_text, "倒下了"):
        save_check(sw, image, "storm", sw.config.rects.battle_text)
        return "storm"
    if Field.change(image.read_text(sw.config.rects.battle_text)) is not None:
        return "field"
    return "none"


def _move_cursor(sw: Switch, image: ImageChecker) -> int:
    """招式列表光标在第几行，不在招式列表上返回 -1。"""
    marks = [_marker_shown(sw, image, rect) for rect in sw.config.rects.move_cursor_rects]
    return marks.index(True) if marks.count(True) == 1 else -1
