"""steps.hatch：一列一批孵蛋、逐只检查、整盒孵完之后的处理，返回 "fetch"（右边盒子满了返回 "done"）。

分三层测：
- hatch 本身（一批一批的顺序、存档、重启、放生）：_hatch_eggs_at_zero_gate、_process_baby、box 里的操作都换成假函数。
- _process_baby（逐只检查：闪光、比亲代好、不留）：box 里读格子、移光标、交换的操作换成假函数。
- 下坡、绕圈、孵化那几段（_hatch_eggs_at_zero_gate、_leave_ramp、_do_egg_cycle_motion、_handle_egg_hatching）。
默认模式：留下的东西（闪光、换下来的亲代）存档；一盒什么都没留下就重启游戏回档；不当场放生，孵出来的放回盒子。
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from control_switch.session import Frame

box_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.box")
fly_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.fly")
actions_module: ModuleType = importlib.import_module("control_switch.games.sv.actions")
flow_module: ModuleType = importlib.import_module("control_switch.flow")
hatch_module: ModuleType = importlib.import_module("control_switch.games.sv.egg.steps.hatch")
hatch = hatch_module.hatch

Entry = tuple[Any, ...]


class RecordingNotifier:
    """假 notifier：记下 send 和 send_everyone 的文字和附件，不发消息。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[Path]]] = []
        self.sent_everyone: list[tuple[str, list[Path]]] = []

    def send(self, text: str, files: Any = None) -> None:
        self.sent.append((text, [Path(path) for path in files or []]))

    def send_everyone(self, text: str, files: Any = None) -> None:
        self.sent_everyone.append((text, [Path(path) for path in files or []]))


class Box:
    """盒子的画面模型：光标在哪、哪些格子有宝可梦，box.move_cursor、box.slot_has_pokemon 读写它。"""

    def __init__(self, stage: Any, occupied: set[tuple[int, int]]) -> None:
        self.cursor: tuple[str, int, int] = ("party", 0, 0)
        self.occupied = occupied
        self.log: list[Entry] = stage.log
        stage.replace(box_module, "move_cursor", self.move)
        stage.replace(box_module, "slot_has_pokemon", lambda sw: self.has())

    def move(self, sw: Any, place: str, row: int, col: int) -> None:
        self.cursor = (place, row, col)
        self.log.append(("cursor", place, row, col))

    def has(self) -> bool:
        return self.cursor[0] == "slots" and self.cursor[1:] in self.occupied


# ---- hatch 本身 ----


class Plan:
    """hatch 的一次运行用的假环境。

    filled：中间盒子里放着蛋的列（第 0 列已经装进队伍了）。counts：每次装一列之后数到的蛋数（用完了是 5）。
    keep_in：在第几批（从 0 数）里留下了东西。stop_in：在第几批里右边盒子满了（_process_baby 返回 False）。
    """

    def __init__(
        self,
        stage: Any,
        filled: set[int],
        counts: list[int] | None = None,
        keep_in: set[int] | None = None,
        stop_in: int | None = None,
    ) -> None:
        self.stage = stage
        self.batch = -1
        self.counts = list(counts or [])
        keep = keep_in or set()
        self.box = Box(stage, {(0, col) for col in filled})

        def hatch_batch(sw: Any, count: int) -> None:
            self.batch += 1
            stage.log.append(("hatch", count))

        def process_baby(sw: Any, index: int, count: int) -> bool:
            stage.log.append(("baby", index, count))
            if index == 0 and self.batch in keep:
                sw.kept_in_box = True
                sw.save_pending = True
            return not (stop_in == self.batch and index == count - 1)

        stage.replace(hatch_module, "_hatch_eggs_at_zero_gate", hatch_batch)
        stage.replace(hatch_module, "_process_baby", process_baby)
        stage.stub(fly_module, "fly_to_gate")
        stage.stub(box_module, "open_box")
        stage.stub(box_module, "exit_to_overworld")
        stage.stub(box_module, "load_column")
        stage.stub(box_module, "unload_column")
        stage.stub(box_module, "count_party_eggs", lambda: self.counts.pop(0) if self.counts else 5)
        stage.stub(box_module, "release_box")
        stage.stub(box_module, "to_picnic_party")
        stage.stub(actions_module, "save_game")
        stage.stub(flow_module, "restart")
        # 重启之后 hatch 要等画面回到野外才返回；默认马上就是野外
        self.overworld_polls = 0
        stage.set_screens(is_overworld=self.overworld)
        stage.sw.eggs_in_party = 5

    def overworld(self) -> bool:
        self.overworld_polls += 1
        return self.overworld_polls > self.polls_before_overworld

    # 重启之后前几次看画面还不是野外（游戏还在加载）
    polls_before_overworld = 0

    def run(self) -> str:
        return hatch(self.stage.sw)

    def names(self) -> list[str]:
        return [entry[0] for entry in self.stage.log]

    def column_args(self, name: str) -> list[int]:
        return [entry[1] for entry in self.stage.log if entry[0] == name]


