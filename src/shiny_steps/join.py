import logging
import time

from libs import Lair, MapTypeReader, Switch
from tools import (
    act_until,
    capture,
    menu_last_item,
    move_menu_option,
    next_columns,
    press_until,
    wait_for,
)
from type import Boss, MapNode, Maps


def join(sw: Switch) -> str:
    # 先清掉上一局的状态、记下开始时间。后面 seed 或 boss 不一样时 clear 会清掉全部，开始时间保留
    sw.game.new_run()
    _select_target(sw)
    _select_starter(sw)
    _select_path(sw)
    return "path"


def _select_target(sw: Switch):
    """从科学家面前开始对话，在传说菜单里选中 BOSS 并确认，一直到进入选初始宝可梦的界面。

    initialize 已经处理过中途退出的罚款和提醒，并关掉了对话框；这里按 A 重新开始对话：
    开场白 →「现在就出发 / 我想听讲解 / 还是先算了」→ 选「现在就出发」→
    「看来您手边有宝可梦所在位置的记录呢」→「请问您要去找哪个宝可梦呢」→ 传说菜单。
    返回选的是哪只神兽（name_id）。

    BOSS 不在菜单里（刷到闪光带走之后那只就不在列表里了，或者存档改过）时，改成选菜单的第一项，
    这一局就刷它；菜单里全是「不指定」时抛 RuntimeError。
    """
    image = press_until(sw, lambda screen: menu_last_item(sw, screen) == "不指定", "传说菜单")
    bosses = sw.data.boss_pokemon()
    boss = sw.config.boss
    wanted = _select_boss(sw, bosses[boss])
    if wanted != bosses[boss].name():
        logging.warning(
            f"Lair note 里没有「{bosses[sw.config.boss].name()}」，这一局改成刷「{wanted}」"
        )
    move_menu_option(
        sw,
        image,
        wanted,
        lambda: sw.click("DDOWN", 0),
        "选择传说Boss",
    )
    # 选好传说之后：「要保存目前为止的冒险记录吗？」→「是 / 否」→ 选「是」保存。
    # 一直按 A 到画面变黑（保存中）就停，参考 lib/game.py 的 _enter_game
    press_until(sw, lambda screen: screen.is_black(), "保存时画面变黑")
    # 保存要几秒。大厅里选「发起单人挑战！」，队友由电脑来当
    solo = "发起单人挑战！"
    image = wait_for(
        sw,
        lambda screen: menu_last_item(sw, screen, 1, area=sw.config.rects.lobby_menu) == solo,
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
    return sw.game.boss


def _select_starter(sw: Switch) -> None:
    """从内存读取三只租借宝可梦，选择得分最高的。

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

    if seed == sw.game.seed:
        logging.info("seed 和上一局一样，沿用上一局的 starter 选择")
    else:
        sw.game.clear(seed=seed)
        _assign_new_starter(sw)

    _move_starter_cursor(sw)
    sw.click("A", 0)


def _select_path(sw: Switch) -> None:
    """等路线图出现，读出整张路线图，给每条路线打分，把分数最高的记为这一局的目标路线。

    只决定走哪条，真正在岔路口移动光标是下一步 path 的事。
    """
    if len(sw.game.maps["route"]):
        logging.info("沿用上一局的路线规划")
    else:
        _assign_new_path(sw)


def _assign_new_path(sw: Switch) -> None:
    """开场镜头往上移动时只读地图类型，等到路线图出现。"""
    wait_for(sw, lambda screen: not screen.is_black(), sw.config.timeout, "开场黑屏结束")
    reader = MapTypeReader(sw)
    deadline = time.monotonic() + sw.config.timeout
    while True:
        image = capture(sw)
        if image.has_text(sw.config.rects.den_text, "要走哪条路"):
            break
        if sw.game.maps is not None and sw.game.maps["type"] is None:
            map_type = reader.update(image)
            if map_type is not None:
                sw.game.maps["type"] = map_type
                _assign_route(sw)
                sw.game.save()
        if time.monotonic() >= deadline:
            raise TimeoutError(f"等了 {sw.config.timeout} 秒，路线图一直没有出现")
    if sw.game.maps is None or sw.game.maps["type"] is None:
        raise RuntimeError("没读到路线图类型")


def _assign_route(sw: Switch) -> None:
    """地图类型出来后，按 seed 的遭遇和首领相性给所有路线打分，存最高分路线。"""
    maps = sw.game.maps
    map_type = maps["type"]

    rows = maps["rows"]
    paths = [[[0, 0]]]
    for row in (1, 2, 3):
        next_paths = []
        for path in paths:
            prev_row, prev_col = path[-1]
            cols = next_columns(map_type, prev_row, prev_col)
            for col in cols:
                next_paths.append([*path, [row, col]])
        paths = next_paths

    matchups = sw.data.boss_matchups()
    scores = []
    for path in paths:
        score = 0.0
        for index, (row, col) in enumerate(path[1:]):
            encounter = rows[str(row)][col]["encounter"]
            score += (1.0 + index * 0.1) * matchups[encounter][sw.game.boss]
        scores.append(score)

    best = scores.index(max(scores))
    maps["route"] = [*paths[best], [4, 0]]
    sw.game.route_score = scores[best]
    logging.info(
        "路线: " + " → ".join(rows[str(row)][col]["encounter"] for row, col in maps["route"][1:-1])
    )


def _move_starter_cursor(sw: Switch) -> None:
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
        f"选宝可梦的光标移了 {len(rects)} 次，还是没到第 {sw.game.lock_pokemon_index + 1} 只"
    )


def _select_boss(sw: Switch, boss: Boss) -> str:
    """读四个 Lair note 的 species，目标还在就返回目标名字，不在就返回第一个 boss 的名字。"""
    species = [
        int.from_bytes(sw.peek(address, 2), "little") for address in sw.config.addresses.lair_notes
    ]
    logging.debug(f"Lair notes: {species}")
    if boss.id_num in species:
        return boss.name()
    for name_id, candidate in sw.data.boss_pokemon().items():
        if candidate.id_num == species[1]:
            sw.game.clear(boss=name_id)
            return candidate.name()
    raise RuntimeError(f"Lair note 里找不到第一个 boss：{species}")


def _read_seed(sw: Switch) -> int:
    """读这一局的冒险 seed。"""
    raw = sw.peek(sw.config.addresses.seed, 8)
    if len(raw) != 8:
        raise RuntimeError(f"路线 seed 读取长度错误：{len(raw)}")
    seed = int.from_bytes(raw, "little")
    logging.info(f"读取到的 seed 是 {seed}")
    return seed


def _assign_new_starter(sw: Switch) -> None:
    """seed 变了时重新算这一局的候选池和遭遇。"""
    seed = sw.game.seed
    assert seed is not None
    lair = Lair(sw.data, seed)
    sw.game.rental_pool = lair.candidates()
    rental_pokemon = sw.data.rental_pokemon()
    sw.game.maps = Maps(
        type=None,
        rows={
            row: [
                MapNode(
                    col=col,
                    type=rental_pokemon[encounter]["type_ids"][0],
                    encounter=encounter,
                )
                for col, encounter in enumerate(encounters)
            ]
            for row, encounters in lair.encounters().items()
        },
        route=[],
        current_index=0,
    )

    records = sw.pkhex.read_pk8(sw.config.addresses.starter_candidates)
    names = [sw.data.name_id(record["species"], record["form"]) for record in records]
    boss_matchups = sw.data.boss_matchups()
    rental_scores = sw.data.rental_scores()
    # 开始时还剩 3 个对手，最后还有 1 个首领；首领权重更大
    scores = [
        (rental_scores[name] ** 3 * boss_matchups[name][sw.game.boss] ** 2) ** (1 / 5)
        for name in names
    ]
    target = scores.index(max(scores))
    sw.game.candidates = names
    sw.game.lock_pokemon_index = target
    sw.game.save()
