"""steps.battle：一场极巨大冒险对战。

没有战斗界面的截图（logs/keep 里没有），画面判断用假截图（conftest 的 fake_images）：
每张假截图说明各个区域上读到的文字、颜色占比（菜单光标「>」要白色和黑色的占比都够）。
队伍和对手的内存记录用假的 Pk8Reader（conftest 的 make_pkhex），战斗数据读假 Memory。
选好首发和路线之后的状态用 prepare_run 按 seed 算出来（首发流氓熊猫，队友沙铃仙人掌、电蜘蛛、死神棺，
第一关对手斧牙龙，首领卡璞・蝶蝶）。改动前的代码算出来，流氓熊猫对斧牙龙这回合选第 2 个招式（序号 1），
可以极巨化时选第 3 个招式（序号 2）并且极巨化。
"""

import importlib
import logging
from collections.abc import Callable
from dataclasses import replace
from types import ModuleType
from typing import Any, cast

import pytest

from control_switch.config import WaitConfig
from control_switch.device import Controller
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.session import LairSession
from control_switch.types import Rect
from control_switch.vision import ImageChecker

module: ModuleType = importlib.import_module("control_switch.games.swsh.lair.steps.battle")
battle = module.battle

RECTS = GameConfig.rects
ADDRESSES = GameConfig.addresses
STICK_TICK = WaitConfig.stick_tick
SessionFactory = Callable[..., LairSession]
PrepareRun = Callable[..., Any]
ImageFactory = Any

TEAM = ["pangoro", "maractus", "galvantula", "cofagrigus"]
OPPONENT = "fraxure"
# 内存记录里用不会和真的重复的 species 编号（10001 起），name_id 认到它们时返回对应的宝可梦
SPECIES = {10001 + index: name for index, name in enumerate([*TEAM, OPPONENT])}
BATTLE_DATA_SIZE = 0x2C8


def battle_memory() -> dict[int, bytes]:
    """_log_turn 读的战斗数据：对手和队伍四只各 0x2C8 字节（地址是 PK8 记录的地址往前 battle_data 字节），全是 0。"""
    addresses = [ADDRESSES.opponent, *ADDRESSES.party]
    return {address - ADDRESSES.battle_data: bytes(BATTLE_DATA_SIZE) for address in addresses}


def make_war(
    sw: LairSession,
    prepare_run: PrepareRun,
    monkeypatch: pytest.MonkeyPatch,
    make_pkhex: Callable[..., Any],
    *,
    boss: bool = False,
    items: list[tuple[int, str]] | None = None,
) -> Any:
    """选好首发和路线，换上假的内存记录（队伍满血、每个招式 10 点 PP），用 _create_war 建这一场的 War。

    items 是队伍四只带的道具 (编号, 名字)，不给就都没带。boss 是第 4 场（对手是首领）。
    """
    prepare_run(sw)
    sw.game.num_caught = 3 if boss else 0
    real_name_id = sw.data.name_id
    monkeypatch.setattr(
        sw.data,
        "name_id",
        lambda species, form: SPECIES.get(species) or real_name_id(species, form),
    )
    items = items or [(0, "")] * 4
    records: dict[int, dict[str, Any]] = {}
    for index, (address, name) in enumerate(zip(ADDRESSES.party, TEAM, strict=True)):
        max_hp = replace(sw.data.pokemon_object(name), level=50, ivs=(31,) * 6, evs=(0,) * 6).stats[
            0
        ]
        records[address] = {
            "species": 10001 + index,
            "form": 0,
            "level": 50,
            "ivs": [31] * 6,
            "evs": [0] * 6,
            "hp": max_hp,
            "item": items[index][0],
            "itemName": items[index][1],
            "abilityName": "特性",
            "abilityNumber": 1,
            "pp": [10, 10, 10, 10],
        }
    records[ADDRESSES.opponent] = {
        "species": 10005,
        "form": 0,
        "abilityName": "压迫感",
        "abilityNumber": 1,
        "nature": 3,
        "gender": 0,
        "ivs": [31] * 6,
        "level": 50,
        "hp": 100,
        "maxHp": 100,
        "moves": [1, 2, 3, 4],
        "itemName": "",
    }
    monkeypatch.setattr(sw, "pkhex", make_pkhex(records))
    return module._create_war(sw)


# ---------------------------------------------------------------- 假截图


