import time
from dataclasses import replace

from config.layout import (
    ALLY_TARGET_CURSOR_RECTS,
    BATTLE_SYMBOL_RECT,
    BATTLE_TEXT_RECT,
    CATCH_BLACK_RECT,
    CATCH_WHITE_RECT,
    DETAIL_ABILITY_LABEL_RECT,
    DETAIL_NAME_RECT,
    DETAIL_TYPES_RECT,
    DYNAMAX_BUTTON_RECT,
    DYNAMAX_CURSOR_RECT,
    INFO_OPPONENT_RECT,
    MOVE_CURSOR_RECTS,
    TARGET_CURSOR_RECT,
)
from config.timing import DEFAULT_TIMEOUT, POLL_INTERVAL, TICK_SECONDS
from lib import data, pokemon, run, switch
from lib.dialog import marker_shown
from lib.log import log
from lib.scoring import select_best_move, transform_ditto
from lib.wait import capture, wait_for
from tool.check_image import ImageChecker
from tool.image import text_lines
from type.pokemon import Pokemon

# 倒下时战斗文字里会出现的词（「……上空的风暴变强了」），旧项目里实测过
FAINT_TEXT = "风暴"


def battle() -> str:
    """一场对战：每次出现战斗菜单就认出对手（只认一次）、选招式出招，然后等这一回合打完。

    开始时游戏要停在这场对战的战斗菜单上，见 path。使用全局连接，需要先调用 switch.connect。
    返回下一步的名字：出现「要不要抓」的界面返回 "catch"，输掉了（4 次倒下或者 10 回合）
    返回 "select_pokemon"。
    """
    current = run.get()
    current.start_battle()
    log(f"第 {current.num_caught + 1} 场对战开始，节点是 {current.current_node}")
    state = "fight"
    while True:
        if state == "catch":
            log("出现了要不要抓的界面")
            return "catch"
        if state == "loss":
            log("输了，这一局结束")
            current.lives = 0
            return "select_pokemon"
        if state == "cheer":
            _cheer()
        else:
            if current.opponent is None:
                _check_opponent()
            _choose_move()
        state = _wait_turn()


def _check_opponent() -> None:
    """认出这场的对手，记到这一局里。

    第 4 场是首领，不用看。keep path 时上一局在这个节点遇到过的对手就是它，不用看。
    其他时候打开对手的详细页，读名字和属性。
    """
    current = run.get()
    index = current.current_index
    planned = (current.plan or {}).get("opponents", {}).get(str(index))
    if current.num_caught == 3:
        opponent = data.boss_pokemon()[current.boss]
    elif planned is not None:
        opponent = data.rental_pokemon()[planned]
        log(f"沿用上一局在这里遇到的对手 {planned}")
    else:
        opponent = _read_opponent()
    current.opponents[index] = opponent.name_id
    node_type = current.current_node.name
    if (
        opponent.name_id != "ditto"
        and node_type not in opponent.type_ids
        and current.num_caught < 3
    ):
        log(
            f"这个节点是 {node_type} 属性，对手却是 {opponent.name_id}{opponent.type_ids}",
            "WARNING",
        )
    log(
        f"第 {current.num_caught + 1} 场的对手: {opponent.name_id}（{'/'.join(opponent.type_ids)}）"
    )

    # 极巨大冒险里的百变怪有变身者特性，一上场就变成对方
    assert current.pokemon is not None
    if current.pokemon.name_id == "ditto":
        current.pokemon = transform_ditto(current.pokemon, opponent)
    elif opponent.name_id == "ditto":
        opponent = transform_ditto(opponent, current.pokemon)
    current.opponent = opponent


