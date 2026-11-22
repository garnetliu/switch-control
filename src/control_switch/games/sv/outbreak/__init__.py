"""朱紫的大量出现刷闪。"""

from .steps import initialize, knockout, refresh, scan
from .switch import OutbreakSwitch

# 步骤表：每一步是一个函数，传入连接，返回下一步的名字；返回的名字不在表里就结束
STEPS = {
    "initialize": initialize,
    "knockout": knockout,
    "refresh": refresh,
    "scan": scan,
}
# 从哪一步开始
START = "initialize"


def connect() -> OutbreakSwitch:
    """连接 Switch，带上这个脚本的配置和存档块。"""
    return OutbreakSwitch()
