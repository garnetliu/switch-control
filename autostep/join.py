import time
from dataclasses import replace

from config.game import BOSS
from config.layout import (
    ABILITY_RECTS,
    DEN_TEXT_RECT,
    DIALOG_RECT,
    LABEL_ICON_LOWER,
    LABEL_ICON_SCORE,
    LABEL_ICON_UPPER,
    LOBBY_MENU_RECT,
    MOVES_RECTS,
    NAME_RECTS,
    PATH_RECTS,
    POPUP_RECT,
    ROW_MAX_SPREAD,
    STARTER_PANEL_RECTS,
    STARTER_TEAM_NAME_RECTS,
    YES_NO_RECTS,
)
from config.paths import MAP_PAN_DIR
from config.timing import DEFAULT_TIMEOUT, LOAD_TIMEOUT, TICK_SECONDS
from lib import data, pokemon, run, switch
from lib.dialog import advance_until, menu_last_item, press_until
from lib.log import log
from lib.read import read_team
from lib.run import FIRST_ROW, SECOND_ROW, THIRD_ROW
from lib.scoring import weighted_score
from lib.wait import capture, wait_for
from tool.check_image import BASE_SIZE, ImageChecker
from tool.image import locate_template, save, text_lines
from tool.text import levenshtein, pad
from type.image import Rect
from type.path import TypeMatch


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

    对话顺序（真机实测）：（中途退出过时先有罚款或提醒）→ 开场白 →「现在就出发 / 我想听讲解 / 还是先算了」
    → 选「现在就出发」→「看来您手边有宝可梦所在位置的记录呢」→「请问您要去找哪个宝可梦呢」→ 传说菜单。
    """
    # 一直按 A，直到传说菜单弹出来（菜单最后一行是「不指定」）。中途退出的罚款、提醒、开场白，
    # 开场白菜单上的「现在就出发」（光标默认在它上面）都用 A 过掉
    image = press_until(lambda screen: menu_last_item(screen) == "不指定", "传说菜单")
    _select_menu_item(image, POPUP_RECT, data.boss_pokemon()[BOSS].name(), "传说菜单")
    switch.get().click("A", 0)
    # 选好传说之后：「要保存目前为止的冒险记录吗？」→「是 / 否」→ 选「是」保存 → 极巨大冒险的大厅
    wait_for(
        lambda screen: screen.has_text(DIALOG_RECT, "要保存目前为止的"),
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
        log(f"三只的名字 {names} 和上一局一致，直接选上一局选的第 {selection + 1} 个")
    else:
        if plan is not None:
            log(f"三只的名字 {names} 和上一局不一致，不再沿用上一局，照常读和算", "WARNING")
            current.plan = None
            current.keep_path = False
        # 名字加特性就能认出是哪只；名字和特性都一样的（只有野蛮鲈鱼红条纹和蓝条纹）才读招式区分。
        # 顺序和屏幕上一致
        candidates = []
        for name, ability_rect, moves_rect in zip(names, ABILITY_RECTS, MOVES_RECTS):
            ability = image.read_text(ability_rect)
            match = pokemon.identify(name, ability)
            same = [
                rental
                for rental in data.rental_pokemon().values()
                if rental.name() == match.pokemon.name()
                and rental.ability() == match.pokemon.ability()
            ]
            if len(same) > 1:
                moves = "".join(text for text, _ in text_lines(image, moves_rect))
                match = pokemon.identify(name, ability, moves)
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
    current.pokemon = replace(candidates[selection], hp=1.0)
    log(f"选了第 {selection + 1} 个：{current.pokemon.name_id}")
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
    # 只识别还没读到的行：最后一个队友选完之后名单很快就切走了，每帧都把 4 行识别一遍会赶不上
    texts = {
        row: screen.read_text(rect).strip()
        for row, rect in enumerate(STARTER_TEAM_NAME_RECTS)
        if row not in picked
    }
    for row, text in texts.items():
        if text and text != "选择中":
            picked[row] = text
    if len(picked) == len(STARTER_TEAM_NAME_RECTS):
        return True
    # 第 1 行是自己，名单还在时一定有名字；它也没了就是界面已经切走
    return bool(picked) and not screen.read_text(STARTER_TEAM_NAME_RECTS[0]).strip()


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
        # 用副本，之后改血量、扣 PP 不会改到共用的数据；刚出发都是满血
        members.append(replace(match.pokemon, hp=1.0))
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
    image, pan_rows = _watch_intro_pan(adventure_timeout)
    if len(current.team) < 3:
        # 选宝可梦界面上没读全队伍，在路线图左边的队伍栏上读。刚出发大家都是满血，不读血条
        # （路线图上血条的位置不对，读出来是 67%、17% 之类的错数）
        read_team(image, hp_rects=None)
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
        current.keep_path = False

    current.update_paths(FIRST_ROW, first_row)
    if len(pan_rows) == 2:
        current.update_paths(SECOND_ROW, pan_rows[0])
        current.update_paths(THIRD_ROW, pan_rows[1])
        log("开场镜头往上移的时候已经读到第 2、3 层，不用再推摇杆")
    else:
        log(f"开场镜头往上移的时候只读到 {len(pan_rows)} 层，推摇杆补读", "WARNING")
        _scroll_rows(first_row)
    _choose_target_path()


def _scroll_rows(first_row: list[TypeMatch]) -> None:
    """推右摇杆读第 2、3 层，记到这一局里。开场镜头往上移时没读全才用。

    按固定时间推，滚的距离每次不一样（真机上推过头、标签被下面的文字框挡住过），所以一直按住
    往上推，这一层 4 列的标签都认出属性、并且和上一层不一样就松开：标签刚进画面就停，不会推过头。
    """
    # 推着等一层最多几秒
    row_timeout = 10.0
    current = run.get()
    previous = first_row
    for row in (SECOND_ROW, THIRD_ROW):
        found: dict[str, list[TypeMatch]] = {}
        switch.get().press_stick("RIGHT", 0, switch.STICK_MAX)
        try:
            wait_for(
                lambda screen, row=row, previous=previous, found=found: _row_ready(
                    screen, row, previous, found
                ),
                row_timeout,
                f"路线图滚到第 {row} 层",
            )
        finally:
            switch.get().release_stick("RIGHT")
        current.update_paths(row, found["matches"])
        previous = found["matches"]


def _choose_target_path() -> None:
    """画出读到的路线图，给每条路线打分，把分数最高的记为这一局的目标路线。"""
    current = run.get()
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
    current.path_score = path_scores[best]
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
        _identify_type(screen, rect).score >= LABEL_ICON_SCORE for rect in PATH_RECTS[FIRST_ROW]
    )


def _watch_intro_pan(timeout: float) -> tuple[ImageChecker, list[list[TypeMatch]]]:
    """从选完宝可梦开始一直截图，直到路线图回到底部、出现「要走哪条路？」，返回那时的截图和
    开场镜头往上移时依次读到的几层（最多两层：第 2 层、第 3 层）。

    冒险开场时镜头会自己从起点往上移到首领，再回到底部。往上移的时候，第 2、3 层的标签会依次
    经过 PATH_RECTS 里的检测框：4 个都认出属性、并且属性和上一组不同，就记成新的一层。
    每一帧都存进 MAP_PAN_DIR，写明这一帧认出了什么（调试用）。
    """
    rows: list[list[TypeMatch]] = []
    MAP_PAN_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        image = capture()
        if _map_shown(image):
            return image, rows
        matches = [_identify_type(image, rect) for rect in PATH_RECTS[SECOND_ROW]]
        types = [match.type_id if match.score >= LABEL_ICON_SCORE else "-" for match in matches]
        new_row = (
            "-" not in types
            and _same_row(matches)
            and (not rows or types != [m.type_id for m in rows[-1]])
        )
        if new_row and len(rows) < 2:
            rows.append(matches)
            log(f"开场镜头往上移，读到第 {len(rows) + 1} 层: {types}")
        stamp = f"{time.strftime('%H%M%S')}-{int(time.time() * 10) % 10}"
        save(image, str(MAP_PAN_DIR / f"{stamp}-{'-'.join(types)}.jpg"))
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {timeout} 秒，路线图一直没有出现")


def _row_ready(
    screen: ImageChecker, row: int, previous: list[TypeMatch], found: dict[str, list[TypeMatch]]
) -> bool:
    """路线图滚到了第 row 层：这一层每个标签区域都认出了属性，并且和上一层读到的不一样。

    满足时把这一层读到的结果放进 found["matches"]。
    """
    matches = [_identify_type(screen, rect) for rect in PATH_RECTS[row]]
    if any(match.score < LABEL_ICON_SCORE for match in matches) or not _same_row(matches):
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
        score, location = locate_template(image, rect, icon, LABEL_ICON_LOWER, LABEL_ICON_UPPER)
        if score > best.score:
            best = TypeMatch(type_id, score, location)
    return best
