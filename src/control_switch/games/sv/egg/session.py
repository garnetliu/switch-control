"""孵蛋刷闪用的 Session：带着孵蛋过程中的状态。"""

from control_switch.device import Devices
from control_switch.session import Session
from control_switch.settings import Settings

from .config import EggConfig


class EggSession(Session):
    """步骤里用 sw.config、sw.parent_best 等取。"""

    config: EggConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(EggConfig(), settings, devices)
        # 亲代「最棒」的项数，initialize 读出来
        self.parent_best = 0
        # 这次野餐从篮子里收了几个蛋
        self.eggs_in_box = 0
        # 队伍里要孵的蛋数
        self.eggs_in_party = 0
        # 总共孵了几只
        self.hatched = 0
        # 开了几次野餐
        self.picnics = 0
        # 三明治做好的时间（time.monotonic()），还没做过是 None
        self.sandwich_at: float | None = None
