"""朱紫几个脚本都会用到的操作：存档、开野餐、收野餐、开盒子、从主菜单进某一项、退回野外，一个操作一个文件。

每一步按完都看画面，认到了才走下一步，没反应就再按（照 PokemonAutomation 的 save_game_from_overworld、
picnic_from_overworld、leave_picnic）。每一步等完都截一张图记在内存里，出错时会写进日志目录。
"""

from .close_picnic import close_picnic
from .exit_to_overworld import exit_to_overworld
from .menu_to_row import menu_to_row
from .open_box import open_box
from .open_menu import open_menu
from .open_picnic import open_picnic
from .save_game import save_game

__all__ = [
    "close_picnic",
    "exit_to_overworld",
    "menu_to_row",
    "open_box",
    "open_menu",
    "open_picnic",
    "save_game",
]
