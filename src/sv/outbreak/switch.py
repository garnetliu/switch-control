"""大量出现刷闪用的连接：连接之外还带着存档块的读写。"""

from libs import Pkhex, Switch
from sv.blocks import SaveBlocks

from .config import OutbreakConfig


class OutbreakSwitch(Switch):
    """一条连接和存档块。步骤里用 sw.config、sw.blocks 取。"""

    config: OutbreakConfig

    def __init__(self):
        super().__init__(OutbreakConfig())
        self.blocks = SaveBlocks(self, Pkhex(), self.config.block_key_pointer)
