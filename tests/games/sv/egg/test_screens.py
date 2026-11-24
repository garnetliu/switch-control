"""control_switch.games.sv.egg.screens：用真机截图（tests/images/sv/egg/）测每个画面判断。

screens 里的函数只看传进来的 ImageChecker，不按键、不截图。
panel_shiny 没有闪光的真机样本，用合成图：在闪光区域画红白相间的棋盘格。
"""

from collections.abc import Callable

import pytest

from control_switch.games.sv.egg import screens
from control_switch.vision import ImageChecker

Checker = Callable[[str], ImageChecker]

DIALOG_YES = [
    "篮子-看了一看.jpg",
    "篮子-已领走蛋.jpg",
    "篮子-还有蛋.jpg",
    "篮子-没有蛋.jpg",
    "篮子-要领走蛋吗.jpg",
    "结束野餐确认.jpg",
    "桌子菜单.jpg",
    "孵化-哦.jpg",
    "盒子-操作菜单.jpg",
    "盒子-菜单选中放生.jpg",
    "盒子-放生确认.jpg",
]
DIALOG_NO = [
    "野餐.jpg",
    "选三明治签.jpg",
    "三明治效果.jpg",
    "野外.jpg",
    "野外-骑着.jpg",
    "野外-野餐结束后.jpg",
    "孵化后回到野外.jpg",
    "孵化动画.jpg",
]
OVERWORLD = ["野外.jpg", "野外-骑着.jpg", "野外-野餐结束后.jpg", "孵化后回到野外.jpg"]
BASKET = ["篮子-看了一看.jpg", "篮子-已领走蛋.jpg", "篮子-还有蛋.jpg", "篮子-没有蛋.jpg"]


# ---------- is_dialog ----------


@pytest.mark.parametrize("name", DIALOG_YES)
def test_is_dialog_true_on_screens_with_dialog_box(checker: Checker, name: str) -> None:
    """is_dialog：下方有对话框的画面（篮子、结束野餐、桌子菜单、孵化的对话、盒子里的操作菜单和放生）是 True。"""
    assert screens.is_dialog(checker(name)) is True


@pytest.mark.parametrize("name", DIALOG_NO)
def test_is_dialog_false_on_screens_without_dialog_box(checker: Checker, name: str) -> None:
    """is_dialog：野餐、做三明治、野外、孵化动画这些没有对话框的画面是 False。"""
    assert screens.is_dialog(checker(name)) is False


# ---------- is_battle ----------


def test_is_battle_true_on_battle_menu(checker: Checker) -> None:
    """is_battle：战斗菜单是 True。"""
    assert screens.is_battle(checker("战斗菜单.jpg")) is True


@pytest.mark.parametrize("name", ["野餐.jpg", *OVERWORLD, "盒子-放生确认.jpg"])
def test_is_battle_false_elsewhere_including_release_prompt(checker: Checker, name: str) -> None:
    """is_battle：野餐、野外都是 False；「真的要放生吗？」的画面「战斗」按钮那里也是黄色，也要是 False。"""
    assert screens.is_battle(checker(name)) is False


# ---------- is_overworld ----------


@pytest.mark.parametrize("name", OVERWORLD)
def test_is_overworld_true_on_overworld_screens(checker: Checker, name: str) -> None:
    """is_overworld：野外（走路、骑着、野餐结束后、孵化后回到野外）右下角有小地图，是 True。"""
    assert screens.is_overworld(checker(name)) is True


@pytest.mark.parametrize(
    "name",
    ["野餐.jpg", "战斗菜单.jpg", "孵化-哦.jpg", "孵化动画.jpg", "选三明治签.jpg", "三明治效果.jpg"],
)
def test_is_overworld_false_off_the_field(checker: Checker, name: str) -> None:
    """is_overworld：野餐、战斗、孵化、做三明治的画面是 False。"""
    assert screens.is_overworld(checker(name)) is False


# ---------- is_picnic ----------


def test_is_picnic_true_on_picnic_screen(checker: Checker) -> None:
    """is_picnic：野餐中没有对话的画面是 True。"""
    assert screens.is_picnic(checker("野餐.jpg")) is True


@pytest.mark.parametrize("name", [*BASKET, *OVERWORLD, "选三明治签.jpg", "三明治效果.jpg"])
def test_is_picnic_false_with_dialog_or_off_picnic(checker: Checker, name: str) -> None:
    """is_picnic：篮子的对话（野餐中，但有对话框）、野外、做三明治的画面是 False。"""
    assert screens.is_picnic(checker(name)) is False


def test_picnic_screen_is_not_dialog_overworld_or_battle(checker: Checker) -> None:
    """野餐.jpg 不是 is_dialog、is_overworld、is_battle。"""
    image = checker("野餐.jpg")
    assert not screens.is_dialog(image)
    assert not screens.is_overworld(image)
    assert not screens.is_battle(image)


