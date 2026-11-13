"""朱紫的脚本共用的配置：内存指针、存档块、按键之后等多久。

指针和等待时间照 Eppin/Sysbot.NET（朱紫 4.0.0）的 PokeDataOffsetsSV、SaveGame、DoPicnicResetting。
"""

from libs import BaseConfig
from sv import TITLE_IDS


class SvConfig(BaseConfig):
    """朱紫的配置。"""

    game_title_ids = TITLE_IDS
    # 存档块表的指针链：main+... → ...，游戏版本 4.0.0
    block_key_pointer = (0x47350D8, 0xD8, 0x0, 0x0, 0x30, 0x0)
    # 存档：X 开菜单、R 存档、A 确认，每个键按完等几秒；再按 save_back 下 B 回到野外，每下等 save_back_wait 秒
    save_menu_wait = 2.5
    save_prompt_wait = 2.3
    save_done_wait = 7.0
    save_back = 4
    save_back_wait = 0.4
    # 野餐：X 开菜单、A 进野餐（光标要事先停在「野餐」上），每个键按完等几秒
    picnic_menu_wait = 2.5
    picnic_open_wait = 6.5
    # 收起野餐：Y、A，每个键按完等几秒
    picnic_close_prompt_wait = 2.5
    picnic_close_wait = 3.5
