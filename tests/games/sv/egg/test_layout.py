"""sv/egg 重写后的结构：步骤只有 initialize、fetch、hatch 三个，写法照极巨大冒险（一个步骤一个文件）。"""

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from control_switch.games.sv import egg
from control_switch.games.sv.egg import STEPS

STEP_NAMES = ["initialize", "fetch", "hatch"]
STEPS_DIR = Path(str(egg.__file__)).parent / "steps"


def test_steps_table_has_exactly_initialize_fetch_and_hatch() -> None:
    """STEPS 里正好是 initialize、fetch、hatch 三个步骤。"""
    assert set(STEPS) == set(STEP_NAMES)


def test_start_is_initialize() -> None:
    """脚本从 initialize 开始。"""
    assert egg.START == "initialize"


def test_steps_directory_only_has_init_and_the_three_step_files() -> None:
    """steps/ 下只有 __init__.py、initialize.py、fetch.py、hatch.py。"""
    names = {path.name for path in STEPS_DIR.glob("*.py")}
    assert names == {"__init__.py", "initialize.py", "fetch.py", "hatch.py"}


@pytest.mark.parametrize("name", STEP_NAMES)
def test_each_step_is_a_function_with_the_same_name_as_its_file(name: str) -> None:
    """每个步骤文件里有一个和文件同名的函数，STEPS 里放的就是它。"""
    module = importlib.import_module(f"control_switch.games.sv.egg.steps.{name}")
    function: Callable[..., Any] = getattr(module, name)
    assert inspect.isfunction(function)
    assert STEPS[name] is function


@pytest.mark.parametrize("name", STEP_NAMES)
def test_each_step_takes_only_the_session(name: str) -> None:
    """每个步骤只有一个参数（session），写法照大冒险。"""
    assert len(inspect.signature(STEPS[name]).parameters) == 1


@pytest.mark.parametrize("name", STEP_NAMES)
def test_steps_package_exports_each_step(name: str) -> None:
    """steps 包的 __all__ 里有每个步骤，包上能取到同一个函数。"""
    steps = importlib.import_module("control_switch.games.sv.egg.steps")
    assert name in steps.__all__
    assert getattr(steps, name) is STEPS[name]
