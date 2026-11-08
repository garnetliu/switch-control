import time
from collections.abc import Iterable
from dataclasses import replace

from config.game import BOSS
from config.layout import (
    DEN_TEXT_RECT,
    LABEL_ICON_LOWER,
    LABEL_ICON_SCORE,
    LABEL_ICON_UPPER,
    LOBBY_MENU_RECT,
    PATH_RECTS,
    POPUP_RECT,
    ROW_MAX_SPREAD,
    STARTER_PANEL_RECTS,
)
from config.timing import LOAD_TIMEOUT
from lib import data, lair, run, switch
from lib.dialog import menu_last_item, press_until
from lib.game_state import GameState
from lib.log import log
from lib.run import FIRST_ROW, SECOND_ROW, THIRD_ROW
from lib.scoring import weighted_score
from lib.wait import capture, wait_for
from tool import pk8
from tool.check_image import BASE_SIZE, ImageChecker
from tool.image import locate_template, text_lines
from tool.text import levenshtein, pad
from type.image import Rect
from type.path import TypeMatch

RENTAL_CANDIDATE_ADDRESSES = (0x83E93070, 0x83E93300, 0x83E93590)


def join(game: GameState) -> str:
    """开一局极巨大冒险：选目标传说、选初始宝可梦、选路线。

    开始时游戏要停在科学家面前、没有对话框，见 initialize。
    使用全局连接，需要先调用 switch.connect。
    要找的传说见 config/game.py 的 BOSS；菜单里没有它时选菜单第一项，见 _select_target。
    会用 run.start 开新的一局，读到的信息都记在这一局里。
    返回下一步的名字 "path"，在岔路口移动光标、走上目标路线是 path 的事。

    做完后把这一局写进状态文件（见 lib/run.py）。租借候选从内存读取；keep path 时，
    候选和上一局一致且上一局已保存完整候选池，才沿用上一局的选择、队伍和路线。
    """
    state = run.load()
    boss = _select_target()
    keep = (
        state is not None
        and state["keep_path"]
        and state["boss"] == boss
        and state["selection"] is not None
        and state["target_path"]
    )
    run.start(boss, state if keep else None)
    if keep:
        log("keep path：沿用上一局的结果，只核对选初始和选路线时的画面")
    _select_starter()
    _select_path()
    run.get().record_start()
    run.save()
    return "path"


def _select_target() -> str:
    """从科学家面前开始对话，在传说菜单里选中 BOSS 并确认，一直到进入选初始宝可梦的界面。

    initialize 已经处理过中途退出的罚款和提醒，并关掉了对话框；这里按 A 重新开始对话：
    开场白 →「现在就出发 / 我想听讲解 / 还是先算了」→ 选「现在就出发」→
    「看来您手边有宝可梦所在位置的记录呢」→「请问您要去找哪个宝可梦呢」→ 传说菜单。
    返回选的是哪只神兽（name_id）。

    BOSS 不在菜单里（刷到闪光带走之后那只就不在列表里了，或者存档改过）时，改成选菜单的第一项，
    这一局就刷它；菜单里全是「不指定」时抛 RuntimeError。
    """
    # 一直按 A，直到传说菜单弹出来（菜单最后一行是「不指定」）。开场白会重新出现，
    # 连同菜单上默认选中的「现在就出发」一起用 A 过掉
    image = press_until(lambda screen: menu_last_item(screen) == "不指定", "传说菜单")
    bosses = data.boss_pokemon()
    wanted = bosses[BOSS].name()
    try:
        _select_menu_item(image, POPUP_RECT, wanted, "选择传说Boss")
        boss = BOSS
    except RuntimeError:
        boss = _select_first_item(image, "选择传说Boss")
        log(f"传说菜单里没有「{wanted}」，这一局改成刷「{bosses[boss].name()}」", "WARNING")
    # 选好传说之后：「要保存目前为止的冒险记录吗？」→「是 / 否」→ 选「是」保存。
    # 一直按 A 到画面变黑（保存中）就停，参考 lib/game.py 的 _enter_game
    press_until(lambda screen: screen.is_black(), "保存时画面变黑")
    # 保存要几秒。大厅里选「发起单人挑战！」，队友由电脑来当
    solo = "发起单人挑战！"
    image = wait_for(
        lambda screen: solo in [text for text, _ in text_lines(screen, LOBBY_MENU_RECT)],
        LOAD_TIMEOUT,
        "极巨大冒险的大厅",
    )
    _select_menu_item(image, LOBBY_MENU_RECT, solo, "大厅菜单")
    switch.get().click("A", 0)
    return boss


