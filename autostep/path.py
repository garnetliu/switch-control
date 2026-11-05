from dataclasses import replace
from functools import cache

import cv2
import numpy as np

from config.layout import (
    BACKPACKER_ITEM_RECTS,
    BACKPACKER_RECT,
    BATTLE_SYMBOL_RECT,
    DEN_TEXT_RECT,
    PATH_MAP_RECT,
)
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, TICK_SECONDS
from lib import data, run, switch
from lib.dialog import advance_until
from lib.log import log
from lib.read import read_team
from lib.scoring import evaluate_matchup, weighted_score
from lib.wait import wait_for
from tool.check_image import ImageChecker
from tool.image import find_templates

# 文字框里的提示语。选路线和研究员的已经在游戏里实测过；树果的是按常见译法写的，待实测
FORK_TEXT = "要走哪条路"
SCIENTIST_TEXT = "交换成别的租用宝可梦"
BERRY_TEXT = "树果"


def path() -> str:
    """在冒险的路上一直看画面，看到什么就交给对应的处理函数，处理完接着看，
    直到出现可以选择招式的战斗菜单。

    会遇到的：岔路口选路线、研究员、背包客、树果。
    使用全局连接，需要先调用 switch.connect。返回下一步的名字 "battle"。
    """
    handlers = {
        "fork": _choose_fork,
        "scientist": _meet_scientist,
        "backpacker": _meet_backpacker,
        "berry": _take_berry,
    }
    while True:
        image = wait_for(lambda screen: _den_state(screen) is not None, LOAD_TIMEOUT, "下一个界面")
        state = _den_state(image)
        if state == "battle":
            log("出现了战斗菜单")
            return "battle"
        log(f"遇到了: {state}")
        handlers[state](image)


def _choose_fork(image: ImageChecker) -> None:
    """岔路口：把光标移到目标路线的下一个节点上并确认，等选路线的提示消失。

    光标是选中的节点标签下方的白色箭头。光标从最左边的路开始，每往右推一下，
    就等箭头出现在更靠右的节点下面，才算移过去了。读路线时镜头滚到了上面几层，
    这时直接推左摇杆，镜头会自己回到岔路口（真机实测），不用先往回滚。
    """
    current = run.get()
    offset = current.next_fork_offset()
    x = _fork_cursor_x(image)
    for _ in range(offset):
        switch.get().stick("LEFT", switch.STICK_MAX, 0, TICK_SECONDS)
        screen = wait_for(
            lambda screen, before=x: _fork_cursor_moved_right(screen, before),
            DEFAULT_TIMEOUT,
            "选路线的光标移到右边那条路",
        )
        x = _fork_cursor_x(screen)
    switch.get().click("A", 0)
    # 提示消失才算选好了，否则会把还没消失的提示当成又到了岔路口
    wait_for(lambda screen: not _text_shown(screen, FORK_TEXT), DEFAULT_TIMEOUT, "选路线的提示消失")
    current.advance()
    log(f"选了从左数第 {offset + 1} 条路，走向 {current.current_node}")


def _meet_scientist(image: ImageChecker) -> None:
    """研究员：问要不要换一只租借宝可梦。照搬上游的判断：
    「随便换一只」的平均分比现在这只的分数高就换，否则不换。

    换了的话，读队伍栏认出换来的是哪只。keep path 时上一局在这个节点换来过，就直接沿用，不读。
    """
    current = run.get()
    # 还剩几个对手要打决定权重：每抓到一只少一个，最后的首领更难，权重更大
    rental_weight, boss_weight = 3 - current.num_caught, 2

    rental_scores, boss_matchups = data.rental_scores(), data.boss_matchups()
    scores = [
        weighted_score(
            rental_scores[name_id], rental_weight, boss_matchups[name_id][current.boss], boss_weight
        )
        for name_id in data.rental_pokemon()
    ]
    average = sum(scores) / len(scores)
    own = current.pokemon
    assert own is not None
    boss = data.boss_pokemon()[current.boss]
    existing = weighted_score(
        rental_scores[own.name_id],
        rental_weight,
        evaluate_matchup(own, boss, current.team, current.lives),
        boss_weight,
    )
    take = average > existing
    log(f"研究员：随便换一只的平均分 {average:.2f}，{own.name_id} 的分数 {existing:.2f}")

    # 照搬上游：问「你希望交换成别的租用宝可梦吗？」这一页上直接按，A 换、B 不换
    advance_until(lambda screen: _text_shown(screen, SCIENTIST_TEXT), "研究员问换不换")
    switch.get().click("A" if take else "B", 0)
    wait_for(
        lambda screen: not _text_shown(screen, SCIENTIST_TEXT), DEFAULT_TIMEOUT, "研究员的对话结束"
    )
    if not take:
        log(f"不换，继续用 {own.name_id}")
        return

    planned = (current.plan or {}).get("scientist", {}).get(str(current.current_index))
    if planned is not None:
        current.pokemon = replace(data.rental_pokemon()[planned], hp=1.0)
        log(f"换了，沿用上一局在这里换来的 {planned}")
    else:
        # 换来的是哪只要看队伍栏，读之前先清掉旧的，免得报「和之前选的不一致」
        current.pokemon = None
        wait_for(read_team, DEFAULT_TIMEOUT, "换来的宝可梦出现在队伍栏")
        assert current.pokemon is not None
        log(f"换了，换来的是 {current.pokemon.name_id}")
    current.scientist[current.current_index] = current.pokemon.name_id


