import re
from dataclasses import replace

from config.game import BASE_BALL, CATCH_BOSS, LEGENDARY_BALL
from config.layout import (
    BALL_COUNT_RECT,
    BALL_NAME_RECT,
    CATCH_BLACK_RECT,
    CATCH_WHITE_RECT,
    CAUGHT_ABILITY_RECT,
    CAUGHT_MOVES_RECT,
    CAUGHT_NAME_RECT,
    SWAP_CURSOR_RECTS,
    SWAP_HP_RECT,
    SWAP_OPTION_RECTS,
    SWAP_PLAYER_RECTS,
    SWAP_RESULT_RECT,
)
from config.timing import DEFAULT_TIMEOUT, TICK_SECONDS
from lib import data, pokemon, run, switch
from lib.dialog import marker_shown
from lib.log import log
from lib.scoring import evaluate_average_matchup, evaluate_matchup, weighted_score
from lib.wait import wait_for
from tool.check_image import ImageChecker
from tool.image import text_lines
from type.pokemon import Pokemon


def catch() -> str:
    """打赢之后抓：选好配置里的球扔出去，抓到普通对手时再决定要不要换成它。照搬上游。

    开始时游戏要停在「捕捉 / 不捕捉」上，见 battle。使用全局连接，需要先调用 switch.connect。
    返回下一步的名字：抓的是普通对手返回 "path"，首领（第 4 只）返回 "select_pokemon"。
    """
    current = run.get()
    boss = current.num_caught == 3
    if boss and not CATCH_BOSS:
        _skip_boss()
        log("不抓首领，这一局结束")
        return "select_pokemon"

    log(f"抓第 {current.num_caught + 1} 只")
    switch.get().click("A", 0)
    _select_ball(LEGENDARY_BALL if boss else BASE_BALL)
    switch.get().click("A", 0)
    wait_for(lambda screen: not _ball_name(screen), DEFAULT_TIMEOUT, "扔出球，选球界面消失")
    current.num_caught += 1
    if boss:
        current.caught.append(current.boss)
        log("抓了首领，这一局结束")
        return "select_pokemon"

    # 抓的动画大约 25 秒，之后才出现换不换的界面
    image = wait_for(
        lambda screen: screen.has_text(SWAP_OPTION_RECTS[0], "替换"), 60, "换不换的界面"
    )
    _swap(image)
    return "path"


def _skip_boss() -> None:
    """把光标从「捕捉」移到「不捕捉」上按 A，等这个界面消失。"""
    switch.get().stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
    # 选中的那一行是黑底：移过去之后上面一行变白、下面一行变黑
    wait_for(
        lambda screen: (
            screen.color_ratio(CATCH_BLACK_RECT, (0, 0, 250), (180, 10, 255)) > 200 / 255
            and screen.color_ratio(CATCH_WHITE_RECT, (0, 0, 0), (180, 10, 10)) > 200 / 255
        ),
        DEFAULT_TIMEOUT,
        "光标移到「不捕捉」上",
    )
    switch.get().click("A", 0)
    wait_for(
        lambda screen: screen.color_ratio(CATCH_WHITE_RECT, (0, 0, 0), (180, 10, 10)) <= 200 / 255,
        DEFAULT_TIMEOUT,
        "「捕捉 / 不捕捉」消失",
    )


def _select_ball(ball: str) -> None:
    """选球界面上一个个往左翻，直到选中 ball。

    翻遍了也没找到就抛 RuntimeError，绝不扔别的球。每翻一下都等球名变了再判断。
    """
    # 最多翻几下：背包里的球不会超过这么多种
    max_turns = 30

    image = wait_for(_ball_name, DEFAULT_TIMEOUT, "选球界面")
    name = _ball_name(image)
    for _ in range(max_turns):
        if ball in name:
            break
        switch.get().click("DLEFT", 0)
        image = wait_for(
            lambda screen, before=name: _ball_name(screen) not in ("", before),
            DEFAULT_TIMEOUT,
            "换到左边那种球",
        )
        name = _ball_name(image)
    else:
        raise RuntimeError(f"翻了 {max_turns} 下也没找到{ball}，不扔别的球")
    count = image.read_text(BALL_COUNT_RECT).strip()
    log(f"选好了{ball}，还有 {count}")
    # 数量写成「×767」，扔完少一个
    digits = re.sub(r"\D", "", count)
    if digits:
        run.get().balls[ball] = int(digits) - 1


