"""一次运行的状态：配置、当前步骤、这一局的截图、通知，以及取图、按键、读写内存的设备。"""

import time
from collections.abc import Sequence
from typing import NamedTuple

from control_switch.config import BaseConfig
from control_switch.device import Controller, Devices, Memory, Screen
from control_switch.notifier import Notifier
from control_switch.settings import Settings
from control_switch.types import Picture, Press, Push, Rect


class Frame(NamedTuple):
    """记在内存里的一张截图。"""

    # 截图的时间（time.time()）
    time: float
    # 截图时在哪一步、在看什么
    step: str
    what: str
    # 截图：JPEG 字节，或者采集卡的 BGR 数组（存文件时才编码）
    data: Picture
    # 在这张图上检查过的区域（和 ImageChecker.rects 是同一个列表，检查时往里加），存图时画出来
    rects: Sequence[Rect] = ()


class Session:
    """步骤里用 sw 取：sw.config、sw.click(...)、sw.pixel_peek()、sw.memory.peek(...)。"""

    def __init__(
        self,
        config: BaseConfig,
        settings: Settings,
        devices: Devices,
    ):
        self.config = config
        # 这台机器在 runs/switches.toml 里的名字，日志目录和通知里用来区分是哪台
        self.switch = settings.switch
        # 现在是哪一步，入口的循环每一步之前写进来
        self.step = ""
        # 这一局截过的图，只放在内存里；出错时入口才把它们写进日志目录，新的一局开始时清空
        self.frames: list[Frame] = []
        # 往 Discord 推送消息，步骤里用 sw.notifier 取
        self.notifier = Notifier(webhook_url=settings.discord_webhook_url, name=settings.switch)
        self.screen = devices.screen
        self.controller = devices.controller
        self._memory = devices.memory

    @property
    def memory(self) -> Memory:
        """读写内存的设备。这个脚本没有配置时抛 RuntimeError。"""
        if self._memory is None:
            raise RuntimeError(
                "这个脚本要读写内存，runs/switches.toml 里这台机器的 memory 不能是 none"
            )
        return self._memory

    def click(self, button: str, delay: float = 0.15) -> None:
        self.controller.click(button, delay)

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        self.controller.stick(side, x, y, hold)

    def press(self, button: str) -> None:
        self.controller.press(button)

    def release(self, button: str) -> None:
        self.controller.release(button)

    def press_stick(self, side: str, x: int, y: int) -> None:
        self.controller.press_stick(side, x, y)

    def release_stick(self, side: str) -> None:
        self.controller.release_stick(side)

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

    def pixel_peek(self) -> Picture:
        return self.screen.pixel_peek()

    def close(self) -> None:
        """关闭设备：同一个对象只关一次，没有的跳过。"""
        closed: list[Screen | Controller | Memory] = []
        for device in (self.screen, self.controller, self._memory):
            if device is None or any(device is done for done in closed):
                continue
            closed.append(device)
            device.close()
