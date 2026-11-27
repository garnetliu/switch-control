"""一场极巨大冒险对战。"""

import logging
import time
from dataclasses import replace
from typing import cast

from control_switch.flow import capture, press_until, wait_until
from control_switch.games.swsh.field import Field
from control_switch.games.swsh.lair.session import LairSession
from control_switch.games.swsh.lair.war import War
from control_switch.games.swsh.pokemon import Pokemon
from control_switch.types import Rect
from control_switch.vision import ImageChecker


def battle(sw: LairSession) -> str:
    """打到出现要不要抓的界面返回 "catch"，命数扣到 0 或者认到战败返回 "select_pokemon"。"""
    war = _create_war(sw)
    rects = sw.config.rects
    messages = Messages((rects.black_full_line1, rects.black_full_line2), "战斗文字")

    while True:
        image = capture(sw, "战斗")
        messages.read(image)
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
            time.sleep(sw.config.wait.interval)


class Messages:
    """画面下方黑色面板上的两行字，一句话显示完了打印到日志（谁用了什么招式、谁换上了哪只这些）。"""

    def __init__(self, rects: tuple[Rect, Rect], label: str) -> None:
        """rects 是面板上第一行和第二行的区域，label 是日志里这一行开头写什么。"""
        self._rects = rects
        self._label = label
        # 面板上现在这句话读到的部分
        self._text = ""

    def read(self, image: ImageChecker) -> None:
        """读这张截图上的两行字。字是一个一个出来的：新读到的接着上一次的，就还是同一句，先不打印；
        换成了别的字或者字没了，上一句就是显示完了，打印出来。"""
        lines = [image.read_text(rect) for rect in self._rects]
        text = " / ".join(line for line in lines if line)
        if text.startswith(self._text):
            self._text = text
            return
        logging.info(f"{self._label}: {self._text}")
        self._text = text


def _create_war(sw: LairSession) -> War:
    """建这场对战的场上状态：自己、队友和对手。自己的 PP 用内存里读到的剩余值。"""
    own_pp = _read_team(sw)
    own_name, own_hp = sw.game.team[0]
    opponent = _read_opponent(sw)
    return War(
        own=replace(sw.data.pokemon_object(own_name), hp=own_hp, pp=own_pp),
        teammates=[replace(sw.data.pokemon_object(name), hp=hp) for name, hp in sw.game.team[1:]],
        opponent=opponent,
        max_move_rate=sw.data.max_move_rate(opponent.name_id),
    )


def _read_team(sw: LairSession) -> list[int]:
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
    # 每只带着什么道具：遇到背包客之后能看出四个人各拿了哪一样
    items = [record["itemName"] if record["item"] else "无" for record in records]
    logging.info(f"队伍道具: {'，'.join(items)}")
    abilities = [f"{record['abilityName']}（{record['abilityNumber']}）" for record in records]
    logging.info(f"队伍特性: {'，'.join(abilities)}")
    sw.game.save()
    own_pp = list(records[0]["pp"])
    logging.info(f"队伍: {sw.game.team}，自己的 PP: {own_pp}")
    return own_pp


def _read_opponent(sw: LairSession) -> Pokemon:
    """第 4 场是首领，直接用这一局的首领；其他场从对手内存记录识别。

    对手（首领也是）的内存记录都读一次记进日志，复盘和核对伤害用。
    """
    record = sw.pkhex.read_pk8([sw.config.addresses.opponent])[0]
    boss = sw.game.num_caught == 3
    # 首领不一定在租借宝可梦的表里，名字直接用这一局的首领，另外记下内存里的种类编号
    name = sw.game.boss if boss else sw.data.name_id(record["species"], record["form"])
    # 对手的特性、性格、性别、个体值：看它们是不是 seed 定死的（同一张图每局一样）
    logging.info(
        f"对手 {name}（种类 {record['species']}）：特性 {record['abilityName']}（编号 {record['abilityNumber']}），"
        f"性格 {record['nature']}，性别 {record['gender']}，个体值 {record['ivs']}，"
        f"等级 {record['level']}，记录里的血量 {record['hp']}/{record['maxHp']}，"
        f"招式 {record['moves']}，道具 {record['itemName'] or '无'}"
    )
    return replace(sw.data.pokemon_object(name))


