from config.game import BOSS
from config.layout import (
    ABILITY_RECTS,
    DEN_TEXT_RECT,
    DIALOG_RECT,
    LOBBY_MENU_RECT,
    MOVES_RECTS,
    NAME_RECTS,
    PATH_RECTS,
    POPUP_RECT,
    STARTER_PANEL_RECTS,
    STARTER_TEAM_NAME_RECTS,
    YES_NO_RECTS,
)
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, TICK_SECONDS
from lib import data, pokemon, run, switch
from lib.dialog import advance_until, menu_items, menu_selected
from lib.log import log
from lib.read import read_team
from lib.run import FIRST_ROW, SECOND_ROW, THIRD_ROW
from lib.scientist import open_start_dialog
from lib.scoring import weighted_score
from lib.wait import capture, wait_for
from tool.check_image import ImageChecker
from tool.image import locate_template, text_lines
from tool.text import levenshtein, pad
from type.image import Hsv, Rect
from type.path import TypeMatch

# 路线图上的属性图标是白色的，先按这个颜色范围转成黑白图，再和二值化的图标模板匹配
ICON_LOWER: Hsv = (0, 0, 200)
ICON_UPPER: Hsv = (180, 50, 255)
# 标签区域里认出属性图标的匹配度至少是这么多。真机上认对的都在 0.90 以上，
# 区域里没有这一层的标签时在 0.24 以下
MIN_LABEL_SCORE = 0.85


def join() -> str:
    """开一局极巨大冒险：选目标传说、选初始宝可梦、选路线。

    开始时游戏要停在科学家面前、没有对话框，见 initialize。
    使用全局连接，需要先调用 switch.connect。
    要找的传说见 config/game.py 的 BOSS。
    会用 run.start 开新的一局，读到的信息都记在这一局里。
    返回下一步的名字 "path"，在岔路口移动光标、走上目标路线是 path 的事。

    做完后把这一局写进状态文件（见 lib/run.py）。上一局标了 keep path 时，
    这一局只在选初始、选路线时核对画面和上一局一致，一致就直接沿用上一局的选择、队伍和路线，
    不再读、不再算；不一致就照常读和算。
    """
    state = run.load()
    keep = (
        state is not None
        and state["keep_path"]
        and state["boss"] == BOSS
        and state["selection"] is not None
        and state["target_path"]
    )
    run.start(BOSS, state if keep else None)
    if keep:
        log("keep path：沿用上一局的结果，只核对选初始和选路线时的画面")
    _select_target()
    _select_starter()
    _select_path()
    run.get().record_start()
    run.save()
    return "path"


def _select_target() -> None:
    """从科学家面前开始对话，在传说菜单里选中 BOSS 并确认，一直到进入选初始宝可梦的界面。

    对话顺序（真机实测）：开场白 →「现在就出发 / 我想听讲解 / 还是先算了」→ 选「现在就出发」
    →「看来您手边有宝可梦所在位置的记录呢」→「请问您要去找哪个宝可梦呢」→ 传说菜单。
    有中途退出的罚款时，开场白之前先付罚款，见 lib/scientist.py。
    """
    go = "现在就出发"
    open_start_dialog()
    image = advance_until(lambda screen: go in menu_items(screen), f"「{go}」的菜单")
    if menu_selected(image) != menu_items(image).index(go):
        raise RuntimeError(f"菜单上光标不在「{go}」上")
    switch.get().click("A", 0)
    # 菜单消失才算选好了，否则下面会在还没消失的菜单上再按一次 A
    wait_for(lambda screen: go not in menu_items(screen), DEFAULT_TIMEOUT, f"「{go}」的菜单消失")
    # 菜单里能认出最后一项「不指定」，就是传说菜单弹出来了
    image = advance_until(lambda screen: menu_items(screen)[-1:] == ["不指定"], "传说菜单")
    _select_menu_item(image, POPUP_RECT, data.boss_pokemon()[BOSS].name(), "传说菜单")
    switch.get().click("A", 0)
    # 选好传说之后：「要保存目前为止的冒险记录吗？」→「是 / 否」→ 选「是」保存 → 极巨大冒险的大厅
    wait_for(
        lambda screen: screen.has_text(DIALOG_RECT, "要保存目前为止的冒险记录"),
        DEFAULT_TIMEOUT,
        "要不要保存的提示",
    )
    image = advance_until(lambda screen: screen.selected(list(YES_NO_RECTS)) >= 0, "保存的是 / 否")
    if image.selected(list(YES_NO_RECTS)) != 0:
        raise RuntimeError("要不要保存的菜单上光标不在「是」上")
    switch.get().click("A", 0)
    # 保存要几秒。大厅里选「发起单人挑战！」，队友由电脑来当
    solo = "发起单人挑战！"
    image = wait_for(
        lambda screen: solo in [text for text, _ in text_lines(screen, LOBBY_MENU_RECT)],
        LOAD_TIMEOUT,
        "极巨大冒险的大厅",
    )
    _select_menu_item(image, LOBBY_MENU_RECT, solo, "大厅菜单")
    switch.get().click("A", 0)


