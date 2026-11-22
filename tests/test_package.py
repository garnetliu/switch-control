"""control_switch 包本身能被引用、来源位置正确。"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_import_control_switch_succeeds() -> None:
    """`import control_switch` 不报错。"""
    import control_switch

    assert control_switch is not None


def test_package_file_is_under_repo_src_control_switch() -> None:
    """`control_switch.__file__` 位于仓库的 src/control_switch/ 目录下。"""
    import control_switch

    assert control_switch.__file__ is not None
    package_file = Path(control_switch.__file__).resolve()
    assert package_file.is_relative_to(REPO_ROOT / "src" / "control_switch")