def _choose_move(sw: LairSession, war: War) -> None:
    """算出这回合用哪个招式、要不要极巨化，然后出招。

    极巨招式经常重名，所以按序号移光标，不按名字找。
    """
    war.start_turn()
    image = press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: _move_cursor(sw, screen) >= 0,
        "招式列表",
    )
    _log_turn(sw, war)
    # 这回合试过、被封住用不了的招式
    blocked: set[int] = set()
    while True:
        best, score, dynamax = war.best_move(_dynamax_available(sw, image), blocked)
        if dynamax:
            image = _dynamax(sw)
            war.dynamax()
        own = war.own
        move = own.max_moves[best] if own.dynamax else own.moves[best]
        logging.info(f"用第 {best + 1} 个招式 {move.name()}，得分 {score:.2f}")

        _move_cursor_to(sw, image, best)
        if _use_move(sw):
            break
        blocked.add(best)
        if len(blocked) == len(own.moves):
            raise RuntimeError("四个招式都用不了")
        logging.info(f"{move.name()} 被封住了用不了，换一个招式")
        # 「无法使出」这行字自己会消失，消失后回到招式列表
        image = wait_until(
            sw,
            lambda screen: not _move_blocked(sw, screen) and _move_cursor(sw, screen) >= 0,
            "回到招式列表",
        )
    war.use_move(best)


def _log_turn(sw: LairSession, war: War) -> None:
    """把这回合选招时对手和我方四只战斗里的实时数据记进日志，之后可以逐回合复盘。

    每只的 PK8 记录往前 battle_data 字节起是它战斗用的数据（见 docs/实测-对手的真实血量.md）：
    种类、最大血量、当前血量各 2 字节（最大血量是极巨化之后的）；0x232 起是攻击、防御、特攻、特防、速度；
    0x244 起 7 字节是能力变化的等级（攻击、防御、特攻、特防、速度、命中、闪避，6 是没变）；
    0x258 起是 4 个招式，每个 28 字节，开头 2 字节是招式编号，第 4、5 字节是剩余 PP 和 PP 上限。
    特性、个体值、性格、道具每场开打时记过（「队伍特性」「队伍道具」「对手」那几行）。
    """
    addresses = sw.config.addresses
    names = [war.opponent.name_id, *(name for name, _ in sw.game.team)]
    labels = ["对手", "自己", "队友1", "队友2", "队友3"]
    for label, name, address in zip(
        labels, names, (addresses.opponent, *addresses.party), strict=True
    ):
        data = sw.memory.peek(address - addresses.battle_data, 0x2C8)
        numbers = [int.from_bytes(data[at : at + 2], "little") for at in range(0, 6, 2)]
        stats = [int.from_bytes(data[at : at + 2], "little") for at in range(0x232, 0x23C, 2)]
        stages = [value - 6 for value in data[0x244:0x24B]]
        known = {move.id_num: move.name() for move in sw.data.pokemon_object(name).moves}
        moves = []
        for at in range(0x258, 0x2C8, 28):
            number = int.from_bytes(data[at : at + 2], "little")
            if number:
                moves.append(f"{known.get(number, number)} {data[at + 4]}/{data[at + 5]}")
        logging.info(
            f"回合数据 {label} {name}（种类 {numbers[0]}）：血量 {numbers[2]}/{numbers[1]}，"
            f"能力 {stats}，变化 {stages}，招式 {'、'.join(moves)}"
        )


def _move_blocked(sw: LairSession, image: ImageChecker) -> bool:
    """招式被定身法之类封住：战斗文字第二行是「而无法使出×××！」。"""
    return image.has_text(sw.config.rects.black_full_line2, "无法使出")


