"""所有游戏共用的配置：路径、计时、摇杆、重启游戏。每个脚本的配置继承 BaseConfig。"""

from pathlib import Path

from type import Hsv, Rect

ROOT = Path(__file__).resolve().parents[2]


class BaseRects:
    """Switch 系统界面上的坐标范围，和游戏无关。"""

    # 重启游戏：HOME 菜单底部「切换用户」的提示、关闭软件的确认框、选用户界面的标题
    home_hint: Rect = ((0.5, 0.9), (1.0, 1.0))
    close_dialog: Rect = ((0.45, 0.38), (0.8, 0.5))
    user_picker: Rect = ((0.0, 0.45), (0.5, 0.55))


class BaseConfig:
    """和游戏无关的配置。"""

    # 画面上的坐标范围
    rects = BaseRects()
    # 这个脚本的日志和出错时的截图，每个脚本一个目录
    log_dir = ROOT / "logs"
    # 闪光的截图
    catch_dir = ROOT / "catches"
    # 能跑这个脚本的游戏的 Title ID
    game_title_ids: tuple[str, ...] = ()
    # 摇杆坐标最大值和推一格保持的时间
    stick_max = 0x7FFF
    stick_tick = 0.08
    # 等画面变化和操作超时
    timeout = 60.0
    # 重启游戏：等选用户界面、等开场彩色画面最多几秒
    load_timeout = 30.0
    boot_timeout = 60.0
    # 开场画面是彩色的：鲜艳的像素（饱和度、亮度都不低）至少占这么多
    colorful_lower: Hsv = (0, 100, 60)
    colorful_upper: Hsv = (180, 255, 255)
    colorful_ratio = 0.3
    # 两次截图之间的间隔
    interval = 0.3

    @property
    def check_dir(self) -> Path:
        """判定成功时的截图，环境变量 SAVE_CHECKS 里写了现在的步骤才存。"""
        return self.log_dir / "checks"

    @property
    def keep_dir(self) -> Path:
        """长期留着的截图，清空日志时不删。"""
        return self.log_dir / "keep"