# ---------- is_prompt ----------


@pytest.mark.parametrize("name", ["篮子-要领走蛋吗.jpg", "结束野餐确认.jpg", "盒子-放生确认.jpg"])
def test_is_prompt_true_when_dialog_has_yes_no_box(checker: Checker, name: str) -> None:
    """is_prompt：对话里有「是/否」选择框（要领走蛋吗、结束野餐、放生确认）是 True，同时是 is_dialog。"""
    image = checker(name)
    assert screens.is_dialog(image) is True
    assert screens.is_prompt(image) is True


@pytest.mark.parametrize(
    "name",
    [*BASKET, "桌子菜单.jpg", "盒子-操作菜单.jpg", "盒子-菜单选中放生.jpg"],
)
def test_is_prompt_false_on_dialogs_without_yes_no_box(checker: Checker, name: str) -> None:
    """is_prompt：篮子的普通对话、桌子的做料理菜单、盒子的操作菜单是 is_dialog 但不是 is_prompt。"""
    image = checker(name)
    assert screens.is_dialog(image) is True
    assert screens.is_prompt(image) is False


@pytest.mark.parametrize("name", ["野餐.jpg", "野外.jpg"])
def test_is_prompt_false_without_dialog(checker: Checker, name: str) -> None:
    """is_prompt：没有对话框的画面是 False。"""
    assert screens.is_prompt(checker(name)) is False


# ---------- menu_row、is_riding ----------


def test_menu_row_is_2_on_picnic_row_and_not_riding(checker: Checker) -> None:
    """主菜单-野餐.jpg：menu_row 是 2，is_riding 是 False（写的是「骑上」）。"""
    image = checker("主菜单-野餐.jpg")
    assert screens.menu_row(image) == 2
    assert screens.is_riding(image) is False


def test_menu_row_is_1_on_box_row_and_riding(checker: Checker) -> None:
    """主菜单-盒子-骑着.jpg：menu_row 是 1，is_riding 是 True（写的是「下来」）。"""
    image = checker("主菜单-盒子-骑着.jpg")
    assert screens.menu_row(image) == 1
    assert screens.is_riding(image) is True


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg", "盒子-打开.jpg"])
def test_menu_row_is_minus_1_when_no_main_menu(checker: Checker, name: str) -> None:
    """menu_row：不是主菜单的画面，没有哪一行黄色占比够，返回 -1。"""
    assert screens.menu_row(checker(name)) == -1


# ---------- box_title ----------


def test_box_title_reads_10_on_opened_box(checker: Checker) -> None:
    """盒子-打开.jpg：box_title 是 10（整数）。"""
    assert screens.box_title(checker("盒子-打开.jpg")) == 10


def test_box_title_reads_21_while_holding_egg(checker: Checker) -> None:
    """盒子-拿着蛋.jpg：box_title 是 21。"""
    assert screens.box_title(checker("盒子-拿着蛋.jpg")) == 21


def test_box_title_is_none_when_not_in_box(checker: Checker) -> None:
    """野外画面里没有「盒子」标题：box_title 返回 None。"""
    assert screens.box_title(checker("野外.jpg")) is None


# ---------- box_cursor ----------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-打开.jpg", ("box", 0, 0)),
        ("盒子-拿着蛋.jpg", ("box", 1, 0)),
        ("盒子-空格.jpg", ("box", 3, 0)),
        ("盒子-爱吃豚-3V.jpg", ("party", 3)),
        ("盒子-爱吃豚-4V.jpg", ("party", 5)),
        ("盒子-百变怪-6V.jpg", ("party", 1)),
    ],
)
def test_box_cursor_finds_highlighted_cell(
    checker: Checker, name: str, expected: tuple[object, ...]
) -> None:
    """box_cursor：返回黄色占比最大的格子，队伍是 ("party", i)，盒子是 ("box", r, c)。"""
    assert screens.box_cursor(checker(name)) == expected


@pytest.mark.parametrize("name", ["野外.jpg", "野餐.jpg"])
def test_box_cursor_is_none_when_no_cell_is_highlighted(checker: Checker, name: str) -> None:
    """box_cursor：不是盒子的画面，没有格子黄色占比超过 0.5，返回 None。"""
    assert screens.box_cursor(checker(name)) is None


# ---------- panel_name ----------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-拿着蛋.jpg", "蛋"),
        ("盒子-空格.jpg", ""),
        ("盒子-爱吃豚-3V.jpg", "爱吃豚"),
        ("盒子-爱吃豚-4V.jpg", "爱吃豚"),
        ("盒子-百变怪-6V.jpg", "Ditto"),
    ],
)
def test_panel_name_reads_name_egg_or_empty(checker: Checker, name: str, expected: str) -> None:
    """panel_name：面板顶上的名字——宝可梦名、「蛋」，空格是空字符串。"""
    assert screens.panel_name(checker(name)) == expected


