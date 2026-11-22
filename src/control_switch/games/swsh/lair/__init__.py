"""极巨大冒险刷闪。"""

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
