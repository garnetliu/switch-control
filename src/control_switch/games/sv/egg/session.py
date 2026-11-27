"""孵蛋刷闪用的 Session：带着孵蛋过程中的状态。"""

from control_switch.device import Devices
from control_switch.games.sv.session import SvSession
from control_switch.settings import Settings

from .config import EggConfig


class EggSession(SvSession):
    """步骤里用 sw.config、sw.parent_best 等取。"""

    config: EggConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(EggConfig(), settings, devices)
        # 亲代是野餐队伍的第几只（从 0 数）、名字、「最棒」的项数，initialize 读出来
        self.parent_index = 0
        self.parent_name = ""
        self.parent_best = 0
        # 游戏里的评定功能解锁了没有：没解锁读不到「最棒」的项数，不换亲代
        self.judge_unlocked = False
        # 放蛋的盒子编号：第一次打开盒子时读出开着的是哪个，放蛋的是它后面那个
        self.egg_box: int | None = None
        # 现在有几个蛋，initialize 数出来：拿蛋时是放蛋的盒子里的蛋（还差 max_eggs 减它），
        # 孵蛋时是放蛋的盒子和队伍里的蛋（就是还要孵的数）
        self.eggs = 0
        # 队伍里还剩几个蛋：换蛋时数出来，每孵出一个减 1
        self.eggs_in_party = 0
        # 这一盒有没有留下过东西（闪光、换下来的旧亲代）：没留下就重启游戏回档，留下了要放生整盒再存档
        self.kept_in_box = False
        # 留下东西之后还没存档
        self.save_pending = False
        # 开了几次野餐，写日志用
        self.picnics = 0
