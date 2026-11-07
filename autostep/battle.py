import time
from dataclasses import replace

from config.layout import (
    ALLY_TARGET_CURSOR_RECTS,
    BATTLE_LINE2_RECT,
    BATTLE_SYMBOL_RECT,
    BATTLE_TEXT_RECT,
    DYNAMAX_BUTTON_RECT,
    DYNAMAX_CURSOR_RECT,
    MOVE_CURSOR_RECTS,
    RESULT_TITLE_RECT,
    TARGET_CURSOR_RECT,
)
from config.timing import DEFAULT_TIMEOUT, POLL_INTERVAL, TICK_SECONDS
from lib import data, pkhex, run, switch
from lib.dialog import marker_shown
from lib.log import log
from lib.scoring import select_best_move, transform_ditto
from lib.wait import act_until, capture, wait_for
from tool.check_image import ImageChecker
from type.pokemon import Pokemon

# 打赢时战斗文字的第二行「现在是使用精灵球的好机会！」（第一行是「×××变得虚弱了！」，真机截图），之后问要不要抓
WEAK_TEXT = "使用精灵球的好机会"
# 倒下时先出「×××倒下了！」，接着出「上空的风暴变强了！」或「风暴变得越来越强了！！」（真机截图）
DOWN_TEXT = "倒下了"
FAINT_TEXT = "风暴"
# 输掉（4 次倒下或者打满回合）时没有要不要抓的界面，结算完直接到「选 1 只带回去」的列表
RESULT_TEXT = "选1只要带回去的宝可梦"
OPPONENT_ADDRESS = 0x886A95B8
# 队伍 P1–P4：自己 + 3 个队友。选初始界面读不到，战斗开始后才有效（实测）
LAIR_PARTY_ADDRESSES = (0x886B67C8, 0x886BC348, 0x886B9588, 0x886BF108)
PK8_SIZE = 0x158


def battle() -> str:
    """一场对战：从内存识别对手、选招式出招，然后等这一回合打完。

    开始时游戏在这场对战开场的「×××出现了！」上，见 path：先等战斗菜单出来，等的时候也读战斗文字，
    开场时特性带来的天气、场地（比如电气制造者）就是这时出现的。使用全局连接，需要先调用 switch.connect。
    返回下一步的名字：出现「要不要抓」的界面返回 "catch"，输掉了（4 次倒下或者 10 回合）
    返回 "select_pokemon"。
    """
    current = run.get()
    current.start_battle()
    if current.num_caught == 3 and current.current_index < len(current.target_path) - 1:
        # 首领前面没有岔路，path 不会往前走一格，这里补上；否则首领这场会记到第 3 关头上（真机上出现过）
        current.advance()
    log(f"第 {current.num_caught + 1} 场对战开始，节点是 {current.current_node}")
    # 开场到战斗菜单出来，真机上二十多秒
    wait_for(_battle_ready, 60, "战斗菜单")
    _read_team()
    lives_before = current.lives
    state = "fight"
    turn = 0
    while True:
        if state == "catch":
            log("出现了要不要抓的界面")
            current.battle_faints[current.current_index] = lives_before - current.lives
            return "catch"
        if state == "loss":
            log("输了，这一局结束")
            current.lives = 0
            current.battle_faints[current.current_index] = lives_before
            return "select_pokemon"
        turn += 1
        log(f"第 {turn} 回合", "DEBUG")
        if state == "cheer":
            _cheer()
        else:
            if current.opponent is None:
                _check_opponent()
            _choose_move()
        state = _wait_turn()


