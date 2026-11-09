import logging

from libs import Switch
from tools import menu_last_item, move_menu_option, press_until, wait_for
from type import Boss


def join(sw: Switch) -> str:
    _select_target(sw)
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
        logging.warning(  # noqa: LOG015
            f"Lair note 里没有「{bosses[sw.config.boss].name()}」，"
            f"这一局改成刷「{wanted}」"
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


def _select_boss(sw: Switch, boss: Boss) -> str:
    """读四个 Lair note 的 species，目标还在就返回目标名字，不在就返回第一个 boss 的名字。"""
    species = [
        int.from_bytes(sw.peek(address, 2), "little")
        for address in sw.config.addresses.lair_notes
    ]
    logging.debug(f"Lair notes: {species}")  # noqa: LOG015
    if boss.id_num in species:
        return boss.name()
    for candidate in sw.data.boss_pokemon().values():
        if candidate.id_num == species[1]:
            return candidate.name()
    raise RuntimeError(f"Lair note 里找不到第一个 boss：{species}")
