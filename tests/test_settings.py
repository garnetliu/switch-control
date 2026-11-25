"""control_switch.settings：从 runs/switches.toml 读机器和脚本用哪台，从 .env 读 webhook 和 PKHeX 地址。

build_settings 直接传一台机器的配置；load_* 读 tmp_path 下写好的 toml 文件。
conftest 的 clean_settings_env 把 .env 和相关环境变量清掉了。
"""

from pathlib import Path

import pytest
import tomlkit

from control_switch.settings import (
    SettingsError,
    build_settings,
    load_script_settings,
    load_switch_settings,
    set_switch_ip,
    switch_mac,
    switches_file,
)

SWITCHES = """\
# 机器
[switch.living]
connection = "wifi"
mac = "aa:bb:cc:dd:ee:ff"
port = 6000

[switch.lite]
screen = "capture"
controller = "serial"
serial_port = "/dev/cu.usbserial-1"
memory = "none"

# 脚本用哪台
[scripts]
"swsh/lair" = "living"
"sv/egg" = "lite"
"""


@pytest.fixture
def switches(tmp_path: Path) -> Path:
    """tmp_path 下写好的 switches.toml：两台机器，两个脚本。"""
    path = tmp_path / "switches.toml"
    path.write_text(SWITCHES, encoding="utf-8")
    return path


# ---------- build_settings ----------


def test_empty_machine_gives_defaults() -> None:
    """空的机器配置：三项设备都是 botbase，connection 是 wifi，其余是默认值或 None。"""
    settings = build_settings({})
    assert settings.screen == "botbase"
    assert settings.controller == "botbase"
    assert settings.memory == "botbase"
    assert settings.switch_connection == "wifi"
    assert settings.switch_ip is None
    assert settings.switch_port is None
    assert settings.serial_port is None
    assert settings.serial_baud == 9600
    assert settings.capture_device == 0
    assert settings.pkhex_api_url is None
    assert settings.discord_webhook_url is None


def test_choice_value_is_case_insensitive() -> None:
    """screen = "Capture"：得到小写的 capture。"""
    assert build_settings({"screen": "Capture"}).screen == "capture"


@pytest.mark.parametrize(
    ("key", "value", "allowed"),
    [
        ("screen", "hdmi", ("botbase", "capture")),
        ("controller", "usb", ("botbase", "serial")),
        ("memory", "yes", ("botbase", "none")),
        ("connection", "bt", ("wifi", "usb")),
    ],
)
def test_unknown_choice_raises_naming_machine_key_and_allowed_values(
    key: str, value: str, allowed: tuple[str, ...]
) -> None:
    """可选值写错：抛 SettingsError，报错里有机器名、项名、写的值和可以写的值。"""
    with pytest.raises(SettingsError) as error:
        build_settings({key: value}, switch="living")
    message = str(error.value)
    assert "[switch.living]" in message
    assert key in message
    assert value in message
    for option in allowed:
        assert option in message


def test_unknown_key_raises_naming_it() -> None:
    """写了不认识的项（拼错的 contoller）：抛 SettingsError，报错里有这一项。"""
    with pytest.raises(SettingsError, match="contoller"):
        build_settings({"contoller": "serial"})


def test_integer_values_are_kept() -> None:
    """port、serial_baud、capture_device 写了整数：原样得到。"""
    settings = build_settings({"port": 6001, "serial_baud": 115200, "capture_device": 2})
    assert settings.switch_port == 6001
    assert settings.serial_baud == 115200
    assert settings.capture_device == 2


@pytest.mark.parametrize("key", ["port", "serial_baud", "capture_device"])
@pytest.mark.parametrize("value", ["6000", -1, True])
def test_invalid_integer_raises_naming_key(key: str, value: object) -> None:
    """整数项写成文字、负数或 true：抛 SettingsError，报错里有这一项。"""
    with pytest.raises(SettingsError, match=key):
        build_settings({key: value})


def test_text_values_are_kept_and_empty_is_none() -> None:
    """ip、serial_port 写了值：原样得到；写空字符串和没写一样是 None。"""
    settings = build_settings({"ip": "192.168.1.2", "serial_port": "/dev/cu.usbserial-1"})
    assert settings.switch_ip == "192.168.1.2"
    assert settings.serial_port == "/dev/cu.usbserial-1"
    assert build_settings({"ip": ""}).switch_ip is None


