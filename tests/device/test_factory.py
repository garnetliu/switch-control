"""control_switch.device.factory：按配置创建设备。

control_switch.device.factory.connect_botbase 换成返回假设备的函数，并记下被调了几次。
"""

from collections.abc import Callable
from typing import Any

import pytest
import usb.core

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


class Opens:
    """假的 open_serial_pad：记下被调的次数，每次都返回同一个假按键设备。可以设成调用时抛错。"""

    def __init__(self, pad: Any, error: Exception | None = None) -> None:
        self.pad = pad
        self.error = error
        self.calls = 0

    def __call__(self, settings: Any) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.pad


@pytest.fixture
def opens(monkeypatch: pytest.MonkeyPatch, controller: Any) -> Opens:
    """把 control_switch.device.factory.open_serial_pad 换成返回假按键设备的函数。"""
    fake = Opens(controller)
    monkeypatch.setattr("control_switch.device.factory.open_serial_pad", fake)
    return fake


def test_controller_serial_uses_pad_for_controller_and_botbase_for_the_rest(
    connects: Connects, opens: Opens
) -> None:
    """CONTROLLER=serial：controller 是 open_serial_pad 返回的对象，
    screen、memory 是 botbase 的同一个对象，botbase 只连一次。
    """
    devices = create_devices(load_settings({"CONTROLLER": "serial"}))
    assert opens.calls == 1
    assert devices.controller is opens.pad
    assert devices.screen is connects.botbase
    assert devices.memory is connects.botbase
    assert connects.calls == 1


def test_controller_serial_with_memory_none_gives_none_memory(
    connects: Connects, opens: Opens
) -> None:
    """CONTROLLER=serial 加 MEMORY=none：memory 是 None，controller 仍是单片机。"""
    devices = create_devices(load_settings({"CONTROLLER": "serial", "MEMORY": "none"}))
    assert devices.memory is None
    assert devices.controller is opens.pad
    assert devices.screen is connects.botbase


def test_screen_capture_with_controller_serial_raises_without_opening_or_connecting(
    connects: Connects, opens: Opens
) -> None:
    """SCREEN=capture 加 CONTROLLER=serial：抛 NotImplementedError，报错里有 SCREEN，
    open_serial_pad 和 connect_botbase 都没被调。
    """
    with pytest.raises(NotImplementedError) as error:
        create_devices(load_settings({"SCREEN": "capture", "CONTROLLER": "serial"}))
    assert "SCREEN" in str(error.value)
    assert opens.calls == 0
    assert connects.calls == 0


def test_open_serial_pad_device_check_error_is_raised_as_is_without_connecting(
    connects: Connects, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open_serial_pad 抛 DeviceCheckError：原样抛出（同一个对象），connect_botbase 没被调。"""
    original = DeviceCheckError("按键：串口 /dev/x 打不开")
    monkeypatch.setattr("control_switch.device.factory.open_serial_pad", Opens(None, original))
    with pytest.raises(DeviceCheckError) as error:
        create_devices(load_settings({"CONTROLLER": "serial"}))
    assert error.value is original
    assert connects.calls == 0


def test_botbase_failure_closes_opened_pad_once_and_raises_device_check_error(
    monkeypatch: pytest.MonkeyPatch, opens: Opens, controller: Any
) -> None:
    """connect_botbase 抛 ConnectionError：open_serial_pad 返回的设备被关了一次，
    抛的是 DeviceCheckError。
    """

    def refuse(settings: Any) -> Any:
        raise ConnectionError("连不上")

    monkeypatch.setattr("control_switch.device.factory.connect_botbase", refuse)
    with pytest.raises(DeviceCheckError):
        create_devices(load_settings({"CONTROLLER": "serial"}))
    assert controller.close_calls == 1


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


def test_botbase_value_error_still_closes_opened_pad(opens: Opens, controller: Any) -> None:
    """防止：CONTROLLER=serial、SWITCH_CONNECTION=wifi 但没写 SWITCH_IP 时，
    真的 connect_botbase 在建 socket 之前就抛 ValueError，已经打开的单片机没被关。

    约定：「连 botbase 失败时，先把已经打开的单片机关掉再抛错」，没有限定异常类型。
    这里不替换 connect_botbase，它在联网之前就抛错，不会真的去连。
    """
    settings = load_settings({"CONTROLLER": "serial", "SWITCH_CONNECTION": "wifi"})
    with pytest.raises(ValueError):
        create_devices(settings)
    assert opens.calls == 1
    assert controller.close_calls == 1


def test_botbase_no_usb_backend_still_closes_opened_pad(
    monkeypatch: pytest.MonkeyPatch, opens: Opens, controller: Any
) -> None:
    """防止：USB 连接没装 libusb 时 connect_botbase 抛 usb.core.NoBackendError
    （继承 ValueError，不是 OSError），已经打开的单片机没被关。
    """

    def no_backend(settings: Any) -> Any:
        raise usb.core.NoBackendError("No backend available")

    monkeypatch.setattr("control_switch.device.factory.connect_botbase", no_backend)
    with pytest.raises(ValueError):
        create_devices(load_settings({"CONTROLLER": "serial", "SWITCH_CONNECTION": "usb"}))
    assert controller.close_calls == 1


def test_botbase_failure_with_serial_names_only_screen_and_memory(
    monkeypatch: pytest.MonkeyPatch, opens: Opens
) -> None:
    """CONTROLLER=serial 时 botbase 连不上：报错开头是「取图、内存」，不含「按键」。"""

    def refuse(settings: Any) -> Any:
        raise ConnectionError("连不上")

    monkeypatch.setattr("control_switch.device.factory.connect_botbase", refuse)
    with pytest.raises(DeviceCheckError) as error:
        create_devices(load_settings({"CONTROLLER": "serial"}))
    assert str(error.value).startswith("取图、内存：")
