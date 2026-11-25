"""所有游戏共用的配置：路径、计时、摇杆、重启游戏。每个脚本的配置继承 BaseConfig。"""

from pathlib import Path

from control_switch.types import Hsv, Rect


class RestartConfig:
    """重启游戏。"""

    # 要认的几处画面位置：HOME 菜单底部「切换用户」的提示、关闭软件的确认框、选用户界面的标题
    home_hint: Rect = ((0.5, 0.9), (1.0, 1.0))
    close_dialog: Rect = ((0.45, 0.38), (0.8, 0.5))
    user_picker: Rect = ((0.0, 0.45), (0.5, 0.55))
    # 等选用户界面、等开场彩色画面最多几秒
    load_timeout = 30.0
    boot_timeout = 60.0
    # 开场画面是彩色的：鲜艳的像素（饱和度、亮度都不低）至少占这么多
    colorful_lower: Hsv = (0, 100, 60)
    colorful_upper: Hsv = (180, 255, 255)
    colorful_ratio = 0.3


class CheckConfig:
    """启动时检查按键。"""

    # 按一下 HOME 后最多等几秒画面变化
    timeout = 10.0


class WaitConfig:
    """等画面。"""

    # 等画面变化和操作超时
    timeout = 60.0
    # 两次截图之间的间隔
    interval = 0.1
    # press_until 连续按键时两次按键之间的间隔。比游戏的反应快的话，画面还没变就又按了一次，会多按进下一个菜单
    press_interval = 0.3
    # 推一下摇杆保持多久，光标正好移一格
    stick_tick = 0.08


class BaseConfig:
    """和游戏无关的配置。"""

    # 仓库根目录
    root = Path(__file__).resolve().parents[2]
    # 这个脚本的日志和出错时的截图，每个脚本一个目录
    log_dir = root / "runs" / "logs"
    # 闪光的截图
    shiny_dir = root / "runs" / "shinys"

    def __init__(self) -> None:
        # 每个 config 各建一份，改一个 config 的值不会影响别的
        self.restart = RestartConfig()
        self.check = CheckConfig()
        self.wait = WaitConfig()

    @property
    def failed_dir(self) -> Path:
        """出错时存下的这一局的截图，清空日志时不删。"""
        return self.log_dir / "failed"