def _select_starter() -> None:
    """从内存读取三只租借宝可梦，选择得分最高的。

    屏幕只用来看光标停在哪只上；宝可梦信息都从内存读取。队友等第一场战斗再读（见 battle._read_team），
    选初始界面读不到队伍地址。
    """
    # 不能用面板高亮判断界面是否出来：刚切出来时面板还在淡入，选中位置会看错
    wait_for(
        lambda screen: screen.has_text(((0.015, 0.068), (0.14, 0.122)), "按顺序选择"),
        LOAD_TIMEOUT,
        "选宝可梦的界面",
    )

    current = run.get()
    seed = _read_seed()

    if seed == current.seed:
        _reuse_starter()
    else:
        if current.plan is not None:
            log("seed 和上一局不一致，不再沿用上一局，照常计算", "WARNING")
            current.plan = None
            current.keep_path = False
        _assign_new_starter(seed)

    selection = current.selection
    assert selection is not None
    _move_starter_cursor(selection)
    switch.get().click("A", 0)


def _read_seed() -> int:
    """读这一局的冒险 seed。"""
    seed_raw = switch.get().peek(lair.SEED_ADDRESS, 8)
    if len(seed_raw) != 8:
        raise RuntimeError(f"路线 seed 读取长度错误：{len(seed_raw)}")
    return int.from_bytes(seed_raw, "little")


def _reuse_starter() -> None:
    """seed 和 boss 都和上一局一样，只打日志，沿用上一局的选择和队伍。"""
    current = run.get()
    plan = current.plan
    assert plan is not None
    seed = current.seed
    assert seed is not None
    current.candidates = plan["candidates"]
    current.selection = plan["selection"]
    current.restore_team(plan, full_hp=True)
    assert current.pokemon is not None
    log(
        f"沿用上一局的 seed {seed:016X} 和 boss {current.boss}，"
        f"选第 {current.selection + 1} 个：{current.pokemon.name_id}"
    )


def _assign_new_starter(seed: int) -> None:
    """seed 不一样时重新算：把 6 只候选写进这一局，读当前三只，算分选一只。"""
    current = run.get()
    current.seed = seed
    current.rental_pool = lair.rental_candidates(seed)
    current.encountered.update(current.rental_pool)
    log(f"seed {seed:016X} 对应的租借候选：{current.rental_pool}")

    # 选宝可梦的界面刚出来时，候选记录可能还没写进内存（真机上碰到过一次校验失败），过一会儿重读
    for attempt in range(6):
        records = pk8.read(RENTAL_CANDIDATE_ADDRESSES, data.rental_pokemon().values())
        if all(candidate is not None for _, _, candidate in records):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("租借候选内存记录校验失败，未选择宝可梦")
    candidates = [candidate for _, _, candidate in records if candidate is not None]
    for candidate in candidates:
        log(f"内存读取候选：{candidate.name_id}")
    # seed 读错时算出来的候选和画面上不是同一组，之后路线图的属性也和 seed 对不上（读不出层），
    # 提前停下，别进到冒险里再崩
    expected = current.rental_pool[:3]
    if [candidate.name_id for candidate in candidates] != expected:
        raise RuntimeError(
            f"seed {seed:016X} 算出来的候选是 {expected}，"
            f"和内存读到的 {[candidate.name_id for candidate in candidates]} 对不上"
        )

    # 开始时还剩 3 个对手要打、最后还有 1 个首领。首领更难，权重更大
    scores = []
    for candidate in candidates:
        score = weighted_score(
            data.rental_scores()[candidate.name_id],
            3,
            data.boss_matchups()[candidate.name_id][current.boss],
            2,
        )
        log(f"{candidate.name_id} 的得分 {score:.2f}", "DEBUG")
        scores.append(score)
    selection = scores.index(max(scores))

    current.candidates = [candidate.name_id for candidate in candidates]
    current.selection = selection
    current.pokemon = replace(candidates[selection], hp=1.0)
    log(f"选了第 {selection + 1} 个：{current.pokemon.name_id}")