def _read_opponent() -> Pokemon:
    """打开对手的详细页读名字和属性，认出是哪只，再退回战斗菜单。

    战斗菜单上按 Y 打开场上宝可梦一览，A 打开自己这只的详细页，L 切到对手的详细页（真机实测）。
    """
    sw = switch.get()
    sw.click("Y", 0)
    wait_for(
        lambda screen: bool(screen.read_text(INFO_OPPONENT_RECT)), DEFAULT_TIMEOUT, "宝可梦一览"
    )
    sw.click("A", 0)
    wait_for(
        lambda screen: screen.has_text(DETAIL_ABILITY_LABEL_RECT, "特性"),
        DEFAULT_TIMEOUT,
        "自己这只的详细页",
    )
    sw.click("L", 0)
    # 对手的详细页上没有「特性」，并且名字读得出来
    image = wait_for(
        lambda screen: (
            not screen.has_text(DETAIL_ABILITY_LABEL_RECT, "特性")
            and bool(screen.read_text(DETAIL_NAME_RECT))
        ),
        DEFAULT_TIMEOUT,
        "对手的详细页",
    )
    name = image.read_text(DETAIL_NAME_RECT).strip()
    by_name = {zh: type_id for type_id, zh in data.type_names().items()}
    # 属性标签左边的图标也会被读成字，只留认得出的属性名
    type_ids = [
        by_name[text] for text, _ in text_lines(image, DETAIL_TYPES_RECT) if text in by_name
    ]
    match = pokemon.identify(name, type_ids=type_ids)
    log(
        f"对手详细页上读到「{name}」{type_ids}，认成 {match.pokemon.name_id}",
        "WARNING" if match.is_poor else "DEBUG",
    )

    # 详细页 → 一览 → 战斗菜单
    sw.click("B", 0)
    wait_for(
        lambda screen: bool(screen.read_text(INFO_OPPONENT_RECT)), DEFAULT_TIMEOUT, "回到宝可梦一览"
    )
    sw.click("B", 0)
    wait_for(_fight_shown, DEFAULT_TIMEOUT, "回到战斗菜单")
    return match.pokemon


def _choose_move() -> None:
    """算出这回合用哪个招式、要不要极巨化，然后出招。照搬上游的判断。

    打分返回的是招式的序号：极巨招式经常重名（比如两个「极巨钢铁」威力不同），
    所以一定按序号移光标，不按名字找。
    """
    current = run.get()
    own, opponent = current.pokemon, current.opponent
    assert own is not None and opponent is not None
    # 极巨化持续 3 回合，最后一回合用完就结束
    if current.dynamax_turns == 1:
        current.dynamax_turns = 0
        own.dynamax = False
    elif current.dynamax_turns > 1:
        current.dynamax_turns -= 1

    switch.get().click("A", 0)
    image = wait_for(lambda screen: _move_cursor(screen) >= 0, DEFAULT_TIMEOUT, "招式列表")
    best, _, score = select_best_move(own, opponent, current.field, current.team)
    if current.dynamax_turns == -1 and _dynamax_available(image):
        dynamax_best, _, dynamax_score = select_best_move(
            replace(own, dynamax=True), opponent, current.field, current.team
        )
        if dynamax_score > score:
            _dynamax()
            own.dynamax = True
            current.dynamax_turns = 3
            best, score = dynamax_best, dynamax_score
    move = own.max_moves[best] if own.dynamax else own.moves[best]
    log(f"用第 {best + 1} 个招式 {move.name()}（得分 {score:.2f}）")
    _move_cursor_to(best)

    switch.get().click("A", 0)
    # 招式列表消失、或者出现了选目标的界面，就是选好了。选目标由 _wait_turn 处理：
    # 招式列表比选目标的界面先消失（真机上中间有几帧两个都没有），在这里等会把它漏掉。
    # 选目标的界面上我方卡片的名字条会落进招式光标的检测框，看起来像招式列表还在，所以两个都要看
    wait_for(
        lambda screen: _move_cursor(screen) < 0 or _target_shown(screen),
        DEFAULT_TIMEOUT,
        "招式列表消失",
    )
    # 对手有压迫感特性时每次扣 2 点 PP
    own.pp[best] -= 2 if opponent.ability_name_id == "pressure" else 1


