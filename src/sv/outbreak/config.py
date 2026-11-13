"""大量出现刷闪的配置。"""

from libs.config import ROOT
from sv.config import SvConfig


class OutbreakConfig(SvConfig):
    """大量出现刷闪的配置。"""

    # 日志和出错时的截图
    log_dir = ROOT / "logs" / "sv-outbreak"
    # 要找的宝可梦，写简体中文名，比如 ("伊布", "拉鲁拉丝")。空着就是任何闪光都停
    targets: tuple[str, ...] = ()
    # 开始时要不要把大量出现的击败数改满（要重启一次游戏）
    knockout = True
    # 击败数达到 knockout_enough 就不改；不够的改成 knockout_count，但不超过这个大量出现的总数减 1
    knockout_enough = 60
    knockout_count = 64
    # 重启游戏后，开场的彩色画面出现再等几秒才改击败数，等存档读进内存
    title_wait = 19.0
    # 从标题画面进游戏，画面变黑之后等几秒回到野外
    enter_wait = 15.0
    # 收起野餐之后先等几秒再存档，让身边的宝可梦生成完
    spawn_wait = 0.0
