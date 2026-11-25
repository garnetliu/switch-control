"""朱紫的脚本共用的配置：内存指针、存档块、认画面用的区域和颜色、存档和野餐的等待。

指针照 Eppin/Sysbot.NET（朱紫 4.0.0）的 PokeDataOffsetsSV。
画面上的区域都是占画面宽高的比例，720p（botbase）和 1080p（采集卡）通用；
位置照 PokemonAutomation（Arduino-Source）的 PokemonSV 识别，颜色和阈值在真机上量过。
"""

from control_switch.config import BaseConfig
from control_switch.types import Hsv, Rect


class SvConfig(BaseConfig):
    """朱紫的配置。"""

    # 存档块表的指针链：main+... → ...，游戏版本 4.0.0
    block_key_pointer = (0x47350D8, 0xD8, 0x0, 0x0, 0x30, 0x0)

    # ---- 对话框 ----
    # 对话框左上角的黄色小角标、框里的暗色底
    dialog_corner: Rect = ((0.251, 0.724), (0.271, 0.741))
    dialog_body: Rect = ((0.292, 0.75), (0.708, 0.88))
    dialog_yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    dialog_corner_ratio = 0.3
    dialog_dark_max = 60
    dialog_dark_ratio = 0.8
    # 右下角提示翻页的小三角（▽）：白色像素占这个区域的比例超过 dialog_arrow_ratio
    dialog_arrow: Rect = ((0.705, 0.845), (0.745, 0.900))
    dialog_arrow_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 60, 255))
    dialog_arrow_ratio = 0.03
    # 对话框带「是 / 否」这样的选择框时，选择框的箭头在这个范围里
    prompt_area: Rect = ((0.50, 0.40), (0.90, 0.90))

    # ---- 渐变箭头（黄绿色渐变到青色的选中箭头）----
    # 黄绿色、青色的像素数占整张截图的比例，两种都够才算有箭头
    arrow_yellow: tuple[Hsv, Hsv] = ((30, 150, 200), (48, 255, 255))
    arrow_cyan: tuple[Hsv, Hsv] = ((75, 100, 150), (105, 255, 255))
    arrow_yellow_min = 0.0002
    arrow_cyan_min = 0.0001

    # ---- 野外 ----
    # 小地图外圈：圆心和半径（半径按画面高度的比例），圈上按青、绿、黄分段着色。
    # 三种颜色在圈上各占至少 minimap_ratio 才算野外。只看一种颜色不行：盒子画面那里是青色，
    # 野餐画面是绿色；只看地图里的土黄色也不行，沙漠地形孵化动画时整片地面都是土黄色
    minimap_center = (0.90625, 0.8333)
    minimap_radii = (0.124, 0.128)
    minimap_colors: tuple[tuple[Hsv, Hsv], ...] = (
        ((80, 100, 150), (105, 255, 255)),
        ((40, 100, 150), (80, 255, 255)),
        ((20, 100, 150), (35, 255, 255)),
    )
    minimap_ratio = 0.1

    # ---- 野餐 ----
    # 野餐时左下角三个白色按键图标（B、减号、Y）的位置，白色像素占比超过 picnic_ratio
    picnic_icons: tuple[Rect, ...] = (
        ((0.024, 0.702), (0.048, 0.747)),
        ((0.024, 0.866), (0.048, 0.911)),
        ((0.024, 0.917), (0.048, 0.962)),
    )
    picnic_white: tuple[Hsv, Hsv] = ((0, 0, 200), (180, 40, 255))
    picnic_ratio = 0.15
    # 图标底下是暗色的标签：暗色像素也要占一定比例，不然桌布上白色的餐巾、碗沿会被当成按键图标
    picnic_dark: tuple[Hsv, Hsv] = ((0, 0, 0), (180, 255, 90))
    picnic_dark_ratio = 0.3

    # ---- 主菜单（按 X）----
    # 右边六行，第一行的位置和行高；光标在这一行上时整行是黄色。光标在左边队伍栏上时，队伍第一格是黄色
    menu_rows = 6
    menu_left = 0.693
    menu_right = 0.953
    menu_top = 0.224
    menu_row_height = 0.0736
    menu_yellow: tuple[Hsv, Hsv] = ((20, 150, 180), (35, 255, 255))
    menu_ratio = 0.4
    menu_party: Rect = ((0.045, 0.16), (0.30, 0.25))
    # 菜单里「盒子」「野餐」在第几行（从 0 数）
    menu_box_row = 1
    menu_picnic_row = 2

    # ---- 按键之后的等待和超时 ----
    # 按 X 之后几秒没出主菜单就再按一次
    menu_retry = 3.0
    # 菜单里按一下方向键、按 A 之后等几秒再看画面
    menu_move_wait = 0.4
    menu_enter_interval = 1.5
    # 开野餐最多等几秒，认出之后再等几秒（丢精灵球的动画期间人不能动）
    picnic_timeout = 120.0
    picnic_settle_wait = 8.0
    # 收起野餐：按 Y 等确认框、按 A 等回到野外，每隔几秒重按，最多等几秒，最后再等几秒
    leave_prompt_interval = 5.0
    leave_prompt_timeout = 25.0
    leave_overworld_interval = 1.2
    leave_overworld_timeout = 20.0
    leave_final_wait = 3.0
    # 存档：认到「存档完成」的对话按 B，再按 B 回到野外，每次按键之间隔几秒；整个存档最多几秒
    save_press_wait = 0.84
    save_timeout = 300.0
    # 按了「是」之后，存完的对话几秒没出来就当没存上，重来
    save_confirm_timeout = 10.0
