"""朱紫的脚本共用的 Session：config 是 SvConfig。每个脚本的 Session 继承它。"""

from control_switch.device import Devices
from control_switch.games.sv.config import SvConfig
from control_switch.session import Session
from control_switch.settings import Settings


class SvSession(Session):
    """朱紫的 Session，sw.config 是 SvConfig。"""

    def __init__(self, config: SvConfig, settings: Settings, devices: Devices):
        super().__init__(config, settings, devices)
        self.config = config