def _select_path() -> None:
    """等路线图出现，读出整张路线图，给每条路线打分，把分数最高的记为这一局的目标路线。

    只决定走哪条，真正在岔路口移动光标是下一步 path 的事。
    """
    current = run.get()
    # _select_starter 已经比较过 seed 和 boss：一样时 plan 还在，不一样时已经清掉
    if current.plan is not None:
        _reuse_path()
    else:
        _assign_new_path()


def _reuse_path() -> None:
    """seed 和 boss 都和上一局一样，直接沿用上一局的路线，不读地图、不算分。"""
    current = run.get()
    plan = current.plan
    assert plan is not None
    seed = current.seed
    assert seed is not None
    current.path_opponents = {
        int(row): names for row, names in plan.get("path_opponents", {}).items()
    }
    if not current.path_opponents:
        current.path_opponents = lair.encounter_rows_by_layer(seed)
    current.restore_paths(plan)
    log(f"沿用上一局的路线（{current.path_type}），seed {seed:016X}")


def _assign_new_path() -> None:
    """seed 不一样时：看队友选择，按 seed 算遭遇，读整张路线图并选一条。"""
    current = run.get()
    seed = current.seed
    assert seed is not None
    current.path_opponents = lair.encounter_rows_by_layer(seed)
    log(f"从 seed {seed:016X} 读取路线遭遇：{current.path_opponents}")
    image, pan_rows = _watch_intro_pan(60)
    first_row = [_identify_type(image, rect) for rect in PATH_RECTS[FIRST_ROW]]
    current.update_paths(FIRST_ROW, first_row)
    second = pan_rows.get(SECOND_ROW)
    third = pan_rows.get(THIRD_ROW)
    if second is not None:
        current.update_paths(SECOND_ROW, second)
    if second is not None and third is not None:
        current.update_paths(THIRD_ROW, third)
        log("开场镜头往上移的时候已经读到第 2、3 层，不用再推摇杆")
    else:
        log(f"开场镜头往上移的时候只读到 {len(pan_rows)} 层，推摇杆补读", "WARNING")
        need = [row for row in (SECOND_ROW, THIRD_ROW) if pan_rows.get(row) is None]
        previous = first_row
        if SECOND_ROW not in need:
            # 第 2 层已经读到，从它往上补第 3 层
            previous = second
        _scroll_rows(previous, need)
        if third is not None:
            # 第 3 层是开场镜头读到的，等第 2 层补读完再记（记第 3 层要先知道路线形状）
            current.update_paths(THIRD_ROW, third)
    _choose_target_path()


def _scroll_rows(previous: list[TypeMatch], rows: list[int]) -> None:
    """推右摇杆读还缺的那几层，记到这一局里。开场镜头往上移时没读全才用。

    一直按住往上推，这一层 4 列的标签都认出属性、并且和上一层不一样就松开。
    认出来的属性还要和 seed 里这一层遇到的宝可梦对得上：上下两层的属性可以完全一样，
    只看「和上一层不同」会把同一层再认一遍。
    """
    # 推着等一层最多几秒
    row_timeout = 10.0
    current = run.get()
    for row in rows:
        allowed = _allowed_types(row)
        found: dict[str, list[TypeMatch]] = {}
        switch.get().press_stick("RIGHT", 0, switch.STICK_MAX)
        try:
            wait_for(
                lambda screen, row=row, previous=previous, found=found, allowed=allowed: _row_ready(
                    screen, row, previous, found, allowed
                ),
                row_timeout,
                f"路线图滚到第 {row} 层",
            )
        finally:
            switch.get().release_stick("RIGHT")
        current.update_paths(row, found["matches"])
        previous = found["matches"]