FULL = {1, 2, 3, 4, 5}


def test_hatch_returns_fetch_when_box_is_done(stage: Any) -> None:
    """整盒孵完：返回 "fetch"。"""
    assert Plan(stage, FULL).run() == "fetch"


def test_hatch_hatches_six_batches_loading_columns_one_to_five(stage: Any) -> None:
    """一盒 6 列蛋，第 0 列已经在队伍里：孵 6 批，每批之后把孵出来的卸回刚装蛋的那一列（0 到 5），
    再装下一列（1 到 5）。
    """
    plan = Plan(stage, FULL)
    plan.run()
    assert plan.column_args("hatch") == [5] * 6
    assert plan.column_args("unload_column") == [0, 1, 2, 3, 4, 5]
    assert plan.column_args("load_column") == [1, 2, 3, 4, 5]


def test_hatch_first_batch_uses_number_of_eggs_fetch_left_in_party(stage: Any) -> None:
    """第一批的蛋数是 sw.eggs_in_party（fetch 换队伍时数到的），之后每批是装一列之后数到的蛋数。"""
    plan = Plan(stage, FULL, counts=[4, 3, 2, 1, 5])
    stage.sw.eggs_in_party = 3
    plan.run()
    assert plan.column_args("hatch") == [3, 4, 3, 2, 1, 5]


def test_hatch_checks_every_baby_of_each_batch(stage: Any) -> None:
    """每批孵完之后逐只检查：第 0 到 count-1 只，带上这批的蛋数，检查的顺序在孵完这一批之后。"""
    plan = Plan(stage, FULL, counts=[4, 5, 5, 5, 5])
    plan.run()
    babies = [entry for entry in stage.log if entry[0] in ("hatch", "baby")]
    assert babies[:6] == [("hatch", 5)] + [("baby", i, 5) for i in range(5)]
    assert babies[6:11] == [("hatch", 4)] + [("baby", i, 4) for i in range(4)]


def test_hatch_between_batches_flies_back_opens_box_checks_unloads_loads_and_leaves(
    stage: Any,
) -> None:
    """两批之间的顺序：孵完飞回闸口，开盒子，逐只检查，把孵出来的卸回第 0 列，光标到下一个有东西的列（第 1 列），
    装进队伍，光标到队伍第 0 只，数蛋，退出盒子，再孵下一批。
    """
    Plan(stage, FULL).run()
    first = stage.log.index(("hatch", 5))
    second = stage.log.index(("hatch", 5), first + 1)
    assert stage.log[first:second] == [
        ("hatch", 5),
        ("fly_to_gate",),
        ("open_box",),
        *[("baby", i, 5) for i in range(5)],
        ("unload_column", 0),
        ("cursor", "slots", 0, 1),
        ("load_column", 1),
        ("cursor", "party", 0, 0),
        ("count_party_eggs",),
        ("exit_to_overworld",),
    ]


def test_hatch_skips_empty_columns_when_looking_for_next_egg_column(stage: Any) -> None:
    """盒子里只有第 1 列和第 3 列有蛋：光标依次看第 1、2、3、4、5 列，装的是第 1 列和第 3 列，
    卸的是第 0、1、3 列（卸到刚装蛋的那一列）。
    """
    plan = Plan(stage, {1, 3})
    plan.run()
    visited = [entry[3] for entry in stage.log if entry[:3] == ("cursor", "slots", 0)]
    assert visited == [1, 2, 3, 4, 5]
    assert plan.column_args("load_column") == [1, 3]
    assert plan.column_args("unload_column") == [0, 1, 3]
    assert plan.column_args("hatch") == [5, 5, 5]


