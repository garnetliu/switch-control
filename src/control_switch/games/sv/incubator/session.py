"""孵蛋刷闪用的 Session：带着孵蛋过程中的状态。"""

from control_switch.device import Devices
from control_switch.games.sv.session import SvSession
from control_switch.settings import Settings

from .config import IncubatorConfig
from .types import TeamType


class IncubatorSession(SvSession):
    """步骤里用 sw.config、sw.parent_best 等取。"""

    config: IncubatorConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(IncubatorConfig(), settings, devices)
        # 当前队伍是孵蛋还是拿蛋、亲代「最棒」的项数，initialize 读出来
        self.team_type = TeamType.FETCH
        self.parent_best = 0
        # 放蛋的盒子编号：第一次打开盒子时读出开着的是哪个，放蛋的是它后面那个
        self.egg_box: int | None = None
        # 现在有几个蛋，initialize 数出来：拿蛋时是放蛋的盒子里的蛋（还差 max_eggs 减它），
        # 孵蛋时是放蛋的盒子和队伍里的蛋（就是还要孵的数）
        self.eggs = 0
        # 队伍里还剩几个蛋：换蛋时数出来，每孵出一个减 1
        self.eggs_in_party = 0
        # 这一盒有没有出闪光，是盒子里面的第几个，-1 代表没有
        self.shiny_in_box = -1
        # 这一盒有没有需要和亲代换的，是盒子的第几个，-1 代表没有
        self.parent_in_box = -1
        # 留下东西之后还没存档
        self.save_pending = False
        # 开了几次野餐，写日志用
        self.picnics = 0
