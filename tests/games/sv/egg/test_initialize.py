"""steps.initialize：换新日志文件，退回野外，读野餐队伍里的亲代，存档，返回 "fetch"。

亲代是野餐队伍里不是百变怪的那只，读它的名字和「最棒」项数（box.read_party 返回队伍里每一只的 box.Mon）。
游戏里评定功能没解锁时 Mon.best 是 None：不换亲代，只记一条日志。
box、actions 里要看画面的操作都换成假函数，只看调用的顺序。
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.flow import capture

box_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.box")
actions_module: ModuleType = importlib.import_module("control_switch.games.sv.actions")
initialize_module: ModuleType = importlib.import_module(
    "control_switch.games.sv.egg.steps.initialize"
)
initialize = initialize_module.initialize

DITTO = "百变怪"


@pytest.fixture
def party(stage: Any) -> list[Any]:
    """野餐队伍：烛光灵（3 项最棒）在第 1 只，百变怪在第 2 只。box、actions 里的操作换成假函数。"""
    mons = [box_module.Mon("烛光灵", 3, False), box_module.Mon(DITTO, None, False)]
    stage.sw.config.ditto_name = DITTO
    stage.stub(box_module, "exit_to_overworld")
    stage.stub(box_module, "open_box")
    stage.stub(box_module, "read_party", lambda: mons)
    stage.stub(actions_module, "save_game")
    return mons


def log_text(stage: Any) -> str:
    """这一局日志文件里的全部内容。"""
    files = list((Path(stage.sw.config.log_dir) / "start").rglob("*.log"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")


def test_initialize_returns_fetch(stage: Any, party: list[Any]) -> None:
    """正常走完：返回 "fetch"。"""
    assert initialize(stage.sw) == "fetch"


def test_initialize_leaves_to_overworld_reads_party_leaves_box_then_saves_once(
    stage: Any, party: list[Any]
) -> None:
    """顺序：先退回野外，开盒子，读队伍，退出盒子，最后存档，存一次。"""
    initialize(stage.sw)
    assert stage.log == [
        ("exit_to_overworld",),
        ("open_box",),
        ("read_party",),
        ("exit_to_overworld",),
        ("save_game",),
    ]


def test_initialize_creates_new_log_file_in_start_directory(stage: Any, party: list[Any]) -> None:
    """开始时换一个新的日志文件：log_dir/start/ 下（再按机器名分一层）有一个 .log 文件。"""
    initialize(stage.sw)
    assert len(list((Path(stage.sw.config.log_dir) / "start").rglob("*.log"))) == 1


def test_initialize_clears_frames_of_previous_run(stage: Any, party: list[Any]) -> None:
    """开始时清空 sw.frames：上一局留下的截图不在里面。"""
    capture(stage.sw, "上一局的截图")
    initialize(stage.sw)
    assert all(frame.what != "上一局的截图" for frame in stage.sw.frames)


def test_initialize_reads_parent_when_parent_is_first_in_party(
    stage: Any, party: list[Any]
) -> None:
    """亲代在野餐队伍第 1 只：parent_index 0，parent_name「烛光灵」，parent_best 3，评定已解锁。"""
    initialize(stage.sw)
    assert stage.sw.parent_index == 0
    assert stage.sw.parent_name == "烛光灵"
    assert stage.sw.parent_best == 3
    assert stage.sw.judge_unlocked is True


def test_initialize_reads_parent_when_ditto_is_first_in_party(stage: Any, party: list[Any]) -> None:
    """百变怪在第 1 只、亲代在第 2 只：亲代是不是百变怪的那只，parent_index 1，项数取亲代自己的。"""
    party[:] = [box_module.Mon(DITTO, None, False), box_module.Mon("烛光灵", 5, False)]
    initialize(stage.sw)
    assert stage.sw.parent_index == 1
    assert stage.sw.parent_name == "烛光灵"
    assert stage.sw.parent_best == 5


def test_initialize_logs_once_and_skips_swapping_when_judge_is_not_unlocked(
    stage: Any, party: list[Any]
) -> None:
    """游戏里评定功能没解锁（亲代的 best 是 None）：judge_unlocked 是 False，parent_best 是 0，
    日志里有一条说评定没解锁、不换亲代的记录，步骤照常返回 "fetch"。
    """
    party[:] = [box_module.Mon("烛光灵", None, False), box_module.Mon(DITTO, None, False)]
    assert initialize(stage.sw) == "fetch"
    assert stage.sw.judge_unlocked is False
    assert stage.sw.parent_best == 0
    assert len([line for line in log_text(stage).splitlines() if "评定" in line]) == 1


def test_initialize_raises_runtime_error_when_party_has_only_ditto(
    stage: Any, party: list[Any]
) -> None:
    """队伍里只有百变怪，找不到亲代：抛 RuntimeError，没有存档。"""
    party[:] = [box_module.Mon(DITTO, None, False)]
    with pytest.raises(RuntimeError):
        initialize(stage.sw)
    assert ("save_game",) not in stage.log
