import logging
import time
import unicodedata
from typing import cast

from control_switch.flow import (
    act_until,
    capture,
    menu_last_item,
    move_menu_option,
    press_until,
    wait_for,
)
from control_switch.games.swsh.lair import upstream
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.map import MapNode, Maps, MapType
from control_switch.games.swsh.lair.map_type_reader import MapTypeReader
from control_switch.games.swsh.lair.plan import Plan, positions
from control_switch.games.swsh.lair.switch import LairSwitch


def join(sw: LairSwitch) -> str:
    # 记下开始时间，清掉上一局打到一半的数据
    sw.game.start_run()
    _read_legends(sw)
    boss = _select_target(sw)
    kept = _select_starter(sw, boss)
    _select_path(sw, kept)
    return "path"


def _read_legends(sw: LairSwitch) -> None:
    """从存档读已经抓到哪些神兽、究极异兽解锁了没有，写进配置：按 seed 算租借和首领要用（见 GameData.lair_legends）。

    读不出来就用配置里手写的，只记一条警告。
    """
    try:
        caught, unlocked = sw.caught_legends()
    except RuntimeError as error:
        logging.warning(f"没读出抓过哪些神兽，用配置里写的 {sw.config.lair_caught}：{error}")
        return
    if set(caught) != set(sw.config.lair_caught):
        logging.info(
            f"存档里抓过的神兽 {caught} 和配置里写的 {sw.config.lair_caught} 不一样，按存档的算"
        )
    if unlocked != sw.config.lair_ultra_beasts_unlocked:
        logging.info(
            f"存档里究极异兽{'解锁了' if unlocked else '没解锁'}，和配置里写的不一样，按存档的算"
        )
    sw.config.lair_caught = caught
    sw.config.lair_ultra_beasts_unlocked = unlocked
    logging.debug(f"抓过的神兽 {caught}，还能遇到 {len(sw.data.lair_legends())} 只")


def _select_target(sw: LairSwitch):
    """从科学家面前开始对话，在传说菜单里选中 BOSS 并确认，一直到进入选初始宝可梦的界面。

    initialize 已经处理过中途退出的罚款和提醒，并关掉了对话框；这里按 A 重新开始对话：
    开场白 →「现在就出发 / 我想听讲解 / 还是先算了」→ 选「现在就出发」→
    「看来您手边有宝可梦所在位置的记录呢」→「请问您要去找哪个宝可梦呢」→ 传说菜单。
    返回选的是哪只神兽（name_id）。

    BOSS 不在菜单里（刷到闪光带走之后那只就不在列表里了，或者存档改过）时，改成选菜单的第一项，
    这一局就刷它；菜单里全是「不指定」时抛 RuntimeError。
    """
    rects = sw.config.rects
    image = press_until(
        sw,
        lambda screen: (
            menu_last_item(screen, rects.menu_search, dialog=rects.white_center_line1) == "不指定"
        ),
        "传说菜单",
    )
    bosses = sw.data.boss_pokemon()
    boss, index = _select_boss(sw, sw.config.boss)
    wanted = "不指定" if boss is None else bosses[boss].name()
    if boss != sw.config.boss:
        logging.warning(
            f"Lair note 里没有「{bosses[cast(str, sw.config.boss)].name()}」，这一局改成刷「{wanted}」"
        )
    # 菜单顺序和 Lair note 一样，按位置选；菜单文字 OCR 会认错（「哞哞」读成「哗眸」）
    move_menu_option(
        sw,
        image,
        index,
        lambda: sw.click("DDOWN", 0),
        "选择传说Boss",
        rects.menu_search,
    )
    logging.info(f"选择传说Boss选中了第 {index + 1} 项「{wanted}」")
    # 选好传说之后：「要保存目前为止的冒险记录吗？」→「是 / 否」→ 选「是」保存。
    # 一直按 A 到画面变黑（保存中）就停，参考 lib/game.py 的 _enter_game
    press_until(sw, lambda screen: screen.is_black(), "保存时画面变黑")
    # 保存要几秒。大厅里选「发起单人挑战！」，队友由电脑来当
    solo = "发起单人挑战！"
    image = wait_for(
        sw,
        lambda screen: menu_last_item(screen, rects.lobby_menu, 1) == solo,
        sw.config.timeout,
        "极巨大冒险的大厅",
    )
    move_menu_option(
        sw,
        image,
        solo,
        lambda: sw.click("DDOWN", 0),
        "大厅菜单",
        area=sw.config.rects.lobby_menu,
    )
    sw.click("A", 0)
    return boss


