"""极巨大冒险刷闪。"""

from .steps import battle, catch, initialize, join, path, select_pokemon
from .switch import LairSwitch

# 步骤表：每一步是一个函数，传入连接，返回下一步的名字
STEPS = {
    "initialize": initialize,
    "join": join,
    "path": path,
    "battle": battle,
    "catch": catch,
    "select_pokemon": select_pokemon,
}
# 从哪一步开始
START = "initialize"


def connect() -> LairSwitch:
    """连接 Switch，带上这个脚本的配置和状态。"""
    return LairSwitch()
