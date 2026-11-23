"""按配置创建设备：选了 botbase 的共用同一个 Botbase，只连接一次。"""

from typing import NamedTuple

from control_switch.settings import Settings

from .base import Controller, Memory, Screen
from .botbase import connect_botbase
from .check import DeviceCheckError


class Devices(NamedTuple):
    """取图、按键、读写内存的设备，memory 没有配置时是 None。"""

    screen: Screen
    controller: Controller
    memory: Memory | None


def create_devices(settings: Settings) -> Devices:
    """按 settings 创建设备。还没有实现的先全部检查完再抛 NotImplementedError，不去连接。"""
    unimplemented = [
        name
        for name, value, implemented in (
            ("SCREEN", settings.screen, "botbase"),
            ("CONTROLLER", settings.controller, "botbase"),
        )
        if value != implemented
    ]
    if unimplemented:
        raise NotImplementedError(
            f"{'、'.join(unimplemented)} 选的设备还没有实现，现在只能写 botbase"
        )
    try:
        botbase = connect_botbase(settings)
    except OSError as error:
        used = [
            label
            for label, value in (
                ("取图", settings.screen),
                ("按键", settings.controller),
                ("内存", settings.memory),
            )
            if value == "botbase"
        ]
        way = "USB" if settings.switch_connection == "usb" else "WiFi"
        raise DeviceCheckError(f"{'、'.join(used)}：botbase（{way}）连接失败：{error}") from error
    return Devices(botbase, botbase, None if settings.memory == "none" else botbase)
