"""打赢之后抓宝可梦，普通关再决定要不要换。"""

import logging
import re
from dataclasses import replace

from libs import Switch
from libs.scoring import (
    evaluate_average_matchup,
    evaluate_matchup,
    weighted_score,
)
from tools import act_until, wait_for
from type import Pokemon


def catch(sw: Switch) -> str:
    """抓当前这只；首领抓完返回 "select_pokemon"，普通对手返回 "path"。"""
    boss = sw.game.num_caught == 3
    _catch_pokemon(sw, boss)
    if boss:
        sw.game.caught.append(sw.game.boss)
        sw.game.save()
        logging.info("抓了首领，这一局结束")
        return "select_pokemon"
    _swap_pokemon(sw)
    sw.game.save()
    return "path"


def _catch_pokemon(sw: Switch, boss: bool) -> None:
    """选「捕捉」，在选球界面向左翻到要用的球，扔出去。"""
    ball = sw.config.legendary_ball if boss else sw.config.base_ball
    wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.catch_option, "捕捉"),
        sw.config.timeout,
        "「捕捉 / 不捕捉」",
    )
    logging.info(f"抓第 {sw.game.num_caught + 1} 只")
    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.has_text(sw.config.rects.catch_option, "捕捉"),
        "「捕捉」消失",
    )

    image = wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.ball_use, "使用"),
        sw.config.timeout,
        "选球界面",
    )

    max_turns = 30
    for _ in range(max_turns):
        name = image.read_text(sw.config.rects.ball_name).strip()
        if ball in name:
            break
        image = act_until(
            sw,
            lambda: sw.click("DLEFT", 0),
            lambda screen, before=name: (
                screen.read_text(sw.config.rects.ball_name).strip() not in ("", before)
            ),
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

    act_until(
        sw,
        lambda: sw.click("A", 0),
        lambda screen: not screen.read_text(sw.config.rects.ball_name).strip(),
        "扔出球，选球界面消失",
    )
    sw.game.num_caught += 1


def _swap_pokemon(sw: Switch) -> None:
    """等换不换的界面，决定要不要换成新抓到的，等结果并按结果更新队伍。"""
    image = wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.swap_options[0], "替换"),
        sw.config.timeout,
        "换不换的界面",
    )

    maps = sw.game.maps
    row, col = maps["route"][maps["current_index"]]
    caught_name = maps["rows"][str(row)][col]["encounter"]
    sw.game.caught.append(caught_name)

    hp_lines = sorted(
        image.text_lines(sw.config.rects.swap_hp),
        key=lambda line: line[1][0][1],
    )
    hps = [found for text, _ in hp_lines if (found := re.fullmatch(r"(\d+)/(\d+)", text))]
    if len(hps) == 4 and all(int(found[2]) for found in hps):
        sw.game.team = [
            (name, int(found[1]) / int(found[2])) for (name, _), found in zip(sw.game.team, hps)
        ]

    take = _should_swap(sw, caught_name)
    _apply_swap(sw, caught_name, take)


def _should_swap(sw: Switch, caught_name: str) -> bool:
    """给换和不换打分，换成新抓到的分数更高返回 True。"""
    maps = sw.game.maps
    caught = replace(sw.data.pokemon_object(caught_name), hp=1.0)
    own_name, own_hp = sw.game.team[0]
    own = replace(sw.data.pokemon_object(own_name), hp=own_hp)
    team = [replace(sw.data.pokemon_object(name), hp=hp) for name, hp in sw.game.team[1:]]

    # 后面还可能遇到的对手：没见过、属性和剩下的路线节点对得上的租借宝可梦
    encountered = set(sw.game.rental_pool)
    for nodes in maps["rows"].values():
        encountered.update(node["encounter"] for node in nodes)
    encountered.update(sw.game.caught)
    encountered.update(name for name, _ in sw.game.team)
    # route 最后一项 [4, 0] 是首领，不在 rows 里
    types_left = {
        maps["rows"][str(row)][col]["type"]
        for row, col in maps["route"][maps["current_index"] + 1 : -1]
    }
    potential = [
        pokemon
        for name_id, pokemon in sw.data.rental_pokemon_objects().items()
        if name_id not in encountered and not types_left.isdisjoint(pokemon.type_ids)
    ]

    rental_weight, boss_weight = 3 - sw.game.num_caught, 2
    boss = sw.data.pokemon_object(sw.game.boss)
    potential_teams: tuple[tuple[Pokemon, Pokemon, Pokemon, Pokemon], ...] = (
        (caught, team[0], team[1], team[2]),
        (own, team[0], team[1], team[2]),
        (own, caught, team[1], team[2]),
        (own, team[0], caught, team[2]),
        (own, team[0], team[1], caught),
    )
    scores = [
        weighted_score(
            evaluate_average_matchup(first, potential, rest, sw.game.lives),
            rental_weight,
            evaluate_matchup(first, boss, rest, sw.game.lives),
            boss_weight,
        )
        for first, *rest in potential_teams
    ]
    take_score = scores[0]
    leave_score = 0.125 * scores[1] + 0.875 * sum(scores[2:]) / 3
    logging.info(f"换成 {caught_name} 的分数 {take_score:.2f}，不换 {leave_score:.2f}")
    return take_score > leave_score


def _apply_swap(sw: Switch, caught_name: str, take: bool) -> None:
    """选换或不换，等画面变黑。队伍在 path 里重新读。"""
    own_name = sw.game.team[0][0]

    logging.info(f"决定{'换成 ' + caught_name if take else '不换，继续用 ' + own_name}")
    # 换按 A，不换按 B，一直按到画面变黑
    act_until(
        sw,
        lambda: sw.click("A" if take else "B", 0),
        lambda screen: screen.is_black(),
        "换不换之后的黑屏",
    )