def _use_move(sw: LairSession) -> bool:
    """光标已经在要用的招式上：按 A 出招。出了招返回 True，招式被封住用不了返回 False。

    按 A 到招式列表消失，之后等三种结果里的一种：
    出现「无法使出」：招式被封住，返回 False，由外面换一个招式。
    出现选目标的界面：光标所在的卡片不能选（比如花瓣舞，光标默认在对手上，但只能选自己）
    就把光标移到能选的卡片上，然后一直按 A 到「×××使出了」。
    选目标界面上好几张卡片同时带光标（比如广域防守，对象是我方全体）：不用移，直接按 A。
    出现「×××使出了」：没有选目标界面的招式，已经出招（到现在没见过）。
    """

    # 招式列表在不在看它上方的「招式说明」，不看光标：选目标界面上我方卡片的名牌正好落在
    # 招式列表第一行的光标框里，会被当成招式光标；招式列表还在时背景里的训练家也会被当成选目标的光标
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.move_hint, "招式说明"),
        "招式列表消失",
    )

    def used(screen: ImageChecker) -> bool:
        return screen.has_text(sw.config.rects.black_full_line1, "使出了")

    # 先看「无法使出」再看「使出了」：两句都带「使出」
    image = wait_until(
        sw,
        lambda screen: cast(
            bool, _move_blocked(sw, screen) or _target_cursors(sw, screen) or used(screen)
        ),
        "无法使出、选目标的界面或者出招",
    )
    if _move_blocked(sw, image):
        return False
    if len(_target_cursors(sw, image)) > 1:
        # 对象是固定的一组（比如广域防守是我方全体）：几张卡片同时带光标，没有可以移的，直接按 A
        logging.info("选目标界面上有好几个光标，对象是固定的，不用移")
    else:
        _move_target_cursor(sw)
    press_until(
        sw,
        lambda: sw.click("A", 0),
        used,
        "出招",
    )
    return True


def _target_cursors(sw: LairSession, image: ImageChecker) -> list[int]:
    """选目标界面上哪些卡片左边有光标：0 是对手，1 到 4 是我方四张；不在选目标界面返回空列表。

    一般只有一个；对象是固定的一组的招式（比如广域防守是我方全体），那一组卡片同时带光标。
    """
    rects = (sw.config.rects.target_cursor, *sw.config.rects.ally_target_cursor_rects)
    return [index for index, rect in enumerate(rects) if _marker_shown(sw, image, rect)]


def _target_cursor(sw: LairSession, image: ImageChecker) -> int:
    """选目标界面的光标在哪张卡片上：0 是对手，1 到 4 是我方四张；没有光标或者不止一个返回 -1。"""
    cursors = _target_cursors(sw, image)
    return cursors[0] if len(cursors) == 1 else -1


def _target_selectable(sw: LairSession, image: ImageChecker, index: int) -> bool:
    """选目标界面第 index 张卡片能不能选：能选的是不透明的白底或黑底，不能选的是半透明的灰底。"""
    rect = (sw.config.rects.target_card, *sw.config.rects.ally_target_card_rects)[index]
    white = image.color_ratio(
        rect, sw.config.target_card_white_lower, sw.config.target_card_white_upper
    )
    dark = image.color_ratio(rect, sw.config.marker_dark_lower, sw.config.marker_dark_upper)
    return max(white, dark) > sw.config.target_card_ratio


def _target_blocked(sw: LairSession) -> bool:
    """光标停在一张不能选的卡片上返回 True。

    界面刚出来时卡片还在淡入，所以连着看 3 张：有一张能选，或者已经不在选目标界面了，就返回 False。
    """
    for _ in range(3):
        image = capture(sw, "选目标的光标能不能选")
        index = _target_cursor(sw, image)
        if index == -1 or _target_selectable(sw, image, index):
            return False
        time.sleep(sw.config.wait.interval)
    return True


def _move_target_cursor(sw: LairSession) -> None:
    """光标所在的卡片不能选：先按下移到我方那一排，再一张一张往右，停在第一张能选的卡片上。"""
    for button in ("DDOWN", "DRIGHT", "DRIGHT", "DRIGHT"):
        if not _target_blocked(sw):
            logging.info("选目标的光标在能选的卡片上")
            return
        before = _target_cursor(sw, capture(sw, "选目标的光标"))
        press_until(
            sw,
            lambda key=button: sw.click(key, 0),
            lambda screen, last=before: _target_cursor(sw, screen) not in (last, -1),
            "选目标的光标移动",
        )


