"""孵蛋刷闪的步骤：initialize 开始，fetch 收蛋，hatch 孵蛋，release 放生，一直循环。"""

from .fetch import fetch
from .hatch import hatch
from .initialize import initialize
from .release import release

__all__ = ["fetch", "hatch", "initialize", "release"]
