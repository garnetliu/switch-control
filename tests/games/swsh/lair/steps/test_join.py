"""steps.join：从科学家面前开始，选首领、选首发和路线，返回 "path"。

读内存都走 sw.memory：假 Memory 按地址给 Lair note（四个 species）和这一局的 seed，记下读过的地址。
菜单、选宝可梦界面这些没有截图（logs/keep 里没有），用假截图（conftest 的 fake_images）；
读地图类型用真机截图（tests/images 里的地图类型和路线上的界面）。
选初始宝可梦界面的三只候选用假的内存记录（conftest 的 starters）。
基准 seed 的图：2x2，布局 4，首发流氓熊猫，路线 斧牙龙 → 龟足巨铠 → 狃拉，首领按 seed 算是 moltres。
期望值是改动前的代码跑出来的。
"""

import importlib
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.map import Maps, MapType
from control_switch.games.swsh.lair.session import LairSession
from control_switch.types import Rect

module: ModuleType = importlib.import_module("control_switch.games.swsh.lair.steps.join")
join = module.join

IMAGES = Path(__file__).resolve().parents[4] / "images"
MAP_2X2 = (IMAGES / "地图类型-2x2.jpg").read_bytes()
FORK = (IMAGES / "路线上的界面-要走哪条路.jpg").read_bytes()

RECTS = GameConfig.rects
ADDRESSES = GameConfig.addresses
SEED = 3076008315599927110
SessionFactory = Callable[..., LairSession]
PrepareRun = Callable[..., Any]
Starters = Callable[..., Lair]
ImageFactory = Any

# 四个 Lair note 里的 species：tapu-koko、tapu-lele、xerneas 的编号，最后一个不是首领
NOTES = [785, 786, 716, 0]
OPTION_RECT: Rect = ((0.7, 0.5), (0.8, 0.55))
ROUTE = [[0, 0], [1, 1], [2, 2], [3, 1], [4, 0]]


def notes_memory(notes: list[int] = NOTES, seed: int | None = SEED) -> dict[int, bytes]:
    """假 Memory：四个 Lair note 开头 2 字节的 species，和这一局的 seed（8 字节小端）。"""
    data = {
        address: number.to_bytes(2, "little")
        for address, number in zip(ADDRESSES.lair_notes, notes, strict=True)
    }
    if seed is not None:
        data[ADDRESSES.seed] = seed.to_bytes(8, "little")
    return data


def menu_options(*names: str) -> list[tuple[str, Rect]]:
    return [(name, OPTION_RECT) for name in names]


def legend_menu(images: ImageFactory, selected: int = 1) -> bytes:
    """传说菜单：koko、lele、xerneas 和最后一项「不指定」，对话框里有字。"""
    return images.add(
        texts={RECTS.white_center_line1: "请问您要去找哪个宝可梦呢"},
        menu=(RECTS.menu_search, menu_options("闪电", "蝶蝶", "哲尔尼亚斯", "不指定")),
        selected=selected,
    )


def lobby_menu(images: ImageFactory) -> bytes:
    """极巨大冒险的大厅菜单，第 2 项是「发起单人挑战！」，光标在它上面。"""
    return images.add(
        menu=(RECTS.lobby_menu, menu_options("加入", "发起单人挑战！", "返回")),
        selected=1,
    )


def plain(images: ImageFactory) -> bytes:
    return images.add()


def black(images: ImageFactory) -> bytes:
    return images.add(black=True)


def starter_screen(images: ImageFactory) -> bytes:
    """选初始宝可梦的界面：左上角有「按顺序选择」。"""
    return images.add(texts={RECTS.starter_hint: "按顺序选择"})


def cursor(images: ImageFactory, index: int) -> bytes:
    """选初始宝可梦界面，光标停在第 index 只上。"""
    return images.add(selected=index)


def fork_text(images: ImageFactory) -> bytes:
    """路线图出现：黑色中间面板写着「要走哪条路？」。"""
    return images.add(texts={RECTS.black_center_line1: "要走哪条路？"})


