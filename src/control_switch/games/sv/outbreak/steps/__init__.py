"""大量出现刷闪的步骤。

人站在大量出现的范围里，菜单的光标停在「野餐」上。先把击败数改满，然后循环：
开野餐再收起，刷新身边的宝可梦；存档，读内存里身边的宝可梦；有闪光就停下并推送。
"""

from .initialize import initialize
from .knockout import knockout
from .refresh import refresh
from .scan import scan

__all__ = [
    "initialize",
    "knockout",
    "refresh",
    "scan",
]
