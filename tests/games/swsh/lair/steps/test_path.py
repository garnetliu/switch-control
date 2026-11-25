"""steps.path：处理冒险路上的分支（背包客、研究员、树果、岔路口），直到进入战斗，返回 "battle"。

认分支的画面用真机截图（tests/images：出现了、遇到了背包客、遇到了研究员、树果、要走哪条路、
背包客的道具面板和消失、树果的对话结束、研究员问换不换和问话消失）。
岔路口光标在两列之间移动的画面没有截图，用假截图（conftest 的 fake_images）：
光标区域里白色占比高的那一列就是光标所在的列。
选好首发和路线之后的状态用 prepare_run 按 seed 算出来（基准 seed，2x2 的图，布局 4，
路线 (1,1) → (2,2) → (3,1)）；需要的地方把 route 改成别的。路上的事件表在临时目录里。
"""

import importlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from control_switch.config import StickConfig
from control_switch.games.swsh.lair import upstream
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.next_columns import next_columns
from control_switch.games.swsh.lair.session import LairSession
from control_switch.vision import ImageChecker

module: ModuleType = importlib.import_module("control_switch.games.swsh.lair.steps.path")
path = module.path

IMAGES = Path(__file__).resolve().parents[4] / "images"
BATTLE = (IMAGES / "路线上的界面-出现了.jpg").read_bytes()
BACKPACKER = (IMAGES / "路线上的界面-遇到了背包客.jpg").read_bytes()
BACKPACKER_PANEL = (IMAGES / "背包客的道具面板.jpg").read_bytes()
BACKPACKER_GONE = (IMAGES / "背包客的道具面板消失.jpg").read_bytes()
BERRY = (IMAGES / "路线上的界面-树果.jpg").read_bytes()
BERRY_DONE = (IMAGES / "树果的对话结束.jpg").read_bytes()
SCIENTIST = (IMAGES / "路线上的界面-遇到了研究员.jpg").read_bytes()
RESEARCHER_ASK = (IMAGES / "研究员问换不换.jpg").read_bytes()
RESEARCHER_GONE = (IMAGES / "研究员问话消失.jpg").read_bytes()
FORK = (IMAGES / "路线上的界面-要走哪条路.jpg").read_bytes()

RECTS = GameConfig.rects
STICK_MAX = StickConfig.max
SessionFactory = Callable[..., LairSession]
PrepareRun = Callable[..., Any]
ImageFactory = Any

MAP_TYPE = "2x2"
LAYOUT = 4


def plain(images: ImageFactory) -> bytes:
    """什么字也读不到的画面。"""
    return images.add()


def fork_screen(images: ImageFactory, column: int | None, node: tuple[int, int] = (0, 0)) -> bytes:
    """岔路口：黑色中间面板写「要走哪条路？」，光标在第 column 列上（None 是看不到光标）。node 是出发的节点。"""
    ratios: dict[Any, float] = {}
    if column is not None:
        columns = next_columns(MAP_TYPE, *node)
        rect = RECTS.path_cursors[MAP_TYPE][node][columns.index(column)]
        ratios[(rect, GameConfig.cursor_white_lower)] = 0.1
    return images.add(texts={RECTS.black_center_line1: "要走哪条路？"}, ratios=ratios)


def prepared(sw: LairSession, prepare_run: PrepareRun, route: list[list[int]] | None = None) -> Any:
    """选好首发和路线，返回 sw.game.maps；route 不是 None 时把选的路线换成它，current_index 是 0。"""
    prepare_run(sw)
    maps = sw.game.maps
    assert maps is not None
    if route is not None:
        maps["route"] = route
    maps["current_index"] = 0
    return maps


def events(sw: LairSession) -> dict[str, list[str]]:
    """事件表里这张图（2x2，布局 4）记着的事件。"""
    return sw.data.lair_events(MAP_TYPE, LAYOUT)


# ---------------------------------------------------------------- path：整个步骤