def _read_team() -> None:
    """从战斗内存读 P1–P4，把队友补进这一局。选初始界面读不到队伍地址，第一场战斗才有效。

    P1 是自己，P2–P4 是队友；这一局已经有队友（keep path 沿用上一局）就不再读。
    """
    current = run.get()
    if current.team:
        return
    raw = [switch.get().peek(address, PK8_SIZE) for address in LAIR_PARTY_ADDRESSES]
    records = pkhex.parse_pk8_batch(raw)
    members = []
    for record in records:
        member = pkhex.match_pokemon(record, list(data.rental_pokemon().values()))
        if member is None:
            raise RuntimeError(
                f"战斗内存里的队伍记录识别不了：species={record.get('species')} "
                f"form={record.get('form', 0)} moves={record.get('moves')}"
            )
        members.append(replace(member, hp=1.0))
    own, *teammates = members
    if current.pokemon is not None and own.name_id != current.pokemon.name_id:
        log(
            f"内存里的自己 {own.name_id} 和选的 {current.pokemon.name_id} 不一致，用内存里的",
            "WARNING",
        )
    current.pokemon, current.team = own, teammates
    current.record_start()
    log(f"从战斗内存读到队伍: {[m.name_id for m in [own, *teammates]]}")


def _check_opponent() -> None:
    """认出这场的对手，记到这一局里。

    每场都从战斗内存读取；上一局记录只用于对照，不代替当前读取结果。
    """
    current = run.get()
    index = current.current_index
    planned = (current.plan or {}).get("opponents", {}).get(str(index))
    expected = current.boss if current.num_caught == 3 else planned
    opponent = _read_opponent(expected)
    if planned is not None and opponent.name_id != planned:
        log(f"内存读到的对手 {opponent.name_id} 和上一局记录 {planned} 不同", "WARNING")
    if current.num_caught == 3 and opponent.name_id != current.boss:
        log(f"内存读到的首领 {opponent.name_id} 和目标 {current.boss} 不同", "WARNING")
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


