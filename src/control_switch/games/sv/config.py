"""朱紫的脚本共用的配置：认画面用的区域和颜色、存档和野餐的等待。

画面上的区域都是占画面宽高的比例，720p（botbase）和 1080p（采集卡）通用；
位置照 PokemonAutomation（Arduino-Source）的 PokemonSV 识别，颜色和阈值在真机上量过。
"""

from control_switch.config import BaseConfig
from control_switch.types import Hsv, Rect


class DialogConfig:
    """对话框和对话框里的选择框。"""

    # 对话框左上角的黄色小角标、框里的暗色底
    corner: Rect = ((0.251, 0.724), (0.271, 0.741))
    body: Rect = ((0.292, 0.75), (0.708, 0.88))
    yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    corner_ratio = 0.3
    dark_max = 60
    dark_ratio = 0.8
    # 右下角提示翻页的小三角（▽）：白色像素占这个区域的比例超过 arrow_ratio
    arrow: Rect = ((0.705, 0.845), (0.745, 0.900))
    arrow_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 60, 255))
    arrow_ratio = 0.03
    # 对话框带「是 / 否」这样的选择框时，选择框的箭头在这个范围里
    prompt_area: Rect = ((0.50, 0.40), (0.90, 0.90))


class GradientArrowConfig:
    """黄绿色渐变到青色的选中箭头。"""

    # 黄绿色、青色的像素数占整张截图的比例，两种都够才算有箭头
    yellow: tuple[Hsv, Hsv] = ((30, 150, 200), (48, 255, 255))
    cyan: tuple[Hsv, Hsv] = ((75, 100, 150), (105, 255, 255))
    yellow_min = 0.0002
    cyan_min = 0.0001


class MenuConfig:
    """主菜单（按 X）。"""

    # 右边六行，第一行的位置和行高；光标在这一行上时整行是黄色。光标在左边队伍栏上时，队伍第一格是黄色
    rows = 6
    left = 0.693
    right = 0.953
    top = 0.224
    row_height = 0.0736
    yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    ratio = 0.4
    party: Rect = ((0.045, 0.16), (0.30, 0.25))
    # 「野餐」在第几行（从 0 数）
    picnic_row = 2


class SaveConfig:
    """存档。"""

    # 认到「存档完成」的对话按 B，再按 B 回到野外，每次按键之间隔几秒；整个存档最多几秒
    press_wait = 0.84
    timeout = 300.0
    # 按了「是」之后，存完的对话几秒没出来就当没存上，重来
    confirm_timeout = 10.0


class BoxConfig:
    """盒子。"""

    # 主菜单里「盒子」在第几行（从 0 数）
    menu_row = 1
    # 打开盒子最多等几秒
    open_timeout = 30.0
    # 盒子名（「盒子 N」）的位置
    title_area: Rect = ((0.34, 0.11), (0.56, 0.165))


class SvConfig(BaseConfig):
    """朱紫的配置。"""

    def __init__(self) -> None:
        super().__init__()
        self.dialog = DialogConfig()
        self.gradient_arrow = GradientArrowConfig()
        self.menu = MenuConfig()
        self.save = SaveConfig()
        self.box = BoxConfig()
