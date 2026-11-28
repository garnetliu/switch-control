"""孵蛋刷闪的配置：玩法、走路路线、坐标、颜色阈值、等待时间。

坐标是占画面宽高的比例，720p（botbase）和 1080p（采集卡）通用；
照 PokemonAutomation（Arduino-Source）的 PokemonSV 孵蛋流程，真机上和上游不同的在 README 里写明。
几个脚本共用的画面判断（对话框、野外、野餐、主菜单）的配置在 SvConfig。
"""

from control_switch.games.sv.config import SvConfig


class IncubatorConfig(SvConfig):
    """孵蛋刷闪的配置。"""

    log_dir = SvConfig.root / "runs" / "logs" / "incubator"

    # ---- 玩法 ----
    # 野餐队伍里的百变怪（不是亲代），日志和盒子面板上读到的名字
    ditto_name = "百变怪"
    # 做的三明治：超级花生酱三明治的食谱编号
    recipe_number = 17
    # 一次野餐最多收几个蛋，收蛋最多等几秒（三明治的效果 30 分钟）
    max_eggs = 30
    fetch_limit = 1800
    # 一共有多少个盒子，最后一个往后是第一个
    box_count = 32
    # 盒子有多少行多少列
    box_rows = 5
    box_columns = 6
    # 队伍一共有多少个
    party_rows = 6