def _swap(image: ImageChecker) -> None:
    """换不换的界面：认出新捉到的宝可梦，照搬上游给几种可能的队伍打分，决定换不换，
    再等大家选完的结果，按结果更新队伍。

    这个界面有倒计时，所以一出现就算、就按。keep path 时新捉到的就是上一局在这里遇到的对手，不读。
    """
    current = run.get()
    own = current.pokemon
    assert own is not None
    index = current.current_index
    planned = (current.plan or {}).get("opponents", {}).get(str(index))
    caught = replace(data.rental_pokemon()[planned], hp=1.0) if planned else _read_caught(image)
    current.caught.append(caught.name_id)
    current.encountered.add(caught.name_id)

    # 左边列表上读血量
    team = current.team
    # 血条旁边偶尔会被读出杂字（真机上读出过「Z」），只留「数字/数字」的行
    lines = sorted(text_lines(image, SWAP_HP_RECT), key=lambda line: line[1][0][1])
    hps = [found for text, _ in lines if (found := re.fullmatch(r"(\d+)/(\d+)", text))]
    if len(hps) == 4 and all(int(found[2]) for found in hps):
        for member, found in zip([own, *team], hps):
            member.hp = int(found[1]) / int(found[2])
    else:
        log(f"血量读不全: {[text for text, _ in lines]}，保留原来的", "WARNING")
    log(f"血量 {[f'{m.hp:.0%}' for m in [own, *team]]}")

    # 还会遇到的对手：没见过的、属性和目标路线上剩下的节点对得上的租借宝可梦
    types_left = {node.name for node in current.target_path[index + 1 :]}
    potential = [
        rental
        for name_id, rental in data.rental_pokemon().items()
        if name_id not in current.encountered and not types_left.isdisjoint(rental.type_ids)
    ]
    # 还剩几个对手要打决定权重，首领更难，权重更大
    rental_weight, boss_weight = 3 - current.num_caught, 2
    boss = data.boss_pokemon()[current.boss]
    potential_teams = (
        (caught, team[0], team[1], team[2]),
        (own, team[0], team[1], team[2]),
        (own, caught, team[1], team[2]),
        (own, team[0], caught, team[2]),
        (own, team[0], team[1], caught),
    )
    scores = [
        weighted_score(
            evaluate_average_matchup(first, potential, rest, current.lives),
            rental_weight,
            evaluate_matchup(first, boss, rest, current.lives),
            boss_weight,
        )
        for first, *rest in potential_teams
    ]
    # 不换的话，队友大约一半的机会会换，三个都不换的机会是 (1/2)^3
    take_score = scores[0]
    leave_score = 0.125 * scores[1] + 0.875 * sum(scores[2:]) / 3
    take = take_score > leave_score
    log(f"换成 {caught.name_id} 的分数 {take_score:.2f}，不换 {leave_score:.2f}")

    if not take:
        switch.get().stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
        wait_for(
            lambda screen: marker_shown(screen, SWAP_CURSOR_RECTS[1]),
            DEFAULT_TIMEOUT,
            "光标移到「维持现状继续前进」上",
        )
    elif not marker_shown(image, SWAP_CURSOR_RECTS[0]):
        raise RuntimeError("换不换的界面上光标不在「我想替换同行宝可梦」上")
    switch.get().click("A", 0)
    log(f"决定{'换成 ' + caught.name_id if take else '不换，继续用 ' + own.name_id}")

    # 大家都选完（或者倒计时到了）才出现结果，例如「礼嘉决定带走皮皮了！」
    image = wait_for(
        lambda screen: bool(screen.read_text(SWAP_RESULT_RECT).strip()), 60, "换不换的结果"
    )
    result = image.read_text(SWAP_RESULT_RECT).strip()
    log(f"结果: {result}")
    if "带走" not in result:
        return
    taker = result.split("决定", 1)[0]
    players = [image.read_text(rect).strip() for rect in SWAP_PLAYER_RECTS]
    if taker not in players:
        log(f"认不出是谁带走的，列表上的玩家是 {players}", "WARNING")
        return
    slot = players.index(taker)
    if slot == 0:
        current.pokemon = caught
    else:
        team[slot - 1] = caught
    log(f"{taker} 带走了 {caught.name_id}，队伍: {[m.name_id for m in [current.pokemon, *team]]}")


def _read_caught(image: ImageChecker) -> Pokemon:
    """读右边标着 NEW 的那张卡片：名字、特性、招式，认出新捉到的是哪只。

    照搬上游不看属性：两个属性的标签读不全（真机上巴大蝶只读到「虫」），按属性筛反而认错。
    """
    name = image.read_text(CAUGHT_NAME_RECT).strip()
    ability = image.read_text(CAUGHT_ABILITY_RECT).strip()
    moves = "".join(text for text, _ in text_lines(image, CAUGHT_MOVES_RECT))
    match = pokemon.identify(name, ability, moves)
    log(
        f"新捉到的读到「{name} {ability} {moves}」，认成 {match.pokemon.name_id}",
        "WARNING" if match.is_poor else "DEBUG",
    )
    return replace(match.pokemon, hp=1.0)


def _ball_name(screen: ImageChecker) -> str:
    """选球界面上现在选中的球名，不在选球界面返回空字符串。"""
    return screen.read_text(BALL_NAME_RECT).strip()
