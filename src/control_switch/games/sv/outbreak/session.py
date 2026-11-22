"""大量出现刷闪用的 Session：带着存档块的读写。"""

from control_switch.device import Devices
from control_switch.games.sv.blocks import SaveBlocks
from control_switch.pkhex import Pkhex
from control_switch.session import Session
from control_switch.settings import Settings

from .config import OutbreakConfig


class OutbreakSession(Session):
    """步骤里用 sw.config、sw.blocks 取。"""

    config: OutbreakConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(OutbreakConfig(), settings, devices)
        self.blocks = SaveBlocks(
            self.memory, Pkhex(settings.pkhex_api_url), self.config.block_key_pointer
        )
