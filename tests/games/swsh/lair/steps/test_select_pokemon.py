"""steps.select_pokemon：一局结束，检查抓到的宝可梦是不是闪光，带走或留下，写战报。

没有带走宝可梦界面的截图（logs/keep 里没有），画面判断用假截图（conftest 的 fake_images）。
战报里的极矿石和球的数量读假 Memory 的道具口袋（极矿石 37 个、究极球 25 个）。
战果截图存进临时目录的 result_dir、shiny_dir。keep_path 不开（不锁定）；要锁定的用例创建 LairSession 时传 keep_path=True。
选好首发和路线之后的状态用 prepare_run 按 seed 算出来（基准 seed，路线 斧牙龙 → 龟足巨铠 → 狃拉，
首领卡璞・蝶蝶，首发流氓熊猫）。期望值是改动前的代码跑出来的。
"""

import importlib
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.config import WaitConfig
from control_switch.device import Controller
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.session import LairSession

module: ModuleType = importlib.import_module("control_switch.games.swsh.lair.steps.select_pokemon")
select_pokemon = module.select_pokemon

RECTS = GameConfig.rects
ADDRESSES = GameConfig.addresses
SessionFactory = Callable[..., LairSession]
PrepareRun = Callable[..., Any]
ImageFactory = Any

TITLE_TEXT = "选1只要带回去的宝可梦"
OPTION_RECT = ((0.75, 0.40), (0.85, 0.45))
OPTIONS = [("选择", OPTION_RECT), ("查看能力", OPTION_RECT), ("取消", OPTION_RECT)]
SHINY_RATIO = 0.2


def pouch(slots: int, item: int, count: int) -> bytes:
    values = [item | count << 15] + [0] * (slots - 1)
    return b"".join(value.to_bytes(4, "little") for value in values)


MEMORY = {
    ADDRESSES.items + ADDRESSES.item_pouch_offset: pouch(
        ADDRESSES.item_pouch_slots, GameConfig.dynite_ore_item, 37
    ),
    ADDRESSES.items + ADDRESSES.ball_pouch_offset: pouch(
        ADDRESSES.ball_pouch_slots, GameConfig.ball_items["究极球"], 25
    ),
}


class Screens:
    """用到的各种假截图，每次调用登记一张新的，返回它在假 Screen 里的字节。"""

    def __init__(self, images: ImageFactory) -> None:
        self._images = images

    def plain(self) -> bytes:
        """什么字也读不到的画面（也当作带走列表左边的预览已经画出来了）。"""
        return self._images.add()

    def title(self) -> bytes:
        """带走宝可梦的界面。"""
        return self._images.add(texts={RECTS.result_title: TITLE_TEXT})

    def option_menu(self) -> bytes:
        """「选择 / 查看能力 / 取消」，光标在「查看能力」上。"""
        return self._images.add(
            texts={RECTS.result_view_ability: "查看能力"},
            menu=(RECTS.result_option_menu, OPTIONS),
            selected=1,
        )

    def summary(self, name: str, shiny: bool = False) -> bytes:
        """资料页：名字，闪光框的占比（闪光的是 0.2，换算成 51，在 10 到 100 之间）。"""
        ratio = SHINY_RATIO if shiny else 0.0
        return self._images.add(
            texts={RECTS.summary_name: name}, ratios={(RECTS.shiny, GameConfig.shiny_lower): ratio}
        )

    def sprite(self) -> bytes:
        """资料页右边的宝可梦已经画出来了。"""
        return self._images.add(edge=0.5)

    def cursor(self, index: int) -> bytes:
        """带走列表，光标在第 index 只上。"""
        return self._images.add(selected=index)

    def confirm(self) -> bytes:
        """「不带宝可梦回去了，你确定吗？」，光标在「是」上。"""
        return self._images.add(
            texts={RECTS.white_center_line1: "不带宝可梦回去了，你确定吗？"}, selected=0
        )

    def black(self) -> bytes:
        """黑屏。"""
        return self._images.add(black=True)


@pytest.fixture
def screens(fake_images: ImageFactory) -> Screens:
    return Screens(fake_images)


