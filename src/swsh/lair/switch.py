"""极巨大冒险用的连接：连接之外还带着这一局的状态、游戏数据和 PK8 读取。"""

from libs import Pkhex, Switch
from swsh.pk8 import Pk8Reader

from .game_config import GameConfig
from .game_data import GameData
from .game_state import GameState


class LairSwitch(Switch):
    """一条连接和这一局的状态。步骤里用 sw.config、sw.game、sw.data、sw.pkhex 取。"""

    config: GameConfig

    def __init__(self):
        super().__init__(GameConfig())
        self.game = GameState(self.config)
        self.data = GameData(self.config)
        self.pkhex = Pk8Reader(Pkhex(), self.peek)
