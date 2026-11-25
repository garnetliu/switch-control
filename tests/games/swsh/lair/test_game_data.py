"""control_switch.games.swsh.lair.game_data：src/control_switch/games/swsh/data/ 里的数据文件。

用 src/control_switch/games/swsh/data/ 里真实的数据，只读。要写文件的测试（record_lair_events）和要换路上事件表的测试，
把 data_dir 指到 pytest 临时目录里的一份复制，不碰仓库里的 src/control_switch/games/swsh/data/。
期望值取自搬迁前 swsh.lair.game_data 的运行结果。
租借宝可梦挑 rhydon，首领挑 tapu-lele。
"""

import json
import logging
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData

REPO_DATA_DIR = GameConfig.data_dir

CAUGHT = (
    "tapu-fini",
    "xerneas",
    "tapu-koko",
    "solgaleo",
    "mewtwo",
    "tapu-bulu",
    "tornadus-incarnate",
    "tapu-lele",
)


def make_data(**attributes: object) -> GameData:
    """用子类改了几项配置的 GameData：已抓名单固定、按剑的存档算，其余按传进来的值改。"""
    values: dict[str, object] = {
        "lair_caught": CAUGHT,
        "lair_other_version": GameConfig.lair_version_exclusives["0100ABF008968000"],
    }
    values.update(attributes)
    config_class = type("TmpConfig", (GameConfig,), values)
    return GameData(config_class())


def copy_data(tmp_path: Path) -> Path:
    """把 src/control_switch/games/swsh/data 复制到临时目录，返回复制出来的目录。"""
    target = tmp_path / "swsh"
    shutil.copytree(REPO_DATA_DIR, target)
    return target


def data_in(directory: Path) -> GameData:
    """data_dir 指到 directory 的 GameData。"""
    return make_data(data_dir=directory)


def test_boss_pokemon_is_not_empty_and_has_names(data: GameData) -> None:
    """boss_pokemon：不为空，tapu-lele 的名字是中文的「卡璞・蝶蝶」，id_num 是 786。"""
    bosses = data.boss_pokemon()
    assert len(bosses) == 47
    assert bosses["tapu-lele"].name() == "卡璞・蝶蝶"
    assert bosses["tapu-lele"].id_num == 786


def test_rental_pokemon_is_not_empty(data: GameData) -> None:
    """rental_pokemon：不为空（226 只），rhydon 的 id_num 是 112。"""
    rentals = data.rental_pokemon()
    assert len(rentals) == 226
    assert rentals["rhydon"]["id_num"] == 112


def test_lair_rows_is_not_empty(data: GameData) -> None:
    """lair_rows：遭遇表不为空，共 273 行，第一行是 species 2、形态 0、不是首领。"""
    rows = data.lair_rows()
    assert len(rows) == 273
    assert rows[0][:3] == [2, 0, False]


def test_name_id_for_plain_species(data: GameData) -> None:
    """name_id：species 112、形态 0 是 rhydon。"""
    assert data.name_id(112, 0) == "rhydon"


def test_name_id_for_regional_forms(data: GameData) -> None:
    """name_id：有地区形态的 species，形态 1 对应 -alola、-galar 的 name_id，形态 0 是原来的。"""
    assert data.name_id(26, 0) == "raichu"
    assert data.name_id(26, 1) == "raichu-alola"
    assert data.name_id(105, 1) == "marowak-alola"
    assert data.name_id(110, 1) == "weezing-galar"


def test_name_id_unknown_species_raises_value_error(data: GameData) -> None:
    """name_id：没有这个 species 时抛 ValueError，写明 species 和 form。"""
    with pytest.raises(ValueError, match="species=9999, form=0"):
        data.name_id(9999, 0)


def test_pokemon_object_of_rental(data: GameData) -> None:
    """pokemon_object：租借宝可梦 rhydon 的名字、等级、个体值（固定 31）。"""
    pokemon = data.pokemon_object("rhydon")
    assert (pokemon.name_id, pokemon.id_num, pokemon.level) == ("rhydon", 112, 65)
    assert pokemon.ivs == (31,) * 6


def test_pokemon_object_of_boss(data: GameData) -> None:
    """pokemon_object：租借表里没有时到首领表里找，tapu-lele 的 id_num 是 786，特性是 psychic-surge。"""
    pokemon = data.pokemon_object("tapu-lele")
    assert (pokemon.name_id, pokemon.id_num) == ("tapu-lele", 786)
    assert pokemon.ability_name_id == "psychic-surge"
    assert pokemon is data.boss_pokemon_objects()["tapu-lele"]


def test_pokemon_object_unknown_name_raises_key_error(data: GameData) -> None:
    """pokemon_object：两个表里都没有的 name_id 抛 KeyError。"""
    with pytest.raises(KeyError):
        data.pokemon_object("没有这只")


