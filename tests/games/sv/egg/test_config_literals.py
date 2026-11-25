"""约定：「config.py：所有坐标、阈值、时间、按键路线都写在这里」。

screens.py、box.py、steps/ 里不该再有写死的小数（坐标比例、等待秒数），
不然真机上要调时只改 EggConfig 不起作用。
"""

import ast
from pathlib import Path

import pytest

from control_switch.games.sv import egg

EGG_DIR = Path(egg.__file__).resolve().parent


def _fraction_literals(path: Path) -> list[str]:
    """文件里不是整数的数字字面量（像 0.15、0.021），返回「行号: 值」。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, float)
            and not node.value.is_integer()
        ):
            found.append(f"{node.lineno}: {node.value}")
    return sorted(found)


@pytest.mark.parametrize(
    "name",
    ["screens.py", "box.py", *sorted(f"steps/{p.name}" for p in (EGG_DIR / "steps").glob("*.py"))],
)
def test_no_hard_coded_coordinates_or_waits_outside_egg_config(name: str) -> None:
    """screens.py 的格子坐标（_party_cell、_box_cell 里的 0.021、0.1167 等）、box.py 和 steps/ 里
    sw.click 写死的等待（0.15、0.5 等）都应该在 EggConfig 里。
    """
    assert _fraction_literals(EGG_DIR / name) == []