def _read_opponent(expected_name: str | None = None) -> Pokemon:
    """从战斗中的 PK8 内存记录识别对手。"""
    raw = switch.get().peek(OPPONENT_ADDRESS, PK8_SIZE)
    record = pkhex.parse_pk8_batch([raw])[0]
    candidates = [*data.rental_pokemon().values(), *data.boss_pokemon().values()]
    opponent = pkhex.match_pokemon(record, candidates)
    if opponent is not None:
        log(
            f"从内存读取对手：{opponent.name_id}，"
            f"species={record['species']} form={record.get('form', 0)}"
        )
        return opponent

    if expected_name is not None:
        expected = data.boss_pokemon().get(expected_name) or data.rental_pokemon().get(
            expected_name
        )
        if (
            expected is not None
            and record.get("checksumValid")
            and (record.get("species"), record.get("form", 0))
            == pkhex.pokemon_species_form(expected)
        ):
            log(f"内存记录校验有效且物种/形态匹配 {expected_name}，使用本地招式数据", "WARNING")
            return expected
    raise RuntimeError(
        f"无法从战斗内存识别对手：checksum={record.get('checksumValid')} "
        f"species={record.get('species')} form={record.get('form', 0)} "
        f"moves={record.get('moves')}"
    )


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

    # 一直按 A，直到招式列表消失（选招式的那几行），或者出现选目标的界面，就是选好了。
    # 按键会被游戏吞掉，吞多久和加载有关，所以不限制按的次数。选目标由 _wait_turn 处理：
    # 招式列表比选目标的界面先消失（真机上中间有几帧两个都没有），在这里等会把它漏掉。
    # 选目标的界面上我方卡片的名字条会落进招式光标的检测框，看起来像招式列表还在，所以两个都要看
    act_until(
        lambda: switch.get().click("A", 0),
        lambda screen: _move_cursor(screen) < 0 or _target_shown(screen),
        "招式列表消失",
        interval=2.0,
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
    catch 打赢了（要不要抓）、loss 输了（4 条命都没了）。

    出现选目标的界面就按 A 确认默认的目标。
    每一帧都读战斗文字，天气和场地变了就记下来，见 _update_field。
    倒下的计数：先看到「倒下了」记一只待扣，接着看到「风暴」才扣 1 条命，扣完清掉；没有待扣时的
    「风暴」是同一行字又读了一次，不算。命数减到 0 就是输了。打满 10 回合没打完也会输，那时的文字还没见过，待实测。
    """
    # 一回合最多等几秒：真机上一回合（四只各出一招）约 66 秒
    turn_timeout = 180.0

    current = run.get()
    deadline = time.monotonic() + turn_timeout
    # 看到了「倒下了」、还没看到它后面那行「风暴」
    down_pending = False
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {turn_timeout} 秒，这一回合还没打完")
        screen = capture()
        if _fight_shown(screen):
            return "fight"
        if _cheer_shown(screen):
            return "cheer"
        if _catch_shown(screen):
            # 打赢时的完整文字还没记下来过，先记一次原话
            log(
                f"打赢了：{screen.read_text(BATTLE_TEXT_RECT)}{screen.read_text(BATTLE_LINE2_RECT)}"
            )
            return "catch"
        if screen.has_text(RESULT_TITLE_RECT, RESULT_TEXT):
            # 输掉时不会出要不要抓的界面，直接到「选 1 只带回去」的列表（真机上因此空等过 180 秒）
            log("到带走界面，这一局结束了")
            return "loss"
        if _target_shown(screen):
            # 选目标的界面，光标默认就在该选的目标上：打对手的在对手上，作用于我方全体的在我方卡片上
            switch.get().click("A", 0)
            wait_for(lambda screen: not _target_shown(screen), DEFAULT_TIMEOUT, "选好目标")
            continue
        _update_field(screen.read_text(BATTLE_TEXT_RECT))
        # 同一行「风暴」OCR 会时对时错（一帧「风暴」、下一帧「风泰」），按文字消失来去重，一只倒下
        # 扣过两条命，还把在打的首领战判成了输（真机上发生过两次）。所以要先看到「倒下了」才算数
        if screen.has_text(BATTLE_TEXT_RECT, DOWN_TEXT):
            down_pending = True
        elif down_pending and _storm_text(screen.read_text(BATTLE_TEXT_RECT)):
            down_pending = False
            # 命数不会小于 0：最后一条命没了时还会再出一行带「风暴」的字（减到 0 就直接返回了，保险起见）
            current.lives = max(current.lives - 1, 0)
            log(f"有一只倒下了，还剩 {current.lives} 条命")
            if current.lives == 0:
                return "loss"
        time.sleep(POLL_INTERVAL)


def _storm_text(text: str) -> bool:
    """「倒下了」之后的那行风暴提示。OCR 常把「风暴」读成「风泰」（真机上），所以只要有「风」字、
    又不是「×××使出了」的出招文字就算；只在刚看到「倒下了」之后用，那时下一行一定是风暴提示。
    """
    return FAINT_TEXT in text or ("风" in text and "使出了" not in text)


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


def _battle_ready(screen: ImageChecker) -> bool:
    """战斗菜单出来了。没出来时读战斗文字，记下开场时的天气、场地变化。"""
    if _fight_shown(screen):
        return True
    _update_field(screen.read_text(BATTLE_TEXT_RECT))
    return False


def _fight_shown(screen: ImageChecker) -> bool:
    """战斗菜单：右下角有「战斗」图标。真机上是 0.91 到 0.96，其他画面 0.25 以下。"""
    return screen.match_template(BATTLE_SYMBOL_RECT, data.misc_icons()["fight"]) >= 0.85


def _cheer_shown(screen: ImageChecker) -> bool:
    """应援菜单：右下角有「应援」图标（data/misc_icons/cheer.png，上游的图）。待实测"""
    return screen.match_template(BATTLE_SYMBOL_RECT, data.misc_icons()["cheer"]) >= 0.85


def _catch_shown(screen: ImageChecker) -> bool:
    """打赢了：战斗文字的第二行是「现在是使用精灵球的好机会！」，接着会问要不要抓。"""
    return screen.has_text(BATTLE_LINE2_RECT, WEAK_TEXT)


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
