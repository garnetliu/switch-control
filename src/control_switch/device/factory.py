"""按配置创建设备：选了 botbase 的共用同一个 Botbase，只连接一次。"""

from typing import NamedTuple

from control_switch.settings import Settings

from .base import Controller, Memory, Screen
from .botbase import Botbase, connect_botbase
from .capture_card import open_capture_card
from .check import DeviceCheckError
from .serial_pad import open_serial_pad


class Devices(NamedTuple):
    """取图、按键、读写内存的设备，memory 没有配置时是 None。"""

    screen: Screen
    controller: Controller
    memory: Memory | None


def create_devices(settings: Settings) -> Devices:
    """按 settings 创建设备。

    打开顺序：采集卡、单片机、botbase；后面的失败时先把前面已经打开的关掉再抛错。
    取图、按键、内存都不用 botbase 时不连 botbase。
    """
    opened: list[Screen | Controller] = []
    try:
        screen = open_capture_card(settings) if settings.screen == "capture" else None
        if screen is not None:
            opened.append(screen)
        controller = open_serial_pad(settings) if settings.controller == "serial" else None
        if controller is not None:
            opened.append(controller)
        used = [
            label
            for label, value in (
                ("取图", settings.screen),
                ("按键", settings.controller),
                ("内存", settings.memory),
            )
            if value == "botbase"
        ]
        botbase = _connect_if_used(settings, used)
    except BaseException:
        for device in opened:
            device.close()
        raise
    return Devices(
        screen or _required(botbase),
        controller or _required(botbase),
        None if settings.memory == "none" else _required(botbase),
    )


def _required(botbase: Botbase | None) -> Botbase:
    assert botbase is not None
    return botbase


def _connect_if_used(settings: Settings, used: list[str]) -> Botbase | None:
    if not used:
        return None
    try:
        return connect_botbase(settings)
    except OSError as error:
        way = "USB" if settings.switch_connection == "usb" else "WiFi"
        raise DeviceCheckError(f"{'、'.join(used)}：botbase（{way}）连接失败：{error}") from error
