"""steps.initialize：把游戏带到科学家面前、没有对话框的状态，返回 "join"。

没有开场白菜单（现在就出发 / 我想听讲解 / 还是先算了）的截图，画面判断用假截图（conftest 的 fake_images）：
白色中间面板有字加上菜单，就是开场白的菜单；白色中间面板没有字，就是对话框消失。
GameConfig 的目录都指到临时目录，initialize 会删 log_dir 下的文件，不能碰仓库里的。
"""

import importlib
import logging
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.session import LairSession
from control_switch.session import Frame

initialize_module: ModuleType = importlib.import_module(
    "control_switch.games.swsh.lair.steps.initialize"
)
initialize = initialize_module.initialize

RECTS = GameConfig.rects
ADDRESSES = GameConfig.addresses
ITEM_POUCH = ADDRESSES.items + ADDRESSES.item_pouch_offset
BALL_POUCH = ADDRESSES.items + ADDRESSES.ball_pouch_offset
OPTION_RECT = ((0.7, 0.5), (0.8, 0.55))
OPTIONS = [("现在就出发", OPTION_RECT), ("我想听讲解", OPTION_RECT), ("还是先算了", OPTION_RECT)]
ULTRA_BALL = GameConfig.ball_items["究极球"]

SessionFactory = Callable[..., LairSession]
ImageFactory = Any


def pouches(ore: int = 37, ball: int = 25) -> dict[int, bytes]:
    """假 Memory 里的道具口袋：极矿石 ore 个，究极球 ball 个。"""

    def pouch(slots: int, item: int, count: int) -> bytes:
        values = [item | count << 15] + [0] * (slots - 1)
        return b"".join(value.to_bytes(4, "little") for value in values)

    return {
        ITEM_POUCH: pouch(ADDRESSES.item_pouch_slots, GameConfig.dynite_ore_item, ore),
        BALL_POUCH: pouch(ADDRESSES.ball_pouch_slots, ULTRA_BALL, ball),
    }


@pytest.fixture
def screens(fake_images: ImageFactory) -> dict[str, bytes]:
    """三种假截图：普通对话（有字没有菜单）、开场白的菜单、对话框消失。"""
    return {
        "dialog": fake_images.add(texts={RECTS.white_center_line1: "欢迎来到巢穴"}),
        "menu": fake_images.add(
            texts={RECTS.white_center_line1: "怎么样"}, menu=(RECTS.menu_search, OPTIONS)
        ),
        "gone": fake_images.add(),
    }


@pytest.fixture(autouse=True)
def root_logger(clean_root_logger: logging.Logger) -> logging.Logger:
    """initialize 会往根 logger 上挂日志文件，测试结束时清掉。"""
    return clean_root_logger


def log_text(sw: LairSession) -> str:
    """这一局日志文件里的全部内容。"""
    files = list((sw.config.log_dir / "start").glob("*.log"))
    assert len(files) == 1
    return files[0].read_text(encoding="utf-8")


def test_initialize_presses_a_until_menu_then_b_until_dialog_gone_and_returns_join(
    make_lair_session: SessionFactory, controller: Any, screens: dict[str, bytes]
) -> None:
    """正常走完：先按 A 到出现开场白的菜单，再按 B 到对话框消失，按过的键是 ["A", "B"]，返回 "join"。"""
    sw = make_lair_session(
        [screens["dialog"], screens["menu"], screens["menu"], screens["gone"]], data=pouches()
    )
    assert initialize(sw) == "join"
    assert controller.pressed == ["A", "B"]


def test_initialize_records_ore_count_into_game_state_and_saves_it(
    make_lair_session: SessionFactory, screens: dict[str, bytes]
) -> None:
    """正常走完：game.dynite_ore 是内存里读到的极矿石数量（37），状态已经写进 game_state_file。"""
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches(ore=37))
    initialize(sw)
    assert sw.game.dynite_ore == 37
    assert sw.config.game_state_file.exists()
    assert "dynite_ore: 37" in sw.config.game_state_file.read_text(encoding="utf-8")