def _dynamax() -> None:
    """招式列表上把光标移到「极巨化」按钮上按 A，等列表换成极巨招式。"""
    switch.get().stick("LEFT", -switch.STICK_MAX, 0, TICK_SECONDS)
    wait_for(
        lambda screen: marker_shown(screen, DYNAMAX_CURSOR_RECT),
        DEFAULT_TIMEOUT,
        "光标移到极巨化按钮上",
    )
    switch.get().click("A", 0)
    # 极巨化之后按钮消失，光标回到招式列表上
    wait_for(
        lambda screen: not _dynamax_available(screen) and _move_cursor(screen) >= 0,
        DEFAULT_TIMEOUT,
        "换成极巨招式",
    )
    log("极巨化")


def _move_cursor_to(target: int) -> None:
    """把招式列表的光标移到第 target 个上：每下移一格，等「>」真的移到下一行再判断。

    光标不一定从第 1 个开始：游戏会记住上回合停在哪一行。
    """
    selected = _move_cursor(capture())
    for _ in range(len(MOVE_CURSOR_RECTS)):
        if selected == target:
            return
        switch.get().stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
        image = wait_for(
            lambda screen, before=selected: _move_cursor(screen) not in (before, -1),
            DEFAULT_TIMEOUT,
            "招式光标移到下一行",
        )
        selected = _move_cursor(image)
    if selected != target:
        raise RuntimeError(
            f"招式光标移了 {len(MOVE_CURSOR_RECTS)} 次，还是没到第 {target + 1} 个上"
        )


def _cheer() -> None:
    """自己的宝可梦倒下时只能应援：按 A 应援，等应援菜单消失。倒下时极巨化也结束了。"""
    current = run.get()
    if current.pokemon is not None and current.pokemon.dynamax:
        current.pokemon.dynamax = False
        current.dynamax_turns = 0
    switch.get().click("A", 0)
    wait_for(lambda screen: not _cheer_shown(screen), DEFAULT_TIMEOUT, "应援菜单消失")
    log("应援")


def _wait_turn() -> str:
    """一直看画面，等这一回合打完，返回接下来是什么：fight 战斗菜单、cheer 应援菜单、
    catch 要不要抓、loss 输了（一直黑屏）。

    出现选目标的界面就按 A 确认默认的目标。
    每一帧都读战斗文字，天气和场地变了就记下来，见 _update_field。
    出现「风暴」的文字就是有一只倒下了，命数减 1，等这行字消失再接着看，免得同一行字被算两次。
    """
    # 一回合最多等几秒：真机上一回合（四只各出一招）约 66 秒
    turn_timeout = 180.0
    # 黑屏持续这么久才算输了：极巨化动画之后也会闪一下黑屏
    loss_black_seconds = 1.0

    current = run.get()
    deadline = time.monotonic() + turn_timeout
    black_since: float | None = None
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {turn_timeout} 秒，这一回合还没打完")
        screen = capture()
        if _fight_shown(screen):
            return "fight"
        if _cheer_shown(screen):
            return "cheer"
        if _catch_shown(screen):
            return "catch"
        if _target_shown(screen):
            # 选目标的界面，光标默认就在该选的目标上：打对手的在对手上，作用于我方全体的在我方卡片上
            switch.get().click("A", 0)
            wait_for(lambda screen: not _target_shown(screen), DEFAULT_TIMEOUT, "选好目标")
            continue
        if screen.is_black():
            black_since = black_since or time.monotonic()
            if time.monotonic() - black_since >= loss_black_seconds:
                return "loss"
        else:
            black_since = None
        _update_field(screen.read_text(BATTLE_TEXT_RECT))
        if screen.has_text(BATTLE_TEXT_RECT, FAINT_TEXT):
            # 命数不会小于 0：最后一条命没了时还会再出一行带「风暴」的字
            current.lives = max(current.lives - 1, 0)
            log(f"有一只倒下了，还剩 {current.lives} 条命")
            wait_for(
                lambda screen: not screen.has_text(BATTLE_TEXT_RECT, FAINT_TEXT),
                DEFAULT_TIMEOUT,
                "风暴的文字消失",
            )
        time.sleep(POLL_INTERVAL)


