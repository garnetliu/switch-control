"""control_switch.games.swsh.lair.game_state：一局冒险的状态和 keep path 的锁定、解锁。

GameConfig 用子类把 game_state_file 指到 pytest 的临时目录，不读写仓库里真实的状态文件；
boss 也由子类指定，不依赖 GameConfig.boss 的默认值。keep_path 在创建 GameState 时传进去。
"""

import time
from pathlib import Path

import pytest

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_state import GameState

BOSS = "mewtwo"
OTHER_BOSS = "xerneas"


def make_config(directory: Path, boss_name: str = BOSS) -> GameConfig:
    """game_state_file 在临时目录里、boss 固定的配置。"""

    class TmpConfig(GameConfig):
        game_state_file = directory / "run" / "game.yaml"
        boss = boss_name

    return TmpConfig()


@pytest.fixture
def config(tmp_path: Path) -> GameConfig:
    """状态文件在临时目录里的配置。"""
    return make_config(tmp_path)


def finished_run(
    config: GameConfig, minutes: float = 5.0, faints: int = 0, keep_path: bool = False
) -> GameState:
    """抓满 4 只（打赢）、极矿石足够、开始了 minutes 分钟、倒下 faints 次的一局，还没锁定。

    keep_path 是创建 GameState 时传的值。
    """
    state = GameState(config, keep_path=keep_path)
    state.num_caught = 4
    state.caught = ["a", "b", "c", "d"]
    state.faints = [faints, 0, 0]
    state.dynite_ore = 50
    state.started = time.time() - minutes * 60
    return state


def test_new_state_without_file_uses_defaults(config: GameConfig) -> None:
    """没有状态文件时用默认值创建：boss 是配置里的，其余是空值，不会创建文件。"""
    state = GameState(config)
    assert state.boss == BOSS
    assert state.lock_path is False
    assert state.seed is None
    assert state.rental_pool == []
    assert state.candidates == []
    assert state.maps is None
    assert state.lock_pokemon_index is None
    assert state.lock_results == []
    assert state.path_results == []
    assert state.caught_total == 0
    assert state.shinies == []
    assert state.dynite_ore == 0
    assert state.team == []
    assert state.num_caught == 0
    assert state.caught == []
    assert state.faints == []
    assert state.fielded == []
    assert state.choices == []
    assert state.route_score == 0.0
    assert state.stage_score == 0.0
    assert state.boss_score == 0.0
    assert state.balls == {}
    assert state.started == 0.0
    assert not config.game_state_file.exists()


def test_save_then_reload_reads_back_same_values(config: GameConfig) -> None:
    """save 之后再建一个 GameState，读回来的值一样，包括 fielded、choices、stage_score、boss_score。"""
    state = GameState(config)
    state.boss = OTHER_BOSS
    state.lock_path = True
    state.seed = 3076008315599927110
    state.rental_pool = ["rhydon", "glalie", "ditto"]
    state.candidates = ["rhydon", "glalie", "ditto"]
    state.lock_pokemon_index = 1
    state.lock_results = [True, False]
    state.path_results = [True]
    state.caught_total = 6
    state.dynite_ore = 123
    state.team = [("rhydon", 1.0), ("glalie", 0.5)]
    state.num_caught = 2
    state.caught = ["a", "b"]
    state.faints = [0, 1]
    state.fielded = ["rhydon", "glalie"]
    state.choices = [True, False, True]
    state.route_score = 0.75
    state.stage_score = 0.5
    state.boss_score = 0.25
    state.balls = {"究极球": 7}
    state.started = 1234.5
    state.save()

    again = GameState(config)
    assert again.boss == OTHER_BOSS
    assert again.lock_path is True
    assert again.seed == 3076008315599927110
    assert again.rental_pool == ["rhydon", "glalie", "ditto"]
    assert again.candidates == ["rhydon", "glalie", "ditto"]
    assert again.lock_pokemon_index == 1
    assert again.lock_results == [True, False]
    assert again.path_results == [True]
    assert again.caught_total == 6
    assert again.dynite_ore == 123
    assert again.team == [("rhydon", 1.0), ("glalie", 0.5)]
    assert again.num_caught == 2
    assert again.caught == ["a", "b"]
    assert again.faints == [0, 1]
    assert again.fielded == ["rhydon", "glalie"]
    assert again.choices == [True, False, True]
    assert again.route_score == 0.75
    assert again.stage_score == 0.5
    assert again.boss_score == 0.25
    assert again.balls == {"究极球": 7}
    assert again.started == 1234.5