def test_initialize_logs_ore_and_ball_counts(
    make_lair_session: SessionFactory, screens: dict[str, bytes]
) -> None:
    """正常走完：日志里有「极矿石还有 37 个」和「抓宝可梦用的究极球还有 25 个」。"""
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches(ore=37, ball=25))
    initialize(sw)
    text = log_text(sw)
    assert "极矿石还有 37 个" in text
    assert "抓宝可梦用的究极球还有 25 个" in text


def test_initialize_warns_when_ball_has_no_item_number(
    make_lair_session: SessionFactory, monkeypatch: pytest.MonkeyPatch, screens: dict[str, bytes]
) -> None:
    """配置里的球名不在 ball_items 里：日志里有「不知道…的道具编号」的警告，步骤照常返回 "join"。"""
    monkeypatch.setattr(GameConfig, "base_ball", "没有这种球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "没有这种球")
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches())
    assert initialize(sw) == "join"
    assert "不知道没有这种球的道具编号" in log_text(sw)


def test_initialize_raises_timeout_error_when_menu_never_appears(
    make_lair_session: SessionFactory, controller: Any, screens: dict[str, bytes]
) -> None:
    """开场白的菜单一直不出现：抛 TimeoutError，报错里有「开场白的菜单」，按的都是 A。"""
    sw = make_lair_session([screens["dialog"]], data=pouches())
    with pytest.raises(TimeoutError, match="开场白的菜单"):
        initialize(sw)
    assert controller.pressed
    assert set(controller.pressed) == {"A"}


def test_initialize_raises_timeout_error_when_dialog_never_disappears(
    make_lair_session: SessionFactory, controller: Any, screens: dict[str, bytes]
) -> None:
    """对话框一直不消失：抛 TimeoutError，报错里有「对话框消失」，菜单出现后按的都是 B。"""
    sw = make_lair_session([screens["menu"]], data=pouches())
    with pytest.raises(TimeoutError, match="对话框消失"):
        initialize(sw)
    assert controller.pressed
    assert set(controller.pressed) == {"B"}


def test_initialize_clears_frames_of_previous_run(
    make_lair_session: SessionFactory, screens: dict[str, bytes]
) -> None:
    """开始时清空 sw.frames：上一局留下的截图不在里面，里面只有这一次截的图。"""
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches())
    sw.frames.append(Frame(0.0, "上一局", "旧截图", b"old"))
    initialize(sw)
    assert sw.frames
    assert all(frame.step != "上一局" for frame in sw.frames)


def test_initialize_creates_new_log_file_in_start_directory(
    make_lair_session: SessionFactory, screens: dict[str, bytes]
) -> None:
    """开始时换一个新的日志文件：log_dir/start/ 下有一个 .log 文件。"""
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches())
    initialize(sw)
    assert len(list((sw.config.log_dir / "start").glob("*.log"))) == 1


def test_initialize_cleans_log_dir_but_keeps_start_and_failed(
    make_lair_session: SessionFactory, screens: dict[str, bytes]
) -> None:
    """清空日志目录：留下 start（运行日志）和 failed（出错截图），其他的文件和目录都删掉，日志里写明删了几个文件。"""
    sw = make_lair_session([screens["menu"], screens["gone"]], data=pouches())
    log_dir: Path = sw.config.log_dir
    (log_dir / "failed" / "20260101-000000").mkdir(parents=True)
    kept_failed = log_dir / "failed" / "20260101-000000" / "0000-出错.jpg"
    kept_failed.write_bytes(b"failed")
    (log_dir / "results").mkdir(parents=True)
    (log_dir / "results" / "a.jpg").write_bytes(b"a")
    (log_dir / "results" / "b.jpg").write_bytes(b"b")
    (log_dir / "maps").mkdir()
    (log_dir / "maps" / "2x2-0.jpg").write_bytes(b"m")
    (log_dir / "loose.txt").write_text("x", encoding="utf-8")
    initialize(sw)
    assert sorted(path.name for path in log_dir.iterdir()) == ["failed", "start"]
    assert kept_failed.read_bytes() == b"failed"
    assert "删掉 4 个文件" in log_text(sw)
