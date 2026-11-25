"""control_switch.settings：从环境变量读配置。

conftest 的 clean_settings_env 把 .env 和相关环境变量清掉了，这里传进去的字典就是全部配置。
"""

import pytest

from control_switch.settings import load_settings


def test_empty_env_gives_defaults() -> None:
    """空字典：三项设备都是 botbase，switch_connection 是 wifi，keep_path 是 False，其余是 None。"""
    settings = load_settings({})
    assert settings.screen == "botbase"
    assert settings.controller == "botbase"
    assert settings.memory == "botbase"
    assert settings.switch_connection == "wifi"
    assert settings.switch_ip is None
    assert settings.switch_port is None
    assert settings.pkhex_api_url is None
    assert settings.discord_webhook_url is None
    assert settings.keep_path is False


def test_screen_value_is_case_insensitive() -> None:
    """SCREEN=Capture：得到小写的 capture。"""
    assert load_settings({"SCREEN": "Capture"}).screen == "capture"


@pytest.mark.parametrize(
    ("name", "value", "allowed"),
    [
        ("SCREEN", "hdmi", ("botbase", "capture")),
        ("CONTROLLER", "usb", ("botbase", "serial")),
        ("MEMORY", "yes", ("botbase", "none")),
        ("SWITCH_CONNECTION", "bt", ("wifi", "usb")),
    ],
)
def test_unknown_choice_raises_value_error_naming_variable_and_allowed_values(
    name: str, value: str, allowed: tuple[str, ...]
) -> None:
    """SCREEN=hdmi、CONTROLLER=usb、MEMORY=yes、SWITCH_CONNECTION=bt：抛 ValueError，报错里有环境变量名、写的值和可以写的值。"""
    with pytest.raises(ValueError) as error:
        load_settings({name: value})
    message = str(error.value)
    assert name in message
    assert value in message
    for option in allowed:
        assert option in message


def test_switch_port_is_converted_to_int() -> None:
    """SWITCH_PORT=6000：得到整数 6000。"""
    port = load_settings({"SWITCH_PORT": "6000"}).switch_port
    assert port == 6000
    assert isinstance(port, int)


def test_non_numeric_switch_port_raises_value_error_naming_switch_port() -> None:
    """SWITCH_PORT=abc：抛 ValueError，报错里有 SWITCH_PORT。"""
    with pytest.raises(ValueError) as error:
        load_settings({"SWITCH_PORT": "abc"})
    assert "SWITCH_PORT" in str(error.value)


def test_keep_path_is_true_only_for_exactly_one() -> None:
    """KEEP_PATH=1：True。"""
    assert load_settings({"KEEP_PATH": "1"}).keep_path is True


@pytest.mark.parametrize("value", ["0", "true"])
def test_keep_path_other_than_one_is_false(value: str) -> None:
    """KEEP_PATH=0、KEEP_PATH=true：False。"""
    assert load_settings({"KEEP_PATH": value}).keep_path is False


def test_optional_string_values_are_passed_through() -> None:
    """SWITCH_IP、PKHEX_API_URL、DISCORD_WEBHOOK_URL 写了值：原样得到。"""
    settings = load_settings(
        {
            "SWITCH_IP": "192.168.1.2",
            "PKHEX_API_URL": "http://x",
            "DISCORD_WEBHOOK_URL": "http://hook",
        }
    )
    assert settings.switch_ip == "192.168.1.2"
    assert settings.pkhex_api_url == "http://x"
    assert settings.discord_webhook_url == "http://hook"


@pytest.mark.parametrize(
    "name",
    [
        "SCREEN",
        "CONTROLLER",
        "MEMORY",
        "SWITCH_CONNECTION",
        "SWITCH_IP",
        "SWITCH_PORT",
        "PKHEX_API_URL",
        "DISCORD_WEBHOOK_URL",
        "KEEP_PATH",
        "SERIAL_PORT",
        "SERIAL_BAUD",
        "CAPTURE_DEVICE",
    ],
)
def test_empty_string_is_same_as_not_set(name: str) -> None:
    """值是空字符串：和没写一样，得到的设置和空字典相同。"""
    assert load_settings({name: ""}) == load_settings({})


def test_serial_port_is_passed_through_unchanged() -> None:
    """SERIAL_PORT 写了路径：原样得到；不写是 None。"""
    assert load_settings({"SERIAL_PORT": "/dev/cu.usbserial-2021230"}).serial_port == (
        "/dev/cu.usbserial-2021230"
    )
    assert load_settings({}).serial_port is None


def test_serial_baud_defaults_to_9600() -> None:
    """SERIAL_BAUD 不写：得到整数 9600。"""
    assert load_settings({}).serial_baud == 9600


def test_serial_baud_is_converted_to_int() -> None:
    """SERIAL_BAUD=115200：得到整数 115200。"""
    baud = load_settings({"SERIAL_BAUD": "115200"}).serial_baud
    assert baud == 115200
    assert isinstance(baud, int)


def test_non_numeric_serial_baud_raises_value_error_naming_serial_baud() -> None:
    """SERIAL_BAUD=abc：抛 ValueError，报错里有 SERIAL_BAUD。"""
    with pytest.raises(ValueError) as error:
        load_settings({"SERIAL_BAUD": "abc"})
    assert "SERIAL_BAUD" in str(error.value)


def test_capture_device_defaults_to_0() -> None:
    """CAPTURE_DEVICE 不写：得到整数 0。"""
    assert load_settings({}).capture_device == 0


def test_capture_device_is_converted_to_int() -> None:
    """CAPTURE_DEVICE=2：得到整数 2。"""
    device = load_settings({"CAPTURE_DEVICE": "2"}).capture_device
    assert device == 2
    assert isinstance(device, int)


@pytest.mark.parametrize("text", ["abc", "-1"])
def test_invalid_capture_device_raises_value_error_naming_capture_device(text: str) -> None:
    """CAPTURE_DEVICE=abc（不是整数）或 -1（负数）：抛 ValueError，报错里有 CAPTURE_DEVICE。"""
    with pytest.raises(ValueError) as error:
        load_settings({"CAPTURE_DEVICE": text})
    assert "CAPTURE_DEVICE" in str(error.value)