def test_save_reload_keeps_maps_and_shinies(config: GameConfig) -> None:
    """save 之后读回来：路线图 maps 和闪光记录 shinies 里的嵌套内容一样。"""
    state = GameState(config)
    state.maps = {
        "type": "2x3",
        "layout": 4,
        "rows": {"1": [{"col": 0, "type": "ice", "encounter": "glalie"}]},
        "route": [[1, 0]],
        "current_index": 1,
    }
    state.shinies = [{"time": "2026-11-22 10:00:00", "round": 3, "stage": 2, "pokemon": "ditto"}]
    state.save()

    again = GameState(config)
    assert again.maps == state.maps
    assert again.shinies == state.shinies


def test_save_creates_parent_directory_and_leaves_no_temp_file(config: GameConfig) -> None:
    """save：目录不存在时先创建，写完后没有留下 .tmp 文件。"""
    GameState(config).save()
    assert config.game_state_file.exists()
    assert not config.game_state_file.with_suffix(".tmp").exists()


def test_old_state_file_without_new_keys_reads_defaults(config: GameConfig) -> None:
    """旧的状态文件没有 fielded、choices、stage_score、boss_score 这 4 个键，读出来是默认值，其余键照读。"""
    config.game_state_file.parent.mkdir(parents=True)
    config.game_state_file.write_text(
        f"boss: {OTHER_BOSS}\nseed: 99\nnum_caught: 2\nroute_score: 0.5\nfaints:\n- 1\n",
        encoding="utf-8",
    )
    state = GameState(config)
    assert state.boss == OTHER_BOSS
    assert state.seed == 99
    assert state.num_caught == 2
    assert state.route_score == 0.5
    assert state.faints == [1]
    assert state.fielded == []
    assert state.choices == []
    assert state.stage_score == 0.0
    assert state.boss_score == 0.0


def test_empty_state_file_is_treated_as_missing(config: GameConfig) -> None:
    """状态文件是空的时按没有文件处理，用默认值。"""
    config.game_state_file.parent.mkdir(parents=True)
    config.game_state_file.write_text("", encoding="utf-8")
    state = GameState(config)
    assert state.boss == BOSS
    assert state.seed is None


def test_lives_is_four_minus_total_faints(config: GameConfig) -> None:
    """lives：4 减去各关倒下次数的合计。"""
    state = GameState(config)
    assert state.lives == 4
    state.faints = [1, 0, 2]
    assert state.lives == 1


def test_start_run_clears_this_run_data(config: GameConfig) -> None:
    """start_run：清掉这一局的数据（包括 fielded、choices），记下开始时间，并写进文件。"""
    state = GameState(config)
    state.num_caught = 3
    state.caught = ["a", "b", "c"]
    state.faints = [1, 0]
    state.fielded = ["a", "b"]
    state.choices = [True, False]
    state.team = [("a", 1.0)]
    state.lock_results = [True]
    state.seed = 7
    before = time.time()
    state.start_run()
    assert state.started >= before
    assert state.num_caught == 0
    assert state.caught == []
    assert state.faints == []
    assert state.fielded == []
    assert state.choices == []
    assert state.team == []
    # 不属于这一局的数据不清
    assert state.lock_results == [True]
    assert state.seed == 7
    again = GameState(config)
    assert again.fielded == []
    assert again.started == state.started


def test_start_run_resets_current_index_when_maps_exist(config: GameConfig) -> None:
    """start_run：maps 不为空时 current_index 归零，maps 的其余内容不变。"""
    state = GameState(config)
    state.maps = {
        "type": "2x2",
        "layout": 1,
        "rows": {},
        "route": [[1, 0], [2, 1], [3, 2]],
        "current_index": 2,
    }
    state.start_run()
    assert state.maps is not None
    assert state.maps["current_index"] == 0
    assert state.maps["route"] == [[1, 0], [2, 1], [3, 2]]


def test_start_run_keeps_maps_none(config: GameConfig) -> None:
    """start_run：maps 是 None 时仍然是 None。"""
    state = GameState(config)
    state.start_run()
    assert state.maps is None


