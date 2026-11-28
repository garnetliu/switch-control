from .session import IncubatorSession
from .steps import fetch, hatch, initialize, release

# 步骤表：每一步是一个函数，传入连接，返回下一步的名字；返回的名字不在表里就结束
STEPS = {
    "initialize": initialize,
    "fetch": fetch,
    "hatch": hatch,
    "release": release,
}

# 从哪一步开始
START = "initialize"

# 这个脚本用的 Session
SESSION = IncubatorSession

# 这个脚本需要的设备：取图和按键，不读写内存
REQUIRES = frozenset({"screen", "controller"})