def _select_starter() -> None:
    """读出三只可选的租借宝可梦，选综合得分最高的那只并确认，再等队友都选好，读出队伍。

    keep path 时只读三只的名字和上一局核对：一致就直接选上一局选的那只、沿用上一局的队伍，
    不读特性和招式、不打分、不读队伍；不一致就照常读、照常算。
    """
    # 开始时还剩 3 个对手要打、最后还有 1 个首领。首领更难，权重更大
    rental_weight, boss_weight = 3, 2
    # 我确认之后等三个队友都选好，最多等几秒。待实测
    team_timeout = 30.0

    current = run.get()
    # 三只的名字区域都能读出文字，就是选宝可梦的界面出来了。待实测
    image = wait_for(lambda screen: all(_read_names(screen)), LOAD_TIMEOUT, "选宝可梦的界面")
    names = _read_names(image)

    plan = current.plan
    if plan is not None and _same_names(names, plan["candidates"]):
        candidates = [data.rental_pokemon()[name_id] for name_id in plan["candidates"]]
        selection = plan["selection"]
        log(f"三只的名字 {names} 和上一局一致，直接选上一局选的第 {selection} 个")
    else:
        if plan is not None:
            log(f"三只的名字 {names} 和上一局不一致，不再沿用上一局，照常读和算", "WARNING")
            current.plan = None
        # 名字加上特性、招式一起认，顺序和屏幕上一致
        candidates = []
        for name, ability_rect, moves_rect in zip(names, ABILITY_RECTS, MOVES_RECTS):
            match = pokemon.identify(
                name, image.read_text(ability_rect).strip(), image.read_text(moves_rect).strip()
            )
            level = "WARNING" if match.is_poor else "DEBUG"
            log(f"识别「{match.text}」为 {match.pokemon.name_id}，编辑距离 {match.distance}", level)
            candidates.append(match.pokemon)
        scores = []
        for candidate in candidates:
            score = weighted_score(
                data.rental_scores()[candidate.name_id],
                rental_weight,
                data.boss_matchups()[candidate.name_id][current.boss],
                boss_weight,
            )
            log(f"{candidate.name_id} 的得分 {score:.2f}", "DEBUG")
            scores.append(score)
        selection = scores.index(max(scores))
    current.candidates = [candidate.name_id for candidate in candidates]
    current.encountered.update(current.candidates)
    current.selection = selection
    _move_starter_cursor(selection)
    current.pokemon = candidates[selection]
    log(f"选了第 {selection} 个：{current.pokemon.name_id}")
    switch.get().click("A", 0)

    if current.plan is not None:
        # 同一个种子，队友选的也和上一局一样。刚开局都是满血
        current.restore_team(current.plan, full_hp=True)
        log(f"沿用上一局的队伍: {[m.name_id for m in [current.pokemon, *current.team]]}")
        return
    # 我选完之后队友依次选，左边名单上每一行依次出现选好的宝可梦名字。
    # 最后一个队友选好后这个界面很快就切走（真机上只截到一帧），所以每读到一行就记下来；
    # 界面切走了还没读全，就留到路线图上再读
    picked: dict[int, str] = {}
    wait_for(lambda screen: _read_starter_team(screen, picked), team_timeout, "队友都选好")
    _record_starter_team(picked)


def _read_starter_team(screen: ImageChecker, picked: dict[int, str]) -> bool:
    """读选宝可梦界面左边的名单，把新出现的宝可梦名字记进 picked（行号到名字）。

    4 行都有名字了返回 True；名单整个空了（界面已经切走）也返回 True，这时 picked 可能不全。
    """
    texts = [screen.read_text(rect).strip() for rect in STARTER_TEAM_NAME_RECTS]
    for row, text in enumerate(texts):
        if text and text != "选择中":
            picked.setdefault(row, text)
    return len(picked) == len(STARTER_TEAM_NAME_RECTS) or (bool(picked) and not any(texts))


