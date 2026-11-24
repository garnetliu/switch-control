"""朱紫的孵蛋刷闪：只用取图和按键，不读内存。"""

from control_switch.games.sv import TITLE_IDS as TITLE_IDS

from .session import EggSession
from .steps import check, collect, hatch_load, hatch_walk, initialize, picnic, sandwich, to_basket

# 步骤表：每一步是一个函数，传入连接，返回下一步的名字；返回的名字不在表里就结束
STEPS = {
    "initialize": initialize,
    "picnic": picnic,
    "sandwich": sandwich,
    "to_basket": to_basket,
    "collect": collect,
    "hatch_load": hatch_load,
    "hatch_walk": hatch_walk,
    "check": check,
}
# 从哪一步开始
START = "initialize"

# 这个脚本用的 Session
SESSION = EggSession

# 这个脚本需要的设备：取图和按键，不读写内存
REQUIRES = frozenset({"screen", "controller"})

# TITLE_IDS：能跑这个脚本的游戏的 Title ID，从所属游戏引用（见文件开头的 import）
