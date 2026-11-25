"""孵蛋刷闪的步骤。

人站在野外空地，队伍第 3 格是亲代，第 4–6 格空着。循环：开野餐、做三明治、去篮子收蛋，
收够了把蛋三个一组放进队伍，骑着坐骑绕圈孵化，看孵出来的：闪光就推送并停下，
个体比亲代好的换掉亲代，其余放生。
"""

from .check import check
from .collect import collect
from .hatch_load import hatch_load
from .hatch_walk import hatch_walk
from .initialize import initialize
from .picnic import picnic
from .sandwich import sandwich
from .to_basket import to_basket

__all__ = [
    "check",
    "collect",
    "hatch_load",
    "hatch_walk",
    "initialize",
    "picnic",
    "sandwich",
    "to_basket",
]
