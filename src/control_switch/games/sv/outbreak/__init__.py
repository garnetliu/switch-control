"""朱紫的大量出现刷闪。"""

from control_switch.games.sv import TITLE_IDS as TITLE_IDS

from .session import OutbreakSession
from .steps import initialize, knockout, refresh, scan

# 步骤表：每一步是一个函数，传入连接，返回下一步的名字；返回的名字不在表里就结束
STEPS = {
    "initialize": initialize,
    "knockout": knockout,
    "refresh": refresh,
    "scan": scan,
}
# 从哪一步开始
START = "initialize"

# 这个脚本用的 Session
SESSION = OutbreakSession

# 这个脚本需要的设备：screen（取图）、controller（按键）、memory（读写内存）
REQUIRES = frozenset({"screen", "controller", "memory"})

# TITLE_IDS：能跑这个脚本的游戏的 Title ID，从所属游戏引用（见文件开头的 import）
