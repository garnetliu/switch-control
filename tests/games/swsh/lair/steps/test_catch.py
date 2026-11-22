"""steps.catch：打赢之后抓宝可梦，普通关再决定要不要换。

没有抓宝可梦界面的截图（logs/keep 里没有），画面判断用假截图（conftest 的 fake_images）：
每张假截图说明各个区域上读到的文字。选好首发和路线之后的状态用 prepare_run 按 seed 算出来
（基准 seed，2x2 的图，路线 (1,1) → (2,2) → (3,1)，第一关的对手是 fraxure），队伍是首发加三个队友。
"""

import importlib
import logging
from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from control_switch.games.swsh.lair import upstream
from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.session import LairSession

catch_module: ModuleType = importlib.import_module("control_switch.games.swsh.lair.steps.catch")
catch = catch_module.catch

RECTS = GameConfig.rects
SessionFactory = Callable[..., LairSession]
PrepareRun = Callable[..., Any]
ImageFactory = Any

# 第一关抓的对手，队伍（首发 pangoro 加三个队友）
FIRST_OPPONENT = "fraxure"
TEAM = ["pangoro", "maractus", "galvantula", "cofagrigus"]


def plain(images: ImageFactory) -> bytes:
    """什么字也读不到的画面。"""
    return images.add()


def catch_option(images: ImageFactory) -> bytes:
    """「捕捉 / 不捕捉」的菜单。"""
    return images.add(texts={RECTS.catch_option: "捕捉"})


def ball_menu(images: ImageFactory, name: str = "究极球", count: str = "×26") -> bytes:
    """选球界面：「使用」按钮，球名和数量。"""
    return images.add(
        texts={RECTS.ball_use: "使用", RECTS.ball_name: name, RECTS.ball_count: count}
    )


def swap_menu(images: ImageFactory, hps: list[str] | None = None) -> bytes:
    """换不换的界面：第一个选项是「替换」，hps 是队伍血量文字，自上而下，在画面上打乱顺序给。"""
    hps = ["100/100", "80/100", "60/100", "40/100"] if hps is None else hps
    lines = [
        (text, ((0.2, 0.35 + 0.1 * index), (0.3, 0.4 + 0.1 * index)))
        for index, text in enumerate(hps)
    ]
    lines.reverse()
    return images.add(texts={RECTS.swap_options[0]: "替换"}, lines={RECTS.swap_hp: lines})


def black(images: ImageFactory) -> bytes:
    """黑屏。"""
    return images.add(black=True)


def throw_ball(images: ImageFactory, **ball: str) -> list[bytes]:
    """从「捕捉 / 不捕捉」到球扔出去的画面：按 A 选捕捉、选球界面、按 A 扔球、选球界面消失。"""
    return [
        catch_option(images),
        catch_option(images),
        plain(images),
        ball_menu(images, **ball),
        ball_menu(images, **ball),
        plain(images),
    ]


def setup_first_stage(sw: LairSession, prepare_run: PrepareRun) -> None:
    """第一关打完、要抓 fraxure：current_index 是 1，队伍是首发加三个队友，血量满。"""
    prepare_run(sw)
    maps = sw.game.maps
    assert maps is not None
    maps["current_index"] = 1
    sw.game.team = [(name, 1.0) for name in TEAM]


def force_decision(monkeypatch: pytest.MonkeyPatch, take: bool) -> None:
    """upstream.decide_catch 换成固定返回 take 的函数。"""
    monkeypatch.setattr(
        upstream, "decide_catch", lambda scorer, walker: (take, {"不换": 1.0, "换": 2.0})
    )


# ---------------------------------------------------------------- catch：整个步骤