# ---------- panel_best_count ----------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("盒子-爱吃豚-3V.jpg", 3),
        ("盒子-爱吃豚-4V.jpg", 4),
        ("盒子-百变怪-6V.jpg", 6),
    ],
)
def test_panel_best_count_counts_stats_that_read_best(
    checker: Checker, name: str, expected: int
) -> None:
    """panel_best_count：六项能力里读到「最棒」的有几项；OCR 多读一个点（「最棒·」）也算。"""
    assert screens.panel_best_count(checker(name)) == expected


def test_panel_best_count_is_zero_on_empty_slot(checker: Checker) -> None:
    """panel_best_count：空格的面板上没有任何能力，是 0。"""
    assert screens.panel_best_count(checker("盒子-空格.jpg")) == 0


# ---------- panel_shiny ----------


@pytest.mark.parametrize("name", ["盒子-爱吃豚-3V.jpg", "盒子-爱吃豚-4V.jpg", "盒子-百变怪-6V.jpg"])
def test_panel_shiny_false_on_real_non_shiny_panels(checker: Checker, name: str) -> None:
    """panel_shiny：真机上不是闪光的面板（三个通道标准差之和 0.4–2.4）是 False。"""
    assert screens.panel_shiny(checker(name)) is False


def test_panel_shiny_true_on_synthetic_checkerboard_in_star_area(shiny_image: bytes) -> None:
    """panel_shiny：「盒子-爱吃豚-4V.jpg」在闪光区域画上红白相间的棋盘格之后是 True。"""
    assert screens.panel_shiny(ImageChecker(shiny_image)) is True


# ---------- 食谱 ----------


def test_recipe_screen_has_title_and_super_peanut_butter(checker: Checker) -> None:
    """食谱-17.jpg：左上标题 ((0.05, 0.0), (0.2, 0.06)) 有「食谱」，右侧 ((0.57, 0.21), (0.80, 0.26)) 有「超级花生酱」。"""
    image = checker("食谱-17.jpg")
    assert image.has_text(((0.05, 0.0), (0.2, 0.06)), "食谱")
    assert image.has_text(((0.57, 0.21), (0.80, 0.26)), "超级花生酱")


# ---------- 其他画面的组合 ----------


@pytest.mark.parametrize("name", ["选三明治签.jpg", "三明治效果.jpg"])
def test_sandwich_making_screens_are_nothing_else(checker: Checker, name: str) -> None:
    """做三明治中（选签子、效果）：不是 is_picnic、is_overworld、is_dialog。"""
    image = checker(name)
    assert not screens.is_picnic(image)
    assert not screens.is_overworld(image)
    assert not screens.is_dialog(image)


@pytest.mark.parametrize("name", ["战斗菜单.jpg"])
def test_battle_menu_is_not_overworld(checker: Checker, name: str) -> None:
    """战斗菜单.jpg：是 is_battle，不是 is_overworld。"""
    image = checker(name)
    assert screens.is_battle(image)
    assert not screens.is_overworld(image)


def test_hatch_dialog_is_dialog_and_not_overworld(checker: Checker) -> None:
    """孵化-哦.jpg：是 is_dialog，不是 is_overworld。"""
    image = checker("孵化-哦.jpg")
    assert screens.is_dialog(image)
    assert not screens.is_overworld(image)


def test_hatch_animation_is_neither_dialog_nor_overworld(checker: Checker) -> None:
    """孵化动画.jpg（没有对话框）：不是 is_dialog，不是 is_overworld。"""
    image = checker("孵化动画.jpg")
    assert not screens.is_dialog(image)
    assert not screens.is_overworld(image)


# ---------- egg_cells ----------

ALL_ROW = [(r, c) for r in range(5) for c in range(6)]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "盒子-21-蛋和宝可梦.jpg",
            [(1, 0), (1, 3), (1, 4), (1, 5)]
            + [(2, c) for c in range(6)]
            + [(3, c) for c in range(6)]
            + [(4, 0), (4, 2), (4, 3), (4, 4), (4, 5)],
        ),
        (
            "盒子-22-蛋和宝可梦.jpg",
            [(0, 2), (0, 3), (0, 4), (0, 5)] + [(r, c) for r in range(1, 5) for c in range(1, 6)],
        ),
        ("盒子-23-两个蛋.jpg", [(0, 0), (0, 3)]),
        ("盒子-打开.jpg", [(2, 1)]),
        ("盒子-爱吃豚-3V.jpg", [(1, 4), (1, 5)]),
    ],
)
def test_egg_cells_lists_egg_cells_in_row_column_order(
    checker: Checker, name: str, expected: list[tuple[int, int]]
) -> None:
    """egg_cells：盒子画面里认出的蛋格 (行, 列)，按行、列排好；别的宝可梦和空格不算，光标停在蛋上也算。"""
    assert screens.egg_cells(checker(name)) == expected