def test_hatch_with_no_more_egg_columns_ends_after_first_batch(stage: Any) -> None:
    """盒子里没有别的蛋了：孵一批、检查、卸回第 0 列就结束，没有装过列。"""
    plan = Plan(stage, set())
    assert plan.run() == "fetch"
    assert plan.column_args("hatch") == [5]
    assert plan.column_args("load_column") == []
    assert plan.column_args("unload_column") == [0]


def test_hatch_restarts_game_and_does_nothing_else_when_nothing_was_kept(stage: Any) -> None:
    """一盒什么都没留下：最后一批卸完之后重启游戏（flow.restart）回档，这是最后一件事；
    没放生、没换回野餐队伍、没存档。
    """
    plan = Plan(stage, FULL)
    plan.run()
    assert stage.log[-1] == ("restart",)
    assert plan.names().count("restart") == 1
    for name in ("release_box", "to_picnic_party", "save_game"):
        assert name not in plan.names()


def test_hatch_waits_for_overworld_after_restart_by_watching_screen_not_fixed_sleep(
    stage: Any,
) -> None:
    """重启回档之后：一直看画面，到了野外（screens.is_overworld）才返回 "fetch"，不能固定等几秒
    （加载慢于固定的秒数，后面开野餐的路线按键就丢了）。前 3 次看画面还不是野外：看了 4 次画面，
    只过了几秒，没有固定等 20 秒。
    """
    plan = Plan(stage, FULL)
    plan.polls_before_overworld = 3
    start = stage.clock.now
    assert plan.run() == "fetch"
    assert plan.overworld_polls == 4
    assert stage.clock.now - start < 20


def test_hatch_does_not_return_while_game_is_still_loading_after_restart(stage: Any) -> None:
    """重启回档之后一直不是野外（游戏卡住了）：不能当作回来了，hatch 抛 TimeoutError，不是正常返回。"""
    plan = Plan(stage, FULL)
    plan.polls_before_overworld = 10**9
    with pytest.raises(TimeoutError):
        plan.run()


@pytest.mark.parametrize("keep_in", [set(), {5}])
def test_hatch_clears_frames_after_finishing_a_box(stage: Any, keep_in: set[int]) -> None:
    """一盒孵完返回 "fetch" 之后，sw.frames 是空的：fetch 和 hatch 一直循环，截图只在 initialize 里清的话，
    列表会越来越大，出错时 save_frames 还会把从开始到现在的截图全写进日志目录。重启回档和留过东西两种收尾都要清。
    """
    plan = Plan(stage, FULL, keep_in=keep_in)
    for number in range(50):
        stage.sw.frames.append(Frame(0.0, "hatch", f"第 {number} 张", b"x"))
    assert plan.run() == "fetch"
    assert stage.sw.frames == []


def test_hatch_ignores_kept_flags_left_over_from_earlier_box(stage: Any) -> None:
    """kept_in_box、save_pending 在一盒开始时清掉：上一盒留下的标记不算这一盒的，这一盒没留下就重启，不存档。"""
    plan = Plan(stage, FULL)
    stage.sw.kept_in_box = True
    stage.sw.save_pending = True
    plan.run()
    assert plan.names().count("restart") == 1
    assert "save_game" not in plan.names()


def test_hatch_releases_box_changes_party_back_and_saves_when_kept_in_last_batch(
    stage: Any,
) -> None:
    """最后一批里留下了东西：整盒孵完后放生整盒、换回野餐队伍、退出盒子、存档，不重启；只存一次档。"""
    plan = Plan(stage, FULL, keep_in={5})
    assert plan.run() == "fetch"
    assert stage.log[-5:] == [
        ("unload_column", 5),
        ("release_box",),
        ("to_picnic_party",),
        ("exit_to_overworld",),
        ("save_game",),
    ]
    assert plan.names().count("save_game") == 1
    assert "restart" not in plan.names()