def test_rental_and_boss_pokemon_objects_sizes(data: GameData) -> None:
    """rental_pokemon_objects、boss_pokemon_objects：数量和原始数据一样。"""
    assert len(data.rental_pokemon_objects()) == 226
    assert len(data.boss_pokemon_objects()) == 47
    assert data.rental_pokemon_objects()["rhydon"] is data.pokemon_object("rhydon")


def test_pokemon_data_of_rental_and_boss(data: GameData) -> None:
    """pokemon_data：先在租借表里找，再找首领表，返回原始的字典。"""
    assert data.pokemon_data("rhydon")["id_num"] == 112
    assert data.pokemon_data("tapu-lele")["id_num"] == 786


def test_rental_scores_of_rhydon(data: GameData) -> None:
    """rental_scores：rhydon 对其他租借宝可梦的平均相性。"""
    assert data.rental_scores()["rhydon"] == pytest.approx(4.336089126657407)


def test_boss_matchups_of_rhydon_against_tapu_lele(data: GameData) -> None:
    """boss_matchups：rhydon 对 tapu-lele 的相性。"""
    assert data.boss_matchups()["rhydon"]["tapu-lele"] == pytest.approx(2.067855655511344)


def test_rental_matchups_of_rhydon_against_glalie(data: GameData) -> None:
    """rental_matchups：rhydon 对 glalie 的相性。"""
    assert data.rental_matchups()["rhydon"]["glalie"] == pytest.approx(5.464669593795666)


def test_rental_damages_of_rhydon_against_glalie(data: GameData) -> None:
    """rental_damages：rhydon 打 glalie 的 [普通, 极巨, 平均] 三项伤害。"""
    assert data.rental_damages()["rhydon"]["glalie"] == pytest.approx(
        [0.1618634789615151, 0.3163876297029826, 0.10858747083540922]
    )


def test_boss_attack_defense_of_rhydon_against_tapu_lele(data: GameData) -> None:
    """boss_attack_defense：rhydon 对 tapu-lele 的 [普通进攻, 极巨进攻, 挨打]。"""
    assert data.boss_attack_defense()["rhydon"]["tapu-lele"] == pytest.approx(
        [0.13355777756527995, 0.2257789917482515, 0.31977007573236194]
    )


def test_type_icons_are_grayscale_images_for_each_type(data: GameData) -> None:
    """type_icons：18 个属性各一张单通道图，冰属性的是 27x27。"""
    icons = data.type_icons()
    assert len(icons) == 18
    assert {"ice", "flying", "steel", "fighting", "electric"} <= set(icons)
    ice = icons["ice"]
    assert isinstance(ice, np.ndarray)
    assert ice.shape == (27, 27)


def test_first_draw_top_uses_config_value_when_given() -> None:
    """first_draw_top：配置里给了 lair_first_draw_top 就用它，不看已抓名单。"""
    assert make_data(lair_first_draw_top=7).first_draw_top() == 7


def test_first_draw_top_without_config_value_counts_remaining_legends() -> None:
    """first_draw_top：没给时是还没抓到的神兽只数减 1：当前名单 21 只，上限 20。"""
    assert make_data(lair_first_draw_top=None).first_draw_top() == 20


def test_first_draw_top_grows_when_nothing_is_caught() -> None:
    """first_draw_top：已抓名单是空的，神兽多 8 只，上限 28。"""
    assert make_data(lair_first_draw_top=None, lair_caught=()).first_draw_top() == 28


def test_lair_legends_excludes_other_version_and_caught() -> None:
    """lair_legends：另一个版本的（lugia、kyogre）和已经抓到的（mewtwo）都不在里面，共 21 只。"""
    legends = make_data().lair_legends()
    assert len(legends) == 21
    assert legends[:3] == ["zapdos", "moltres", "articuno"]
    for gone in ("lugia", "kyogre", "mewtwo", "tapu-lele", "xerneas"):
        assert gone not in legends


def test_lair_legends_includes_caught_ones_when_list_is_empty() -> None:
    """lair_legends：已抓名单是空的时 mewtwo 等 8 只回到列表里，另一个版本的仍然不在。"""
    legends = make_data(lair_caught=()).lair_legends()
    assert len(legends) == 29
    assert "mewtwo" in legends
    assert "lugia" not in legends


def test_lair_legends_ultra_beasts_locked() -> None:
    """lair_legends：究极异兽没解锁时 necrozma、nihilego 等 10 只不在里面。"""
    legends = make_data(lair_caught=(), lair_ultra_beasts_unlocked=False).lair_legends()
    assert "necrozma" not in legends
    assert "nihilego" not in legends


def test_lair_legends_ultra_beasts_unlocked() -> None:
    """lair_legends：究极异兽解锁后 10 只回到列表里，共 39 只。"""
    legends = make_data(lair_caught=(), lair_ultra_beasts_unlocked=True).lair_legends()
    assert len(legends) == 39
    for name in ("necrozma", "nihilego", "stakataka"):
        assert name in legends


def test_lair_legends_maps_species_718_to_zygarde_50() -> None:
    """lair_legends：遭遇表里基格尔德写的是 718，对应首领数据里的 zygarde-50，在列表最后。"""
    legends = make_data().lair_legends()
    assert legends[-1] == "zygarde-50"