def _select_starter(sw: LairSwitch, boss: str | None) -> bool:
    """从内存读取三只租借宝可梦，和路线一起选总分最高的那种，返回是不是沿用了锁定的这张图。

    屏幕只用来看光标停在哪只上；宝可梦信息都从内存读取。队友等第一场战斗再读（见 battle._read_team），
    选初始界面读不到队伍地址。
    """
    # 不能用面板高亮判断界面是否出来：刚切出来时面板还在淡入，选中位置会看错
    wait_for(
        sw,
        lambda screen: screen.has_text(sw.config.rects.starter_hint, "按顺序选择"),
        sw.config.timeout,
        "选宝可梦的界面",
    )

    seed = _read_seed(sw)
    if boss is None:
        boss = Lair(sw.data, seed).boss()
        logging.info(
            f"选的是不指定，按 seed 算这一局的首领是「{sw.data.boss_pokemon()[boss].name()}」"
        )

    # 锁定了这张图并且 boss、seed 都对得上才沿用上一局的选择，否则 check_keep 会清掉旧数据
    kept = sw.game.check_keep(boss, seed)
    if kept:
        logging.info("锁定了这张图，沿用上一局的 starter 选择")
    else:
        _assign_new_starter(sw)

    _move_starter_cursor(sw)
    sw.click("A", 0)
    return kept


def _select_path(sw: LairSwitch, kept: bool) -> None:
    """路线在选首发时已经和首发一起定了。新的图还要等路线图出现，读画面上的地图类型对一下。

    只决定走哪条，真正在岔路口移动光标是下一步 path 的事。
    """
    if kept and cast(Maps, sw.game.maps)["route"]:
        logging.info("沿用上一局的路线规划")
        _log_map(sw)
    else:
        _check_map_type(sw)


def _check_map_type(sw: LairSwitch) -> None:
    """开场镜头往上移动时读地图类型，等到路线图出现。

    读到的类型和 seed 算出来的不一样，按画面上的类型、首发不变重新选路线。
    """
    wait_for(sw, lambda screen: not screen.is_black(), sw.config.timeout, "开场黑屏结束")
    reader = MapTypeReader(sw)
    deadline = time.monotonic() + sw.config.timeout
    seen: str | None = None
    while True:
        image = capture(sw, "读地图类型")
        if image.has_text(sw.config.rects.black_center_line1, "要走哪条路"):
            break
        if seen is None:
            seen = reader.update(image)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {sw.config.timeout} 秒，路线图一直没有出现")
    if seen is None:
        raise RuntimeError("没读到路线图类型")
    maps = sw.game.maps
    assert maps is not None
    # 每种地图类型、每个布局编号的路线图存一张，以后认图上的研究员、背包客、树果图标用
    picture = sw.config.log_dir / "maps" / f"{seen}-{maps.get('layout')}.jpg"
    if not picture.exists():
        picture.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(picture))
    if seen != maps["type"]:
        logging.warning(
            f"画面上的地图类型是 {seen}，seed 算出来的是 {maps['type']}，按画面上的重新选路线"
        )
        maps["type"] = cast(MapType, seen)
        maps["route"] = []
    if not maps["route"]:
        _assign_route(sw)
        sw.game.save()


def _assign_route(sw: LairSwitch) -> None:
    """首发已经定了，按现在的地图类型重新选路线。"""
    seed = sw.game.seed
    assert seed is not None and sw.game.lock_pokemon_index is not None
    lair = _matching_lair(sw, seed, sw.game.candidates)
    assert sw.game.maps is not None
    plan = _upstream_plan(
        sw,
        lair,
        cast(str, sw.game.maps["type"]),
        sw.game.maps.get("layout"),
        (sw.game.lock_pokemon_index,),
    )
    _apply_plan(sw, plan)


def _upstream_plan(
    sw: LairSwitch, lair: Lair, map_type: str, layout: int | None, starters: tuple[int, ...]
) -> Plan:
    """按 upstream.py 选首发和路线，再从开局推一遍预计的三关换法（只写日志，真打时每关再定）。

    Plan 里 total 记路线分，stage 记首发分，boss 不用（0）。
    """
    names = sw.game.candidates
    scorer = upstream.Scorer(sw.data, sw.game.boss)
    starter = max(starters, key=lambda index: scorer.starter_score(names[index]))
    path, route_score = upstream.best_path(scorer, lair.encounters(), map_type)
    team = [names[starter], *lair.teammates(starter)]
    events = sw.data.lair_events(map_type, layout)
    walker = upstream.Walker(lair, sw.data, sw.game.boss, path, team, events)
    swaps = upstream.plan_swaps(scorer, walker)
    return Plan(
        starter,
        path,
        tuple(walker.opponents),
        tuple(team[1:]),
        route_score,
        scorer.starter_score(names[starter]),
        0.0,
        tuple(swaps),
    )


