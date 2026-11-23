"""control_switch.device.factory：按配置创建设备。

control_switch.device.factory.connect_botbase 换成返回假设备的函数，并记下被调了几次。
"""

from collections.abc import Callable
from typing import Any

import pytest

from control_switch.device import DeviceCheckError
from control_switch.device.factory import Devices, create_devices
from control_switch.settings import load_settings

MemoryFactory = Callable[..., Any]


class Connects:
    """假的 connect_botbase：记下被调的次数，每次都返回同一个假设备。"""

    def __init__(self, botbase: Any) -> None:
        self.botbase = botbase
        self.calls = 0

    def __call__(self, settings: Any) -> Any:
        self.calls += 1
        return self.botbase


@pytest.fixture
def connects(monkeypatch: pytest.MonkeyPatch, make_memory: MemoryFactory) -> Connects:
    """把 control_switch.device.factory.connect_botbase 换成假的。"""
    fake = Connects(make_memory())
    monkeypatch.setattr("control_switch.device.factory.connect_botbase", fake)
    return fake


def test_all_botbase_connects_once_and_shares_one_object(connects: Connects) -> None:
    """三项都是 botbase：只连接一次，screen、controller、memory 是同一个对象。"""
    devices = create_devices(load_settings({}))
    assert isinstance(devices, Devices)
    assert connects.calls == 1
    assert devices.screen is connects.botbase
    assert devices.controller is connects.botbase
    assert devices.memory is connects.botbase


def test_memory_none_gives_none_memory_and_shares_the_other_two(connects: Connects) -> None:
    """MEMORY=none：memory 是 None，screen 和 controller 是同一个对象，只连接一次。"""
    devices = create_devices(load_settings({"MEMORY": "none"}))
    assert devices.memory is None
    assert devices.screen is connects.botbase
    assert devices.controller is devices.screen
    assert connects.calls == 1


def test_screen_capture_raises_not_implemented_without_connecting(connects: Connects) -> None:
    """SCREEN=capture：抛 NotImplementedError，报错里有 SCREEN，连接函数没有被调。"""
    with pytest.raises(NotImplementedError) as error:
        create_devices(load_settings({"SCREEN": "capture"}))
    assert "SCREEN" in str(error.value)
    assert connects.calls == 0


def test_controller_serial_raises_not_implemented_without_connecting(connects: Connects) -> None:
    """CONTROLLER=serial：抛 NotImplementedError，报错里有 CONTROLLER，连接函数没有被调。"""
    with pytest.raises(NotImplementedError) as error:
        create_devices(load_settings({"CONTROLLER": "serial"}))
    assert "CONTROLLER" in str(error.value)
    assert connects.calls == 0


@pytest.mark.parametrize(("connection", "label"), [("usb", "USB"), ("wifi", "WiFi")])
def test_connect_failure_raises_device_check_error_naming_botbase_and_connection(
    monkeypatch: pytest.MonkeyPatch, connection: str, label: str
) -> None:
    """connect_botbase 抛 ConnectionError：create_devices 抛 DeviceCheckError，
    报错里有 botbase 和连接方式（USB 或 WiFi）。
    """

    def refuse(settings: Any) -> Any:
        raise ConnectionError("连不上")

    monkeypatch.setattr("control_switch.device.factory.connect_botbase", refuse)
    with pytest.raises(DeviceCheckError) as error:
        create_devices(load_settings({"SWITCH_CONNECTION": connection}))
    message = str(error.value)
    assert "botbase" in message
    assert label in message