def test_hatch_saves_before_next_batch_when_kept_earlier_and_again_at_end(stage: Any) -> None:
    """第一批里留下了东西：退出盒子后、孵下一批之前存一次档；整盒孵完之后放生、换队伍、再存一次档；共 2 次，不重启。"""
    plan = Plan(stage, FULL, keep_in={0})
    assert plan.run() == "fetch"
    first = stage.log.index(("hatch", 5))
    second = stage.log.index(("hatch", 5), first + 1)
    between = stage.log[first:second]
    assert between[-2:] == [("exit_to_overworld",), ("save_game",)]
    assert plan.names().count("save_game") == 2
    assert stage.log[-1] == ("save_game",)
    assert "restart" not in plan.names()


def test_hatch_does_not_save_between_batches_when_nothing_kept_yet(stage: Any) -> None:
    """留下东西之前不存档：只在第 3 批留下东西，第 1、2 批之间没有存档。"""
    plan = Plan(stage, FULL, keep_in={2})
    plan.run()
    third = [index for index, entry in enumerate(stage.log) if entry == ("hatch", 5)][2]
    assert "save_game" not in plan.names()[:third]


def test_hatch_returns_done_without_restart_or_save_when_right_box_is_full(stage: Any) -> None:
    """检查时右边盒子没空格（_process_baby 返回 False）：马上返回 "done"，不再孵下一批，不重启、不存档、不放生。"""
    plan = Plan(stage, FULL, stop_in=1)
    assert plan.run() == "done"
    assert plan.column_args("hatch") == [5, 5]
    for name in ("restart", "save_game", "release_box", "to_picnic_party"):
        assert name not in plan.names()


# ---- 逐只检查 ----


def make_mon(**kwargs: Any) -> Any:
    """box.Mon，默认是烛光灵、没有「最棒」、不是闪光。"""
    fields: dict[str, Any] = {"name": "烛光灵", "best": 0, "shiny": False}
    fields.update(kwargs)
    return box_module.Mon(**fields)


class BabyScene:
    """逐只检查的假环境：光标所在格子读到的宝可梦是 mon，右边盒子里 occupied 的格子有宝可梦。

    亲代是烛光灵，3 项最棒，在野餐队伍第 1 只（parent_index 0），评定已解锁。
    """

    def __init__(self, stage: Any, mon: Any, occupied: set[tuple[int, int]] | None = None) -> None:
        self.stage = stage
        self.notifier = RecordingNotifier()
        stage.monkeypatch.setattr(stage.sw, "notifier", self.notifier)
        self.box = Box(stage, occupied or set())
        stage.stub(box_module, "read_mon", mon)
        stage.stub(box_module, "to_left_box")
        stage.stub(box_module, "to_right_box")
        stage.stub(box_module, "swap_slots")
        stage.stub(box_module, "release_one")
        sw = stage.sw
        sw.parent_name = "烛光灵"
        sw.parent_best = 3
        sw.parent_index = 0
        sw.judge_unlocked = True
        sw.kept_in_box = False
        sw.save_pending = False

    def run(self, index: int = 0, count: int = 5) -> bool:
        return hatch_module._process_baby(self.stage.sw, index, count)

    def without_reads(self) -> list[Entry]:
        return [entry for entry in self.stage.log if entry[0] != "read_mon"]


@pytest.mark.parametrize(("index", "count", "row"), [(0, 5, 5), (4, 5, 1), (0, 3, 3), (2, 3, 1)])
def test_process_baby_checks_party_from_bottom_to_top(
    stage: Any, index: int, count: int, row: int
) -> None:
    """检查从队伍最下面往上：第 index 只孵出来的在队伍第 count - index 行（第 0 行是带队的，不查）。"""
    scene = BabyScene(stage, make_mon())
    scene.run(index, count)
    assert stage.log[0] == ("cursor", "party", row, 0)


def test_process_baby_discards_by_leaving_it_in_party(stage: Any) -> None:
    """不留的（不是闪光，也不比亲代好）：不放生、不交换、不推送，留在队伍里等会儿卸回盒子；返回 True，标记不变。"""
    scene = BabyScene(stage, make_mon(best=2))
    assert scene.run() is True
    assert scene.without_reads() == [("cursor", "party", 5, 0)]
    assert scene.notifier.sent == []
    assert scene.notifier.sent_everyone == []
    assert stage.sw.kept_in_box is False
    assert stage.sw.save_pending is False
    assert stage.sw.parent_best == 3