class FakeReader:
    """代替 MapTypeReader：不管看到什么画面，都认出来是 2x2。"""

    def __init__(self, sw: object) -> None:
        pass

    def update(self, image: object) -> str | None:
        return "2x2"


def legends_from_config(sw: LairSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """caught_legends 换成返回和配置里写的一样的结果（存档数据块的表这里不用管）。"""
    caught = tuple(sw.config.lair_caught)
    unlocked = sw.config.lair_ultra_beasts_unlocked
    monkeypatch.setattr(sw, "caught_legends", lambda: (caught, unlocked))


class NoRecords:
    """读内存记录就报错的假 Pk8Reader：用来确认没有去读。"""

    def read_pk8(self, addresses: list[int]) -> list[dict[str, Any]]:
        raise AssertionError(f"不该去读内存记录：{addresses}")


def logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


# ---------------------------------------------------------------- join：整个步骤


def test_join_selects_boss_starter_and_route_and_returns_path(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    controller: Any,
) -> None:
    """配置里的首领是 tapu-lele（在传说菜单的第 2 项）：按过的键是 A（保存时到黑屏）、A（大厅里确认）、
    A（确认首发），返回 "path"；记下的有：这一局的 seed、首发（第 1 位）、路线、地图类型 2x2、
    路线图存了一张。读内存读的是四个 Lair note 和 seed（都是 sw.memory）。
    """
    monkeypatch.setattr(module, "MapTypeReader", FakeReader)
    sw = make_lair_session(
        [
            legend_menu(fake_images),
            plain(fake_images),
            black(fake_images),
            lobby_menu(fake_images),
            starter_screen(fake_images),
            cursor(fake_images, 0),
            plain(fake_images),
            plain(fake_images),
            fork_text(fake_images),
        ],
        data=notes_memory(),
    )
    starters(sw)
    legends_from_config(sw, monkeypatch)
    assert join(sw) == "path"
    assert controller.pressed == ["A", "A", "A"]
    assert sw.game.seed == SEED
    assert sw.game.boss == "tapu-lele"
    assert sw.game.lock_pokemon_index == 0
    assert sw.game.candidates == ["pangoro", "galvantula", "maractus"]
    assert sw.game.maps is not None
    assert sw.game.maps["type"] == "2x2"
    assert sw.game.maps["route"] == ROUTE
    assert (sw.config.log_dir / "maps" / "2x2-4.jpg").exists()
    memory: Any = sw.memory
    assert [read for read in memory.reads if read[1] in ADDRESSES.lair_notes] == [
        ("peek", address, 2) for address in ADDRESSES.lair_notes
    ]
    assert ("peek", ADDRESSES.seed, 8) in memory.reads


def test_join_with_unspecified_boss_uses_boss_computed_from_seed(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    controller: Any,
) -> None:
    """配置里的首领是 None（选「不指定」，菜单最后一项）：读到 seed 之后用 Lair.boss() 算这一局的首领
    （基准 seed 算出来是 moltres），记进 game.boss，日志里写明按 seed 算的首领。首领不一样，
    选的首发也不一样（第 2 位电蜘蛛），光标从第 1 只往下按 DDOWN 一次；按过的键是 A、A、DDOWN、A。
    """
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(GameConfig, "boss", None)
    monkeypatch.setattr(module, "MapTypeReader", FakeReader)
    sw = make_lair_session(
        [
            legend_menu(fake_images, selected=3),
            plain(fake_images),
            black(fake_images),
            lobby_menu(fake_images),
            starter_screen(fake_images),
            cursor(fake_images, 0),
            cursor(fake_images, 0),
            cursor(fake_images, 1),
            plain(fake_images),
            plain(fake_images),
            fork_text(fake_images),
        ],
        data=notes_memory(),
    )
    starters(sw)
    legends_from_config(sw, monkeypatch)
    assert join(sw) == "path"
    assert controller.pressed == ["A", "A", "DDOWN", "A"]
    assert sw.game.boss == "moltres"
    assert sw.game.lock_pokemon_index == 1
    assert any("选的是不指定，按 seed 算这一局的首领是" in message for message in logged(caplog))


def test_join_without_lair_notes_skips_legend_menu_and_uses_boss_computed_from_seed(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    controller: Any,
) -> None:
    """四个 Lair note 都是 0（没有记下神兽的位置）：研究员不问找哪只，没有传说菜单。
    配置里的首领是 tapu-lele 也改成不指定，日志里有警告；一直按 A 到保存时黑屏，进大厅选单人挑战，
    首领按 seed 算（moltres），选的首发是第 2 位，按过的键是 A（对话）、A（大厅里确认）、DDOWN、A。
    """
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(module, "MapTypeReader", FakeReader)
    sw = make_lair_session(
        [
            plain(fake_images),
            black(fake_images),
            lobby_menu(fake_images),
            starter_screen(fake_images),
            cursor(fake_images, 0),
            cursor(fake_images, 0),
            cursor(fake_images, 1),
            plain(fake_images),
            plain(fake_images),
            fork_text(fake_images),
        ],
        data=notes_memory([0, 0, 0, 0]),
    )
    starters(sw)
    legends_from_config(sw, monkeypatch)
    assert join(sw) == "path"
    assert controller.pressed == ["A", "A", "DDOWN", "A"]
    assert sw.game.boss == "moltres"
    messages = logged(caplog)
    assert any(
        "Lair note 里一只神兽都没有" in message and "改成不指定" in message for message in messages
    )
    assert not any("选择传说Boss选中了" in message for message in messages)


def test_select_target_picks_first_menu_item_and_warns_when_configured_boss_is_not_in_menu(
    make_lair_session: SessionFactory,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """配置里的首领 mewtwo 不在 Lair note 里（已经带走了）：这一局改成刷菜单第一项 tapu-koko，选的是第 1 项，
    返回 "tapu-koko"，日志里有「Lair note 里没有…，这一局改成刷…」的警告。
    """
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(GameConfig, "boss", "mewtwo")
    sw = make_lair_session(
        [
            legend_menu(fake_images, selected=0),
            plain(fake_images),
            black(fake_images),
            lobby_menu(fake_images),
        ],
        data=notes_memory(),
    )
    assert module._select_target(sw) == "tapu-koko"
    messages = logged(caplog)
    assert any(
        "Lair note 里没有「" in message and "这一局改成刷「" in message for message in messages
    )
    assert any("选择传说Boss选中了第 1 项" in message for message in messages)


def test_join_raises_timeout_error_when_legend_menu_never_appears(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一直按 A 也出现不了传说菜单：抛 TimeoutError，报错里有「传说菜单」，按的都是 A。"""
    sw = make_lair_session([plain(fake_images)], data=notes_memory())
    starters(sw)
    legends_from_config(sw, monkeypatch)
    with pytest.raises(TimeoutError, match="传说菜单"):
        join(sw)
    assert set(controller.pressed) == {"A"}


def test_join_raises_timeout_error_when_screen_never_turns_black_while_saving(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """选好传说之后一直按 A，画面一直不变黑：抛 TimeoutError，报错里有「保存时画面变黑」。"""
    sw = make_lair_session([legend_menu(fake_images), plain(fake_images)], data=notes_memory())
    starters(sw)
    legends_from_config(sw, monkeypatch)
    with pytest.raises(TimeoutError, match="保存时画面变黑"):
        join(sw)


def test_join_raises_timeout_error_when_lobby_never_appears(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存之后大厅菜单一直不出现：抛 TimeoutError，报错里有「极巨大冒险的大厅」。"""
    sw = make_lair_session(
        [legend_menu(fake_images), plain(fake_images), black(fake_images)], data=notes_memory()
    )
    starters(sw)
    legends_from_config(sw, monkeypatch)
    with pytest.raises(TimeoutError, match="极巨大冒险的大厅"):
        join(sw)


# ---------------------------------------------------------------- _read_legends


def test_read_legends_writes_caught_legends_into_config(
    make_lair_session: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """caught_legends 读出抓到的神兽和究极异兽解锁了：写进 sw.config（lair_caught、
    lair_ultra_beasts_unlocked），和配置里写的不一样时日志里有说明。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    monkeypatch.setattr(sw, "caught_legends", lambda: (("xerneas", "mewtwo"), True))
    module._read_legends(sw)
    assert sw.config.lair_caught == ("xerneas", "mewtwo")
    assert sw.config.lair_ultra_beasts_unlocked is True
    messages = logged(caplog)
    assert any(
        "不一样，按存档的算" in message and "存档里抓过的神兽" in message for message in messages
    )
    assert any("存档里究极异兽解锁了" in message for message in messages)


def test_read_legends_logs_nothing_special_when_save_matches_config(
    make_lair_session: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """读出来的和配置里写的一样：不记「不一样」的说明。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    caught = tuple(sw.config.lair_caught)
    unlocked = sw.config.lair_ultra_beasts_unlocked
    monkeypatch.setattr(sw, "caught_legends", lambda: (caught, unlocked))
    module._read_legends(sw)
    assert not any("不一样" in message for message in logged(caplog))
    assert sw.config.lair_caught == caught


def test_read_legends_falls_back_to_config_when_caught_legends_raises(
    make_lair_session: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """caught_legends 抛 RuntimeError（读不出来）：不抛错，配置不变（还是配置里手写的），日志里有警告。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    before = (sw.config.lair_caught, sw.config.lair_ultra_beasts_unlocked)

    def fail() -> tuple[tuple[str, ...], bool]:
        raise RuntimeError("读不出来")

    monkeypatch.setattr(sw, "caught_legends", fail)
    module._read_legends(sw)
    assert (sw.config.lair_caught, sw.config.lair_ultra_beasts_unlocked) == before
    assert any("没读出抓过哪些神兽，用配置里写的" in message for message in logged(caplog))


# ---------------------------------------------------------------- _select_boss


def test_select_boss_returns_none_and_last_index_when_target_is_none(
    make_lair_session: SessionFactory,
) -> None:
    """target 是 None（选「不指定」）：返回 (None, 菜单里 boss 的个数)，「不指定」是菜单最后一项；
    不是 boss 的 note（species 是 0）不进菜单。读的是四个 Lair note，每个 2 字节。
    """
    sw = make_lair_session(data=notes_memory())
    assert module._select_boss(sw, None) == (None, 3)
    memory: Any = sw.memory
    assert memory.reads == [("peek", address, 2) for address in ADDRESSES.lair_notes]


def test_select_boss_returns_target_and_its_index_when_in_menu(
    make_lair_session: SessionFactory,
) -> None:
    """target 在菜单里：返回 (target, 它在菜单里的下标)，tapu-lele 是第 2 项，下标 1。"""
    sw = make_lair_session(data=notes_memory())
    assert module._select_boss(sw, "tapu-lele") == ("tapu-lele", 1)


def test_select_boss_returns_first_menu_item_when_target_is_not_in_menu(
    make_lair_session: SessionFactory,
) -> None:
    """target 不在菜单里（那只已经带走了）：选菜单第一项，返回 (tapu-koko, 0)。"""
    sw = make_lair_session(data=notes_memory())
    assert module._select_boss(sw, "mewtwo") == ("tapu-koko", 0)


def test_select_boss_returns_none_and_none_when_menu_is_empty(
    make_lair_session: SessionFactory,
) -> None:
    """四个 Lair note 里没有 boss（没有传说菜单）：target 是 tapu-lele 也返回 (None, None)，不抛错。"""
    sw = make_lair_session(data=notes_memory([0, 0, 0, 0]))
    assert module._select_boss(sw, "tapu-lele") == (None, None)


def test_select_boss_with_none_target_and_empty_menu_returns_none_and_none(
    make_lair_session: SessionFactory,
) -> None:
    """target 是 None、菜单是空的：返回 (None, None)。"""
    sw = make_lair_session(data=notes_memory([0, 0, 0, 0]))
    assert module._select_boss(sw, None) == (None, None)


# ---------------------------------------------------------------- _read_seed


def test_read_seed_reads_eight_bytes_little_endian_through_memory(
    make_lair_session: SessionFactory,
) -> None:
    """_read_seed：读 seed 地址的 8 个字节，按小端转成整数。"""
    sw = make_lair_session(data=notes_memory())
    assert module._read_seed(sw) == SEED
    memory: Any = sw.memory
    assert memory.reads == [("peek", ADDRESSES.seed, 8)]


def test_read_seed_raises_runtime_error_when_length_is_wrong(
    make_lair_session: SessionFactory,
) -> None:
    """读到的不是 8 个字节：抛 RuntimeError，报错里有「路线 seed 读取长度错误」和读到的长度。"""
    sw = make_lair_session(data={ADDRESSES.seed: b"\x01\x02\x03"})
    with pytest.raises(RuntimeError, match="路线 seed 读取长度错误：3"):
        module._read_seed(sw)


# ---------------------------------------------------------------- _select_starter


def test_select_starter_raises_timeout_error_when_screen_never_appears(
    make_lair_session: SessionFactory, fake_images: ImageFactory
) -> None:
    """选宝可梦的界面（左上角「按顺序选择」）一直不出现：抛 TimeoutError，报错里有「选宝可梦的界面」。"""
    sw = make_lair_session([plain(fake_images)], data=notes_memory())
    with pytest.raises(TimeoutError, match="选宝可梦的界面"):
        module._select_starter(sw, "tapu-lele")


def test_select_starter_reuses_locked_choice_when_boss_and_seed_match(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """这张图锁定了（lock_path）、boss 和 seed 都对得上：返回 True，沿用上一局的首发和路线，
    不再从内存读候选（假 pkhex 里没有记录，读了就会报错）；按 A 确认首发；日志里有「锁定了这张图」。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session(
        [starter_screen(fake_images), cursor(fake_images, 0)], data=notes_memory()
    )
    prepare_run(sw)
    sw.game.lock_path = True
    monkeypatch.setattr(sw, "pkhex", NoRecords())
    maps_before = sw.game.maps
    assert module._select_starter(sw, "tapu-lele") is True
    assert controller.pressed == ["A"]
    assert sw.game.maps is maps_before
    assert any("锁定了这张图，沿用上一局的 starter 选择" in message for message in logged(caplog))


def test_select_starter_assigns_new_starter_when_not_locked(
    make_lair_session: SessionFactory,
    starters: Starters,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """没有锁定：返回 False，从内存读三只候选，按 seed 选首发和路线（首发第 1 位流氓熊猫，路线
    (1,1) → (2,2) → (3,1)），路线分记成改动前的代码算出来的 20.356，按 A 确认首发。
    """
    sw = make_lair_session(
        [starter_screen(fake_images), cursor(fake_images, 0)], data=notes_memory()
    )
    lair = starters(sw)
    assert module._select_starter(sw, "tapu-lele") is False
    assert controller.pressed == ["A"]
    assert sw.game.lock_pokemon_index == 0
    assert sw.game.rental_pool == lair.candidates()
    assert sw.game.candidates == ["pangoro", "galvantula", "maractus"]
    assert sw.game.maps is not None
    assert sw.game.maps["route"] == ROUTE
    assert sw.game.route_score == pytest.approx(20.355610916828724)
    assert sw.game.stage_score == 0.0
    assert sw.game.boss_score == 0.0
    assert "pangoro" in sw.config.game_state_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------- _move_starter_cursor


def test_move_starter_cursor_pushes_down_until_cursor_reaches_locked_starter(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """选好的首发是第 3 只、光标在第 1 只：按 DDOWN 两次，光标每次往下一只，到了就停；按过的键是 DDOWN、DDOWN。"""
    sw = make_lair_session(
        [
            cursor(fake_images, 0),
            cursor(fake_images, 0),
            cursor(fake_images, 1),
            cursor(fake_images, 1),
            cursor(fake_images, 2),
        ]
    )
    prepare_run(sw)
    sw.game.lock_pokemon_index = 2
    module._move_starter_cursor(sw)
    assert controller.pressed == ["DDOWN", "DDOWN"]


def test_move_starter_cursor_does_not_press_when_cursor_is_already_on_starter(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """光标已经在选好的首发上：一个键都不按。"""
    sw = make_lair_session([cursor(fake_images, 0)])
    prepare_run(sw)
    module._move_starter_cursor(sw)
    assert controller.pressed == []


def test_move_starter_cursor_raises_timeout_error_when_cursor_never_visible(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """一直看不到光标：抛 TimeoutError，报错里有「选宝可梦的光标」。"""
    sw = make_lair_session([plain(fake_images)])
    prepare_run(sw)
    with pytest.raises(TimeoutError, match="选宝可梦的光标$"):
        module._move_starter_cursor(sw)


def test_move_starter_cursor_raises_timeout_error_when_cursor_never_moves(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """按了 DDOWN 光标也一直不动：抛 TimeoutError，报错里有「选宝可梦的光标移一格」。"""
    sw = make_lair_session([cursor(fake_images, 0)])
    prepare_run(sw)
    sw.game.lock_pokemon_index = 1
    with pytest.raises(TimeoutError, match="选宝可梦的光标移一格"):
        module._move_starter_cursor(sw)
    assert set(controller.pressed) == {"DDOWN"}


def test_move_starter_cursor_raises_runtime_error_when_cursor_keeps_missing_starter(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """每次按完光标都落在第 1、2 只之间来回跳，按满 3 次还没到第 3 只：抛 RuntimeError，
    报错里有「选宝可梦的光标移了 3 次，还是没到第 3 只」。
    """
    frames = [cursor(fake_images, 0)]
    for before, after in [(0, 1), (1, 0), (0, 1)]:
        frames += [cursor(fake_images, before), cursor(fake_images, after)]
    sw = make_lair_session(frames)
    prepare_run(sw)
    sw.game.lock_pokemon_index = 2
    with pytest.raises(RuntimeError, match="选宝可梦的光标移了 3 次，还是没到第 3 只"):
        module._move_starter_cursor(sw)


# ---------------------------------------------------------------- _select_path、_check_map_type


def test_select_path_keeps_route_when_locked_and_route_exists(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """kept 是 True（锁定的图）而且已经有路线：不读地图类型（一张图都不截），沿用路线，日志里有「沿用上一局的路线规划」。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    prepare_run(sw)
    module._select_path(sw, True)
    assert sw.frames == []
    assert sw.game.maps is not None
    assert sw.game.maps["route"] == ROUTE
    assert any("沿用上一局的路线规划" in message for message in logged(caplog))


def second_row_maps(sw: LairSession) -> Maps:
    """地图类型-2x2.jpg 上第 2 层四列依次是飞行、钢、格斗、电；第 3 层都是冰（glalie）：
    把这一局的 maps 里第 2、3 层的遭遇换成对得上这张截图的，MapTypeReader 才认得出来。
    """
    maps = sw.game.maps
    assert maps is not None
    rentals = sw.data.rental_pokemon()
    for row, names in (("2", ["noctowl", "klang", "machoke", "raichu"]), ("3", ["glalie"] * 4)):
        maps["rows"][row] = [
            {"col": col, "type": rentals[name]["type_ids"][0], "encounter": name}
            for col, name in enumerate(names)
        ]
    return maps


def test_check_map_type_keeps_route_and_saves_picture_when_type_matches(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """画面上的地图类型（2x2）和 seed 算的一样：路线不变，不记警告；这种类型、这个布局的路线图存了一张
    （log_dir/maps/2x2-4.jpg）。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session([MAP_2X2, MAP_2X2, FORK])
    prepare_run(sw)
    maps = second_row_maps(sw)
    module._check_map_type(sw)
    assert maps["type"] == "2x2"
    assert maps["route"] == ROUTE
    assert (sw.config.log_dir / "maps" / "2x2-4.jpg").exists()
    assert not any("按画面上的重新选路线" in message for message in logged(caplog))


def test_check_map_type_reselects_route_when_screen_type_differs_from_seed(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """seed 算的是 2x3、画面上是 2x2：日志里有警告，类型改成画面上的 2x2，按 2x2 重新选路线
    （首发不变，路线是 (1,1) → (2,2) → (3,1)），状态存盘。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session([MAP_2X2, MAP_2X2, FORK])
    prepare_run(sw)
    maps = second_row_maps(sw)
    maps["type"] = cast(MapType, "2x3")
    maps["route"] = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]]
    module._check_map_type(sw)
    assert maps["type"] == "2x2"
    assert maps["route"] == ROUTE
    assert sw.game.lock_pokemon_index == 0
    messages = logged(caplog)
    assert any(
        "画面上的地图类型是 2x2，seed 算出来的是 2x3，按画面上的重新选路线" in message
        for message in messages
    )
    assert "type: 2x2" in sw.config.game_state_file.read_text(encoding="utf-8")


def test_check_map_type_assigns_route_when_there_is_none_yet(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """类型一样但还没有路线（route 是空的）：按画面上的类型选路线，路线是 (1,1) → (2,2) → (3,1)。"""
    sw = make_lair_session([MAP_2X2, MAP_2X2, FORK])
    prepare_run(sw)
    maps = second_row_maps(sw)
    maps["route"] = []
    module._check_map_type(sw)
    assert maps["route"] == ROUTE


def test_check_map_type_does_not_overwrite_saved_picture(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """这张路线图已经存过了：不再覆盖（文件内容不变）。"""
    sw = make_lair_session([MAP_2X2, MAP_2X2, FORK])
    prepare_run(sw)
    second_row_maps(sw)
    picture = sw.config.log_dir / "maps" / "2x2-4.jpg"
    picture.parent.mkdir(parents=True)
    picture.write_bytes(b"old")
    module._check_map_type(sw)
    assert picture.read_bytes() == b"old"


def test_check_map_type_raises_timeout_error_when_screen_stays_black(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """开场黑屏一直不结束：抛 TimeoutError，报错里有「开场黑屏结束」。"""
    sw = make_lair_session([black(fake_images)])
    prepare_run(sw)
    with pytest.raises(TimeoutError, match="开场黑屏结束"):
        module._check_map_type(sw)


def test_check_map_type_raises_timeout_error_when_route_screen_never_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """一直看到的是地图类型画面，「要走哪条路」一直不出现：抛 TimeoutError，报错里有「路线图一直没有出现」。"""
    sw = make_lair_session([MAP_2X2])
    prepare_run(sw)
    second_row_maps(sw)
    with pytest.raises(TimeoutError, match="路线图一直没有出现"):
        module._check_map_type(sw)


def test_check_map_type_raises_runtime_error_when_no_type_was_read(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """路线图出现之前一张认出地图类型的图都没有（直接就是「要走哪条路」）：抛 RuntimeError，报错里有「没读到路线图类型」。"""
    sw = make_lair_session([FORK])
    prepare_run(sw)
    with pytest.raises(RuntimeError, match="没读到路线图类型"):
        module._check_map_type(sw)


# ---------------------------------------------------------------- _matching_lair


def test_matching_lair_returns_lair_when_first_three_match(
    make_lair_session: SessionFactory,
) -> None:
    """按 seed 算的前 3 只租借和界面上的一样：返回不多取随机数的 Lair。"""
    sw = make_lair_session()
    lair = module._matching_lair(sw, SEED, ["pangoro", "galvantula", "maractus"])
    assert lair.candidates()[:3] == ["pangoro", "galvantula", "maractus"]


def test_matching_lair_draws_extra_random_numbers_when_first_try_does_not_match(
    make_lair_session: SessionFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """界面上的 3 只是多取 1 个随机数算出来的（galvantula、maractus、cofagrigus）：对上之后返回那个 Lair，
    日志里有「开头多取 1 个随机数后对上了」的警告。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    shown = ["galvantula", "maractus", "cofagrigus"]
    lair = module._matching_lair(sw, SEED, shown)
    assert lair.candidates()[:3] == shown
    assert any("开头多取 1 个随机数后对上了" in message for message in logged(caplog))


def test_matching_lair_raises_runtime_error_when_nothing_matches(
    make_lair_session: SessionFactory,
) -> None:
    """多取 0 到 lair_extra_max 个随机数都对不上界面上的 3 只：抛 RuntimeError，报错里有「对不上」。"""
    sw = make_lair_session()
    with pytest.raises(RuntimeError, match="对不上"):
        module._matching_lair(sw, SEED, ["没有", "这三", "只"])


# ---------------------------------------------------------------- _path_diagram、_name、_display_width


def test_path_diagram_draws_four_lines_with_chosen_route_marked(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """路线图画成 4 行：中文名，选的路线上的节点前面加 *，中间是 2x2 的连线，最后是首领。"""
    sw = make_lair_session()
    prepare_run(sw)
    assert module._path_diagram(sw) == [
        "     ┌心蝙蝠─────┬──冻原熊──────┬─爆炸头水牛─┐",
        "起点─┤           └──肯泰罗─────┐╞═*狃拉──────┼─卡璞・蝶蝶",
        "     └*斧牙龙────┬──*龟足巨铠──┼┼─煤炭龟─────┤",
        "                 └──堵拦熊─────┘└─战舞郎─────┘",
    ]


@pytest.mark.parametrize("map_type", ["2x3", "3x2"])
def test_path_diagram_uses_link_lines_of_the_map_type(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, map_type: str
) -> None:
    """地图类型是 2x3、3x2 时连线和 2x2 的不一样：画出来还是 4 行，起点那一段不变，连线不是 2x2 的那一套。"""
    sw = make_lair_session()
    prepare_run(sw)
    default = module._path_diagram(sw)
    assert sw.game.maps is not None
    sw.game.maps["type"] = cast(MapType, map_type)
    lines = module._path_diagram(sw)
    assert len(lines) == 4
    assert lines != default
    assert [line[:5] for line in lines] == [line[:5] for line in default]


def test_name_adds_form_in_brackets_for_regional_forms(make_lair_session: SessionFactory) -> None:
    """_name：宝可梦的中文名；name_id 以 -galar 结尾的在后面标「（伽勒尔）」，-alola 标「（阿罗拉）」，
    其他的不标。
    """
    sw = make_lair_session()
    plain_name = sw.data.pokemon_object("raichu").name(sw.config.language)
    assert module._name(sw, "raichu") == plain_name
    assert module._name(sw, "raichu-alola").endswith("（阿罗拉）")
    assert module._name(sw, "weezing-galar").endswith("（伽勒尔）")


@pytest.mark.parametrize(
    ("text", "width"), [("ab", 2), ("斧牙龙", 6), ("a斧", 3), ("ｘ", 2), ("", 0)]
)
def test_display_width_counts_wide_characters_as_two_columns(text: str, width: int) -> None:
    """_display_width：中文和全角字符算 2 列，半角字符算 1 列，空字符串是 0。"""
    assert module._display_width(text) == width