# ---------- is_holding ----------


def test_is_holding_true_when_bottom_bar_has_no_replace(checker: Checker) -> None:
    """is_holding：拿着东西时底栏只剩「显示宝可梦」「返回」，读不到「替换」，是 True（盒子-拿着蛋.jpg）。"""
    assert screens.is_holding(checker("盒子-拿着蛋.jpg")) is True


@pytest.mark.parametrize("name", ["盒子-打开.jpg", "盒子-爱吃豚-3V.jpg", "盒子-爱吃豚-4V.jpg"])
def test_is_holding_false_when_bottom_bar_has_replace(checker: Checker, name: str) -> None:
    """is_holding：没拿东西时底栏有「替换」，是 False。"""
    assert screens.is_holding(checker(name)) is False


# ---------- judge_count ----------


@pytest.mark.parametrize(
    ("name", "at_least"),
    [
        ("盒子-爱吃豚-3V.jpg", 4),
        ("盒子-爱吃豚-4V.jpg", 4),
        ("盒子-百变怪-6V.jpg", 4),
        ("盒子-打开.jpg", 4),
    ],
)
def test_judge_count_is_at_least_4_on_judge_page(
    checker: Checker, name: str, at_least: int
) -> None:
    """judge_count：面板在能力判定页（六项能力写「最棒」「一般般」这些词）时，读得出判定词的至少 4 项。"""
    assert screens.judge_count(checker(name)) >= at_least


@pytest.mark.parametrize("name", ["盒子-拿着蛋.jpg", "野外.jpg"])
def test_judge_count_is_below_4_without_a_pokemon_panel(checker: Checker, name: str) -> None:
    """judge_count：面板上没有能力（蛋、野外）时读得出判定词的不到 4 项。"""
    assert screens.judge_count(checker(name)) < 4


# ---------- battle_row ----------


def test_battle_row_is_0_on_real_battle_menu(checker: Checker) -> None:
    """battle_row：战斗菜单.jpg 黄色光标在「战斗」，是第 0 行。"""
    assert screens.battle_row(checker("战斗菜单.jpg")) == 0


def test_battle_row_is_minus_1_off_the_battle_menu(checker: Checker) -> None:
    """battle_row：野外没有战斗菜单，认不出光标，返回 -1。"""
    assert screens.battle_row(checker("野外.jpg")) == -1


@pytest.mark.parametrize("row", [1, 2, 3])
def test_battle_row_follows_synthetic_yellow_cursor(
    battle_image: Callable[[int], bytes], row: int
) -> None:
    """battle_row：战斗菜单 4 行（战斗、宝可梦、包包、逃走），黄色光标在第 row 行（合成图：
    把那一行的按钮位置涂成黄色）时返回 row。
    """
    assert screens.battle_row(ImageChecker(battle_image(row))) == row


# ---------- is_pick_screen ----------


def test_is_pick_screen_true_on_sandwich_pick_screen(checker: Checker) -> None:
    """is_pick_screen：选三明治签子的界面（左上「食谱模式」、右上有「签」）是 True。"""
    assert screens.is_pick_screen(checker("选三明治签.jpg")) is True


@pytest.mark.parametrize("name", ["食谱-17.jpg", "三明治效果.jpg", "桌子菜单.jpg", "野餐.jpg"])
def test_is_pick_screen_false_on_other_screens(checker: Checker, name: str) -> None:
    """is_pick_screen：食谱画面、做三明治的画面、桌子菜单、野餐都不是选签子的界面。"""
    assert screens.is_pick_screen(checker(name)) is False


# ---------- operation_selected ----------


def test_operation_selected_reads_release_when_release_is_highlighted(checker: Checker) -> None:
    """operation_selected：操作菜单里黄色选中的是「放生」时读出「放生」（盒子-菜单选中放生.jpg）。"""
    assert "放生" in screens.operation_selected(checker("盒子-菜单选中放生.jpg"))


@pytest.mark.parametrize("name", ["盒子-操作菜单.jpg", "野外.jpg"])
def test_operation_selected_is_not_release_otherwise(checker: Checker, name: str) -> None:
    """operation_selected：光标不在「放生」上（盒子-操作菜单.jpg）或没有操作菜单时读不到「放生」。"""
    assert "放生" not in screens.operation_selected(checker(name))
