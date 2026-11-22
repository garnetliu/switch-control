"""一次运行的状态：配置、当前步骤、这一局的截图、通知，以及取图、按键、读写内存的设备。"""

from typing import NamedTuple

from control_switch.config import BaseConfig
from control_switch.device import Controller, Memory, Screen
from control_switch.notifier import Notifier


class Frame(NamedTuple):
    """记在内存里的一张截图。"""

    # 截图的时间（time.time()）
    time: float
    # 截图时在哪一步、在看什么
    step: str
    what: str
    # 截图的 JPEG 字节
    data: bytes


class Session:
    """步骤里用 sw 取：sw.config、sw.click(...)、sw.pixel_peek()、sw.memory.peek(...)。"""

    def __init__(
        self,
        config: BaseConfig,
        screen: Screen,
        controller: Controller,
        memory: Memory | None,
    ):
        self.config = config
        # 现在是哪一步，入口的循环每一步之前写进来
        self.step = ""
        # 这一局截过的图，只放在内存里；出错时入口才把它们写进日志目录，新的一局开始时清空
        self.frames: list[Frame] = []
        # 往 Discord 推送消息，步骤里用 sw.notifier 取
        self.notifier = Notifier()
        self.screen = screen
        self.controller = controller
        self._memory = memory

    @property
    def memory(self) -> Memory:
        """读写内存的设备。这个脚本没有配置时抛 RuntimeError。"""
        if self._memory is None:
            raise RuntimeError("这个脚本要读写内存，但没有配置内存设备")
        return self._memory

    def click(self, button: str, delay: float = 0.15) -> None:
        self.controller.click(button, delay)

    def stick(self, side: str, x: int, y: int, hold: float) -> None:
        self.controller.stick(side, x, y, hold)

    def pixel_peek(self) -> bytes:
        return self.screen.pixel_peek()

    def close(self) -> None:
        """关闭设备：同一个对象只关一次，没有的跳过。"""
        closed: list[Screen | Controller | Memory] = []
        for device in (self.screen, self.controller, self._memory):
            if device is None or any(device is done for done in closed):
                continue
            closed.append(device)
            device.close()