def test_process_baby_discards_same_species_with_equal_best_count(stage: Any) -> None:
    """和亲代同种、「最棒」项数一样（3 对 3）：不比亲代好，不留。"""
    scene = BabyScene(stage, make_mon(best=3))
    scene.run()
    assert scene.without_reads() == [("cursor", "party", 5, 0)]


def test_process_baby_discards_other_species_even_with_more_best_stats(stage: Any) -> None:
    """不是亲代的种类（水晶灯火灵）：「最棒」再多也不换亲代，不留。"""
    scene = BabyScene(stage, make_mon(name="水晶灯火灵", best=6))
    scene.run()
    assert scene.without_reads() == [("cursor", "party", 5, 0)]
    assert stage.sw.parent_best == 3


def test_process_baby_shiny_moves_to_first_empty_slot_of_right_box(stage: Any) -> None:
    """闪光：到右边盒子，从第 0 行第 0 列起按行找第一个空格（前两格有宝可梦，第三格空），
    把队伍里这只和那个空格交换，再回到中间盒子；返回 True。
    """
    scene = BabyScene(stage, make_mon(shiny=True), occupied={(0, 0), (0, 1)})
    assert scene.run() is True
    assert scene.without_reads() == [
        ("cursor", "party", 5, 0),
        ("to_right_box",),
        ("cursor", "slots", 0, 0),
        ("cursor", "slots", 0, 1),
        ("cursor", "slots", 0, 2),
        ("swap_slots", ("party", 5, 0), ("slots", 0, 2)),
        ("to_left_box",),
    ]


def test_process_baby_shiny_goes_to_next_row_when_first_row_is_full(stage: Any) -> None:
    """闪光：右边盒子第 0 行 6 格都满了：放到第 1 行第 0 列。"""
    scene = BabyScene(stage, make_mon(shiny=True), occupied={(0, col) for col in range(6)})
    scene.run()
    assert ("swap_slots", ("party", 5, 0), ("slots", 1, 0)) in stage.log


def test_process_baby_shiny_sends_everyone_notification_with_screenshot(stage: Any) -> None:
    """闪光：用 notifier.send_everyone 推送一条消息，带一张截图，截图文件存在，消息里有「闪光」。"""
    scene = BabyScene(stage, make_mon(shiny=True))
    scene.run()
    assert len(scene.notifier.sent_everyone) == 1
    text, files = scene.notifier.sent_everyone[0]
    assert "闪光" in text
    assert len(files) == 1
    assert files[0].is_file()


def test_process_baby_shiny_marks_box_as_kept_and_save_pending(stage: Any) -> None:
    """闪光：这一盒留下过东西（kept_in_box），下次退出盒子后要存档（save_pending）。"""
    scene = BabyScene(stage, make_mon(shiny=True))
    scene.run()
    assert stage.sw.kept_in_box is True
    assert stage.sw.save_pending is True


def test_process_baby_shiny_with_full_right_box_returns_false_after_notifying(
    stage: Any,
) -> None:
    """闪光、右边盒子 30 格都满了：先推送，找遍 30 格没有空格，返回 False（程序结束），没有交换。"""
    occupied = {(row, col) for row in range(5) for col in range(6)}
    scene = BabyScene(stage, make_mon(shiny=True), occupied=occupied)
    assert scene.run() is False
    assert len(scene.notifier.sent_everyone) == 1
    assert not any(entry[0] == "swap_slots" for entry in stage.log)
    assert len([entry for entry in stage.log if entry[:2] == ("cursor", "slots")]) == 30


def test_process_baby_shiny_is_kept_even_if_better_than_parent(stage: Any) -> None:
    """既是闪光又比亲代好：按闪光处理（放进右边盒子），不换亲代，parent_best 不变。"""
    scene = BabyScene(stage, make_mon(shiny=True, best=5))
    scene.run()
    swaps = [entry for entry in stage.log if entry[0] == "swap_slots"]
    assert swaps == [("swap_slots", ("party", 5, 0), ("slots", 0, 0))]
    assert stage.sw.parent_best == 3


