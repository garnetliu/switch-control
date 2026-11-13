"""脚本表：按「游戏/脚本」的名字找到脚本。"""

import importlib
from types import ModuleType

# 名字对应的模块。每个模块给出 STEPS（步骤表）、START（起点）、connect()（创建连接）
SCRIPTS = {
    "swsh/lair": "swsh.lair",
    "sv/outbreak": "sv.outbreak",
}


def load_script(name: str) -> ModuleType:
    """按名字导入脚本的模块。用到才导入，跑一个游戏的脚本不会加载另一个游戏的数据。"""
    if name not in SCRIPTS:
        raise SystemExit(f"没有「{name}」这个脚本，可以用的有：{'、'.join(SCRIPTS)}")
    return importlib.import_module(SCRIPTS[name])
