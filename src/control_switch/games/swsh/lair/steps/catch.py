"""打赢之后抓宝可梦，普通关再决定要不要换。"""

import logging
import re

from control_switch.flow import press_until, wait_until
from control_switch.games.swsh.lair import upstream
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.session import LairSession


def catch(sw: LairSession) -> str:
    """抓当前这只；首领抓完返回 "select_pokemon"，普通对手先定换不换再抓，返回 "path"。"""
    boss = sw.game.num_caught == 3
    if boss:
        _catch_pokemon(sw, boss)
        sw.game.caught.append(sw.game.boss)
        sw.game.save()
        logging.info("抓了首领，这一局结束")
        return "select_pokemon"
    take = _decide(sw)
    _catch_pokemon(sw, boss)
    _swap_pokemon(sw, take)
    sw.game.save()
    return "path"


def _decide(sw: LairSession) -> bool:
    """这一关抓到后自己换不换：按 upstream.decide_catch 定，决定记进 game.choices。

    换和不换都按 seed 推出之后的队伍（不换时实际是哪个队友换上，或者没人换）比队伍分。
    算不出来（存档里没有 seed 之类）按不换。
    """
    maps = sw.game.maps
    assert maps is not None
    row, col = maps["route"][maps["current_index"]]
    name = maps["rows"][str(row)][col]["encounter"]
    found = walker_now(sw)
    if found is None:
        logging.warning("队伍会怎么变没算出来，按不换")
        take = False
    else:
        scorer, walker = found
        # 路线上记着研究员、实际却没遇到就走到了这一关：那个研究员按没有出现跳过（不用随机数）
        while walker.next_event() == "scientist":
            logging.warning("路线上记着的研究员没遇到，按没有算")
            walker.index += 1
        if walker.opponents[walker.caught] != name:
            logging.warning(
                f"按 seed 推的这一只是 {walker.opponents[walker.caught]}，实际是 {name}"
            )
        take, scores = upstream.decide_catch(scorer, walker)
        logging.info(f"{name}：抓了不换 {scores['不换']:.2f}，抓了换 {scores['换']:.2f}")
    sw.game.choices.append(take)
    return take


def _catch_pokemon(sw: LairSession, boss: bool) -> None:
    """选「捕捉」，在选球界面向左翻到要用的球，扔出去。"""
    ball = sw.config.legendary_ball if boss else sw.config.base_ball
    wait_until(
        sw,
        lambda screen: screen.has_text(sw.config.rects.catch_option, "捕捉"),
        sw.config.wait.timeout,
        "「捕捉 / 不捕捉」",
    )
    logging.info(f"抓第 {sw.game.num_caught + 1} 只")
    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.catch_option, "捕捉"),
        sw.config.wait.timeout,
        "「捕捉」消失",
    )

    image = wait_until(
        sw,
        lambda screen: screen.has_text(sw.config.rects.ball_use, "使用"),
        sw.config.wait.timeout,
        "选球界面",
    )

    max_turns = 30
    for _ in range(max_turns):
        name = image.read_text(sw.config.rects.ball_name).strip()
        if ball in name:
            break
        image = press_until(
            sw,
            lambda: sw.click("DLEFT", 0),
            lambda screen, before=name: (
                screen.read_text(sw.config.rects.ball_name).strip() not in ("", before)
            ),
            sw.config.wait.timeout,
            "换到左边那种球",
        )
    else:
        name = image.read_text(sw.config.rects.ball_name).strip()
        logging.warning(f"翻了 {max_turns} 下也没找到{ball}，扔现在选中的{name}")
        ball = name
    count = image.read_text(sw.config.rects.ball_count).strip()
    logging.info(f"选好了{ball}，还有 {count}")
    digits = re.sub(r"\D", "", count)
    if digits:
        sw.game.balls[ball] = int(digits) - 1

    press_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.read_text(sw.config.rects.ball_name).strip(),
        sw.config.wait.timeout,
        "扔出球，选球界面消失",
    )
    sw.game.num_caught += 1


def _swap_pokemon(sw: LairSession, take: bool) -> None:
    """等换不换的界面，按 take 换或不换，等结果并按结果更新队伍。"""
    image = wait_until(
        sw,
        lambda screen: screen.has_text(sw.config.rects.swap_options[0], "替换"),
        sw.config.wait.timeout,
        "换不换的界面",
    )

    maps = sw.game.maps
    assert maps is not None
    row, col = maps["route"][maps["current_index"]]
    caught_name = maps["rows"][str(row)][col]["encounter"]
    sw.game.caught.append(caught_name)
    # 这一关是自己现在这只打的
    sw.game.fielded.append(sw.game.team[0][0])

    hp_lines = sorted(
        image.text_lines(sw.config.rects.swap_hp),
        key=lambda line: line[1][0][1],
    )
    hps = [found for text, _ in hp_lines if (found := re.fullmatch(r"(\d+)/(\d+)", text))]
    if len(hps) == 4 and all(int(found[2]) for found in hps):
        sw.game.team = [
            (name, int(found[1]) / int(found[2])) for (name, _), found in zip(sw.game.team, hps)
        ]

    _apply_swap(sw, caught_name, take)


def walker_now(sw: LairSession) -> tuple[upstream.Scorer, upstream.Walker] | None:
    """按这一局已经做过的决定（game.choices）把随机数推到现在要做决定的地方，队伍换成内存里读到的实际队伍。

    算不出来返回 None。
    """
    game = sw.game
    maps = game.maps
    if game.seed is None or game.lock_pokemon_index is None or maps is None:
        return None
    try:
        lair = Lair(sw.data, game.seed)
        path = tuple((row, col) for row, col in maps["route"][1:-1])
        events = sw.data.lair_events(maps["type"], maps.get("layout"))
        starter = game.lock_pokemon_index
        team = [game.candidates[starter], *lair.teammates(starter)]
        walker = upstream.Walker(lair, sw.data, game.boss, path, team, events)
        walker.replay(game.choices)
    except (KeyError, IndexError, ValueError) as error:
        logging.warning(f"按 seed 推队伍出错：{error!r}")
        return None
    if game.team:
        walker.team = [name for name, _ in game.team]
    return upstream.Scorer(sw.data, game.boss), walker


def _apply_swap(sw: LairSession, caught_name: str, take: bool) -> None:
    """选换或不换，等画面变黑。

    换了就把自己这只记成新抓的、满血，研究员要用；队友换没换这里看不到，等下一场战斗重新读队伍。
    """
    own_name = sw.game.team[0][0]

    logging.info(f"决定{'换成 ' + caught_name if take else '不换，继续用 ' + own_name}")
    # 换按 A，不换按 B，一直按到画面变黑
    press_until(
        sw,
        lambda: sw.click("A" if take else "B", 0),
        lambda screen: screen.is_black(),
        sw.config.wait.timeout,
        "换不换之后的黑屏",
    )
    if take:
        sw.game.team[0] = (caught_name, 1.0)
        sw.game.save()
