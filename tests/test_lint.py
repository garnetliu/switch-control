"""tests/ 自己也要过 `make lint`（ruff check）。"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tests_directory_passes_ruff_check_without_cache() -> None:
    """tests/ 下的文件不带缓存跑 ruff check 也没有报错。

    防的是：任务 02 新写的 test_notifier.py、test_pkhex.py、vision/test_image.py 把
    `from control_switch...` 和 `import pytest` 放在同一组，ruff 认为 control_switch 是本项目的包，
    要单独一组，报 I001。ruff 有缓存时可能看不出来，所以加 --no-cache。
    """
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