@pytest.mark.parametrize(
    ("parent_index", "cell"), [(0, (0, 0)), (1, (0, 1)), (2, (1, 1)), (3, (2, 1))]
)
def test_process_baby_better_same_species_swaps_with_parent_in_left_box(
    stage: Any, parent_index: int, cell: tuple[int, int]
) -> None:
    """和亲代同种、「最棒」项数比亲代多（5 对 3）：到左边盒子，和亲代交换，再回中间盒子，返回 True。
    亲代是野餐队伍第 0 只时在左边盒子第 0 行第 0 列，是第 i 只（i ≥ 1）时在第 1 列第 i - 1 行。
    """
    scene = BabyScene(stage, make_mon(best=5))
    stage.sw.parent_index = parent_index
    assert scene.run() is True
    assert scene.without_reads() == [
        ("cursor", "party", 5, 0),
        ("to_left_box",),
        ("swap_slots", ("party", 5, 0), ("slots", *cell)),
        ("to_right_box",),
    ]


def test_process_baby_better_same_species_updates_parent_and_marks_kept(stage: Any) -> None:
    """换亲代之后：parent_best 变成新亲代的项数（5），这一盒留下过东西，要存档；不放生换下来的旧亲代，不推送。"""
    scene = BabyScene(stage, make_mon(best=5))
    scene.run()
    assert stage.sw.parent_best == 5
    assert stage.sw.kept_in_box is True
    assert stage.sw.save_pending is True
    assert not any(entry[0] == "release_one" for entry in stage.log)
    assert scene.notifier.sent_everyone == []


def test_process_baby_does_not_swap_parent_when_judge_is_not_unlocked(stage: Any) -> None:
    """评定功能没解锁（Mon.best 是 None）：同种也不换亲代，不留，parent_best 不变。"""
    scene = BabyScene(stage, make_mon(best=None))
    stage.sw.judge_unlocked = False
    assert scene.run() is True
    assert scene.without_reads() == [("cursor", "party", 5, 0)]
    assert stage.sw.parent_best == 3


# ---- 下坡、绕圈、孵化 ----


def test_hatch_eggs_circles_once_per_egg_leaving_ramp_only_before_first(stage: Any) -> None:
    """零区闸口孵 3 个蛋：每个蛋之前按 L 转镜头；只在第一个蛋之前下坡（离开坡道）；
    每个蛋都绕圈到出现孵化对话，再处理孵化（带上第几个、一共几个）。
    """
    stage.stub(hatch_module, "_leave_ramp", False)
    stage.stub(hatch_module, "_do_egg_cycle_motion")
    stage.stub(hatch_module, "_handle_egg_hatching")
    stage.stub(fly_module, "fly_to_gate")
    hatch_module._hatch_eggs_at_zero_gate(stage.sw, 3)
    assert stage.log == [
        ("click", "L"),
        ("_leave_ramp",),
        ("_do_egg_cycle_motion",),
        ("_handle_egg_hatching", 0, 3),
        ("click", "L"),
        ("_do_egg_cycle_motion",),
        ("_handle_egg_hatching", 1, 3),
        ("click", "L"),
        ("_do_egg_cycle_motion",),
        ("_handle_egg_hatching", 2, 3),
    ]


def test_hatch_eggs_handles_hatching_on_the_ramp_then_flies_back_to_gate(stage: Any) -> None:
    """下坡路上就孵了（_leave_ramp 返回 True）：不绕圈，直接处理这个蛋的孵化，然后用地图飞回闸口（重置位置），
    再继续孵下一个蛋；两个蛋都处理了，最后一件事是处理第 2 个蛋的孵化。
    """
    results = iter([True, False])
    stage.stub(hatch_module, "_leave_ramp", lambda: next(results))
    stage.stub(hatch_module, "_do_egg_cycle_motion")
    stage.stub(hatch_module, "_handle_egg_hatching")
    stage.stub(fly_module, "fly_to_gate")
    hatch_module._hatch_eggs_at_zero_gate(stage.sw, 2)
    assert stage.log[:4] == [
        ("click", "L"),
        ("_leave_ramp",),
        ("_handle_egg_hatching", 0, 2),
        ("fly_to_gate",),
    ]
    assert stage.log[-1] == ("_handle_egg_hatching", 1, 2)
    assert [entry for entry in stage.log if entry[0] == "_handle_egg_hatching"] == [
        ("_handle_egg_hatching", 0, 2),
        ("_handle_egg_hatching", 1, 2),
    ]


