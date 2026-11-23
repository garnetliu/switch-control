"""极巨大冒险刷闪。"""

from control_switch.games.swsh import TITLE_IDS as TITLE_IDS

from .session import LairSession
from .steps import battle, catch, initialize, join, path, select_pokemon

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

# 这个脚本用的 Session
SESSION = LairSession

# 这个脚本需要的设备：screen（取图）、controller（按键）、memory（读写内存）
REQUIRES = frozenset({"screen", "controller", "memory"})

# TITLE_IDS：能跑这个脚本的游戏的 Title ID，从所属游戏引用（见文件开头的 import）