def _apply_plan(sw: LairSwitch, plan: Plan) -> None:
    """把选好的首发和路线记进这一局的状态，写日志。"""
    sw.game.lock_pokemon_index = plan.starter
    assert sw.game.maps is not None
    sw.game.maps["route"] = [[0, 0], *([row, col] for row, col in plan.path), [4, 0]]
    # 战报里的「得分」记路线分；三关、首领分是旧算法的，这里不用
    sw.game.route_score = plan.total
    sw.game.stage_score = 0.0
    sw.game.boss_score = 0.0
    swaps = "、".join("换" if swap else "不换" for swap in plan.swaps)
    logging.info(
        f"首发 {sw.game.candidates[plan.starter]}（第 {plan.starter + 1} 位，首发分 {plan.stage:.2f}），"
        f"队友 {', '.join(plan.teammates)}，路线分 {plan.total:.2f}，按 seed 推的三关换法：{swaps}"
    )
    logging.info("路线: " + " → ".join(plan.opponents))
    known = sw.data.lair_events(sw.game.maps["type"], sw.game.maps.get("layout"))
    seen = {position: known[position] for position in positions(plan.path) if position in known}
    logging.info(
        f"路上的事件（布局 {sw.game.maps.get('layout')}）：这条路线 12 个位置里知道 {len(seen)} 个，"
        f"有事件的 { {position: events for position, events in seen.items() if events} }"
    )
    _log_map(sw)


def _log_map(sw: LairSwitch) -> None:
    """把租借的六只和整张路线图写进日志。"""
    pool = [_name(sw, name_id) for name_id in sw.game.rental_pool]
    logging.info(
        f"租借的六只: 选宝可梦界面 {'、'.join(pool[:3])}；后面补上的 {'、'.join(pool[3:])}"
    )
    logging.info("路线图（* 是选的路线）:\n" + "\n".join(_path_diagram(sw)))


def _path_diagram(sw: LairSwitch) -> list[str]:
    """把这一局的路线图画成 4 行，画法照搬上游：三层节点从左到右，中间是各种地图类型的连线。

    节点和首领用中文名，选的路线上的节点前面加 *。
    """
    maps = sw.game.maps
    assert maps is not None
    route = {(row, col) for row, col in maps["route"]}
    labels = {
        row: [
            ("*" if (int(row), node["col"]) in route else "") + _name(sw, node["encounter"])
            for node in nodes
        ]
        for row, nodes in maps["rows"].items()
    }
    # 每个节点占一样的宽度，不够的用横线补齐；中文算 2 列
    width = max(_display_width(label) for row in labels.values() for label in row) + 1
    first, second, third = (
        [label + "─" * (width - _display_width(label)) for label in labels[row]]
        for row in ("1", "2", "3")
    )
    # 第 1、2 层之间和第 2、3 层之间的连线，按地图类型不同
    links = {
        "2x3": (["┬──", "└┮═", "─┼─", " └─"], ["┐┌─", "┴┼─", "┐╞═", "┴┴─"]),
        "3x2": (["┬──", "└┬─", "┬┶═", "└──"], ["┬┬─", "┘╞═", "┬┼─", "┘└─"]),
        "2x2": (["┬──", "└──", "┬──", "└──"], ["─┬─", "┐╞═", "┼┼─", "┘└─"]),
    }
    first_links, second_links = links[cast(str, maps["type"])]
    boss = sw.data.boss_pokemon()[sw.game.boss].name()
    sections = (
        [f"     ┌{first[0]}", "起点─┤" + " " * width, f"     └{first[1]}", " " * (6 + width)],
        first_links,
        second,
        second_links,
        [f"{third[0]}┐", f"{third[1]}┼─{boss}", f"{third[2]}┤", f"{third[3]}┘"],
    )
    return ["".join(section[line] for section in sections) for line in range(4)]


def _name(sw: LairSwitch, name_id: str) -> str:
    """宝可梦的中文名；同名不同样子的在后面标出来。"""
    name = sw.data.pokemon_object(name_id).name(sw.config.language)
    forms = (("-galar", "伽勒尔"), ("-alola", "阿罗拉"), ("-midday", "白昼"), ("-midnight", "黑夜"))
    for suffix, form in forms:
        if name_id.endswith(suffix):
            name += f"（{form}）"
    return name