def test_leave_ramp_rides_and_goes_off_ramp_and_returns_false_without_dialog(stage: Any) -> None:
    """下坡（上游：骑坐骑，往右前方走，按 L 转镜头，往前走）：按 PLUS 上坐骑，左摇杆往右前推 0.4 秒，按 L，
    往前推 1.6 秒；没有出现孵化对话，返回 False。
    """
    stage.set_screens(is_dialog=lambda: False)
    assert hatch_module._leave_ramp(stage.sw) is False
    assert stage.log == [
        ("click", "PLUS"),
        ("stick", "LEFT", 1.0, 1.0, 0.4),
        ("click", "L"),
        ("stick", "LEFT", 0.0, 1.0, 1.6),
    ]


def test_leave_ramp_stops_and_returns_true_when_egg_hatches_on_the_way(stage: Any) -> None:
    """下坡的途中出现孵化对话：马上停下，不做后面的动作，返回 True。"""
    stage.set_screens(is_dialog=lambda: len(stage.log) >= 1)
    assert hatch_module._leave_ramp(stage.sw) is True
    assert stage.log == [("click", "PLUS")]


def test_egg_cycle_motion_circles_until_hatch_dialog_then_releases_everything(stage: Any) -> None:
    """绕圈（上游 do_egg_cycle_motion）：左摇杆往前推满、右摇杆往右推满、按住左摇杆（LSTICK）；
    出现孵化对话（120 秒后）就停：三样都松开。
    """
    start = stage.clock.now
    stage.set_screens(is_dialog=lambda: stage.clock.now >= start + 120)
    hatch_module._do_egg_cycle_motion(stage.sw)
    assert set(stage.log[:3]) == {
        ("press_stick", "LEFT", 0.0, 1.0),
        ("press_stick", "RIGHT", 1.0, 0.0),
        ("press", "LSTICK"),
    }
    assert set(stage.log[3:]) == {
        ("release_stick", "LEFT"),
        ("release_stick", "RIGHT"),
        ("release", "LSTICK"),
    }
    assert len(stage.log) == 6
    assert stage.clock.now - start >= 120


def test_egg_cycle_motion_raises_timeout_error_after_ten_minutes_and_releases(stage: Any) -> None:
    """绕圈 10 分钟都没有孵化对话：抛 TimeoutError，报错里有「孵化」；摇杆和按键都松开了。"""
    start = stage.clock.now
    stage.set_screens(is_dialog=lambda: False)
    with pytest.raises(TimeoutError, match="孵化"):
        hatch_module._do_egg_cycle_motion(stage.sw)
    assert stage.clock.now - start >= 600
    assert set(stage.log[-3:]) == {
        ("release_stick", "LEFT"),
        ("release_stick", "RIGHT"),
        ("release", "LSTICK"),
    }


def test_handle_egg_hatching_turns_camera_and_presses_a_until_overworld(stage: Any) -> None:
    """处理孵化（上游 handle_egg_hatching）：右摇杆往左推 0.76 秒，然后一直按 A 过孵化动画和对话，
    回到野外（按了 3 下 A 之后）就不再按。
    """
    count = [0]

    def press(button: str) -> None:
        count[0] += 1

    stage.on_click = press
    stage.set_screens(is_overworld=lambda: count[0] >= 3)
    hatch_module._handle_egg_hatching(stage.sw, 0, 5)
    assert stage.log[0] == ("stick", "RIGHT", -1.0, 0.0, 0.76)
    assert set(stage.clicks()) == {"A"}
    assert 3 <= len(stage.clicks()) <= 4


def test_handle_egg_hatching_raises_timeout_error_when_overworld_never_returns(
    stage: Any,
) -> None:
    """一分钟都没回到野外：抛 TimeoutError，按的都是 A。"""
    start = stage.clock.now
    stage.set_screens(is_overworld=lambda: False)
    with pytest.raises(TimeoutError):
        hatch_module._handle_egg_hatching(stage.sw, 0, 5)
    assert stage.clock.now - start >= 60
    assert set(stage.clicks()) == {"A"}