def locked_state(config: GameConfig, seed: int = 5) -> GameState:
    """锁定了的状态：带着初始宝可梦、路线、分数、胜负记录。"""
    state = GameState(config)
    state.lock_path = True
    state.seed = seed
    state.lock_results = [True, False]
    state.caught_total = 5
    state.shinies = [{"time": "t", "round": 1, "stage": 1, "pokemon": "x"}]
    state.path_results = [True, True]
    state.rental_pool = ["a", "b", "c", "d", "e", "f"]
    state.candidates = ["a", "b", "c"]
    state.lock_pokemon_index = 2
    state.maps = {"type": "2x3", "layout": 0, "rows": {}, "route": [], "current_index": 0}
    state.route_score = 0.9
    state.stage_score = 0.8
    state.boss_score = 0.7
    return state


def test_check_keep_returns_true_and_keeps_data_when_locked_and_matching(
    config: GameConfig,
) -> None:
    """check_keep：锁定了、boss 和 seed 都对得上，返回 True，数据不清。"""
    state = locked_state(config)
    assert state.check_keep(BOSS, 5) is True
    assert state.lock_path is True
    assert state.rental_pool == ["a", "b", "c", "d", "e", "f"]
    assert state.candidates == ["a", "b", "c"]
    assert state.lock_pokemon_index == 2
    assert state.maps is not None
    assert (state.route_score, state.stage_score, state.boss_score) == (0.9, 0.8, 0.7)
    assert state.path_results == [True, True]


def test_check_keep_with_different_seed_clears_keep_path_data(config: GameConfig) -> None:
    """check_keep：seed 对不上返回 False，清掉 keep path 的数据（包括 stage_score、boss_score），胜负记录保留。"""
    state = locked_state(config)
    assert state.check_keep(BOSS, 6) is False
    assert state.seed == 6
    assert state.lock_path is False
    assert state.path_results == []
    assert state.rental_pool == []
    assert state.candidates == []
    assert state.lock_pokemon_index is None
    assert state.maps is None
    assert (state.route_score, state.stage_score, state.boss_score) == (0.0, 0.0, 0.0)
    # boss 没变，刷这只 boss 的记录保留
    assert state.lock_results == [True, False]
    assert state.caught_total == 5
    assert len(state.shinies) == 1
    assert GameState(config).seed == 6


def test_check_keep_with_different_boss_also_clears_lock_results(config: GameConfig) -> None:
    """check_keep：boss 对不上，除了 keep path 的数据，还清掉 lock_results、caught_total、shinies。"""
    state = locked_state(config)
    assert state.check_keep(OTHER_BOSS, 5) is False
    assert state.boss == OTHER_BOSS
    assert state.lock_results == []
    assert state.caught_total == 0
    assert state.shinies == []
    assert state.lock_path is False
    assert state.maps is None
    assert (state.stage_score, state.boss_score) == (0.0, 0.0)


def test_check_keep_not_locked_clears_even_if_boss_and_seed_match(config: GameConfig) -> None:
    """check_keep：没锁定时即使 boss 和 seed 一样也返回 False，清掉 keep path 的数据。"""
    state = locked_state(config)
    state.lock_path = False
    assert state.check_keep(BOSS, 5) is False
    assert state.candidates == []
    assert state.maps is None
    assert state.lock_results == [True, False]


def test_finish_run_with_shiny_does_not_lock(config: GameConfig) -> None:
    """finish_run：带走了闪光，不锁定（已经锁定的也解开），记下闪光所在的关。"""
    state = finished_run(config, keep_path=True)
    state.lock_path = True
    state.lock_results = [True]
    locked, text = state.finish_run([1])
    assert (locked, text) == (False, "带走了闪光，不锁定")
    assert state.lock_path is False
    assert state.lock_results == [True, True]
    assert state.caught_total == 4
    assert len(state.shinies) == 1
    assert state.shinies[0]["round"] == 2
    assert state.shinies[0]["stage"] == 2
    assert state.shinies[0]["pokemon"] == "b"


def test_finish_run_with_keep_path_false_does_not_lock(config: GameConfig) -> None:
    """finish_run：keep_path=False 时不锁定。"""
    state = finished_run(config, keep_path=False)
    assert state.finish_run([]) == (False, "没有开启 KEEP_PATH，不锁定")


def test_finish_run_without_keep_path_argument_does_not_lock(config: GameConfig) -> None:
    """finish_run：创建 GameState 时不传 keep_path（默认 False）也不锁定。"""
    state = GameState(config)
    state.num_caught = 4
    state.dynite_ore = 50
    state.started = time.time() - 300
    assert state.finish_run([]) == (False, "没有开启 KEEP_PATH，不锁定")