def _choose_target_path() -> None:
    """用 seed 对应的具体遭遇宝可梦对首领的相性分给路线评分。"""
    current = run.get()
    if [len(current.path_opponents.get(row, [])) for row in (FIRST_ROW, SECOND_ROW, THIRD_ROW)] != [
        2,
        4,
        4,
    ]:
        raise RuntimeError("路线图没有完整的 seed 遭遇宝可梦数据")
    log(f"路线形状: {current.path_type}")
    for line in _path_diagram():
        log(line)

    # 每个节点按 seed 对应的具体遭遇宝可梦评分，不再使用属性组平均分。
    # 越靠后的节点权重越大，每往后一个多加 weight_step。
    weight_step = 0.1
    matchup_scores = data.boss_matchups()
    paths = current.paths(truncate=True)
    path_scores = []
    for path in paths:
        path_score = 0.0
        for index, node in enumerate(path):
            opponent = current.path_opponents[node.row][node.col]
            score = matchup_scores[opponent][current.boss]
            path_score += (1.0 + index * weight_step) * score
        path_scores.append(path_score)
    best = path_scores.index(max(path_scores))
    for index, (path, score) in enumerate(zip(paths, path_scores)):
        route_name = [node.name for node in path]
        pokemon_names = [current.path_opponents[node.row][node.col] for node in path]
        log(
            f"路线 {index}: {_route_name(route_name)}（{' → '.join(pokemon_names)}），得分 {score:.3f}",
            "DEBUG",
        )
    current.target_path = current.paths()[best]
    current.path_score = path_scores[best]
    selected = paths[best]
    selected_pokemon = [current.path_opponents[node.row][node.col] for node in selected]
    log(f"选了路线 {best}：{' → '.join(selected_pokemon)}，得分 {path_scores[best]:.3f}")


def _select_menu_item(image: ImageChecker, area: Rect, target: str, what: str) -> None:
    """在 area 里的菜单上把光标移到 target 那一项：当前选中的不是它就往下移一格，直到选中。

    image: 菜单出现后的截图。what: 是什么菜单，写进日志和报错。
    每移一格都等高亮真的移到了别的项上再判断。菜单旁的光标一直在跳，不能用「等画面稳定」。
    菜单项读不到、或者每一项都试过还是没找到，抛 RuntimeError。
    """
    lines = text_lines(image, area)
    if not lines:
        raise RuntimeError(f"{what}里读不到任何选项")
    texts, rects = [text for text, _ in lines], [rect for _, rect in lines]
    # 菜单有几项就最多移几次，移满一圈还没选中说明菜单里没有它
    for _ in range(len(lines)):
        selected = image.selected(rects)
        # 直接比较已经读出的文字，编辑距离不超过 target 长度的三分之一就算是它。
        # 不能对单独一行的区域再识别一次：区域贴着文字，边缘的字容易认错
        if selected >= 0 and levenshtein(texts[selected], target) <= len(target) / 3:
            log(f"{what}选中了「{texts[selected]}」")
            return
        image = press_until(
            lambda screen, before=selected: screen.selected(rects) not in (before, -1),
            f"{what}的光标移到下一项",
            button="DDOWN",
        )
    raise RuntimeError(f"{what}里找不到「{target}」，读到的选项: {texts}")


def _select_first_item(image: ImageChecker, what: str) -> str:
    """菜单里没有 BOSS 时选菜单的第一项，返回它的 name_id。

    先按 DUP 把光标移到最上面那一项，再从上往下找第一项能认出来的神兽（「不指定」不算）。
    认是哪只和 _select_menu_item 一样按名字的编辑距离判断。
    """
    bosses = data.boss_pokemon()
    for _ in range(10):
        lines = text_lines(image, POPUP_RECT)
        if not lines:
            raise RuntimeError(f"{what}里读不到任何选项")
        rects = [rect for _, rect in lines]
        selected = image.selected(rects)
        if selected == 0:
            break
        if selected < 0:
            raise RuntimeError(f"{what}里认不出光标在哪一项上")
        image = press_until(
            lambda screen, before=selected, rects=rects: screen.selected(rects) not in (before, -1),
            f"{what}的光标移到上一项",
            button="DUP",
        )
    texts = [text for text, _ in text_lines(image, POPUP_RECT)]
    for text in texts:
        name = min(bosses, key=lambda name_id: levenshtein(bosses[name_id].name(), text))
        if levenshtein(bosses[name].name(), text) <= len(bosses[name].name()) / 3:
            return name
    raise RuntimeError(f"{what}里的选项一个都认不出是哪个神兽: {texts}")