@pytest.fixture
def restarts(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """步骤模块里的 restart 换成记下调用的函数，不真的重启游戏。"""
    calls: list[object] = []
    monkeypatch.setattr(module, "restart", calls.append)
    return calls


def finished_run(sw: LairSession, prepare_run: PrepareRun, caught: list[str]) -> None:
    """选好首发和路线，抓到了 caught 里的几只，一局从刚刚开始。"""
    prepare_run(sw)
    sw.game.num_caught = len(caught)
    sw.game.caught = list(caught)
    sw.game.started = time.time() - 1


def notifier_of(sw: LairSession) -> Any:
    """sw.notifier 就是 make_lair_session 换上的 RecordingNotifier（记下 send、send_everyone 的内容）。"""
    return sw.notifier


def kind(path: Path) -> str:
    """战果截图的文件名去掉前面的时间（年月日-时分秒-）。"""
    return re.sub(r"^\d{8}-\d{6}-", "", path.name)


def files_in(directory: Path) -> list[str]:
    return sorted(kind(path) for path in directory.glob("*.jpg"))


# ---------------------------------------------------------------- 一只都没抓到


def test_select_pokemon_without_catch_reports_and_returns_initialize(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    restarts: list[object],
) -> None:
    """一只都没抓到、不锁定：不按键，不重启，发一条战报（里面有「一只都没抓到」），返回 "initialize"，
    这一局记成输。
    """
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, [])
    assert select_pokemon(sw) == "initialize"
    assert controller.pressed == []
    assert restarts == []
    assert len(notifier_of(sw).sent) == 1
    assert "处理：一只都没抓到\n" in notifier_of(sw).sent[0][0]
    assert sw.game.lock_results == [False]


def test_select_pokemon_without_catch_restarts_game_when_path_stays_locked(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    restarts: list[object],
) -> None:
    """一只都没抓到、这张图已经锁定、keep_path 开着、极矿石够：继续锁定，调了一次 restart，战报里有「重启游戏保留路线」。"""
    sw = make_lair_session(data=MEMORY, keep_path=True)
    finished_run(sw, prepare_run, [])
    sw.game.lock_path = True
    sw.game.path_results = [True]
    sw.game.dynite_ore = 50
    assert select_pokemon(sw) == "initialize"
    assert restarts == [sw]
    assert "处理：一只都没抓到，重启游戏保留路线\n" in notifier_of(sw).sent[0][0]


# ---------------------------------------------------------------- 整个步骤：查闪光


def test_select_pokemon_single_non_shiny_goes_back_to_scientist(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    controller: Any,
    restarts: list[object],
) -> None:
    """抓到 1 只、不是闪光、不锁定：按过的键是 A（查看能力）、B（回到列表）、B（不带走）、A（到黑屏），
    返回 "initialize"，战报里「不带走」，战果截图存进 result_dir（一张列表），shiny_dir 里没有。
    """
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.title(),
            screens.plain(),
            screens.plain(),
            screens.confirm(),
            screens.confirm(),
            screens.black(),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    assert select_pokemon(sw) == "initialize"
    assert controller.pressed == ["A", "B", "B", "A"]
    assert restarts == []
    assert "处理：不带走\n" in notifier_of(sw).sent[0][0]
    assert files_in(sw.config.result_dir) == ["list.jpg"]
    assert not sw.config.shiny_dir.exists()
    assert notifier_of(sw).sent_everyone == []


def test_select_pokemon_single_shiny_is_taken_away(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    controller: Any,
) -> None:
    """抓到 1 只、是闪光：资料页截图和列表截图都存进 shiny_dir，各按一次 CAPTURE，发 @全体 的通知（带资料页截图），
    光标已经在这只上不用推摇杆，一直按 A 到黑屏；按过的键是 A、CAPTURE、B、CAPTURE、A，返回 "initialize"，
    战报里「带走第 1 只闪光」，闪光记进 game.shinies。
    """
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A", shiny=True),
            screens.summary("名A", shiny=True),
            screens.sprite(),
            screens.plain(),
            screens.title(),
            screens.plain(),
            screens.cursor(0),
            screens.cursor(0),
            screens.plain(),
            screens.black(),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    assert select_pokemon(sw) == "initialize"
    assert controller.pressed == ["A", "CAPTURE", "B", "CAPTURE", "A"]
    assert controller.sticks == []
    assert files_in(sw.config.shiny_dir) == ["shiny-list.jpg", "shiny-summary.jpg"]
    assert not sw.config.result_dir.exists()
    assert [text for text, _ in notifier_of(sw).sent_everyone] == ["闪光！第 1 只 斧牙龙"]
    summary_files = notifier_of(sw).sent_everyone[0][1]
    assert [kind(path) for path in summary_files] == ["shiny-summary.jpg"]
    assert "处理：带走第 1 只闪光\n" in notifier_of(sw).sent[0][0]
    assert len(sw.game.shinies) == 1
    assert sw.game.shinies[0]["pokemon"] == "fraxure"


