import time
from collections.abc import Callable
from dataclasses import replace
from itertools import combinations

import numpy as np

from config.layout import (
    BACKPACKER_ITEM_RECTS,
    BACKPACKER_RECT,
    FORK_LABEL_RECT,
    LABEL_ICON_LOWER,
    LABEL_ICON_SCORE,
    LABEL_ICON_UPPER,
    PATH_TEXT_RECT,
)
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, POLL_INTERVAL, TICK_SECONDS
from lib import data, run, switch
from lib.dialog import advance_until
from lib.log import log
from lib.read import read_team
from lib.scoring import evaluate_matchup, weighted_score
from lib.wait import capture, wait_for
from tool.check_image import ImageChecker
from tool.image import find_templates, mask
from tool.text import contains
from type.image import Rect

# 文字框里的提示语。选路线、研究员、背包客的已经在游戏里实测过；树果的是按常见译法写的，待实测（游戏里有树果）
# 选路线的提示「要走哪条路？」
FORK_TEXT = "要走哪条路"
BACKPACKER_TEXT = "遇到了背包客"
# 进入战斗时画面下方黑框里的「×××出现了！」（真机截图）
BATTLE_START_TEXT = "出现了"
# 研究员：「遇到了研究员！」之后自己翻两页（「你们的同行宝可梦都没问题吗？」「你们可以和我交换一只
# 别的租用宝可梦」），然后问「你希望交换成别的租用宝可梦吗？」（真机实测）
SCIENTIST_TEXT = "遇到了研究员"
SCIENTIST_QUESTION = "希望交换成"
BERRY_TEXT = "树果"
# 岔路口光标的白色范围（HSV）
CURSOR_LOWER, CURSOR_UPPER = (0, 0, 220), (180, 40, 255)


def path() -> str:
    """在冒险的路上一直看画面，看到什么就交给对应的处理函数，处理完接着看，
    直到画面下方的黑框里出现「×××出现了！」，也就是进入了战斗。

    选路线之前和之后都可能遇到研究员、背包客、树果；去首领那一段没有岔路口。
    每一种在一段路上最多出现一次，所以处理完哪一种就不再认它：
    它的提示还留在画面上时，也不会被当成又遇到了一次。
    使用全局连接，需要先调用 switch.connect。返回下一步的名字 "battle"。
    """
    handlers = {
        "fork": _choose_fork,
        "scientist": _meet_scientist,
        "backpacker": _meet_backpacker,
        "berry": _take_berry,
    }
    states = ("battle", "backpacker", "scientist", "berry", "fork")
    while True:
        # 选完路线到「出现了」，真机上 16 秒到 30 多秒不等
        image = _watch(
            lambda screen, states=states: _den_state(screen, states) is not None, 60, "下一个界面"
        )
        state = _den_state(image, states)
        if state == "battle":
            log("进入战斗")
            return "battle"
        log(f"遇到了: {state}")
        handlers[state](image)
        states = tuple(other for other in states if other != state)


def _watch(condition: Callable[[ImageChecker], bool], timeout: float, what: str) -> ImageChecker:
    """不停截图直到 condition 满足，超时抛 TimeoutError。"""
    deadline = time.monotonic() + timeout
    while True:
        image = capture()
        if condition(image):
            return image
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，画面一直没有出现：{what}")
        time.sleep(POLL_INTERVAL)


