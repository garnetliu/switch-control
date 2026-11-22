"""朱紫的大量出现刷闪。"""

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