def test_select_pokemon_several_shinies_notifies_everyone_and_exits(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    controller: Any,
) -> None:
    """抓到 2 只、两只都是闪光：战报照常发出，发 @全体 的通知（「这一局有 2 只闪光（第 1、2 只）…」），
    然后抛 SystemExit，不替人选，没有按 A 到黑屏。按过的键是 A（查看能力）、两只资料页各一次 CAPTURE、B（回到列表）、
    两只列表各一次 CAPTURE；资料页往下翻两次、列表光标往下推一次（都是 -Controller.STICK_MAX）。
    """
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A", shiny=True),
            # 第 1 只：读名字、等宝可梦画出来，然后往下翻
            screens.summary("名A", shiny=True),
            screens.sprite(),
            screens.summary("名A"),
            screens.summary("名B", shiny=True),
            # 第 2 只
            screens.summary("名B", shiny=True),
            screens.sprite(),
            screens.summary("名B"),
            screens.summary("名A"),
            # 回到列表
            screens.summary("名A"),
            screens.title(),
            # 第 1 只闪光：存列表截图，光标推到第 2 只；第 2 只：存列表截图
            screens.plain(),
            screens.cursor(0),
            screens.cursor(0),
            screens.cursor(1),
            screens.plain(),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    with pytest.raises(SystemExit) as error:
        select_pokemon(sw)
    text = "这一局有 2 只闪光（第 1、2 只），程序停在带走宝可梦的列表上，等你来选"
    assert str(error.value) == text
    assert [sent for sent, _ in notifier_of(sw).sent_everyone][-1] == text
    assert len(notifier_of(sw).sent) == 1
    assert "处理：有 2 只闪光（第 1、2 只），停下来等人选\n" in notifier_of(sw).sent[0][0]
    assert controller.pressed == ["A", "CAPTURE", "CAPTURE", "B", "CAPTURE", "CAPTURE"]
    assert controller.sticks == [
        ("LEFT", 0, -Controller.STICK_MAX, WaitConfig.stick_tick),
        ("LEFT", 0, -Controller.STICK_MAX, WaitConfig.stick_tick),
        ("LEFT", 0, -Controller.STICK_MAX, WaitConfig.stick_tick),
    ]


# ---------------------------------------------------------------- 整个步骤：抛错和超时


def test_select_pokemon_raises_timeout_error_when_result_screen_never_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """带走宝可梦的界面一直不出现：抛 TimeoutError，报错里有「带走宝可梦的界面」。"""
    sw = make_lair_session([screens.plain()], data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="带走宝可梦的界面"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_option_menu_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    controller: Any,
) -> None:
    """按 A 之后「选择 / 查看能力 / 取消」一直不出现：抛 TimeoutError，报错里有「查看能力」，按的都是 A。"""
    sw = make_lair_session([screens.title()], data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="查看能力"):
        select_pokemon(sw)
    assert set(controller.pressed) == {"A"}