def _choose_fork(image: ImageChecker) -> None:
    """岔路口：把光标移到目标路线的下一个节点上，按 A 确认。之后等战斗开始，见 path。

    光标是选中的那个属性标签正下方的白色箭头，箭头的角度会跟着路的方向变，所以不认箭头的形状，
    只看标签正下方那一块：光标移过来时，推之前没有白色、推之后有，白色像素几乎全变（真机上 100%），
    没操作时最多变 0.7%（雾不是白色）。
    先找出下一层的属性标签，从左到右就是这一层的第 0、1、2…列。读路线图时镜头停在了上面几层，
    这时看不到这些标签：按住右摇杆往下推，镜头会回到岔路口，再松开。
    """
    current = run.get()
    offset = current.next_fork_offset()
    target = current.current_node.downstream[offset]
    row_types = [node.name for node in current.rows[target.row]]
    labels = _fork_labels(image, row_types)
    if labels is None:
        # 镜头停在了上面几层，看不到下一层的标签：右摇杆往下推，把镜头带回岔路口。
        # 界面上右摇杆是上下移镜头，左摇杆是选路的，推左摇杆镜头不会动（真机上因此空等到超时）
        log("看不到下一层的属性标签，右摇杆往下推让镜头回到岔路口", "DEBUG")
        switch.get().press_stick("RIGHT", 0, -switch.STICK_MAX)
        found: dict[str, list[tuple[int, int]]] = {}
        try:
            wait_for(
                lambda screen: _store(found, _fork_labels(screen, row_types)),
                DEFAULT_TIMEOUT,
                "岔路口下一层的属性标签",
            )
        finally:
            switch.get().release_stick("RIGHT")
    # 光标和标签要用同一帧的位置：镜头移动时找到的标签位置会偏，拿偏掉的位置去找光标会一直找不到
    latest: dict[str, list[tuple[int, int]]] = {}

    def cursor_shown(screen: ImageChecker) -> bool:
        frame_labels = _fork_labels(screen, row_types)
        if frame_labels is None or _cursor_column(screen, frame_labels) is None:
            return False
        latest["labels"] = frame_labels
        return True

    screen = wait_for(cursor_shown, DEFAULT_TIMEOUT, "岔路口的光标")
    labels = latest["labels"]
    column = _cursor_column(screen, labels)
    assert column is not None
    log(f"光标在第 {column + 1} 列，目标是第 {target.col + 1} 列", "DEBUG")
    while column != target.col:
        step = 1 if target.col > column else -1
        below = _below_label(labels[column + step])
        before = mask(screen, below, CURSOR_LOWER, CURSOR_UPPER)
        switch.get().stick("LEFT", step * switch.STICK_MAX, 0, TICK_SECONDS)
        screen = wait_for(
            lambda screen, below=below, before=before: _cursor_arrived(screen, below, before),
            DEFAULT_TIMEOUT,
            f"光标移到第 {column + step + 1} 列的标签下面",
        )
        column += step
    switch.get().click("A", 0)
    current.advance()
    log(f"选了从左数第 {offset + 1} 条路，走向 {current.current_node}")


def _store(found: dict[str, list[tuple[int, int]]], labels: list[tuple[int, int]] | None) -> bool:
    """把找到的标签放进 found["labels"]，找到了返回 True。用作 wait_for 的条件。"""
    if labels is None:
        return False
    found["labels"] = labels
    return True


def _fork_labels(screen: ImageChecker, row_types: list[str]) -> list[tuple[int, int]] | None:
    """岔路口画面上下一层的属性标签，返回每个标签左边属性图标左上角的像素位置，从左到右；
    这一层的标签没有全部出现在画面上时返回 None。

    row_types: 这一层从左到右各节点的属性，读路线图时记下的。画面上可能还有别的层的标签，
    从找到的标签里挑出从左到右属性正好是 row_types、上下最集中的那几个。
    """
    (left, top), _ = FORK_LABEL_RECT
    width, height = 1920, 1080
    hits = [
        (score, x + round(left * width), y + round(top * height), type_id)
        for type_id in set(row_types)
        for score, (x, y) in find_templates(
            screen,
            FORK_LABEL_RECT,
            data.type_icons()[type_id],
            LABEL_ICON_SCORE,
            LABEL_ICON_LOWER,
            LABEL_ICON_UPPER,
        )
    ]
    # 同一个图标被几种属性都匹配上时，只留匹配度最高的
    labels: list[tuple[int, int, str]] = []
    for _, x, y, type_id in sorted(hits, reverse=True):
        if all(abs(x - lx) > 40 or abs(y - ly) > 40 for lx, ly, _ in labels):
            labels.append((x, y, type_id))
    candidates = [
        combo
        for combo in combinations(sorted(labels), len(row_types))
        if [type_id for _, _, type_id in combo] == row_types
    ]
    if not candidates:
        return None
    best = min(
        candidates, key=lambda combo: max(y for _, y, _ in combo) - min(y for _, y, _ in combo)
    )
    return [(x, y) for x, y, _ in best]


