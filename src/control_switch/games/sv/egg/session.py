"""孵蛋刷闪用的 Session：带着孵蛋过程中的状态。"""

import time
from collections.abc import Sequence

from control_switch.device import Devices
from control_switch.session import Session
from control_switch.settings import Settings

from .config import EggConfig, Press, Push


class EggSession(Session):
    """步骤里用 sw.config、sw.parent_best 等取。"""

    config: EggConfig

    def __init__(self, settings: Settings, devices: Devices):
        super().__init__(EggConfig(), settings, devices)
        # 亲代是野餐队伍的第几只（从 0 数）、名字、「最棒」的项数，initialize 读出来
        self.parent_index = 0
        self.parent_name = ""
        self.parent_best = 0
        # 游戏里的评定功能解锁了没有：没解锁读不到「最棒」的项数，不换亲代
        self.judge_unlocked = False
        # 放蛋的盒子编号：第一次打开盒子时读出开着的是哪个，放蛋的是它后面那个
        self.egg_box: int | None = None
        # 队伍里要孵的蛋数，换成孵蛋队伍时数出来
        self.eggs_in_party = 0
        # 这一盒有没有留下过东西（闪光、换下来的旧亲代）：没留下就重启游戏回档，留下了要放生整盒再存档
        self.kept_in_box = False
        # 留下东西之后还没存档
        self.save_pending = False
        # 开了几次野餐，写日志用
        self.picnics = 0

    def push(self, side: str, x: float, y: float, seconds: float) -> None:
        """摇杆推 seconds 秒再回中。x、y 是占满推的比例，-1 到 1，y 正数向上。"""
        full = self.controller.STICK_MAX
        self.stick(side, round(full * x), round(full * y), seconds)

    def follow(self, route: Sequence[Push | Press]) -> None:
        """按路线走：Push 是左摇杆推一下，Press 是按一下键，每一步之后等 wait 秒。"""
        for step in route:
            if isinstance(step, Push):
                self.push("LEFT", step.x, step.y, step.seconds)
                time.sleep(step.wait)
            else:
                self.click(step.button, step.wait)