def marker(rect: Rect) -> dict[tuple[Rect, Any], float]:
    """区域里有菜单光标「>」：白色和黑色的占比都够。"""
    return {
        (rect, GameConfig.marker_white_lower): 0.5,
        (rect, GameConfig.marker_dark_lower): 0.5,
    }


def plain(images: ImageFactory) -> bytes:
    """什么字也读不到的画面。"""
    return images.add()


def fight(images: ImageFactory) -> bytes:
    """战斗菜单（第一项「战斗」）。"""
    return images.add(texts={RECTS.battle_menu_text: "战斗"})


def cheer(images: ImageFactory) -> bytes:
    """自己倒下了的助威菜单（第一项「助威」）。"""
    return images.add(texts={RECTS.battle_menu_text: "助威"})


def catch_state(images: ImageFactory) -> bytes:
    """「使用精灵球的好机会」。"""
    return images.add(texts={RECTS.black_full_line2: "使用精灵球的好机会"})


def loss_state(images: ImageFactory) -> bytes:
    """战败：「被风刮到巢穴外了」。"""
    return images.add(texts={RECTS.black_full_line2: "被风刮到巢穴外了"})


def storm_state(images: ImageFactory) -> bytes:
    """有宝可梦倒下了。"""
    return images.add(texts={RECTS.black_full_line1: "夜暮林夕倒下了"})


def move_list(
    images: ImageFactory,
    row: int | None,
    *,
    hint: bool = True,
    blocked: bool = False,
    dynamax: bool = False,
) -> bytes:
    """招式列表：光标在第 row 行（None 是没有光标）；hint 是上方有「招式说明」；
    blocked 是战斗文字第二行有「无法使出」；dynamax 是左边有极巨化按钮。
    """
    ratios: dict[tuple[Rect, Any], float] = {}
    if row is not None:
        ratios.update(marker(RECTS.move_cursor_rects[row]))
    if dynamax:
        ratios[(RECTS.dynamax_button, GameConfig.dynamax_lower)] = 1.0
    texts = {}
    if hint:
        texts[RECTS.move_hint] = "Y 招式说明"
    if blocked:
        texts[RECTS.black_full_line2] = "而无法使出臂锤！"
    return images.add(texts=texts, ratios=ratios)


def used(images: ImageFactory) -> bytes:
    """「×××使出了」，没有选目标的界面。"""
    return images.add(texts={RECTS.black_full_line1: "流氓熊猫使出了臂锤"})


def target_screen(
    images: ImageFactory, cursors: list[int], selectable: list[int] | None = None
) -> bytes:
    """选目标界面：cursors 是带光标的卡片（0 是对手，1 到 4 是我方四张），selectable 是能选的卡片。"""
    cursor_rects = (RECTS.target_cursor, *RECTS.ally_target_cursor_rects)
    card_rects = (RECTS.target_card, *RECTS.ally_target_card_rects)
    ratios: dict[tuple[Rect, Any], float] = {}
    for index in cursors:
        ratios.update(marker(cursor_rects[index]))
    for index in selectable or []:
        ratios[(card_rects[index], GameConfig.target_card_white_lower)] = 1.0
    return images.add(ratios=ratios)


def cursor_screen(images: ImageFactory, row: int, hint: bool = False) -> bytes:
    """招式列表的光标停在第 row 行（没有说明文字），用在移光标的测试里。"""
    return move_list(images, row, hint=hint)


# ---------------------------------------------------------------- battle：整个步骤