def _display_width(text: str) -> int:
    """等宽字体下的显示宽度，中文和全角字符算 2 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def _move_starter_cursor(sw: LairSwitch) -> None:
    """读界面上的三只候选，选得分最高的，把黑色光标移过去。"""

    rects = sw.config.rects.starter_candidates
    image = wait_for(
        sw,
        lambda screen: screen.selected(rects) != -1,
        sw.config.timeout,
        "选宝可梦的光标",
    )
    for _ in range(len(rects)):
        current = image.selected(rects)
        if current == sw.game.lock_pokemon_index:
            return
        image = act_until(
            sw,
            lambda: sw.click("DDOWN", 0),
            lambda screen, before=current: screen.selected(rects) not in (before, -1),
            "选宝可梦的光标移一格",
        )
    raise RuntimeError(
        f"选宝可梦的光标移了 {len(rects)} 次，还是没到第 {cast(int, sw.game.lock_pokemon_index) + 1} 只"
    )


def _select_boss(sw: LairSwitch, target: str | None) -> tuple[str | None, int]:
    """读四个 Lair note，返回 (要刷的 boss 的 name_id, 它在传说菜单里的下标)。

    菜单按 Lair note 的顺序列出里面的 boss（不是 boss 的 note 不出现），最后一项是「不指定」。
    target 是 None 就选「不指定」，返回的 name_id 也是 None，首领等读到 seed 再算；
    目标 target 还在就选它，不在就选菜单第一项。
    """
    species = [
        int.from_bytes(sw.peek(address, 2), "little") for address in sw.config.addresses.lair_notes
    ]
    logging.debug(f"Lair notes: {species}")
    by_id = {boss.id_num: name_id for name_id, boss in sw.data.boss_pokemon().items()}
    menu = [by_id[number] for number in species if number in by_id]
    if target is None:
        return None, len(menu)
    if not menu:
        raise RuntimeError(f"Lair note 里没有 boss：{species}")
    if target in menu:
        return target, menu.index(target)
    return menu[0], 0


def _read_seed(sw: LairSwitch) -> int:
    """读这一局的冒险 seed。"""
    raw = sw.peek(sw.config.addresses.seed, 8)
    if len(raw) != 8:
        raise RuntimeError(f"路线 seed 读取长度错误：{len(raw)}")
    seed = int.from_bytes(raw, "little")
    logging.info(f"读取到的 seed 是 {seed}")
    return seed


def _matching_lair(sw: LairSwitch, seed: int, shown: list[str]) -> Lair:
    """按 seed 算租借和遭遇，算出来的前 3 只租借要和选宝可梦界面上的 3 只（shown）一样。

    不一样就在开头多取 1 个随机数重算，最多多取 lair_extra_max 个；都对不上抛 RuntimeError。
    """
    tried = []
    for extra in range(sw.config.lair_extra_max + 1):
        lair = Lair(sw.data, seed, extra)
        first = lair.candidates()[:3]
        if first == shown:
            if extra:
                logging.warning(
                    f"seed {seed} 按原来的算法前 3 只租借是 {tried[0]}，界面上是 {shown}；"
                    f"开头多取 {extra} 个随机数后对上了。"
                    f"配置里的 lair_caught（已经抓到的神兽）可能少写了"
                )
            return lair
        tried.append(first)
    raise RuntimeError(
        f"seed {seed} 算出来的前 3 只租借和界面上的 {shown} 对不上，"
        f"多取 0 到 {sw.config.lair_extra_max} 个随机数依次算出 {tried}"
    )


def _assign_new_starter(sw: LairSwitch) -> None:
    """seed 变了时重新算这一局的候选池、遭遇、地图类型和队友，一起选首发和路线。"""
    seed = sw.game.seed
    assert seed is not None
    records = sw.pkhex.read_pk8(sw.config.addresses.starter_candidates)
    names = [sw.data.name_id(record["species"], record["form"]) for record in records]
    lair = _matching_lair(sw, seed, names)
    sw.game.rental_pool = lair.candidates()
    rental_pokemon = sw.data.rental_pokemon()
    encounters = lair.encounters()
    sw.game.maps = Maps(
        type=cast(MapType, lair.map_type()),
        layout=lair.layout(),
        rows={
            row: [
                MapNode(
                    col=col,
                    type=rental_pokemon[encounter]["type_ids"][0],
                    encounter=encounter,
                )
                for col, encounter in enumerate(nodes)
            ]
            for row, nodes in encounters.items()
        },
        route=[],
        current_index=0,
    )

    sw.game.candidates = names
    # 首发、路线按 upstream.py 选；队友一路上换不换、研究员给谁都从 seed 直接推
    plan = _upstream_plan(sw, lair, lair.map_type(), lair.layout(), (0, 1, 2))
    _apply_plan(sw, plan)
    sw.game.save()
