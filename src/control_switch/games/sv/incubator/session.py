"""孵蛋刷闪用的 Session：带着孵蛋过程中的状态。"""

from control_switch.device import Devices
from control_switch.games.sv.session import SvSession
from control_switch.settings import Settings

from .config import IncubatorConfig
from .types import Boxes, TeamType


class IncubatorSession(SvSession):
    """步骤里用 sw.config、sw.parent_best 等取。"""

    config: IncubatorConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(IncubatorConfig(), settings, devices)
        # 当前队伍是孵蛋还是拿蛋、亲代「最棒」的项数，initialize 读出来
        self.team_type = TeamType.FETCH
        self.parent_best = 0
        # 用到的三个盒子：锚点、放蛋的、放留下来的，initialize 找出来
        self.boxes = Boxes(-1, -1, -1)
        # 现在有几个蛋，initialize 数出来：拿蛋时是放蛋的盒子里的蛋（还差 max_eggs 减它），
        # 孵蛋时是放蛋的盒子和队伍里的蛋（就是还要孵的数）
        self.eggs = 0
        # 队伍里还剩几个蛋：换蛋时数出来，每孵出一个减 1
        self.eggs_in_party = 0
        # 开了几次野餐，写日志用
        self.picnics = 0