def _meet_backpacker(image: ImageChecker) -> None:
    """背包客：照搬上游，读出道具（只记日志），直接拿默认选中的那个，等道具面板消失。

    keep path 时不读道具。
    """
    if run.get().plan is None:
        items = [image.read_text(rect).strip() for rect in BACKPACKER_ITEM_RECTS]
        log(f"背包客的道具: {items}")
    switch.get().click("A", 0)
    wait_for(lambda screen: not _backpacker_shown(screen), DEFAULT_TIMEOUT, "背包客的道具面板消失")


def _take_berry(image: ImageChecker) -> None:
    """树果：按 A 一页页推进对话，直到文字框里不再有树果的对话。

    待实测：游戏里是不是要按键还不确定。
    """
    advance_until(
        lambda screen: not _text_shown(screen, BERRY_TEXT), "树果的对话结束", max_presses=5
    )


def _den_state(screen: ImageChecker) -> str | None:
    """认出路上现在是什么界面，认不出返回 None。

    battle 可以选择招式的战斗菜单、backpacker 背包客、scientist 研究员、berry 树果、fork 岔路口。
    """
    # 「战斗」图标的匹配度至少是这么多
    min_fight_score = 0.85

    if screen.match_template(BATTLE_SYMBOL_RECT, data.misc_icons()["fight"]) >= min_fight_score:
        return "battle"
    if _backpacker_shown(screen):
        return "backpacker"
    for state, text in (("scientist", SCIENTIST_TEXT), ("berry", BERRY_TEXT), ("fork", FORK_TEXT)):
        if _text_shown(screen, text):
            return state
    return None


def _fork_cursor_x(screen: ImageChecker) -> int | None:
    """岔路口光标（白色箭头）在画面上的横坐标（像素），找不到返回 None。

    箭头在左边的路上开口朝右下，在右边的路上开口朝左下，形状也不完全对称（真机截图），
    两个模板都找，取匹配度高的。
    镜头往上滚开、或者已经选完路时箭头不在画面上。
    """
    # 箭头的匹配度至少是这么多。真机上找到时在 0.97 以上
    min_score = 0.85
    hits = [
        hit
        for template in _fork_cursor_icons()
        for hit in find_templates(
            screen, PATH_MAP_RECT, template, min_score, (0, 0, 220), (180, 40, 255)
        )
    ]
    return max(hits)[1][0] if hits else None


def _fork_cursor_moved_right(screen: ImageChecker, before: int | None) -> bool:
    """光标移到了右边那条路：箭头在画面上，并且比 before 靠右至少 100 像素。

    箭头会上下左右跳十几个像素，相邻两条路在画面上相差几百像素。before 为 None
    （之前看不到箭头）时，只要看到箭头就算。
    """
    x = _fork_cursor_x(screen)
    return x is not None and (before is None or x > before + 100)


@cache
def _fork_cursor_icons() -> tuple[np.ndarray, ...]:
    """岔路口光标的两个模板，按白色二值化过的单通道图：左边路上的 data/misc_icons/fork_cursor.png、
    右边路上的 fork_cursor_right.png，都截自真机。
    """
    icons = data.misc_icons()
    return tuple(
        cv2.cvtColor(icons[name], cv2.COLOR_BGR2GRAY)
        for name in ("fork_cursor", "fork_cursor_right")
    )


def _backpacker_shown(screen: ImageChecker) -> bool:
    """背包客的蓝色道具面板正显示着：蓝色像素占比超过上游的阈值（0 到 255 的均值 > 240）。"""
    return screen.color_ratio(BACKPACKER_RECT, (80, 230, 230), (120, 255, 255)) > 240 / 255


def _text_shown(screen: ImageChecker, text: str) -> bool:
    """画面下方的文字框里能认出 text。

    不看文字框的底色：岔路提示「要走哪条路？」是深色底的（真机截图），上游按白底判断会认不出。
    """
    return screen.has_text(DEN_TEXT_RECT, text)