def test_path_returns_battle_when_battle_screen_is_shown(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """第一张截图就是「×××出现了」：返回 "battle"，一个键都没按。"""
    sw = make_lair_session([BATTLE])
    prepared(sw, prepare_run)
    assert path(sw) == "battle"
    assert controller.pressed == []


def test_path_handles_backpacker_and_records_it_as_event_before_fork(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """遇到了背包客：等道具面板出现，按 A 拿默认道具，等面板消失，然后进入战斗；按过的键是 A，
    事件表里起点 0-0 记的是 ["backpacker"]（没走过岔路，记在这个节点上）。
    """
    sw = make_lair_session([BACKPACKER, BACKPACKER_PANEL, BACKPACKER_GONE, BATTLE])
    prepared(sw, prepare_run)
    assert path(sw) == "battle"
    assert controller.pressed == ["A"]
    assert events(sw)["0-0"] == ["backpacker"]


def test_path_handles_berry_and_records_it_as_event_before_fork(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """遇到树果：一直按 A 到文字框里没有「树果」，然后进入战斗；按过的键是 A，事件表里 0-0 记的是 ["berry"]。"""
    sw = make_lair_session([BERRY, BERRY, BERRY_DONE, BATTLE])
    prepared(sw, prepare_run)
    assert path(sw) == "battle"
    assert controller.pressed == ["A"]
    assert events(sw)["0-0"] == ["berry"]


def test_path_handles_scientist_without_known_event_by_not_swapping(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """遇到研究员、算不出队伍（walker_now 返回 None）：等「希望交换成」的画面，按 B 不换，等问话消失，进入战斗；
    决定不记进 choices，事件表里 0-0 记的是 ["scientist"]。
    """
    monkeypatch.setattr(module, "walker_now", lambda sw: None)
    sw = make_lair_session([SCIENTIST, RESEARCHER_ASK, RESEARCHER_GONE, BATTLE])
    prepared(sw, prepare_run)
    sw.game.team = [("pangoro", 1.0)]
    assert path(sw) == "battle"
    assert controller.pressed == ["B"]
    assert sw.game.choices == []
    assert events(sw)["0-0"] == ["scientist"]


def test_path_forks_then_records_events_before_and_after_fork_separately(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """先遇到背包客，再到岔路口（光标本来就在要去的第 0 列，按 A 确认），再遇到树果，最后进入战斗：
    按过的键是 A、A、A；current_index 走到 1；事件表里 0-0 记 ["backpacker"]（选岔路之前），
    0-0>1-0 记 ["berry"]（选岔路之后）；岔路口的路线图存了一张。
    """
    sw = make_lair_session(
        [
            BACKPACKER,
            BACKPACKER_PANEL,
            BACKPACKER_GONE,
            FORK,
            FORK,
            BERRY,
            BERRY,
            BERRY_DONE,
            BATTLE,
        ]
    )
    maps = prepared(sw, prepare_run, [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]])
    assert path(sw) == "battle"
    assert controller.pressed == ["A", "A", "A"]
    assert maps["current_index"] == 1
    assert events(sw)["0-0"] == ["backpacker"]
    assert events(sw)["0-0>1-0"] == ["berry"]
    assert (sw.config.log_dir / "maps" / f"{MAP_TYPE}-{LAYOUT}-0.jpg").exists()


def test_path_fills_in_layout_from_seed_when_old_state_has_none(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """旧存档的 maps 里没有 layout：path 开始时按 seed 补上（基准 seed 的布局是 4）。"""
    sw = make_lair_session([BATTLE])
    maps = prepared(sw, prepare_run)
    cast(dict[str, Any], maps).pop("layout")
    path(sw)
    assert maps["layout"] == LAYOUT


def test_path_raises_timeout_error_when_no_known_screen_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """路线上的界面一直认不出来：抛 TimeoutError，报错里有「路线上的界面」。"""
    sw = make_lair_session([plain(fake_images)])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="路线上的界面"):
        path(sw)


# ---------------------------------------------------------------- 背包客、树果


def test_handle_backpacker_raises_timeout_error_when_panel_never_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """遇到了背包客之后蓝色道具面板一直不出现：抛 TimeoutError，报错里有「背包客的道具面板」。"""
    sw = make_lair_session([BACKPACKER, plain(fake_images)])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="背包客的道具面板$"):
        path(sw)


def test_handle_backpacker_raises_timeout_error_when_panel_never_disappears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """按 A 拿了道具之后面板一直不消失：抛 TimeoutError，报错里有「背包客的道具面板消失」，按过 A。"""
    sw = make_lair_session([BACKPACKER, BACKPACKER_PANEL])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="背包客的道具面板消失"):
        path(sw)
    assert controller.pressed == ["A"]


def test_handle_berry_raises_timeout_error_when_dialog_never_ends(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """按 A 之后文字框里一直有「树果」：抛 TimeoutError，报错里有「树果的对话结束」，按的都是 A。"""
    sw = make_lair_session([BERRY])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="树果的对话结束"):
        path(sw)
    assert set(controller.pressed) == {"A"}


# ---------------------------------------------------------------- 研究员


def scientist_state(sw: LairSession, prepare_run: PrepareRun) -> None:
    """路线改成 (1,1) → (2,3)，第一关抓了不换（choices 是 [False]）：路线上记着下一个事件是研究员，
    研究员实际给 oranguru，改动前的代码算出来是不换。
    """
    maps = prepared(sw, prepare_run, [[0, 0], [1, 1], [2, 3], [3, 1], [4, 0]])
    maps["current_index"] = 2
    sw.game.choices = [False]
    sw.game.team = [(name, 1.0) for name in ["pangoro", "maractus", "galvantula", "cofagrigus"]]


def test_handle_scientist_keeps_pokemon_and_warns_when_next_event_is_not_scientist(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """路线上没记着这个研究员（算出来下一个事件不是研究员）：日志里有警告，按 B 不换，决定不记进 choices，
    队伍不变。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session([RESEARCHER_ASK, RESEARCHER_GONE])
    prepared(sw, prepare_run)
    sw.game.team = [("pangoro", 1.0)]
    module._handle_scientist(sw)
    assert controller.pressed == ["B"]
    assert sw.game.choices == []
    assert sw.game.team == [("pangoro", 1.0)]
    assert any("路线上没记着这个研究员" in record.getMessage() for record in caplog.records)


def test_handle_scientist_declines_and_records_choice_when_decision_is_not_to_swap(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """路线上记着这个研究员、按 seed 推出来不换：按 B，决定 False 记进 choices（前面还有第一关的 False），队伍不变。"""
    sw = make_lair_session([RESEARCHER_ASK, RESEARCHER_GONE])
    scientist_state(sw, prepare_run)
    module._handle_scientist(sw)
    assert controller.pressed == ["B"]
    assert sw.game.choices == [False, False]
    assert sw.game.team[0] == ("pangoro", 1.0)


def test_handle_scientist_does_not_swap_when_offered_name_differs_from_expected(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """决定换（upstream.decide_scientist 换成固定返回换），但画面上「希望交换成…」里的名字和按 seed 算的
    oranguru 的中文名对不上：日志里有警告，不换，按 B，决定记成不换，队伍不变。
    """
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(upstream, "decide_scientist", lambda scorer, walker: True)
    sw = make_lair_session([RESEARCHER_ASK, RESEARCHER_GONE])
    scientist_state(sw, prepare_run)
    module._handle_scientist(sw)
    assert controller.pressed == ["B"]
    assert sw.game.choices == [False, False]
    assert sw.game.team[0] == ("pangoro", 1.0)
    assert any("对不上，不换" in record.getMessage() for record in caplog.records)


def test_handle_scientist_swaps_when_decision_is_to_swap_and_name_matches(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
    fake_images: ImageFactory,
) -> None:
    """决定换、画面上「希望交换成」后面的名字和按 seed 算的一样：按 A，决定 True 记进 choices，
    自己这只换成 oranguru、满血，状态存盘。
    """
    monkeypatch.setattr(upstream, "decide_scientist", lambda scorer, walker: True)
    name = GameData(GameConfig()).pokemon_object("oranguru").name(GameConfig.language)
    ask = fake_images.add(texts={RECTS.black_center_line1: f"希望交换成{name}"})
    sw = make_lair_session([ask, plain(fake_images)])
    scientist_state(sw, prepare_run)
    module._handle_scientist(sw)
    assert controller.pressed == ["A"]
    assert sw.game.choices == [False, True]
    assert sw.game.team[0] == ("oranguru", 1.0)
    assert "oranguru" in sw.config.game_state_file.read_text(encoding="utf-8")


def test_handle_scientist_raises_timeout_error_when_question_never_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """研究员问「希望交换成…」的画面一直不出现：抛 TimeoutError，报错里有「研究员问换不换」。"""
    sw = make_lair_session([plain(fake_images)])
    prepared(sw, prepare_run)
    sw.game.team = [("pangoro", 1.0)]
    with pytest.raises(TimeoutError, match="研究员问换不换"):
        module._handle_scientist(sw)


def test_handle_scientist_raises_timeout_error_when_question_never_disappears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """按了 B 之后问话一直不消失：抛 TimeoutError，报错里有「研究员问话消失」。"""
    sw = make_lair_session([RESEARCHER_ASK])
    prepared(sw, prepare_run)
    sw.game.team = [("pangoro", 1.0)]
    with pytest.raises(TimeoutError, match="研究员问话消失"):
        module._handle_scientist(sw)
    assert controller.pressed == ["B"]


# ---------------------------------------------------------------- 岔路口


def test_handle_fork_moves_cursor_right_by_pushing_stick_then_confirms(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """光标在第 0 列、路线要去第 1 列：往右推左摇杆一次（+stick_max），光标到了就按 A，current_index 加 1。"""
    sw = make_lair_session(
        [
            fork_screen(fake_images, 0),
            fork_screen(fake_images, 0),
            fork_screen(fake_images, 1),
        ]
    )
    maps = prepared(sw, prepare_run)
    module._handle_fork(sw)
    assert controller.sticks == [("LEFT", STICK_MAX, 0, StickConfig.tick)]
    assert controller.pressed == ["A"]
    assert maps["current_index"] == 1


def test_handle_fork_moves_cursor_left_by_pushing_stick_the_other_way(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """光标在第 1 列、路线要去第 0 列：往左推（-stick_max）。"""
    sw = make_lair_session(
        [
            fork_screen(fake_images, 1),
            fork_screen(fake_images, 1),
            fork_screen(fake_images, 0),
        ]
    )
    prepared(sw, prepare_run, [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]])
    module._handle_fork(sw)
    assert controller.sticks == [("LEFT", -STICK_MAX, 0, StickConfig.tick)]


def test_handle_fork_raises_runtime_error_when_route_has_no_next_node(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """当前已经是路线上的最后一个节点：抛 RuntimeError，报错里有「路线规划里没有下一个节点」。"""
    sw = make_lair_session()
    maps = prepared(sw, prepare_run)
    maps["current_index"] = len(maps["route"]) - 1
    with pytest.raises(RuntimeError, match="路线规划里没有下一个节点"):
        module._handle_fork(sw)


def test_handle_fork_raises_runtime_error_when_target_column_is_not_reachable(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, controller: Any
) -> None:
    """路线上下一个节点的列，不在当前节点能走到的列里（起点只能走到第 0、1 列）：抛 RuntimeError，
    报错里有「不在当前节点能走到的」，没按键。
    """
    sw = make_lair_session()
    prepared(sw, prepare_run, [[0, 0], [1, 3], [2, 0], [3, 0], [4, 0]])
    with pytest.raises(RuntimeError, match="不在当前节点能走到的"):
        module._handle_fork(sw)
    assert controller.pressed == []
    assert controller.sticks == []


def test_handle_fork_raises_timeout_error_when_cursor_never_visible(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, fake_images: ImageFactory
) -> None:
    """岔路口一直看不到光标：抛 TimeoutError，报错里有「岔路口光标」。"""
    sw = make_lair_session([fork_screen(fake_images, None)])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="岔路口光标$"):
        module._handle_fork(sw)


def test_handle_fork_raises_timeout_error_when_cursor_never_moves(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """推了摇杆光标也一直不动：抛 TimeoutError，报错里有「岔路口光标移动」，推的都是 +stick_max，没按 A。"""
    sw = make_lair_session([fork_screen(fake_images, 0)])
    prepared(sw, prepare_run)
    with pytest.raises(TimeoutError, match="岔路口光标移动"):
        module._handle_fork(sw)
    assert controller.sticks
    assert set(controller.sticks) == {("LEFT", STICK_MAX, 0, StickConfig.tick)}
    assert controller.pressed == []


def test_handle_fork_raises_runtime_error_when_cursor_keeps_missing_the_target(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """3 个选项的岔路口（2x2 的 (2,1) 能走到第 1、2、3 列），目标是第 3 列：每次推完光标都回到第 1 列和第 2 列之间
    来回跳，推满 3 次还没到：抛 RuntimeError，报错里有「岔路口光标移了 3 次，还是没到第 4 列」。
    """
    node = (2, 1)
    frames: list[bytes] = [fork_screen(fake_images, 1, node)]
    # 每次推之前的那一帧光标位置和上一次推完的一样，推完之后换到另一列
    for column, after in [(1, 2), (2, 1), (1, 2)]:
        frames += [fork_screen(fake_images, column, node), fork_screen(fake_images, after, node)]
    sw = make_lair_session(frames)
    maps = prepared(sw, prepare_run, [[0, 0], [1, 0], [2, 1], [3, 3], [4, 0]])
    maps["current_index"] = 2
    with pytest.raises(RuntimeError, match="岔路口光标移了 3 次，还是没到第 4 列"):
        module._handle_fork(sw)
    assert len(controller.sticks) == 3
    assert controller.pressed == []


# ---------------------------------------------------------------- _save_map、_record_events


def test_save_map_saves_picture_once_per_node(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """_save_map：存到 log_dir/maps/类型-布局-节点序号.jpg；同一个文件已经有了就不再写（内容不变）。"""
    sw = make_lair_session()
    prepared(sw, prepare_run)
    target = sw.config.log_dir / "maps" / f"{MAP_TYPE}-{LAYOUT}-0.jpg"
    module._save_map(sw, ImageChecker(FORK))
    assert target.exists()
    first = target.read_bytes()
    module._save_map(sw, ImageChecker(BATTLE))
    assert target.read_bytes() == first


def test_save_map_does_nothing_when_layout_is_unknown(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """maps 里没有 layout：_save_map 什么都不存。"""
    sw = make_lair_session()
    maps = prepared(sw, prepare_run)
    cast(dict[str, Any], maps).pop("layout")
    module._save_map(sw, ImageChecker(FORK))
    assert not (sw.config.log_dir / "maps").exists()


def table_on_disk(sw: LairSession) -> dict[str, Any]:
    """事件表文件现在的内容。"""
    return json.loads((sw.config.data_dir / "lair_event_LUT.json").read_text(encoding="utf-8"))


def test_record_events_with_fork_records_both_node_and_segment(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """走了岔路：起点 0-0 记选岔路之前的事件，0-0>1-1（起点到路线上下一个节点）记选岔路之后的事件，都写进文件。"""
    sw = make_lair_session()
    maps = prepared(sw, prepare_run)
    maps["current_index"] = 1
    module._record_events(sw, [0, 0], True, ["backpacker"], ["berry", "scientist"])
    saved = table_on_disk(sw)[MAP_TYPE][str(LAYOUT)]
    assert saved["0-0"] == ["backpacker"]
    assert saved["0-0>1-1"] == ["berry", "scientist"]


def test_record_events_without_fork_records_only_the_node(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """没走岔路：只记起点这个节点的事件，不记一段路的。"""
    sw = make_lair_session()
    prepared(sw, prepare_run)
    module._record_events(sw, [0, 0], False, ["berry"], [])
    saved = table_on_disk(sw)[MAP_TYPE][str(LAYOUT)]
    assert saved["0-0"] == ["berry"]
    assert saved["0-0>1-1"] == []


def test_record_events_does_nothing_when_layout_is_unknown(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """maps 里没有 layout：什么都不记，事件表文件不变。"""
    sw = make_lair_session()
    maps = prepared(sw, prepare_run)
    cast(dict[str, Any], maps).pop("layout")
    before = table_on_disk(sw)
    module._record_events(sw, [0, 0], False, ["berry"], [])
    assert table_on_disk(sw) == before