def test_finish_run_with_ore_at_minimum_does_not_lock_and_unlocks(config: GameConfig) -> None:
    """finish_run：极矿石不多于 lock_min_ore（10）个时不锁定，已经锁定的也解锁。"""
    state = finished_run(config, keep_path=True)
    state.dynite_ore = config.lock_min_ore
    state.lock_path = True
    locked, text = state.finish_run([])
    assert locked is False
    assert text == "极矿石只剩 10 个，不锁定"
    assert state.lock_path is False


def test_finish_run_locked_run_keeps_locking_when_winning(config: GameConfig) -> None:
    """finish_run：已经锁定、这一局赢了、胜率够，继续锁定，path_results 加一项。"""
    state = finished_run(config, keep_path=True)
    state.lock_path = True
    state.path_results = [True]
    locked, text = state.finish_run([])
    assert locked is True
    assert text == "这张图锁定后打了 2 局，胜率 100%，继续锁定"
    assert state.path_results == [True, True]


def test_finish_run_locked_run_unlocks_after_early_losses(config: GameConfig) -> None:
    """finish_run：已经锁定、这一局输了，锁定以来输满 lock_early_fails（2）局，解锁。"""
    state = finished_run(config, keep_path=True)
    state.num_caught = 3
    state.lock_path = True
    state.path_results = [False]
    locked, text = state.finish_run([])
    assert locked is False
    assert text == "这张图锁定后打了 2 局，胜率 0%，解锁"
    assert state.lock_path is False
    assert state.lock_results == [False]


def test_finish_run_unlocked_run_locks_when_won_fast_and_few_faints(config: GameConfig) -> None:
    """finish_run：没锁定时打赢、倒下 1 次（不超过 lock_max_faints）、用时 5 分钟（不超过 10），锁定这张图。"""
    state = finished_run(config, keep_path=True, minutes=5.0, faints=1)
    locked, text = state.finish_run([])
    assert (locked, text) == (True, "锁定这张图")
    assert state.lock_path is True
    assert state.path_results == [True]


def test_finish_run_unlocked_run_does_not_lock_with_too_many_faints(config: GameConfig) -> None:
    """finish_run：没锁定时倒下 2 次（超过 lock_max_faints）不锁定。"""
    state = finished_run(config, keep_path=True, minutes=5.0, faints=2)
    state.path_results = [False]
    locked, text = state.finish_run([])
    assert (locked, text) == (False, "不锁定")
    assert state.path_results == []


def test_finish_run_unlocked_run_does_not_lock_when_too_slow(config: GameConfig) -> None:
    """finish_run：没锁定时用时 11 分钟（超过 lock_max_minutes）不锁定。"""
    state = finished_run(config, keep_path=True, minutes=11.0, faints=0)
    assert state.finish_run([]) == (False, "不锁定")


def test_finish_run_unlocked_run_does_not_lock_when_lost(config: GameConfig) -> None:
    """finish_run：没锁定时没抓满 4 只（输了）不锁定，lock_results 记下输。"""
    state = finished_run(config, keep_path=True)
    state.num_caught = 2
    assert state.finish_run([]) == (False, "不锁定")
    assert state.lock_results == [False]
    assert state.caught_total == 2


def test_finish_run_saves_state_to_file(config: GameConfig) -> None:
    """finish_run：结束时把状态写进文件，重新读出来锁定状态和胜负记录一致。"""
    state = finished_run(config, keep_path=True)
    state.finish_run([])
    again = GameState(config)
    assert again.lock_path is True
    assert again.lock_results == [True]
    assert again.path_results == [True]


def test_should_unlock_before_window_needs_early_fails(config: GameConfig) -> None:
    """_should_unlock：没打满 lock_window_rounds 局时，输 1 局不解锁，输满 lock_early_fails（2）局解锁。"""
    state = GameState(config)
    state.path_results = [True, False, True]
    assert state._should_unlock() is False
    state.path_results = [True, False, True, False]
    assert state._should_unlock() is True


def test_should_unlock_after_window_uses_win_rate(config: GameConfig) -> None:
    """_should_unlock：打满 10 局后，胜率 90%（不低于 lock_min_win_rate）不解锁，80% 解锁。"""
    state = GameState(config)
    state.path_results = [True] * 9 + [False]
    assert state._should_unlock() is False
    state.path_results = [True] * 8 + [False] * 2
    assert state._should_unlock() is True
