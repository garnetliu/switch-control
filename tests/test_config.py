"""control_switch.config：仓库根目录和日志目录的派生路径。"""

from pathlib import Path

from control_switch.config import ROOT, BaseConfig, BaseRects


def test_root_points_to_repo_root() -> None:
    """ROOT 指向仓库根目录：下面有 pyproject.toml。"""
    assert (ROOT / "pyproject.toml").exists()


def test_failed_dir_is_log_dir_failed() -> None:
    """默认配置的 failed_dir 是 log_dir / "failed"。"""
    assert BaseConfig().failed_dir == BaseConfig.log_dir / "failed"


def test_failed_dir_follows_overridden_log_dir(tmp_path: Path) -> None:
    """子类改了 log_dir，failed_dir 跟着变。"""

    class CustomConfig(BaseConfig):
        log_dir = tmp_path

    assert CustomConfig().failed_dir == tmp_path / "failed"


def test_base_rects_are_ratio_rects() -> None:
    """BaseRects 里的区域是 ((左, 上), (右, 下))，数值都在 0 到 1 之间。"""
    rects = BaseConfig().rects
    assert isinstance(rects, BaseRects)
    for rect in (rects.home_hint, rects.close_dialog, rects.user_picker):
        (left, top), (right, bottom) = rect
        assert 0 <= left < right <= 1
        assert 0 <= top < bottom <= 1