def test_battle_picks_move_presses_keys_and_returns_catch_when_opponent_is_beaten(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """一回合：战斗菜单按 A 打开招式列表，光标已经在选中的第 2 个招式上，按 A 出招，「使出了」之后
    出现「使用精灵球的好机会」：按过的键是 A、A，返回 "catch"，这场倒下 0 次记进 game.faints，
    队伍记成内存里读到的四只。
    """
    sw = make_lair_session(
        [
            fight(fake_images),
            fight(fake_images),
            move_list(fake_images, 1),
            move_list(fake_images, 1),
            move_list(fake_images, 1),
            used(fake_images),
            used(fake_images),
            used(fake_images),
            used(fake_images),
            catch_state(fake_images),
        ],
        data=battle_memory(),
    )
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "catch"
    assert controller.pressed == ["A", "A"]
    assert sw.game.faints == [0]
    assert [name for name, _ in sw.game.team] == TEAM


def test_battle_returns_catch_when_catch_screen_is_shown(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """第一张截图就是「使用精灵球的好机会」：返回 "catch"，不按键，game.faints 加一项 0。"""
    sw = make_lair_session([catch_state(fake_images)], data=battle_memory())
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "catch"
    assert controller.pressed == []
    assert sw.game.faints == [0]


def test_battle_returns_select_pokemon_when_loss_screen_is_shown(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「被风刮到巢穴外了」：返回 "select_pokemon"，game.faints 加一项这场倒下的次数（0）。"""
    sw = make_lair_session([loss_state(fake_images)], data=battle_memory())
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "select_pokemon"
    assert sw.game.faints == [0]


def test_battle_continues_after_a_faint_when_lives_remain(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有宝可梦倒下、还有命（前面没倒过）：等「倒下了」消失，继续打，之后出现抓宝可梦界面返回 "catch"，
    game.faints 记的是这场倒下 1 次。
    """
    sw = make_lair_session(
        [storm_state(fake_images), plain(fake_images), catch_state(fake_images)],
        data=battle_memory(),
    )
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "catch"
    assert sw.game.faints == [1]


def test_battle_returns_select_pokemon_when_last_life_is_lost(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """前面几关已经倒下 3 次（faints 是 [2, 1]），这场又倒下 1 次，命扣到 0：返回 "select_pokemon"，
    game.faints 加一项 1。
    """
    sw = make_lair_session([storm_state(fake_images), plain(fake_images)], data=battle_memory())
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    sw.game.faints = [2, 1]
    assert battle(sw) == "select_pokemon"
    assert sw.game.faints == [2, 1, 1]


def test_battle_cheers_when_own_pokemon_has_fainted(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """战斗菜单第一项是「助威」：按 A 到助威菜单消失，再继续，之后出现抓宝可梦界面返回 "catch"；按过的键是 A。"""
    sw = make_lair_session(
        [cheer(fake_images), cheer(fake_images), plain(fake_images), catch_state(fake_images)],
        data=battle_memory(),
    )
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "catch"
    assert controller.pressed == ["A"]


def test_battle_updates_weather_from_field_text_and_ignores_unknown_screens(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """什么都认不出的画面（出招动画）不按键，隔一会儿再看；战斗文字「开始下雨了」更新天气（日志里有
    「天气变成 rain」）；最后出现抓宝可梦界面返回 "catch"。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session(
        [
            plain(fake_images),
            fake_images.add(texts={RECTS.black_full_line1: "开始下雨了"}),
            catch_state(fake_images),
        ],
        data=battle_memory(),
    )
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert battle(sw) == "catch"
    assert controller.pressed == []
    assert any("天气变成 rain" in record.getMessage() for record in caplog.records)


def test_battle_raises_timeout_error_when_faint_text_never_disappears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「倒下了」一直不消失：抛 TimeoutError，报错里有「「倒下了」消失」。"""
    sw = make_lair_session([storm_state(fake_images)], data=battle_memory())
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    with pytest.raises(TimeoutError, match="「倒下了」消失"):
        battle(sw)


def test_battle_raises_timeout_error_when_cheer_menu_never_disappears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """按 A 之后助威菜单一直不消失：抛 TimeoutError，报错里有「助威菜单消失」，按的都是 A。"""
    sw = make_lair_session([cheer(fake_images)], data=battle_memory())
    make_war(sw, prepare_run, monkeypatch, make_pkhex)
    with pytest.raises(TimeoutError, match="助威菜单消失"):
        battle(sw)
    assert set(controller.pressed) == {"A"}


# ---------------------------------------------------------------- _create_war、_read_team、_read_opponent


def test_create_war_builds_own_teammates_and_opponent_from_memory_records(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_create_war（不是第 4 场）：自己是队伍第一只（流氓熊猫、满血，PP 是内存里读到的 10），队友是后三只，
    对手按内存记录的种类认出来是斧牙龙；game.team 是四只的名字和血量比例；记录读的是队伍和对手的地址。
    """
    sw = make_lair_session()
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    assert war.own.name_id == "pangoro"
    assert war.own.hp == 1.0
    assert war.own.pp == [10, 10, 10, 10]
    assert [pokemon.name_id for pokemon in war.teammates] == TEAM[1:]
    assert war.opponent.name_id == OPPONENT
    assert war.max_move_rate == sw.data.max_move_rate(OPPONENT)
    assert sw.game.team == [(name, 1.0) for name in TEAM]
    pkhex: Any = sw.pkhex
    assert pkhex.reads == [list(ADDRESSES.party), [ADDRESSES.opponent]]


def test_create_war_uses_current_boss_as_opponent_in_fourth_battle(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第 4 场（已经抓了 3 只）：对手直接用这一局的首领 tapu-lele，不看内存记录里的种类。"""
    sw = make_lair_session()
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex, boss=True)
    assert war.opponent.name_id == sw.game.boss == "tapu-lele"


def test_create_war_logs_team_items_abilities_and_opponent(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """建 War 时日志里有：队伍道具（带了的写道具名，没带的写「无」）、队伍特性（名字和编号）、对手的记录
    （种类、特性、性格、性别、个体值、等级、血量、招式、道具）。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    items = [(0, ""), (123, "讲究围巾"), (0, ""), (0, "")]
    make_war(sw, prepare_run, monkeypatch, make_pkhex, items=items)
    messages = [record.getMessage() for record in caplog.records]
    assert "队伍道具: 无，讲究围巾，无，无" in messages
    assert "队伍特性: 特性（1），特性（1），特性（1），特性（1）" in messages
    assert (
        "对手 fraxure（种类 10005）：特性 压迫感（编号 1），性格 3，性别 0，个体值 [31, 31, 31, 31, 31, 31]，"
        "等级 50，记录里的血量 100/100，招式 [1, 2, 3, 4]，道具 无"
    ) in messages


# ---------------------------------------------------------------- Messages


class Panel:
    """假的黑色面板：两行文字，用来喂给 Messages。"""

    def __init__(self, images: ImageFactory) -> None:
        self._images = images

    def show(self, line1: str = "", line2: str = "") -> ImageChecker:
        token = self._images.add(
            texts={RECTS.black_full_line1: line1, RECTS.black_full_line2: line2}
        )
        return cast(ImageChecker, self._images.image(token))


def logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def test_messages_logs_sentence_only_after_it_is_fully_displayed(
    fake_images: ImageFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """字一个一个出来（后一次读到的是前一次的延长）还是同一句，不打印；换成别的字，上一句才打印出来。"""
    caplog.set_level(logging.DEBUG)
    panel = Panel(fake_images)
    messages = module.Messages((RECTS.black_full_line1, RECTS.black_full_line2), "战斗文字")
    messages.read(panel.show("流氓"))
    messages.read(panel.show("流氓熊猫使出了"))
    assert logged(caplog) == []
    messages.read(panel.show("效果拔群"))
    assert logged(caplog) == ["战斗文字: 流氓熊猫使出了"]


def test_messages_joins_two_lines_and_logs_when_text_disappears(
    fake_images: ImageFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """两行都有字时用「 / 」连起来；字没了（读到空）时，上一句也打印出来。"""
    caplog.set_level(logging.DEBUG)
    panel = Panel(fake_images)
    messages = module.Messages((RECTS.black_full_line1, RECTS.black_full_line2), "战斗文字")
    messages.read(panel.show("夜暮林夕他们", "被风刮到巢穴外了"))
    messages.read(panel.show())
    assert logged(caplog) == ["战斗文字: 夜暮林夕他们 / 被风刮到巢穴外了"]


def test_messages_logs_with_given_label_and_skips_empty_first_read(
    fake_images: ImageFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """一开始读到空：什么都不打印；日志里每一行开头写的是传进去的 label。"""
    caplog.set_level(logging.DEBUG)
    panel = Panel(fake_images)
    messages = module.Messages((RECTS.black_full_line1, RECTS.black_full_line2), "路上的文字")
    messages.read(panel.show())
    assert logged(caplog) == []
    messages.read(panel.show("遇到了背包客"))
    messages.read(panel.show())
    assert logged(caplog) == ["路上的文字: 遇到了背包客"]


# ---------------------------------------------------------------- _log_turn、_loss


def test_log_turn_reads_battle_data_through_memory_and_logs_each_pokemon(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_log_turn：对手和队伍四只的战斗数据都是用 sw.memory.peek 读的（地址是 PK8 记录的地址往前 battle_data，
    长度 0x2C8），每只一行日志：种类、血量、能力值、能力变化、招式和剩余 PP。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session(data=battle_memory())
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    move = sw.data.pokemon_object(OPPONENT).moves[0]
    data = bytearray(BATTLE_DATA_SIZE)
    data[0:6] = (
        (321).to_bytes(2, "little") + (200).to_bytes(2, "little") + (150).to_bytes(2, "little")
    )
    for index, stat in enumerate([11, 22, 33, 44, 55]):
        data[0x232 + 2 * index : 0x234 + 2 * index] = stat.to_bytes(2, "little")
    data[0x244:0x24B] = bytes([6, 7, 5, 6, 6, 6, 6])
    data[0x258:0x25A] = move.id_num.to_bytes(2, "little")
    data[0x25C], data[0x25D] = 9, 15
    data[0x258 + 28 : 0x25A + 28] = (9999).to_bytes(2, "little")
    data[0x25C + 28], data[0x25D + 28] = 3, 5
    opponent_address = ADDRESSES.opponent - ADDRESSES.battle_data
    memory: Any = sw.memory
    memory.data[opponent_address] = bytes(data)
    module._log_turn(sw, war)
    assert memory.reads == [
        ("peek", address - ADDRESSES.battle_data, BATTLE_DATA_SIZE)
        for address in (ADDRESSES.opponent, *ADDRESSES.party)
    ]
    messages = logged(caplog)
    assert (
        f"回合数据 对手 {OPPONENT}（种类 321）：血量 150/200，能力 [11, 22, 33, 44, 55]，"
        f"变化 [0, 1, -1, 0, 0, 0, 0]，招式 {move.name()} 9/15、9999 3/5"
    ) in messages
    assert sum(message.startswith("回合数据 ") for message in messages) == 5
    assert any(message.startswith(f"回合数据 队友3 {TEAM[3]}（种类 0）") for message in messages)


def test_loss_with_lives_left_is_logged_as_overtime(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_loss：命没扣完（还剩 2 条）就是超回合输的：日志里写「超回合：回合用完还没打倒对手」，
    这场倒下的 2 次记进 game.faints。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    war.faints = 2
    module._loss(sw, war)
    assert sw.game.faints == [2]
    assert "战败（超回合：回合用完还没打倒对手），这一场倒下 2 次，还剩 2 条命" in logged(caplog)


def test_loss_with_no_lives_left_is_logged_as_wipe_out(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_loss：命扣到 0（前面倒下 1 次，这场倒下 3 次）就是团灭：日志里写「团灭」，这场的 3 次记进 game.faints。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    sw.game.faints = [1]
    war.faints = 3
    module._loss(sw, war)
    assert sw.game.faints == [1, 3]
    assert "战败（团灭），这一场倒下 3 次，还剩 0 条命" in logged(caplog)


# ---------------------------------------------------------------- _choose_move


def fake_best_move(
    results: list[tuple[int, float, bool]], calls: list[tuple[bool, set[int]]]
) -> Any:
    """代替 War.best_move：按顺序返回 results 里的结果（用完后一直返回最后一个），记下每次收到的
    (能不能极巨化, 这回合被封住的招式序号)。
    """

    def best_move(can_dynamax: bool, blocked: set[int]) -> tuple[int, float, bool]:
        calls.append((can_dynamax, set(blocked)))
        return results[min(len(calls) - 1, len(results) - 1)]

    return best_move


def test_choose_move_switches_to_another_move_when_first_one_is_blocked(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """第 2 个招式（序号 1）被封住（出现「无法使出」）：等「无法使出」消失、回到招式列表，
    下一次选招式时序号 1 在 blocked 里，换成第 3 个招式（序号 2）：光标往下推一格，按 A 出招；
    按过的键是 A、A，用掉的是序号 2 的 PP，不是序号 1 的。
    """
    sw = make_lair_session(
        [
            move_list(fake_images, 1),
            move_list(fake_images, 1),
            move_list(fake_images, None, hint=False, blocked=True),
            move_list(fake_images, None, hint=False, blocked=True),
            move_list(fake_images, None, hint=False, blocked=True),
            move_list(fake_images, 1),
            move_list(fake_images, 1),
            move_list(fake_images, 2),
            move_list(fake_images, 2),
            used(fake_images),
            used(fake_images),
            used(fake_images),
            used(fake_images),
        ],
        data=battle_memory(),
    )
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    calls: list[tuple[bool, set[int]]] = []
    monkeypatch.setattr(war, "best_move", fake_best_move([(1, 2.0, False), (2, 1.5, False)], calls))
    module._choose_move(sw, war)
    assert calls == [(False, set()), (False, {1})]
    assert controller.pressed == ["A", "A"]
    assert controller.sticks == [("LEFT", 0, -Controller.STICK_MAX, STICK_TICK)]
    assert war.own.pp[1] == 10
    assert war.own.pp[2] < 10


def test_choose_move_raises_runtime_error_when_all_four_moves_are_blocked(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四个招式一个一个试，都被封住：抛 RuntimeError，报错里有「四个招式都用不了」；
    选了四次，blocked 依次是空、{0}、{0,1}、{0,1,2}。
    """
    sw = make_lair_session([move_list(fake_images, 0)], data=battle_memory())
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    calls: list[tuple[bool, set[int]]] = []
    monkeypatch.setattr(
        war,
        "best_move",
        fake_best_move([(0, 1.0, False), (1, 1.0, False), (2, 1.0, False), (3, 1.0, False)], calls),
    )
    monkeypatch.setattr(module, "_use_move", lambda sw: False)
    monkeypatch.setattr(module, "_move_cursor_to", lambda sw, image, target: None)
    with pytest.raises(RuntimeError, match="四个招式都用不了"):
        module._choose_move(sw, war)
    assert [blocked for _, blocked in calls] == [set(), {0}, {0, 1}, {0, 1, 2}]


def test_choose_move_dynamaxes_when_best_move_says_so(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """画面上有极巨化按钮，best_move 说要极巨化：调 _dynamax，自己进入极巨化（持续 3 回合），
    best_move 收到的 can_dynamax 是 True，用的是极巨招式。
    """
    sw = make_lair_session([move_list(fake_images, 2, dynamax=True)], data=battle_memory())
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    calls: list[tuple[bool, set[int]]] = []
    monkeypatch.setattr(war, "best_move", fake_best_move([(2, 3.0, True)], calls))
    after = cast(ImageChecker, fake_images.image(move_list(fake_images, 2)))
    dynamaxed: list[LairSession] = []
    monkeypatch.setattr(module, "_dynamax", lambda sw: dynamaxed.append(sw) or after)
    monkeypatch.setattr(module, "_use_move", lambda sw: True)
    module._choose_move(sw, war)
    assert calls == [(True, set())]
    assert dynamaxed == [sw]
    assert war.own.dynamax is True
    assert war.dynamax_turns == 3


def test_choose_move_raises_timeout_error_when_move_list_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """按 A 之后招式列表一直不出现（看不到光标）：抛 TimeoutError，报错里有「招式列表」，按的都是 A。"""
    sw = make_lair_session([fight(fake_images)], data=battle_memory())
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    with pytest.raises(TimeoutError, match="招式列表"):
        module._choose_move(sw, war)
    assert set(controller.pressed) == {"A"}


def test_choose_move_raises_timeout_error_when_blocked_text_never_goes_away(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    make_pkhex: Callable[..., Any],
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """招式被封住之后「无法使出」一直不消失、回不到招式列表：抛 TimeoutError，报错里有「回到招式列表」。"""
    sw = make_lair_session(
        [
            move_list(fake_images, 1),
            move_list(fake_images, 1),
            move_list(fake_images, None, hint=False, blocked=True),
        ],
        data=battle_memory(),
    )
    war = make_war(sw, prepare_run, monkeypatch, make_pkhex)
    monkeypatch.setattr(war, "best_move", fake_best_move([(1, 1.0, False)], []))
    with pytest.raises(TimeoutError, match="回到招式列表"):
        module._choose_move(sw, war)


# ---------------------------------------------------------------- _use_move


def test_use_move_presses_a_and_returns_true_when_move_is_used(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """按 A 出招，招式列表消失，出现「使出了」（没有选目标的界面）：返回 True，按过的键是 A。"""
    sw = make_lair_session(
        [
            move_list(fake_images, 1),
            used(fake_images),
        ]
    )
    assert module._use_move(sw) is True
    assert controller.pressed == ["A"]


def test_use_move_returns_false_when_move_is_blocked(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """按 A 之后出现「无法使出」：返回 False，只按了一次 A，不去按选目标的键。"""
    sw = make_lair_session(
        [move_list(fake_images, 1), move_list(fake_images, None, hint=False, blocked=True)]
    )
    assert module._use_move(sw) is False
    assert controller.pressed == ["A"]


def test_use_move_does_not_move_cursor_when_several_cards_have_cursor(
    make_lair_session: SessionFactory,
    fake_images: ImageFactory,
    controller: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """选目标界面上我方四张卡片同时带光标（对象是固定的一组，比如广域防守）：不移光标，直接按 A 到「使出了」，
    日志里有「好几个光标」；按过的键是 A、A。
    """
    caplog.set_level(logging.DEBUG)
    group = target_screen(fake_images, [1, 2, 3, 4])
    sw = make_lair_session([move_list(fake_images, 0), group, group, group, used(fake_images)])
    assert module._use_move(sw) is True
    assert controller.pressed == ["A", "A"]
    assert any("好几个光标" in record.getMessage() for record in caplog.records)


def test_use_move_moves_target_cursor_off_unselectable_card_then_confirms(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """选目标界面光标停在对手卡片上，但那张卡片不能选（比如花瓣舞只能选自己）：先按 DDOWN 把光标移到我方那一排
    第一张（能选的），再按 A 到「使出了」；按过的键是 A、DDOWN、A。
    """
    stuck = target_screen(fake_images, [0])
    moved = target_screen(fake_images, [1], selectable=[1])
    sw = make_lair_session(
        [
            move_list(fake_images, 0),
            stuck,
            stuck,
            stuck,
            stuck,
            stuck,
            stuck,
            stuck,
            moved,
            moved,
            moved,
            used(fake_images),
        ]
    )
    assert module._use_move(sw) is True
    assert controller.pressed == ["A", "DDOWN", "A"]


def test_use_move_leaves_cursor_alone_when_it_is_on_selectable_card(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """选目标界面光标已经在能选的卡片上：不移光标，按 A 到「使出了」，按过的键是 A、A。"""
    ready = target_screen(fake_images, [0], selectable=[0])
    sw = make_lair_session(
        [move_list(fake_images, 0), ready, ready, ready, ready, used(fake_images)]
    )
    assert module._use_move(sw) is True
    assert controller.pressed == ["A", "A"]


def test_use_move_raises_timeout_error_when_move_list_never_disappears(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """按 A 之后招式列表（上方的「招式说明」）一直不消失：抛 TimeoutError，报错里有「招式列表消失」。"""
    sw = make_lair_session([move_list(fake_images, 1)])
    with pytest.raises(TimeoutError, match="招式列表消失"):
        module._use_move(sw)
    assert set(controller.pressed) == {"A"}


def test_use_move_raises_timeout_error_when_nothing_happens_after_move_list_closes(
    make_lair_session: SessionFactory, fake_images: ImageFactory
) -> None:
    """招式列表消失之后既没有「无法使出」、选目标界面，也没有「使出了」：抛 TimeoutError，报错里有「出招」。"""
    sw = make_lair_session([move_list(fake_images, 1), fake_images.add()])
    with pytest.raises(TimeoutError, match="无法使出、选目标的界面或者出招"):
        module._use_move(sw)


def test_use_move_raises_timeout_error_when_move_is_never_used(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """光标已经在能选的卡片上、按 A 之后一直没有「使出了」：抛 TimeoutError，报错里有「出招」，之后按的都是 A。"""
    ready = target_screen(fake_images, [0], selectable=[0])
    sw = make_lair_session([move_list(fake_images, 0), ready])
    with pytest.raises(TimeoutError, match="出招$"):
        module._use_move(sw)
    assert set(controller.pressed) == {"A"}


def test_use_move_raises_timeout_error_when_target_cursor_never_moves(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """光标停在不能选的卡片上、按 DDOWN 光标也不动：抛 TimeoutError，报错里有「选目标的光标移动」。"""
    sw = make_lair_session([move_list(fake_images, 0), target_screen(fake_images, [0])])
    with pytest.raises(TimeoutError, match="选目标的光标移动"):
        module._use_move(sw)
    assert controller.pressed[0] == "A"
    assert set(controller.pressed[1:]) == {"DDOWN"}


# ---------------------------------------------------------------- _move_cursor_to


def test_move_cursor_to_pushes_stick_down_until_cursor_reaches_target_row(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """光标在第 1 行、目标是第 3 行：往下推两次（-stick_max），每次推完光标往下一行，到了就停。"""
    row0 = move_list(fake_images, 0, hint=False)
    row1 = move_list(fake_images, 1, hint=False)
    row2 = move_list(fake_images, 2, hint=False)
    sw = make_lair_session([row0, row1, row1, row2])
    module._move_cursor_to(sw, cast(ImageChecker, fake_images.image(row0)), 2)
    assert controller.sticks == [("LEFT", 0, -Controller.STICK_MAX, STICK_TICK)] * 2


def test_move_cursor_to_does_not_push_stick_when_cursor_is_on_target_row(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """光标已经在目标行上：不推摇杆。"""
    row1 = move_list(fake_images, 1, hint=False)
    sw = make_lair_session([row1])
    module._move_cursor_to(sw, cast(ImageChecker, fake_images.image(row1)), 1)
    assert controller.sticks == []


def test_move_cursor_to_raises_runtime_error_after_four_pushes_without_reaching_target(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """每次推完光标都在第 1、2 行之间来回跳，推满 4 次还没到第 4 行：抛 RuntimeError，
    报错里有「招式光标移了 4 次，还是没到第 4 行」。
    """
    row0 = move_list(fake_images, 0, hint=False)
    row1 = move_list(fake_images, 1, hint=False)
    sw = make_lair_session([row0, row1, row1, row0, row0, row1, row1, row0])
    with pytest.raises(RuntimeError, match="招式光标移了 4 次，还是没到第 4 行"):
        module._move_cursor_to(sw, cast(ImageChecker, fake_images.image(row0)), 3)
    assert len(controller.sticks) == 4


def test_move_cursor_to_raises_timeout_error_when_cursor_never_moves(
    make_lair_session: SessionFactory, fake_images: ImageFactory
) -> None:
    """推了摇杆光标也一直不动：抛 TimeoutError，报错里有「招式光标移动」。"""
    row0 = move_list(fake_images, 0, hint=False)
    sw = make_lair_session([row0])
    with pytest.raises(TimeoutError, match="招式光标移动"):
        module._move_cursor_to(sw, cast(ImageChecker, fake_images.image(row0)), 2)


# ---------------------------------------------------------------- _dynamax


def test_dynamax_retries_a_when_cursor_does_not_leave_button(
    make_lair_session: SessionFactory,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """往左推摇杆把光标移到极巨化按钮上，按 A 之后光标还停在按钮上（按键丢了）：等 2 秒再按一次 A，
    光标离开按钮、招式列表换成极巨招式之后返回；摇杆推了一次，按过的键是 A、A。这条要等 2 秒以上。
    """
    monkeypatch.setattr(WaitConfig, "timeout", 5.0)

    def ratio(rect: Rect, lower: Any) -> float:
        presses = len(controller.pressed)
        if rect == RECTS.dynamax_cursor:
            return 0.5 if presses < 2 else 0.0
        if rect == RECTS.move_cursor_rects[0]:
            return 0.5 if presses >= 2 else 0.0
        return 0.0

    sw = make_lair_session([fake_images.add(ratio_fn=ratio)])
    module._dynamax(sw)
    assert controller.sticks == [("LEFT", -Controller.STICK_MAX, 0, STICK_TICK)]
    assert controller.pressed == ["A", "A"]


def test_dynamax_raises_timeout_error_when_cursor_never_reaches_button(
    make_lair_session: SessionFactory, fake_images: ImageFactory
) -> None:
    """光标一直没移到极巨化按钮上：抛 TimeoutError，报错里有「光标移到极巨化按钮上」。"""
    sw = make_lair_session([fake_images.add()])
    with pytest.raises(TimeoutError, match="光标移到极巨化按钮上"):
        module._dynamax(sw)


def test_dynamax_raises_timeout_error_when_cursor_never_leaves_button(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """按 A 之后光标一直不离开极巨化按钮：抛 TimeoutError，报错里有「光标离开极巨化按钮」，按过 A。"""
    sw = make_lair_session([fake_images.add(ratios=marker(RECTS.dynamax_cursor))])
    with pytest.raises(TimeoutError, match="光标离开极巨化按钮"):
        module._dynamax(sw)
    assert controller.pressed == ["A"]


def test_dynamax_raises_timeout_error_when_move_list_never_switches_to_max_moves(
    make_lair_session: SessionFactory, fake_images: ImageFactory, controller: Any
) -> None:
    """光标离开了按钮，但招式列表一直没有光标（没换成极巨招式）：抛 TimeoutError，报错里有「换成极巨招式」。"""

    def ratio(rect: Rect, lower: Any) -> float:
        on_button = rect == RECTS.dynamax_cursor and not controller.pressed
        return 0.5 if on_button else 0.0

    sw = make_lair_session([fake_images.add(ratio_fn=ratio)])
    with pytest.raises(TimeoutError, match="换成极巨招式"):
        module._dynamax(sw)
