"""朱紫的脚本共用的配置：几个地方都用到的值才放这里，只有一处用的写在那个函数里。"""

from control_switch.config import BaseConfig
from control_switch.types import Hsv


class MenuConfig:
    """主菜单（按 X）：右边六行和左边队伍栏都用的光标颜色。"""

    # 光标所在的那一行（格）是黄色，黄色像素占比超过 ratio
    yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    ratio = 0.4


class SvConfig(BaseConfig):
    """朱紫的配置。"""

    def __init__(self) -> None:
        super().__init__()
        self.menu = MenuConfig()