def _record_starter_team(picked: dict[int, str]) -> None:
    """把名单上读到的名字认成宝可梦，记成这一局的自己和队友；没读全的记一条警告，留到路线图上再读。"""
    current = run.get()
    members = []
    for row in range(len(STARTER_TEAM_NAME_RECTS)):
        if row not in picked:
            log(f"名单第 {row + 1} 行没读到，到路线图上再读队伍", "WARNING")
            return
        match = pokemon.identify(picked[row])
        level = "WARNING" if match.is_poor else "DEBUG"
        log(f"名单第 {row + 1} 行「{match.text}」认成 {match.pokemon.name_id}", level)
        members.append(match.pokemon)
    own, *teammates = members
    if current.pokemon is not None and own.name_id != current.pokemon.name_id:
        log(f"名单上自己的是 {own.name_id}，和选的 {current.pokemon.name_id} 不一致", "WARNING")
    current.pokemon, current.team = own, teammates
    current.encountered.update(member.name_id for member in members)
    log(f"队伍: {[member.name_id for member in members]}")


def _read_names(screen: ImageChecker) -> list[str]:
    """读选宝可梦界面上三只的名字，顺序和屏幕上一致，读不出的是空字符串。"""
    return [screen.read_text(rect).strip() for rect in NAME_RECTS]


def _same_names(names: list[str], name_ids: list[str]) -> bool:
    """屏幕上读到的三个名字是不是依次就是 name_ids 这三只。

    每个名字和对应宝可梦的中文名编辑距离不超过名字长度的三分之一就算是，容得下 OCR 偶尔错字。
    """
    expected = [data.rental_pokemon()[name_id].name() for name_id in name_ids]
    return len(names) == len(expected) and all(
        levenshtein(name, want) <= len(want) / 3 for name, want in zip(names, expected)
    )


def _select_path() -> None:
    """等路线图出现，读出整张路线图，给每条路线打分，把分数最高的记为这一局的目标路线。

    只决定走哪条，真正在岔路口移动光标是下一步 path 的事。
    keep path 时第 1 层和上一局一致，就直接沿用上一局的整张路线图和目标路线，不滚地图也不打分。
    """
    # 选好宝可梦之后要读盘进入冒险，是流程里最长的一次等待（上游盲等 22 秒）
    adventure_timeout = 60.0

    current = run.get()
    image = wait_for(_map_shown, adventure_timeout, "路线图")
    if len(current.team) < 3:
        # 选宝可梦界面上没读全队伍，在路线图左边的队伍栏上读
        read_team(image)
    first_row = [_identify_type(image, rect) for rect in PATH_RECTS[FIRST_ROW]]
    plan = current.plan
    if plan is not None:
        planned = [type_id for type_id, _, _ in plan["rows"][str(FIRST_ROW)]]
        if [match.type_id for match in first_row] == planned:
            current.restore_paths(plan)
            log(f"路线图第 1 层和上一局一致，沿用上一局的路线图（{current.path_type}）")
            for line in _path_diagram():
                log(line)
            log(
                f"沿用上一局的路线：{_route_name([node.name for node in current.target_path[1:-1]])}"
            )
            return
        log(
            f"路线图第 1 层 {[m.type_id for m in first_row]} 和上一局 {planned} 不一致，"
            "不再沿用上一局，照常读整张路线图",
            "WARNING",
        )
        current.plan = None

    # 刚出现时只能看到第 1 层。第 2、3 层要用右摇杆把地图往上滚，分别推 7、8 个 tick（同上游）。
    # 推完之后等这一层每个标签区域都认出属性、并且和上一层读到的不一样，才算滚到了
    current.update_paths(FIRST_ROW, first_row)
    previous = first_row
    for row, scroll_ticks in ((SECOND_ROW, 7), (THIRD_ROW, 8)):
        switch.get().stick("RIGHT", 0, switch.STICK_MAX, scroll_ticks * TICK_SECONDS)
        found: dict[str, list[TypeMatch]] = {}
        wait_for(
            lambda screen, row=row, previous=previous, found=found: _row_ready(
                screen, row, previous, found
            ),
            DEFAULT_TIMEOUT,
            f"路线图滚到第 {row} 层",
        )
        current.update_paths(row, found["matches"])
        previous = found["matches"]
    log(f"路线形状: {current.path_type}")
    for line in _path_diagram():
        log(line)

    # 路线的分数：各节点属性对首领的分数加权求和。评分表只按单个属性打分，
    # 不看队友和血量。越靠后的节点权重越大，每往后一个多加 weight_step：
    # 越靠后，既有属性优势又能回 PP
    weight_step = 0.1
    type_scores = data.path_scores()[current.boss]
    names = [[node.name for node in path] for path in current.paths(truncate=True)]
    path_scores = [
        sum(
            (1.0 + index * weight_step) * type_scores[type_id] for index, type_id in enumerate(path)
        )
        for path in names
    ]
    best = path_scores.index(max(path_scores))
    for index, (path, score) in enumerate(zip(names, path_scores)):
        log(f"路线 {index}: {_route_name(path)}，得分 {score:.3f}", "DEBUG")
    current.target_path = current.paths()[best]
    log(f"选了路线 {best}：{_route_name(names[best])}，得分 {path_scores[best]:.3f}")


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
    selected = image.selected(rects)
    # 菜单有几项就最多移几次，移满一圈还没选中说明菜单里没有它
    for _ in range(len(lines)):
        # 直接比较已经读出的文字，编辑距离不超过 target 长度的三分之一就算是它。
        # 不能对单独一行的区域再识别一次：区域贴着文字，边缘的字容易认错
        if selected >= 0 and levenshtein(texts[selected], target) <= len(target) / 3:
            log(f"{what}选中了「{texts[selected]}」")
            return
        switch.get().stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
        image = wait_for(
            lambda screen, before=selected: screen.selected(rects) not in (before, -1),
            DEFAULT_TIMEOUT,
            f"{what}的光标移到下一项",
        )
        selected = image.selected(rects)
    raise RuntimeError(f"{what}里找不到「{target}」，读到的选项: {texts}")


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
        switch.get().stick("LEFT", 0, -switch.STICK_MAX, TICK_SECONDS)
        image = wait_for(
            lambda screen, before=selected: screen.selected(rects) not in (before, -1),
            DEFAULT_TIMEOUT,
            "选宝可梦的光标移到下一只",
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
        _identify_type(screen, rect).score >= MIN_LABEL_SCORE for rect in PATH_RECTS[FIRST_ROW]
    )


