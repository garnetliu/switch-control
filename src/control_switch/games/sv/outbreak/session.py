"""大量出现刷闪用的 Session：带着存档块的读写。"""

from control_switch.device import Controller, Memory, Screen
from control_switch.games.sv.blocks import SaveBlocks
from control_switch.pkhex import Pkhex
from control_switch.session import Session

from .config import OutbreakConfig


class OutbreakSession(Session):
    """步骤里用 sw.config、sw.blocks 取。"""

    config: OutbreakConfig

    def __init__(self, screen: Screen, controller: Controller, memory: Memory | None):
        super().__init__(OutbreakConfig(), screen, controller, memory)
        self.blocks = SaveBlocks(self.memory, Pkhex(), self.config.block_key_pointer)
