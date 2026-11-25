"""极巨大冒险各个步骤的测试共用的 fixture。

等待都不真的等：time.sleep 换成不等待的函数（步骤模块里的 time 就是标准库的 time 模块，
替换 time.sleep 和替换步骤模块上的 time.sleep 是同一件事）。
"""

import importlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from control_switch.games.swsh.lair.lair import Lair
from control_switch.games.swsh.lair.session import LairSession

# 超梦基准图的 seed（和 tests/games/swsh/lair/conftest.py 里的一样）
SEED = 3076008315599927110

# 这个 seed 的图（2x2，布局 4）路上已经知道的事件，是改动前 src/control_switch/games/swsh/data/lair_event_LUT.json 里的内容。
# 事件表以后会随着真机跑出来的记录变多，测试里固定成这一份，期望值不跟着变
EVENTS = {
    "0-0": [],
    "0-0>1-0": [],
    "0-0>1-1": [],
    "1-0": [],
    "1-0>2-0": [],
    "1-0>2-1": [],
    "1-1": [],
    "1-1>2-2": [],
    "1-1>2-3": ["scientist"],
    "2-0": [],
    "2-0>3-0": [],
    "2-0>3-1": [],
    "2-1": ["berry"],
    "2-1>3-1": ["backpacker"],
    "2-1>3-2": [],
    "2-1>3-3": ["backpacker"],
    "2-2": [],
    "2-2>3-1": ["backpacker"],
    "2-2>3-2": [],
    "2-2>3-3": ["backpacker"],
    "2-3": [],
    "2-3>3-1": ["backpacker"],
    "2-3>3-2": [],
    "2-3>3-3": ["backpacker"],
    "3-0": ["berry"],
    "3-1": [],
    "3-2": [],
    "3-3": [],
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """time.sleep 换成什么都不等的函数。"""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


class FakePkhex:
    """假的 Pk8Reader：按地址返回事先给定的记录（字典，字段同 Pk8Reader.read_pk8 的结果），记下读过的地址。"""

    def __init__(self, records: Mapping[int, dict[str, Any]]) -> None:
        self.records = dict(records)
        self.reads: list[list[int]] = []

    def read_pk8(self, addresses: Sequence[int]) -> list[dict[str, Any]]:
        self.reads.append(list(addresses))
        return [self.records[address] for address in addresses]


@pytest.fixture
def make_pkhex() -> Callable[[Mapping[int, dict[str, Any]]], FakePkhex]:
    """返回一个函数：传入 {地址: 记录}，返回假的 Pk8Reader。"""
    return FakePkhex


def pin_events(sw: LairSession) -> None:
    """路上的事件表换成固定的这一份（要在第一次读事件表之前写好）。"""
    table = {"2x2": {"4": EVENTS}}
    (sw.config.data_dir / "lair_event_LUT.json").write_text(json.dumps(table), encoding="utf-8")


def starter_data(sw: LairSession, seed: int) -> tuple[Lair, FakePkhex, Callable[[int, int], str]]:
    """选初始宝可梦界面三只候选的假内存记录。

    返回 (这个 seed 的 Lair, 假的 Pk8Reader, 代替 GameData.name_id 的函数)。
    内存记录里的 species 用不会和真的重复的编号（10001 起），代替的 name_id 认到它们时返回对应的候选。
    """
    lair = Lair(sw.data, seed)
    fake_species = {10001 + index: name for index, name in enumerate(lair.candidates()[:3])}
    records = {
        address: {"species": 10001 + index, "form": 0}
        for index, address in enumerate(sw.config.addresses.starter_candidates)
    }
    real_name_id = sw.data.name_id

    def name_id(species: int, form: int) -> str:
        return fake_species.get(species) or real_name_id(species, form)

    return lair, FakePkhex(records), name_id


@pytest.fixture
def starters(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Lair]:
    """返回一个函数：把 LairSession 的路上事件表、选初始宝可梦界面的内存记录（pkhex）、name_id 都换成假的，
    返回这个 seed 的 Lair。join 里选首发时读这些。
    """

    def install(sw: LairSession, seed: int = SEED) -> Lair:
        pin_events(sw)
        lair, pkhex, name_id = starter_data(sw, seed)
        monkeypatch.setattr(sw, "pkhex", pkhex)
        monkeypatch.setattr(sw.data, "name_id", name_id)
        return lair

    return install


@pytest.fixture
def prepare_run(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Lair]:
    """返回一个函数：把 LairSession 的状态设成「选完初始宝可梦和路线」之后的样子，返回这一局的 Lair。

    和 join 里选首发时做的一样：读到 seed，从假的内存记录读三只候选，按 seed 算租借、遭遇、
    地图类型，用 upstream 选首发和路线，写进 sw.game（也存进临时目录里的 game_state_file）。
    """

    def prepare(sw: LairSession, seed: int = SEED) -> Lair:
        join = importlib.import_module("control_switch.games.swsh.lair.steps.join")
        pin_events(sw)
        lair, pkhex, name_id = starter_data(sw, seed)
        monkeypatch.setattr(sw, "pkhex", pkhex)
        sw.game.check_keep(str(sw.game.boss), seed)
        with monkeypatch.context() as patch:
            patch.setattr(sw.data, "name_id", name_id)
            join._assign_new_starter(sw)
        return lair

    return prepare
