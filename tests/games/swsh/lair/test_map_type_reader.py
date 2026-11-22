"""control_switch.games.swsh.lair.map_type_reader：从路线图第 2 层的属性标签判断地图类型。

截图是真机的 1280x720：地图类型-2x2、2x3、3x2（3x2 原图 1920x1080，已经缩成 1280x720），
和一张不是地图的截图（研究员问换不换）。
MapTypeReader 靠 game.maps 里第 2、3 层每列宝可梦的属性判断标签在哪一层，所以每张地图截图
各给一个 maps：第 2 层四个节点的 encounter 选一只带截图上这一列属性、不带冰属性的租借宝可梦，
第 3 层四个节点都选只有冰属性的 glalie。不创建连接，MapTypeReader 用一个带 config、data、game 的简单对象。
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import cv2
import numpy as np
import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.lair.map import MapNode, Maps
from control_switch.games.swsh.lair.map_type_reader import MapTypeReader
from control_switch.vision import ImageChecker

IMAGES = Path(__file__).resolve().parents[3] / "images"

# 每张地图截图：文件名里的地图类型、第 2 层四列依次选的宝可梦（属性依次是 ...）
# 2x2：flying、steel、fighting、electric
# 2x3：ground、dragon、fighting、flying
# 3x2：normal、bug、electric、poison
SECOND_ROW_ENCOUNTERS = {
    "2x2": ["noctowl", "klang", "machoke", "raichu"],
    "2x3": ["sandslash", "dragonair", "machoke", "noctowl"],
    "3x2": ["persian", "accelgor", "raichu", "weezing"],
}
MAP_TYPES = ["2x2", "2x3", "3x2"]
NOT_A_MAP = "研究员问换不换"


def load_image(name: str) -> ImageChecker:
    return ImageChecker((IMAGES / f"{name}.jpg").read_bytes())


def node(col: int, encounter: str, data: Any) -> MapNode:
    """路线图上的一个节点，type 用遭遇宝可梦的第一属性占位。"""
    return {
        "col": col,
        "type": data.rental_pokemon()[encounter]["type_ids"][0],
        "encounter": encounter,
    }


def make_maps(data: Any, second_row: list[str], third_row: list[str] | None = None) -> Maps:
    """第 2 层四个节点的遭遇是 second_row，第 3 层四个节点是 third_row（不给就都是 glalie）。"""
    third = third_row if third_row is not None else ["glalie"] * 4
    return {
        "type": None,
        "layout": 0,
        "rows": {
            "2": [node(col, name, data) for col, name in enumerate(second_row)],
            "3": [node(col, name, data) for col, name in enumerate(third)],
        },
        "route": [],
        "current_index": 0,
    }


def make_reader(data: Any, maps: Maps | None, config: GameConfig | None = None) -> MapTypeReader:
    """带 config、data、game 的简单对象，game.maps 是 maps。data 可以是 GameData 或者假的。"""
    sw = SimpleNamespace(config=config or GameConfig(), data=data, game=SimpleNamespace(maps=maps))
    return MapTypeReader(cast(Any, sw))


@pytest.mark.parametrize("name", [f"地图类型-{map_type}" for map_type in MAP_TYPES] + [NOT_A_MAP])
def test_update_without_maps_recognizes_nothing(data: GameData, name: str) -> None:
    """game.maps 是 None：四张截图 update 都返回 None，rects 还是空的。"""
    reader = make_reader(data, None)
    assert reader.update(load_image(name)) is None
    assert reader.rects == ()


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_recognizes_map_type_from_screenshot(data: GameData, map_type: str) -> None:
    """update：每张地图截图配各自的 maps，返回截图对应的地图类型。"""
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS[map_type]))
    assert reader.update(load_image(f"地图类型-{map_type}")) == map_type


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_records_search_rects_of_four_columns(data: GameData, map_type: str) -> None:
    """update：读出地图类型后，rects 里是这一帧找标签的范围：最左一列加另外三列的窄条，共 4 个。"""
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS[map_type]))
    reader.update(load_image(f"地图类型-{map_type}"))
    assert len(reader.rects) == 4


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_with_non_map_screenshot_returns_none(data: GameData, map_type: str) -> None:
    """update：不是地图的截图，用三份 maps 中的任一份，都返回 None，rects 还是空的。"""
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS[map_type]))
    assert reader.update(load_image(NOT_A_MAP)) is None
    assert reader.rects == ()


def test_update_returns_none_when_second_row_types_do_not_match_screenshot(
    data: GameData,
) -> None:
    """update：maps 里第 2 层四列的属性和截图对不上（都是 glalie 的冰属性）时，标签都判不成第 2 层，返回 None。"""
    reader = make_reader(data, make_maps(data, ["glalie"] * 4))
    assert reader.update(load_image("地图类型-2x2")) is None
    assert reader.rects == ()


def test_reader_can_be_reused_for_several_frames(data: GameData) -> None:
    """update：同一个 MapTypeReader 先吃一张不是地图的截图（None），再吃地图截图，仍能认出。"""
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS["2x3"]))
    assert reader.update(load_image(NOT_A_MAP)) is None
    assert reader.update(load_image("地图类型-2x3")) == "2x3"


def encode_png(image: np.ndarray) -> ImageChecker:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return ImageChecker(buffer.tobytes())


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_with_labels_possible_on_both_rows_returns_none(
    data: GameData, map_type: str
) -> None:
    """update：maps 里第 2、3 层每列的属性一样，所有标签都可能是第 2 层也可能是第 3 层，又没有已经确定的层可以参照，返回 None。"""
    second = SECOND_ROW_ENCOUNTERS[map_type]
    reader = make_reader(data, make_maps(data, second, second))
    assert reader.update(load_image(f"地图类型-{map_type}")) is None


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_resolves_ambiguous_labels_by_distance_to_known_row(
    data: GameData, map_type: str
) -> None:
    """update：只有最左一列能确定是第 2 层（第 3 层是 glalie），另外三列两层都可能，按离已确定的第 2 层有多近判断，仍然认出地图类型。"""
    second = SECOND_ROW_ENCOUNTERS[map_type]
    third = ["glalie", *second[1:]]
    reader = make_reader(data, make_maps(data, second, third))
    assert reader.update(load_image(f"地图类型-{map_type}")) == map_type


class AllTypesData:
    """只用 type_icons 和 rental_pokemon 的假数据：有一只什么属性都带的宝可梦 all-types。"""

    def __init__(self, real: GameData) -> None:
        self._real = real

    def type_icons(self) -> dict[str, Any]:
        return self._real.type_icons()

    def rental_pokemon(self) -> dict[str, dict[str, Any]]:
        rentals = dict(self._real.rental_pokemon())
        rentals["all-types"] = {"type_ids": list(self._real.type_icons())}
        return rentals


@pytest.mark.parametrize("map_type", MAP_TYPES)
def test_update_ignores_labels_far_from_second_row_even_if_types_match(
    data: GameData, map_type: str
) -> None:
    """update：第 2 层每列都允许所有属性时，别的层上的标签也会被判成第 2 层，离第 2 层中间高度太远的会被丢掉，仍然认出地图类型。"""
    fake = AllTypesData(data)
    reader = make_reader(fake, make_maps(fake, ["all-types"] * 4))
    assert reader.update(load_image(f"地图类型-{map_type}")) == map_type


def test_update_with_image_smaller_than_icons_returns_none(data: GameData) -> None:
    """update：截图比属性图标还小（20x30）时，没法匹配，返回 None。"""
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS["2x2"]))
    assert reader.update(encode_png(np.zeros((20, 30, 3), np.uint8))) is None


def test_update_with_three_labels_in_first_column_but_no_other_columns_returns_none(
    data: GameData,
) -> None:
    """update：最左一列上下排了 3 个属性图标（一列最多找 3 个），另外三列什么都没有，凑不齐四列，返回 None。"""
    icons = data.type_icons()
    frame = np.zeros((720, 1280, 3), np.uint8)
    x = int(0.17 * 1280)
    for index, type_id in enumerate(["ice", "fire", "water"]):
        icon = icons[type_id]
        y = 100 + index * 200
        frame[y : y + icon.shape[0], x : x + icon.shape[1]][icon > 0] = 255
    reader = make_reader(data, make_maps(data, SECOND_ROW_ENCOUNTERS["2x2"]))
    assert reader.update(encode_png(frame)) is None


class TightSpreadConfig(GameConfig):
    """同一层标签的高度差最多 0.01 倍画面高度（默认是 0.2）。"""

    row_max_spread = 0.01


def test_update_drops_labels_further_from_second_row_than_row_max_spread(
    data: GameData,
) -> None:
    """update：row_max_spread 很小时，四列标签的高度差超过它的都被丢掉，凑不齐四列，返回 None；默认配置能认出。"""
    maps = make_maps(data, SECOND_ROW_ENCOUNTERS["2x2"])
    image = load_image("地图类型-2x2")
    assert make_reader(data, maps).update(image) == "2x2"
    assert make_reader(data, maps, TightSpreadConfig()).update(image) is None