def _below_label(label: tuple[int, int]) -> Rect:
    """属性标签正下方光标会出现的那一块（比例坐标）。label 是标签左边属性图标左上角的像素位置。

    光标在图标下方约 60 到 180 像素、图标左右各一点的范围里（真机截图量的）。
    """
    x, y = label
    return ((max(x - 60, 0) / 1920, (y + 60) / 1080), (min(x + 160, 1920) / 1920, (y + 180) / 1080))


def _cursor_column(screen: ImageChecker, labels: list[tuple[int, int]]) -> int | None:
    """光标在第几列标签的下面：正好一个标签下面有白色时返回它的序号，否则返回 None。

    有光标的标签下面白色占 0.046 以上，没有的是 0（真机截图）。
    """
    shown = [
        screen.color_ratio(_below_label(label), CURSOR_LOWER, CURSOR_UPPER) > 0.02
        for label in labels
    ]
    return shown.index(True) if shown.count(True) == 1 else None


def _cursor_arrived(screen: ImageChecker, below: Rect, before: np.ndarray) -> bool:
    """光标移到了 below 这一块：现在有白色，并且白色像素和推之前比变了 60% 以上。"""
    after = mask(screen, below, CURSOR_LOWER, CURSOR_UPPER)
    union = (before | after).sum()
    return after.mean() > 0.02 and union > 0 and (before ^ after).sum() / union > 0.6


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

    # 前面的对话自己会翻页，不按键，等到问话出来；在问话上直接按，A 换、B 不换（照搬上游）。
    # 问话之前按 A 会翻页，在问话上按 A 就是换（真机上因此换错过）
    wait_for(lambda screen: _text_shown(screen, SCIENTIST_QUESTION), LOAD_TIMEOUT, "研究员问换不换")
    switch.get().click("A" if take else "B", 0)
    wait_for(
        lambda screen: not _text_shown(screen, SCIENTIST_QUESTION), DEFAULT_TIMEOUT, "问话消失"
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
    """背包客：等道具面板出来，照搬上游，读出道具（只记日志），直接拿默认选中的那个，等道具面板消失。

    keep path 时不读道具。
    """
    # 「遇到了背包客！」之后对话自己翻页，道具面板接着出来（真机实测）
    image = wait_for(_backpacker_shown, DEFAULT_TIMEOUT, "背包客的道具面板")
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


def _den_state(screen: ImageChecker, states: tuple[str, ...]) -> str | None:
    """认出路上现在是 states 里的哪种界面，都不是返回 None。

    battle 进入了战斗（黑框里「×××出现了！」）、backpacker 背包客、scientist 研究员、berry 树果、
    fork 岔路口。画面下方的文字只识别一次，再和各个关键词比：「出现了」只停 2 秒左右，
    每个关键词都重新识别一遍的话一帧要两三秒，会把它漏掉（真机上遇到过）。
    """
    keywords = {
        "battle": BATTLE_START_TEXT,
        "backpacker": BACKPACKER_TEXT,
        "scientist": SCIENTIST_TEXT,
        "berry": BERRY_TEXT,
        "fork": FORK_TEXT,
    }
    found = screen.read_text(PATH_TEXT_RECT)
    return next((state for state in states if contains(found, keywords[state])), None)


def _backpacker_shown(screen: ImageChecker) -> bool:
    """背包客的蓝色道具面板正显示着：蓝色像素占比超过上游的阈值（0 到 255 的均值 > 240）。"""
    return screen.color_ratio(BACKPACKER_RECT, (80, 230, 230), (120, 255, 255)) > 240 / 255


def _text_shown(screen: ImageChecker, text: str) -> bool:
    """画面下方的文字框里能认出 text。

    只读一行（见 PATH_TEXT_RECT）：研究员问话的关键词「希望交换成」在第一行。
    不看文字框的底色：岔路提示「要走哪条路？」是深色底的（真机截图），上游按白底判断会认不出。
    """
    return screen.has_text(PATH_TEXT_RECT, text)
