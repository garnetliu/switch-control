"""读写项目根目录的 .env。只用标准库，系统自带的 Python 3.9 也能跑。"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"


def load_env():
    """把 .env 里的 KEY=VALUE 读进环境变量，已经设置的不覆盖。"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def set_env(key: str, value: str):
    """把 KEY=VALUE 写进 .env：已有同名项就替换，没有就追加。"""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(key + "=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