def test_catch_normal_stage_keeps_pokemon_when_decision_is_not_to_swap(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """普通关，按 seed 推出来不换：按过的键是 A（捕捉）、A（扔球）、B（不换），返回 "path"。
    记下的有：抓到 1 只、抓到的是 fraxure、这一关上场的是首发、决定是不换、剩下 25 个究极球。
    """
    sw = make_lair_session(
        [*throw_ball(fake_images), swap_menu(fake_images), plain(fake_images), black(fake_images)]
    )
    setup_first_stage(sw, prepare_run)
    assert catch(sw) == "path"
    assert controller.pressed == ["A", "A", "B"]
    assert sw.game.num_caught == 1
    assert sw.game.caught == [FIRST_OPPONENT]
    assert sw.game.fielded == ["pangoro"]
    assert sw.game.choices == [False]
    assert sw.game.balls == {"究极球": 25}
    assert sw.game.team[0] == ("pangoro", 1.0)


def test_catch_normal_stage_takes_new_pokemon_when_decision_is_to_swap(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """普通关，决定换（upstream.decide_catch 换成固定返回换）：最后按的是 A，自己这只换成抓到的 fraxure、满血，
    决定记成换。
    """
    force_decision(monkeypatch, True)
    sw = make_lair_session(
        [*throw_ball(fake_images), swap_menu(fake_images), plain(fake_images), black(fake_images)]
    )
    setup_first_stage(sw, prepare_run)
    assert catch(sw) == "path"
    assert controller.pressed == ["A", "A", "A"]
    assert sw.game.team[0] == (FIRST_OPPONENT, 1.0)
    assert sw.game.choices == [True]


def test_catch_updates_team_hp_from_swap_screen(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """换不换的界面上队伍血量四行（画面上顺序是乱的，按位置自上而下排）：team 里每只的血量比例按这个顺序更新。"""
    sw = make_lair_session(
        [*throw_ball(fake_images), swap_menu(fake_images), plain(fake_images), black(fake_images)]
    )
    setup_first_stage(sw, prepare_run)
    catch(sw)
    assert sw.game.team == [
        ("pangoro", 1.0),
        ("maractus", 0.8),
        ("galvantula", 0.6),
        ("cofagrigus", 0.4),
    ]


@pytest.mark.parametrize(
    "hps", [["100/100", "80/100", "60/100"], ["100/100", "80/0", "60/100", "40/100"]]
)
def test_catch_keeps_team_hp_when_swap_screen_hp_is_unreadable(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    hps: list[str],
) -> None:
    """血量文字只读到 3 行，或者有一行最大血量是 0：队伍的血量不更新，还是原来的。"""
    sw = make_lair_session(
        [
            *throw_ball(fake_images),
            swap_menu(fake_images, hps),
            plain(fake_images),
            black(fake_images),
        ]
    )
    setup_first_stage(sw, prepare_run)
    sw.game.team = [(name, 0.5) for name in TEAM]
    catch(sw)
    assert sw.game.team == [(name, 0.5) for name in TEAM]


def test_catch_boss_throws_legendary_ball_and_returns_select_pokemon(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第 4 只（首领）：找的是 legendary_ball（大师球，不是 base_ball），按过的键是 A、A，没有换不换，
    返回 "select_pokemon"；抓到的名单里加上首领，抓到 4 只。
    """
    monkeypatch.setattr(GameConfig, "base_ball", "超级球")
    monkeypatch.setattr(GameConfig, "legendary_ball", "大师球")
    sw = make_lair_session(throw_ball(fake_images, name="大师球", count="×3"))
    prepare_run(sw)
    sw.game.num_caught = 3
    assert catch(sw) == "select_pokemon"
    assert controller.pressed == ["A", "A"]
    assert sw.game.caught == [sw.game.boss]
    assert sw.game.num_caught == 4
    assert sw.game.balls == {"大师球": 2}
    assert "tapu-lele" in sw.config.game_state_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------- catch：抛错和超时


def test_catch_raises_timeout_error_when_catch_menu_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """「捕捉 / 不捕捉」一直不出现：抛 TimeoutError，报错里有「捕捉」。"""
    sw = make_lair_session([plain(fake_images)])
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="「捕捉 / 不捕捉」"):
        catch(sw)


def test_catch_raises_timeout_error_when_catch_menu_never_disappears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """按 A 之后「捕捉」一直不消失：抛 TimeoutError，报错里有「「捕捉」消失」，按的都是 A。"""
    sw = make_lair_session([catch_option(fake_images)])
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="「捕捉」消失"):
        catch(sw)
    assert set(controller.pressed) == {"A"}


def test_catch_raises_timeout_error_when_ball_menu_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """「捕捉」消失之后选球界面一直不出现：抛 TimeoutError，报错里有「选球界面」。"""
    sw = make_lair_session(
        [catch_option(fake_images), catch_option(fake_images), plain(fake_images)]
    )
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="选球界面"):
        catch(sw)


def test_catch_raises_timeout_error_when_ball_menu_never_disappears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """按 A 扔球之后球名一直读得到：抛 TimeoutError，报错里有「扔出球，选球界面消失」。"""
    sw = make_lair_session(
        [
            catch_option(fake_images),
            catch_option(fake_images),
            plain(fake_images),
            ball_menu(fake_images),
        ]
    )
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="扔出球，选球界面消失"):
        catch(sw)


def test_catch_raises_timeout_error_when_swap_screen_never_appears(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
) -> None:
    """球扔出去之后换不换的界面一直不出现：抛 TimeoutError，报错里有「换不换的界面」。"""
    sw = make_lair_session([*throw_ball(fake_images), plain(fake_images)])
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="换不换的界面"):
        catch(sw)


def test_catch_raises_timeout_error_when_screen_never_turns_black_after_swap_choice(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """选了换或不换之后画面一直不变黑：抛 TimeoutError，报错里有「换不换之后的黑屏」，之后按的都是 B（不换）。"""
    sw = make_lair_session([*throw_ball(fake_images), swap_menu(fake_images), plain(fake_images)])
    setup_first_stage(sw, prepare_run)
    with pytest.raises(TimeoutError, match="换不换之后的黑屏"):
        catch(sw)
    assert set(controller.pressed[2:]) == {"B"}


# ---------------------------------------------------------------- 选球


def test_catch_moves_ball_cursor_left_until_wanted_ball_is_shown(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
) -> None:
    """选球界面上一开始是超级球：按 DLEFT 一次换成究极球就停，再按 A 扔球；按过的键是 A、DLEFT、A、B。"""
    sw = make_lair_session(
        [
            catch_option(fake_images),
            catch_option(fake_images),
            plain(fake_images),
            ball_menu(fake_images, "超级球", "×5"),
            ball_menu(fake_images, "超级球", "×5"),
            ball_menu(fake_images, "究极球", "×26"),
            ball_menu(fake_images, "究极球", "×26"),
            plain(fake_images),
            swap_menu(fake_images),
            plain(fake_images),
            black(fake_images),
        ]
    )
    setup_first_stage(sw, prepare_run)
    catch(sw)
    assert controller.pressed == ["A", "DLEFT", "A", "B"]
    assert sw.game.balls == {"究极球": 25}


def test_catch_throws_selected_ball_when_wanted_ball_is_not_found_after_30_turns(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    fake_images: ImageFactory,
    controller: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """翻了 30 下也没有究极球：日志里有警告，扔的是现在选中的球（第 30 下之后是高级球），数量记在那种球的名下，
    按了 30 次 DLEFT，最后按 A 扔球。
    """
    caplog.set_level(logging.DEBUG)
    names = ["超级球", "高级球"]
    frames = [catch_option(fake_images), catch_option(fake_images), plain(fake_images)]
    # 球名一开始是超级球；每按一次 DLEFT 之前的那一帧球名不变，按了之后换成另一种
    frames.append(ball_menu(fake_images, names[0], "×7"))
    for index in range(30):
        frames.append(ball_menu(fake_images, names[index % 2], "×7"))
        frames.append(ball_menu(fake_images, names[(index + 1) % 2], "×7"))
    frames += [ball_menu(fake_images, names[0], "×7"), plain(fake_images)]
    frames += [swap_menu(fake_images), plain(fake_images), black(fake_images)]
    sw = make_lair_session(frames)
    setup_first_stage(sw, prepare_run)
    catch(sw)
    assert controller.pressed.count("DLEFT") == 30
    assert controller.pressed[-2:] == ["A", "B"]
    assert any(
        "翻了 30 下也没找到究极球，扔现在选中的超级球" in r.getMessage() for r in caplog.records
    )
    assert sw.game.balls == {"超级球": 6}


# ---------------------------------------------------------------- _decide


def fake_walker(events: list[str], opponents: list[str], caught: int = 0) -> Any:
    """只有 _decide 用到的东西：next_event 按 index 取事件，opponents、caught、index。"""
    walker = SimpleNamespace(index=0, opponents=opponents, caught=caught)
    walker.next_event = lambda: events[walker.index] if walker.index < len(events) else "catch"
    return walker


def test_decide_returns_false_and_records_choice_when_walker_now_is_none(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """walker_now 返回 None（算不出来）：_decide 返回 False，决定记成不换，日志里有警告。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    setup_first_stage(sw, prepare_run)
    monkeypatch.setattr(catch_module, "walker_now", lambda sw: None)
    assert catch_module._decide(sw) is False
    assert sw.game.choices == [False]
    assert any("队伍会怎么变没算出来" in record.getMessage() for record in caplog.records)


def test_decide_skips_scientists_that_were_not_met(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """路线上记着两个研究员、实际没遇到就走到了这一关：walker.index 往后推了两格，每个都记一条警告，
    决定按 upstream.decide_catch 的结果记下。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    setup_first_stage(sw, prepare_run)
    walker = fake_walker(["scientist", "scientist", "catch"], [FIRST_OPPONENT])
    monkeypatch.setattr(catch_module, "walker_now", lambda sw: (object(), walker))
    force_decision(monkeypatch, True)
    assert catch_module._decide(sw) is True
    assert walker.index == 2
    messages = [record.getMessage() for record in caplog.records]
    assert sum("路线上记着的研究员没遇到" in message for message in messages) == 2
    assert sw.game.choices == [True]


def test_decide_only_warns_when_actual_opponent_differs_from_seed(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """按 seed 推的对手和实际的对手对不上：只记一条警告（写明两边的名字），照常决定，不抛错。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    setup_first_stage(sw, prepare_run)
    walker = fake_walker([], ["别的宝可梦"])
    monkeypatch.setattr(catch_module, "walker_now", lambda sw: (object(), walker))
    force_decision(monkeypatch, False)
    assert catch_module._decide(sw) is False
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        f"按 seed 推的这一只是 别的宝可梦，实际是 {FIRST_OPPONENT}" in message
        for message in messages
    )
    assert any("抓了不换 1.00，抓了换 2.00" in message for message in messages)


def test_decide_with_real_walker_decides_not_to_swap_for_first_stage(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """用真的 walker（不替换 walker_now 和 decide_catch）：基准 seed 第一关，改动前的代码算出来是
    不换，日志里是「fraxure：抓了不换 7.97，抓了换 7.71」。
    """
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    setup_first_stage(sw, prepare_run)
    assert catch_module._decide(sw) is False
    assert any(
        "fraxure：抓了不换 7.97，抓了换 7.71" in record.getMessage() for record in caplog.records
    )


# ---------------------------------------------------------------- walker_now


def test_walker_now_returns_none_when_seed_is_not_known(
    make_lair_session: SessionFactory,
) -> None:
    """存档里还没有 seed（刚开始的状态）：walker_now 返回 None。"""
    sw = make_lair_session()
    assert catch_module.walker_now(sw) is None


def test_walker_now_returns_scorer_and_walker_with_default_team(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """已经选好首发和路线、队伍还没读过（team 是空的）：返回 (Scorer, Walker)，队伍是首发加三个队友，
    对手是路线上的三关，一只都没抓。
    """
    sw = make_lair_session()
    prepare_run(sw)
    sw.game.team = []
    found = catch_module.walker_now(sw)
    assert found is not None
    scorer, walker = found
    assert isinstance(scorer, upstream.Scorer)
    assert isinstance(walker, upstream.Walker)
    assert walker.team == TEAM
    assert walker.opponents == [FIRST_OPPONENT, "barbaracle", "sneasel"]
    assert walker.caught == 0


def test_walker_now_uses_actual_team_from_game_state(
    make_lair_session: SessionFactory, prepare_run: PrepareRun
) -> None:
    """game.team 里有实际读到的队伍：walker 的队伍换成它（名字按 game.team 的顺序）。"""
    sw = make_lair_session()
    prepare_run(sw)
    sw.game.team = [("cofagrigus", 1.0), ("pangoro", 0.5), ("maractus", 1.0), ("galvantula", 1.0)]
    found = catch_module.walker_now(sw)
    assert found is not None
    assert found[1].team == ["cofagrigus", "pangoro", "maractus", "galvantula"]


def test_walker_now_returns_none_and_warns_when_replay_raises(
    make_lair_session: SessionFactory,
    prepare_run: PrepareRun,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """推随机数时出异常（候选名单是空的，取首发时 IndexError）：返回 None，日志里有警告，不抛错。"""
    caplog.set_level(logging.DEBUG)
    sw = make_lair_session()
    prepare_run(sw)
    sw.game.candidates = []
    assert catch_module.walker_now(sw) is None
    assert any("按 seed 推队伍出错" in record.getMessage() for record in caplog.records)