def _update_field(text: str) -> None:
    """战斗文字里出现天气、场地变化的提示，就改这一局的天气、场地。照搬上游的做法：只看提示文字。

    上游没有中文的提示，下面是按游戏的中文提示写的关键词，待实测。
    消失的提示放在前面先判断：「脚下的青草消失了」里也有「青草」。
    """
    weathers = (
        (("日照复原", "雨停", "沙暴停止", "冰雹停止"), "clear"),
        (("日照变强",), "sunlight"),
        (("开始下雨",), "rain"),
        (("开始刮沙暴",), "sandstorm"),
        (("开始下冰雹",), "hail"),
    )
    terrains = (
        (("消失",), "clear"),
        (("电光",), "electric"),
        (("青草",), "grassy"),
        (("雾气",), "misty"),
        (("奇妙",), "psychic"),
    )
    field = run.get().field
    for keywords, weather in weathers:
        if any(keyword in text for keyword in keywords):
            if field.weather != weather:
                log(f"天气变成 {weather}：{text}")
            field.weather = weather
            return
    if "脚下" not in text:
        return
    for keywords, terrain in terrains:
        if any(keyword in text for keyword in keywords):
            if field.terrain != terrain:
                log(f"场地变成 {terrain}：{text}")
            field.terrain = terrain
            return


def _fight_shown(screen: ImageChecker) -> bool:
    """战斗菜单：右下角有「战斗」图标。真机上是 0.91 到 0.96，其他画面 0.25 以下。"""
    return screen.match_template(BATTLE_SYMBOL_RECT, data.misc_icons()["fight"]) >= 0.85


def _cheer_shown(screen: ImageChecker) -> bool:
    """应援菜单：右下角有「应援」图标（data/misc_icons/cheer.png，上游的图）。待实测"""
    return screen.match_template(BATTLE_SYMBOL_RECT, data.misc_icons()["cheer"]) >= 0.85


def _catch_shown(screen: ImageChecker) -> bool:
    """要不要抓的界面（右下角「捕捉 / 不捕捉」）：照搬上游，右下角一块几乎全黑、下面一块几乎全白。

    真机上认出来过一次。
    """
    black = screen.color_ratio(CATCH_BLACK_RECT, (0, 0, 0), (180, 10, 10)) > 200 / 255
    white = screen.color_ratio(CATCH_WHITE_RECT, (0, 0, 250), (180, 10, 255)) > 200 / 255
    return black and white


def _move_cursor(screen: ImageChecker) -> int:
    """招式列表上光标在第几个招式上（从 0 开始），不在招式列表上返回 -1。"""
    marks = [marker_shown(screen, rect) for rect in MOVE_CURSOR_RECTS]
    return marks.index(True) if marks.count(True) == 1 else -1


def _dynamax_available(screen: ImageChecker) -> bool:
    """招式列表左边有「极巨化」按钮：按钮上的白色标志占比超过上游的阈值（0 到 255 的均值 > 10）。"""
    return screen.color_ratio(DYNAMAX_BUTTON_RECT, (0, 0, 200), (180, 50, 255)) > 10 / 255


def _target_shown(screen: ImageChecker) -> bool:
    """选目标的界面：光标在对手那张卡片上，或者在我方的卡片上（作用于我方的招式）。"""
    return marker_shown(screen, TARGET_CURSOR_RECT) or any(
        marker_shown(screen, rect) for rect in ALLY_TARGET_CURSOR_RECTS
    )