def _dynamax(sw: LairSession) -> ImageChecker:
    """招式列表上把光标移到「极巨化」按钮上按 A，等列表换成极巨招式，返回换好后的画面。"""
    sw.stick("LEFT", -sw.controller.STICK_MAX, 0, sw.config.wait.stick_tick)
    wait_until(
        sw,
        lambda screen: _marker_shown(sw, screen, sw.config.rects.dynamax_cursor),
        "光标移到极巨化按钮上",
    )
    # 按键偶尔会丢：光标还停在极巨化按钮上就再按。光标一离开按钮就不能再按了，招式列表的光标要过一会儿才画出来，
    # 这时候再按 A 会直接选中第一个招式。不看按钮本身：对手是一大块白色时，按钮那块背景也是白的，会当成按钮还在
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not _marker_shown(sw, screen, sw.config.rects.dynamax_cursor),
        "光标离开极巨化按钮",
    )
    image = wait_until(
        sw,
        lambda screen: _move_cursor(sw, screen) >= 0,
        "换成极巨招式",
    )
    logging.info("极巨化")
    return image


def _dynamax_available(sw: LairSession, image: ImageChecker) -> bool:
    """招式列表左边有「极巨化」按钮：按钮上白色标志的占比超过阈值。"""
    return (
        image.color_ratio(
            sw.config.rects.dynamax_button,
            sw.config.dynamax_lower,
            sw.config.dynamax_upper,
        )
        > sw.config.dynamax_ratio
    )


def _move_cursor_to(sw: LairSession, image: ImageChecker, target: int) -> None:
    """把招式列表光标移到第 target 行。光标会记住上回合的位置，按到目标为止。"""
    for _ in range(len(sw.config.rects.move_cursor_rects)):
        current = _move_cursor(sw, image)
        if current == target:
            return
        image = press_until(
            sw,
            lambda: sw.stick("LEFT", 0, -sw.controller.STICK_MAX, sw.config.wait.stick_tick),
            lambda screen, before=current: _move_cursor(sw, screen) not in (before, -1),
            "招式光标移动",
        )
    raise RuntimeError(f"招式光标移了 4 次，还是没到第 {target + 1} 行")


def _storm(sw: LairSession, war: War) -> bool:
    """有宝可梦倒下：这一场倒下次数加 1，等「倒下了」这行字消失。命数扣到 0 就是输了，返回 True。

    输了之后的带走宝可梦界面由 select_pokemon 去等。
    """
    war.faints += 1
    lives = sw.game.lives - war.faints
    logging.info(f"有一只倒下了，这一场倒下 {war.faints} 次，还剩 {lives} 条命")
    wait_until(
        sw,
        lambda screen: not screen.has_text(sw.config.rects.black_full_line1, "倒下了"),
        "「倒下了」消失",
    )
    return lives <= 0


def _loss(sw: LairSession, war: War) -> None:
    """认到战败（「被风刮到巢穴外了」）：这一场到此结束，倒下次数按已经记下的写进去。

    团灭和打满回合上限还没打倒对手，游戏出的都是这句话；还有命就是超回合输的。
    """
    lives = sw.game.lives - war.faints
    reason = "超回合：回合用完还没打倒对手" if lives > 0 else "团灭"
    logging.info(f"战败（{reason}），这一场倒下 {war.faints} 次，还剩 {lives} 条命")
    _record_faints(sw, war)


def _record_faints(sw: LairSession, war: War) -> None:
    """这一场打完：倒下次数写进 game.faints，每场固定加一项。"""
    sw.game.faints.append(war.faints)
    sw.game.save()


def _cheer(sw: LairSession) -> None:
    """助威：按 A，等助威菜单消失。"""
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.battle_menu_text, "助威"),
        "助威菜单消失",
    )


def _marker_shown(sw: LairSession, image: ImageChecker, rect: Rect) -> bool:
    """区域里有菜单光标「>」：白色描边加黑色填充。"""
    white = image.color_ratio(rect, sw.config.marker_white_lower, sw.config.marker_white_upper)
    dark = image.color_ratio(rect, sw.config.marker_dark_lower, sw.config.marker_dark_upper)
    return white > sw.config.marker_white_ratio and dark > sw.config.marker_dark_ratio


def _battle_state(sw: LairSession, image: ImageChecker) -> str:
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


def _move_cursor(sw: LairSession, image: ImageChecker) -> int:
    """招式列表光标在第几行，不在招式列表上返回 -1。"""
    marks = [_marker_shown(sw, image, rect) for rect in sw.config.rects.move_cursor_rects]
    return marks.index(True) if marks.count(True) == 1 else -1