def _row_ready(
    screen: ImageChecker, row: int, previous: list[TypeMatch], found: dict[str, list[TypeMatch]]
) -> bool:
    """路线图滚到了第 row 层：这一层每个标签区域都认出了属性，并且和上一层读到的不一样。

    满足时把这一层读到的结果放进 found["matches"]。
    """
    matches = [_identify_type(screen, rect) for rect in PATH_RECTS[row]]
    if any(match.score < MIN_LABEL_SCORE for match in matches):
        return False
    if [(m.type_id, m.location) for m in matches] == [(m.type_id, m.location) for m in previous]:
        return False
    found["matches"] = matches
    return True


def _route_name(path: list[str]) -> str:
    """路线上各节点属性的中文名，用箭头连起来，例如「火 → 电 → 钢」。"""
    names = data.type_names()
    return " → ".join(names.get(type_id, type_id) for type_id in path)


def _path_diagram() -> list[str]:
    """把当前这一局的路线图画成 4 行中文，用来写日志，画法照搬上游。"""
    current = run.get()
    names = data.type_names()
    # 每个节点占 8 列，不够的用横线补齐
    first, second, third = (
        [pad(names.get(node.name, node.name), 8, "─") for node in current.rows[row]]
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
        [f"      ┌{first[0]}", pad("起点", 5, "─") + "─┤        ", f"      └{first[1]}", " " * 15],
        first_links,
        second,
        second_links,
        [f"{third[0]}┐", f"{third[1]}┼─{boss}", f"{third[2]}┤", f"{third[3]}┘"],
    )
    return ["".join(section[line] for section in sections) for line in range(4)]


def _identify_type(image: ImageChecker, rect: Rect) -> TypeMatch:
    """认出 rect 区域里节点图标的属性，返回匹配度最高的那个。"""
    best = TypeMatch("", -1.0, (0, 0))
    for type_id, icon in data.type_icons().items():
        score, location = locate_template(image, rect, icon, ICON_LOWER, ICON_UPPER)
        if score > best.score:
            best = TypeMatch(type_id, score, location)
    return best