def test_select_pokemon_raises_timeout_error_when_summary_page_never_opens(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """选了「查看能力」之后菜单一直不消失：抛 TimeoutError，报错里有「进资料页」。"""
    sw = make_lair_session([screens.title(), screens.option_menu()], data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="进资料页"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_summary_name_is_never_read(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """资料页上一直读不到名字：抛 TimeoutError，报错里有「资料页上第 1 只」和它的名字（斧牙龙）。"""
    sw = make_lair_session(
        [screens.title(), screens.option_menu(), screens.option_menu(), screens.plain()],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="资料页上第 1 只（斧牙龙）的名字"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_shiny_sprite_never_appears(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """闪光的那只，资料页右边的宝可梦一直画不出来：抛 TimeoutError，报错里有「资料页右边的宝可梦」。"""
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A", shiny=True),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="资料页右边的宝可梦"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_summary_never_turns_to_next_pokemon(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """抓到 2 只，往下翻页之后名字一直不变：抛 TimeoutError，报错里有「资料页换到下一只」。"""
    sw = make_lair_session(
        [screens.title(), screens.option_menu(), screens.option_menu(), screens.summary("名A")],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    with pytest.raises(TimeoutError, match="资料页换到下一只"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_list_never_comes_back(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens, controller: Any
) -> None:
    """查完之后按 B 一直回不到带走列表：抛 TimeoutError，报错里有「回到带走宝可梦的界面」，之后按的都是 B。"""
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A"),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="回到带走宝可梦的界面"):
        select_pokemon(sw)
    assert set(controller.pressed[1:]) == {"B"}


def test_select_pokemon_raises_timeout_error_when_list_preview_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    fake_images: ImageFactory,
) -> None:
    """带走列表左边的预览一直没有画出来（颜色占比一直是满的）：抛 TimeoutError，报错里有「列表左边的宝可梦」。"""
    covered = fake_images.add(
        texts={RECTS.result_title: TITLE_TEXT},
        ratios={(RECTS.result_preview, GameConfig.result_preview_lower): 1.0},
    )
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.title(),
            covered,
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="列表左边的宝可梦"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_list_cursor_never_moves(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens
) -> None:
    """抓到 2 只、第 1 只是闪光，列表光标推了摇杆也一直不到第 2 只：抛 TimeoutError，报错里有「列表光标移到第 2 只」。"""
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A", shiny=True),
            screens.summary("名A", shiny=True),
            screens.sprite(),
            screens.summary("名A"),
            screens.summary("名B"),
            screens.summary("名B"),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.title(),
            screens.plain(),
            screens.cursor(0),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    with pytest.raises(TimeoutError, match="列表光标移到第 2 只"):
        select_pokemon(sw)


def test_select_pokemon_raises_timeout_error_when_confirm_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    screens: Screens,
    controller: Any,
) -> None:
    """没有闪光、不带走：一直按 B 也出现不了「不带宝可梦回去」的是 / 否：抛 TimeoutError，报错里有「不带走的确认」。"""
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.title(),
            screens.plain(),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="不带走的确认"):
        select_pokemon(sw)
    assert set(controller.pressed[2:]) == {"B"}


def test_select_pokemon_raises_timeout_error_when_transition_black_never_comes(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens, controller: Any
) -> None:
    """确认之后一直按 A 画面也不变黑（等 2 倍的 timeout）：抛 TimeoutError，报错里有「转场黑屏」。"""
    sw = make_lair_session(
        [
            screens.title(),
            screens.option_menu(),
            screens.option_menu(),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.summary("名A"),
            screens.title(),
            screens.plain(),
            screens.confirm(),
        ],
        data=MEMORY,
    )
    finished_run(sw, prepare_run, ["fraxure"])
    with pytest.raises(TimeoutError, match="转场黑屏"):
        select_pokemon(sw)
    assert set(controller.pressed[-3:]) == {"A"}


# ---------------------------------------------------------------- _decide_next_run


def test_decide_next_run_restarts_game_when_no_shiny_and_path_is_locked(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    controller: Any,
    restarts: list[object],
) -> None:
    """没有闪光、打赢、倒下次数和用时都在范围内、keep_path 开着、极矿石够：锁定这张图，调一次 restart，不按键；
    战报里有「锁定这张图」和「重启游戏保留路线」。
    """
    sw = make_lair_session(data=MEMORY, keep_path=True)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle", "sneasel", "tapu-lele"])
    sw.game.faints = [0, 0, 0, 0]
    sw.game.dynite_ore = 50
    module._decide_next_run(sw, [], [0.0, 0.0, 0.0, 0.0])
    assert restarts == [sw]
    assert controller.pressed == []
    assert sw.game.lock_path is True
    report = notifier_of(sw).sent[0][0]
    assert "锁定：锁定这张图\n" in report
    assert "处理：不带走，重启游戏保留路线\n" in report


# ---------------------------------------------------------------- _take / _move_list_cursor


def test_take_exits_with_notification_when_more_than_one_shiny(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """_take 收到两只以上闪光的序号：发 @全体 的通知，抛 SystemExit，内容就是通知的文字。"""
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle", "sneasel"])
    with pytest.raises(SystemExit) as error:
        module._take(sw, [0, 2])
    text = "这一局有 2 只闪光（第 1、3 只），程序停在带走宝可梦的列表上，等你来选"
    assert str(error.value) == text
    assert notifier_of(sw).sent_everyone == [(text, [])]


def test_move_list_cursor_pushes_stick_up_when_target_is_above_cursor(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens, controller: Any
) -> None:
    """列表光标在第 2 只、要移到第 1 只：往上推（+Controller.STICK_MAX），推一次光标就到了。"""
    sw = make_lair_session([screens.cursor(1), screens.cursor(1), screens.cursor(0)], data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    module._move_list_cursor(sw, 0)
    assert controller.sticks == [("LEFT", 0, Controller.STICK_MAX, WaitConfig.stick_tick)]


def test_move_list_cursor_pushes_stick_down_when_target_is_below_cursor(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, screens: Screens, controller: Any
) -> None:
    """列表光标在第 1 只、要移到第 2 只：往下推（-Controller.STICK_MAX）。"""
    sw = make_lair_session([screens.cursor(0), screens.cursor(0), screens.cursor(1)], data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    module._move_list_cursor(sw, 1)
    assert controller.sticks == [("LEFT", 0, -Controller.STICK_MAX, WaitConfig.stick_tick)]


# ---------------------------------------------------------------- _report


def test_report_for_win_with_one_shiny_taken_away(
    make_lair_session: SessionFactory, prepare_run: PrepareRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """打赢（抓到 4/4）、第 2 关倒下 1 次、第 3 只和首领是闪光、带走第 3 只：战报整段文字。"""
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle", "sneasel", "tapu-lele"])
    sw.game.faints = [0, 1, 0, 0]
    keep, lock = sw.game.finish_run([2])
    module._report(sw, [2], [3.0, 5.0, 40.55, 10.2], keep, lock)
    assert notifier_of(sw).sent[0][0] == (
        "```\n"
        "第 1 轮战报：\n"
        "胜，倒下 1 次，0.0 分钟，抓到 4/4\n"
        "路线：斧牙龙 → 龟足巨铠 → 狃拉\n"
        "得分：20.356，首发 流氓熊猫（第 1 位）\n"
        "逐关：\n"
        "  第一关 抓到 斧牙龙（龙）\n"
        "         非闪（03.00 / 阈值 10）\n"
        "  第二关 抓到 龟足巨铠（岩石/水）\n"
        "         非闪（05.00 / 阈值 10）\n"
        "         倒下 1 次\n"
        "  第三关 抓到 狃拉（恶/冰）\n"
        "         闪光（40.55 / 阈值 10）\n"
        "  首　领 抓到 卡璞・蝶蝶（超能力/妖精）\n"
        "         闪光（10.20 / 阈值 10）\n"
        "处理：带走第 3 只闪光\n"
        "锁定：带走了闪光，不锁定\n"
        "剩余：极矿石 37 个，究极球 25 个\n"
        "```"
    )


def test_report_for_overtime_loss_shows_stage_score_in_brackets(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """输了但命没扣完：写「负（超回合）」；有 stage_score 时得分后面带括号（三关、首领的分）；
    输掉的那一关写「超回合」，后面的关卡不写。
    """
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle"])
    sw.game.faints = [0, 0]
    sw.game.stage_score = 0.5
    sw.game.boss_score = 0.25
    sw.game.route_score = 0.75
    keep, lock = sw.game.finish_run([])
    module._report(sw, [], [3.0, 5.0], keep, lock)
    assert notifier_of(sw).sent[0][0] == (
        "```\n"
        "第 1 轮战报：\n"
        "负（超回合），倒下 0 次，0.0 分钟，抓到 2/4\n"
        "路线：斧牙龙 → 龟足巨铠 → 狃拉\n"
        "得分：0.750（三关 0.500，首领 0.250），首发 流氓熊猫（第 1 位）\n"
        "逐关：\n"
        "  第一关 抓到 斧牙龙（龙）\n"
        "         非闪（03.00 / 阈值 10）\n"
        "  第二关 抓到 龟足巨铠（岩石/水）\n"
        "         非闪（05.00 / 阈值 10）\n"
        "  第三关 超回合 狃拉（恶/冰）\n"
        "处理：不带走\n"
        "锁定：没有开启 keep_path，不锁定\n"
        "剩余：极矿石 37 个，究极球 25 个\n"
        "```"
    )


def test_report_for_wipe_out_with_several_shinies_and_faints(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """四次倒下（团灭）：写「负」，输掉的那一关写「团灭」；两只闪光写「有 2 只闪光（第 1、3 只），停下来等人选」；
    倒下的关卡另起一行写倒下几次。
    """
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure", "barbaracle", "sneasel"])
    sw.game.faints = [0, 2, 2]
    sw.game.lock_results = [True, False]
    module._report(sw, [0, 2], [30.0, 1.0, 20.0], False, "x")
    assert notifier_of(sw).sent[0][0] == (
        "```\n"
        "第 2 轮战报：\n"
        "负，倒下 4 次，0.0 分钟，抓到 3/4\n"
        "路线：斧牙龙 → 龟足巨铠 → 狃拉\n"
        "得分：20.356，首发 流氓熊猫（第 1 位）\n"
        "逐关：\n"
        "  第一关 抓到 斧牙龙（龙）\n"
        "         闪光（30.00 / 阈值 10）\n"
        "  第二关 抓到 龟足巨铠（岩石/水）\n"
        "         非闪（01.00 / 阈值 10）\n"
        "         倒下 2 次\n"
        "  第三关 抓到 狃拉（恶/冰）\n"
        "         闪光（20.00 / 阈值 10）\n"
        "         倒下 2 次\n"
        "  首　领 团灭 卡璞・蝶蝶（超能力/妖精）\n"
        "处理：有 2 只闪光（第 1、3 只），停下来等人选\n"
        "锁定：x\n"
        "剩余：极矿石 37 个，究极球 25 个\n"
        "```"
    )


def test_report_without_route_shows_question_marks(
    make_lair_session: SessionFactory,
) -> None:
    """还没有路线和首发的状态（刚开始、什么都没选）：路线和首发写「?」，逐关只有首领一行。"""
    sw = make_lair_session(data=MEMORY)
    sw.game.started = time.time()
    sw.game.faints = [0, 2, 2]
    module._report(sw, [], [], False, "不锁定")
    assert notifier_of(sw).sent[0][0] == (
        "```\n"
        "第 0 轮战报：\n"
        "负，倒下 4 次，0.0 分钟，抓到 0/4\n"
        "路线：?\n"
        "得分：0.000，首发 ?\n"
        "逐关：\n"
        "  首　领 团灭 卡璞・蝶蝶（超能力/妖精）\n"
        "处理：一只都没抓到\n"
        "锁定：不锁定\n"
        "剩余：极矿石 37 个，究极球 25 个\n"
        "```"
    )


def test_report_attaches_screenshots_saved_since_the_run_started(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """战报附上这一局开始之后存下的战果截图（闪光目录和战果目录里的 .jpg）：开始之前的旧图不附。"""
    sw = make_lair_session(data=MEMORY)
    finished_run(sw, prepare_run, ["fraxure"])
    old = sw.config.result_dir / "old.jpg"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    past = time.time() - 1000
    os.utime(old, (past, past))
    new_result = sw.config.result_dir / "new-result.jpg"
    new_result.write_bytes(b"new")
    sw.config.shiny_dir.mkdir(parents=True)
    new_shiny = sw.config.shiny_dir / "new-shiny.jpg"
    new_shiny.write_bytes(b"new")
    module._report(sw, [], [0.0], False, "x")
    assert notifier_of(sw).sent[0][1] == sorted([new_result, new_shiny])