def _move_starter_cursor(target: int) -> None:
    """把选宝可梦界面的光标移到第 target 只上：不是它就往下移一格，等黑底真的移到下一只上再判断。

    光标旁的「>」一直在跳，不能用「等画面稳定」（真机上等了 10 秒，倒计时到了，游戏自己选了）。
    认不出光标在哪只上抛 RuntimeError。
    """
    rects = list(STARTER_PANEL_RECTS)
    selected = capture().selected(rects)
    for _ in range(len(rects)):
        if selected == target:
            return
        if selected < 0:
            raise RuntimeError("选宝可梦的界面上认不出光标在哪只上")
        image = press_until(
            lambda screen, before=selected: screen.selected(rects) not in (before, -1),
            "选宝可梦的光标移到下一只",
            button="DDOWN",
        )
        selected = image.selected(rects)
    if selected != target:
        raise RuntimeError(f"选宝可梦的光标移了 {len(rects)} 次，还是没到第 {target} 只上")


def _map_shown(screen: ImageChecker) -> bool:
    """路线图已经出现、可以操作了：出现了岔路提示「要走哪条路」，并且第 1 层的两个标签都认出了属性。

    只看标签不够：路线图刚出来时镜头会从远处移回起点，经过时第 1 层的标签也会落在区域里，
    这时推摇杆不起作用（真机上因此读错过）。岔路提示是镜头停在起点之后才出现的。
    """
    return screen.has_text(DEN_TEXT_RECT, "要走哪条路") and all(
        _identify_type(screen, rect).score >= LABEL_ICON_SCORE for rect in PATH_RECTS[FIRST_ROW]
    )


def _watch_intro_pan(timeout: float) -> tuple[ImageChecker, dict[int, list[TypeMatch]]]:
    """从选完宝可梦开始一直截图，直到路线图回到底部、出现「要走哪条路？」，返回那时的截图和
    开场镜头移动时读到的标签（按层存，没读到的层没有 key）。

    冒险开场时镜头会自己上下移动，第 2、3 层的标签会经过 PATH_RECTS 里的检测框：
    4 个都认出属性、是同一层、并且能和 seed 里这一层遇到的宝可梦对上，就记成这一层。
    用 seed 判断是哪一层，不按先后顺序：镜头有时会先经过第 3 层。
    """
    rows: dict[int, list[TypeMatch]] = {}
    deadline = time.monotonic() + timeout
    while True:
        image = capture()
        if _map_shown(image):
            return image, rows
        matches = [_identify_type(image, rect) for rect in PATH_RECTS[SECOND_ROW]]
        types = [match.type_id if match.score >= LABEL_ICON_SCORE else "-" for match in matches]
        if "-" not in types and _same_row(matches):
            row = _match_row(matches)
            if row is not None and row not in rows:
                rows[row] = matches
                log(f"开场镜头往上移，读到第 {row} 层: {types}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，路线图一直没有出现")


def _match_row(matches: list[TypeMatch]) -> int | None:
    """认出来的一排标签属于哪一层：和 seed 里第 2、3 层遇到的宝可梦对得上就是哪一层。

    按 seed 判断，不按镜头先后：镜头有时会先经过第 3 层。两层都对得上（属性集合重叠）时返回 None。
    """
    matched = []
    for row in (SECOND_ROW, THIRD_ROW):
        allowed = _allowed_types(row)
        if allowed is not None and all(
            match.type_id in allowed[index] for index, match in enumerate(matches)
        ):
            matched.append(row)
    return matched[0] if len(matched) == 1 else None


def _allowed_types(row: int) -> list[set[str]] | None:
    """这一层每一列的节点可能是哪些属性：seed 里这一层遇到的宝可梦的属性。

    读路线图时用来核对认出来的标签，防止把上下两层读重（两层的属性可能完全一样）。
    数据不全时返回 None，不做核对。
    """
    current = run.get()
    names = current.path_opponents.get(row, [])
    rentals = data.rental_pokemon()
    if len(names) != 4 or any(name not in rentals for name in names):
        return None
    return [set(rentals[name].type_ids) for name in names]