@pytest.mark.parametrize(
    ("name", "rate"),
    [
        # 有实测值的（0.0 也是实测值，不能当成没有）
        ("kadabra", 0.121),
        ("rhydon", 0.0),
        ("tapu-lele", 0.129),
    ],
)
def test_max_move_rate_uses_measured_value(data: GameData, name: str, rate: float) -> None:
    """max_move_rate：有实测值的宝可梦用实测值。"""
    assert data.max_move_rate(name) == pytest.approx(rate)


def test_max_move_rate_unmeasured_boss_uses_boss_total(data: GameData) -> None:
    """max_move_rate：没有实测值的首领（mewtwo）用「首领」那一项 0.128。"""
    assert data.max_move_rate("mewtwo") == pytest.approx(0.128)


def test_max_move_rate_unmeasured_rental_uses_road_total(data: GameData) -> None:
    """max_move_rate：没有实测值的路上宝可梦（ivysaur）用「路上」那一项 0.333。"""
    assert data.max_move_rate("ivysaur") == pytest.approx(0.333)


def test_lair_events_with_none_map_type_or_layout_is_empty(data: GameData) -> None:
    """lair_events：地图类型是 None 或者布局编号是 None 时返回 {}。"""
    assert data.lair_events(None, 4) == {}
    assert data.lair_events("2x2", None) == {}
    assert data.lair_events(None, None) == {}


def test_lair_events_returns_recorded_positions(tmp_path: Path) -> None:
    """lair_events：返回这种地图类型、这个编号已经记下的位置；没记过的地图类型、编号返回 {}。"""
    directory = copy_data(tmp_path)
    table = {"2x3": {"1": {"0-0": [], "1-1>2-2": ["scientist"], "2-1": ["berry"]}}}
    (directory / "lair_event_LUT.json").write_text(json.dumps(table), encoding="utf-8")
    data = data_in(directory)
    assert data.lair_events("2x3", 1) == {"0-0": [], "1-1>2-2": ["scientist"], "2-1": ["berry"]}
    assert data.lair_events("2x3", 2) == {}
    assert data.lair_events("3x2", 1) == {}


def test_lair_events_without_table_file_is_empty(tmp_path: Path) -> None:
    """lair_events：没有 lair_event_LUT.json 文件时返回 {}。"""
    directory = copy_data(tmp_path)
    (directory / "lair_event_LUT.json").unlink()
    assert data_in(directory).lair_events("2x2", 4) == {}


def test_record_lair_events_same_as_recorded_does_not_write(tmp_path: Path) -> None:
    """record_lair_events：和已记的一样时不写文件（文件的修改时间不变）。"""
    directory = copy_data(tmp_path)
    path = directory / "lair_event_LUT.json"
    path.write_text(json.dumps({"2x2": {"4": {"0-0": ["scientist"]}}}), encoding="utf-8")
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = path.read_bytes()
    data_in(directory).record_lair_events("2x2", 4, "0-0", ["scientist"])
    assert path.stat().st_mtime_ns == 1_000_000_000
    assert path.read_bytes() == before


def test_record_lair_events_different_value_warns_and_overwrites(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """record_lair_events：和已记的不一样时记一条警告，写进文件的是这次的值。"""
    directory = copy_data(tmp_path)
    path = directory / "lair_event_LUT.json"
    path.write_text(json.dumps({"2x2": {"4": {"0-0": ["scientist"]}}}), encoding="utf-8")
    data = data_in(directory)
    with caplog.at_level(logging.WARNING):
        data.record_lair_events("2x2", 4, "0-0", ["backpacker"])
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "路上的事件和以前记的不一样" in warnings[0].getMessage()
    assert json.loads(path.read_text(encoding="utf-8")) == {"2x2": {"4": {"0-0": ["backpacker"]}}}
    assert data.lair_events("2x2", 4) == {"0-0": ["backpacker"]}


def test_record_lair_events_new_position_writes_without_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """record_lair_events：已有的图上记一个没记过的位置，写进文件，不警告，原来的位置还在。"""
    directory = copy_data(tmp_path)
    path = directory / "lair_event_LUT.json"
    path.write_text(json.dumps({"2x2": {"4": {"0-0": []}}}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        data_in(directory).record_lair_events("2x2", 4, "1-0", ["berry"])
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "2x2": {"4": {"0-0": [], "1-0": ["berry"]}}
    }


def test_record_lair_events_creates_missing_file(tmp_path: Path) -> None:
    """record_lair_events：文件不存在时新建，里面只有这一条。"""
    directory = copy_data(tmp_path)
    path = directory / "lair_event_LUT.json"
    path.unlink()
    data_in(directory).record_lair_events("3x2", 7, "2-1>3-2", ["backpacker", "berry"])
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "3x2": {"7": {"2-1>3-2": ["backpacker", "berry"]}}
    }