def test_text_value_that_is_not_string_raises() -> None:
    """ip 写成数字：抛 SettingsError，报错里有 ip。"""
    with pytest.raises(SettingsError, match="ip"):
        build_settings({"ip": 192})


# ---------- 读文件 ----------


def test_load_script_settings_uses_machine_of_script(switches: Path) -> None:
    """sv/egg 用 lite：得到 lite 的设备配置，switch 是 lite。"""
    settings = load_script_settings("sv/egg", switches)
    assert settings.switch == "lite"
    assert (settings.screen, settings.controller, settings.memory) == ("capture", "serial", "none")
    assert settings.serial_port == "/dev/cu.usbserial-1"


def test_load_script_settings_without_script_entry_raises_naming_script(switches: Path) -> None:
    """[scripts] 里没写 sv/outbreak：抛 SettingsError，报错里有这个脚本名。"""
    with pytest.raises(SettingsError, match="sv/outbreak"):
        load_script_settings("sv/outbreak", switches)


def test_load_script_settings_with_missing_machine_raises_listing_machines(tmp_path: Path) -> None:
    """脚本写的机器没有那一节：抛 SettingsError，报错里有这台机器和已经写了的机器。"""
    path = tmp_path / "switches.toml"
    path.write_text('[switch.living]\n\n[scripts]\n"sv/egg" = "lite"\n', encoding="utf-8")
    with pytest.raises(SettingsError) as error:
        load_script_settings("sv/egg", path)
    message = str(error.value)
    assert "[switch.lite]" in message
    assert "living" in message


def test_load_switch_settings_reads_machine_by_name(switches: Path) -> None:
    """按机器名读 living：connection 是 wifi，port 是 6000。"""
    settings = load_switch_settings("living", switches)
    assert settings.switch == "living"
    assert settings.switch_connection == "wifi"
    assert settings.switch_port == 6000


def test_missing_file_raises(tmp_path: Path) -> None:
    """文件不存在：抛 SettingsError。"""
    with pytest.raises(SettingsError):
        load_switch_settings("living", tmp_path / "switches.toml")


def test_broken_toml_raises(tmp_path: Path) -> None:
    """文件不是合法的 TOML：抛 SettingsError，报错里说格式不对。"""
    path = tmp_path / "switches.toml"
    path.write_text("[switch.living\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="格式不对"):
        load_switch_settings("living", path)


def test_webhook_and_pkhex_url_come_from_environment(
    switches: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DISCORD_WEBHOOK_URL、PKHEX_API_URL 从环境变量（.env）读。"""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://hook")
    monkeypatch.setenv("PKHEX_API_URL", "http://pkhex")
    settings = load_switch_settings("living", switches)
    assert settings.discord_webhook_url == "http://hook"
    assert settings.pkhex_api_url == "http://pkhex"


def test_switch_mac_reads_mac(switches: Path) -> None:
    """living 写了 mac：返回它；lite 没写：抛 SettingsError，报错里有 mac。"""
    assert switch_mac("living", switches) == "aa:bb:cc:dd:ee:ff"
    with pytest.raises(SettingsError, match="mac"):
        switch_mac("lite", switches)


def test_set_switch_ip_writes_ip_and_keeps_comments(switches: Path) -> None:
    """把 ip 写进 living：读回来是这个 ip，文件里的注释和别的机器不变。"""
    set_switch_ip("living", "192.168.1.50", switches)
    assert load_switch_settings("living", switches).switch_ip == "192.168.1.50"
    text = switches.read_text(encoding="utf-8")
    assert "# 机器" in text
    assert "# 脚本用哪台" in text
    assert load_switch_settings("lite", switches).serial_port == "/dev/cu.usbserial-1"


def test_set_switch_ip_for_unknown_machine_raises(switches: Path) -> None:
    """机器名没有那一节：抛 SettingsError。"""
    with pytest.raises(SettingsError):
        set_switch_ip("bedroom", "192.168.1.50", switches)


def test_repository_switches_file_is_valid_toml() -> None:
    """仓库里的 runs/switches.toml 是合法的 TOML（例子都注释掉了，读出来不报错）。"""
    tomlkit.parse(switches_file().read_text(encoding="utf-8"))