def _row_ready(
    screen: ImageChecker,
    row: int,
    previous: list[TypeMatch],
    found: dict[str, list[TypeMatch]],
    allowed: list[set[str]] | None = None,
) -> bool:
    """路线图滚到了第 row 层：这一层每个标签区域都认出了属性，并且和上一层读到的不一样。

    给了 allowed 时，认出来的属性还要在对应列的可能属性里。
    满足时把这一层读到的结果放进 found["matches"]。
    """
    matches = [
        _identify_type(
            screen,
            rect,
            allowed[index] if allowed is not None else None,
        )
        for index, rect in enumerate(PATH_RECTS[row])
    ]
    if any(match.score < LABEL_ICON_SCORE for match in matches) or not _same_row(matches):
        return False
    if allowed is not None and any(
        match.type_id not in allowed[index] for index, match in enumerate(matches)
    ):
        return False
    if [(m.type_id, m.location) for m in matches] == [(m.type_id, m.location) for m in previous]:
        return False
    found["matches"] = matches
    return True


def _same_row(matches: list[TypeMatch]) -> bool:
    """认出的几个标签高度相近，是同一层的：最高和最低差不超过 ROW_MAX_SPREAD。

    检测框从 0.30 到 0.92 那么高，镜头移动时一帧里可能一列是这一层、另一列是下一层。
    location 是图标在检测框里的像素位置，同一层的检测框上沿相同，可以直接比。
    """
    heights = [match.location[1] for match in matches]
    return max(heights) - min(heights) <= ROW_MAX_SPREAD * BASE_SIZE[1]


def _route_name(path: list[str]) -> str:
    """路线上各节点属性的中文名，用箭头连起来，例如「火 → 电 → 钢」。"""
    names = data.type_names()
    return " → ".join(names.get(type_id, type_id) for type_id in path)


def _path_diagram() -> list[str]:
    """把当前这一局的路线图画成 4 行，用来写日志，画法照搬上游。节点名用英文，首领用中文。"""
    current = run.get()
    # 每个节点占 8 列，不够的用横线补齐
    first, second, third = (
        [pad(node.name.replace("-", " ").title(), 8, "─") for node in current.rows[row]]
        for row in (FIRST_ROW, SECOND_ROW, THIRD_ROW)
    )
    # 第 1、2 层之间和第 2、3 层之间的连线，按路线形状不同
    links = {
        "2x3": (["┬──", "└┮═", "─┼─", " └─"], ["┐┌─", "┴┼─", "┐╞═", "┴┴─"]),
        "3x2": (["┬──", "└┬─", "┬┶═", "└──"], ["┬┬─", "┘╞═", "┬┼─", "┘└─"]),
        "2x2": (["┬──", "└──", "┬──", "└──"], ["─┬─", "┐╞═", "┼┼─", "┘└─"]),
    }
    first_links, second_links = links[current.path_type or "2x2"]
    boss = data.boss_pokemon()[current.boss].name()
    sections = (
        [f"      ┌{first[0]}", pad("Start", 5, "─") + "─┤        ", f"      └{first[1]}", " " * 15],
        first_links,
        second,
        second_links,
        [f"{third[0]}┐", f"{third[1]}┼─{boss}", f"{third[2]}┤", f"{third[3]}┘"],
    )
    return ["".join(section[line] for section in sections) for line in range(4)]


def _identify_type(
    image: ImageChecker, rect: Rect, types: Iterable[str] | None = None
) -> TypeMatch:
    """认出 rect 区域里节点图标的属性，返回匹配度最高的那个。

    types: 只在这些属性里找。给了的话每个属性只做一次模板匹配，快很多，也不容易认错成别的属性。
    """
    icons = data.type_icons()
    best = TypeMatch("", -1.0, (0, 0))
    for type_id in types if types is not None else icons:
        score, location = locate_template(
            image, rect, icons[type_id], LABEL_ICON_LOWER, LABEL_ICON_UPPER
        )
        if score > best.score:
            best = TypeMatch(type_id, score, location)
    return best
