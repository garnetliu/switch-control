"""集中读配置：每台 Switch 用什么设备写在 runs/switches.toml，
Discord 通知的 webhook 和 PKHeX 服务的地址写在 .env。其他地方都用传进来的 Settings，不自己读文件和环境变量。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from dotenv import load_dotenv
from tomlkit.exceptions import TOMLKitError

from control_switch.config import BaseConfig


class SettingsError(ValueError):
    """runs/switches.toml 写错了：缺了要写的项、值不对、有不认识的项。"""


@dataclass(frozen=True)
class Settings:
    """一次运行用到的全部配置。机器各项的写法见 README「机器配置」。"""

    # 这台机器在 runs/switches.toml 里的名字
    switch: str
    # 画面、按键、内存各自用哪种设备
    screen: str
    controller: str
    memory: str
    # 连接 Switch：wifi 或 usb，wifi 要 ip 和端口
    switch_connection: str
    switch_ip: str | None
    switch_port: int | None
    # 单片机的串口路径和波特率，controller = "serial" 时用
    serial_port: str | None
    serial_baud: int
    # 采集卡在 OpenCV 里的序号，screen = "capture" 时用
    capture_device: int
    pkhex_api_url: str | None
    discord_webhook_url: str | None


def switches_file() -> Path:
    """runs/switches.toml 的位置。"""
    return BaseConfig.root / "runs" / "switches.toml"


def load_switch_settings(switch: str, path: Path | None = None) -> Settings:
    """按机器名读 [switch.名字]。"""
    path = path or switches_file()
    return _settings(_read(path), path, switch)


def switch_mac(switch: str, path: Path | None = None) -> str:
    """[switch.名字] 写的 mac，没写抛 SettingsError。"""
    path = path or switches_file()
    machine = _machine(_read(path), switch, path)
    mac = machine.get("mac")
    if not isinstance(mac, str) or not mac:
        raise SettingsError(f"{path.name} 的 [switch.{switch}] 要写 mac，Switch 的 MAC 地址")
    return mac


def set_switch_ip(switch: str, ip: str, path: Path | None = None) -> None:
    """把 ip 写进 [switch.名字]，文件里的注释和其他内容不变。"""
    path = path or switches_file()
    document = tomlkit.parse(path.read_text(encoding="utf-8"))
    machines: Any = document.get("switch")
    if machines is None or switch not in machines:
        raise SettingsError(f"{path.name} 里没有 [switch.{switch}]")
    machines[switch]["ip"] = ip
    path.write_text(tomlkit.dumps(document), encoding="utf-8")


def build_settings(
    machine: Mapping[str, Any],
    *,
    switch: str = "",
    pkhex_api_url: str | None = None,
    discord_webhook_url: str | None = None,
) -> Settings:
    """用一台机器的配置拼出 Settings，写错的项抛 SettingsError。switch 是机器的名字，用在报错里。"""
    machine_where = f"[switch.{switch}]"
    _check_keys(
        machine,
        {
            "connection",
            "mac",
            "ip",
            "port",
            "screen",
            "controller",
            "memory",
            "capture_device",
            "serial_port",
            "serial_baud",
        },
        machine_where,
    )
    serial_baud = _integer(machine, "serial_baud", machine_where)
    capture_device = _integer(machine, "capture_device", machine_where)
    return Settings(
        switch=switch,
        screen=_choice(machine, "screen", ("botbase", "capture"), machine_where),
        controller=_choice(machine, "controller", ("botbase", "serial"), machine_where),
        memory=_choice(machine, "memory", ("botbase", "none"), machine_where),
        switch_connection=_choice(machine, "connection", ("wifi", "usb"), machine_where),
        switch_ip=_text(machine, "ip", machine_where),
        switch_port=_integer(machine, "port", machine_where),
        serial_port=_text(machine, "serial_port", machine_where),
        serial_baud=9600 if serial_baud is None else serial_baud,
        capture_device=0 if capture_device is None else capture_device,
        pkhex_api_url=pkhex_api_url,
        discord_webhook_url=discord_webhook_url,
    )


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SettingsError(f"没有 {path}，照着仓库里的 runs/switches.toml 写好机器和脚本")
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except TOMLKitError as error:
        raise SettingsError(f"{path.name} 格式不对：{error}") from None


def _machine(document: Mapping[str, Any], switch: str, path: Path) -> Mapping[str, Any]:
    machines = document.get("switch", {})
    if switch not in machines:
        written = "、".join(machines) or "一个都没有"
        raise SettingsError(f"{path.name} 里没有 [switch.{switch}]，现在写了的机器有：{written}")
    return machines[switch]


def _settings(document: Mapping[str, Any], path: Path, switch: str) -> Settings:
    machine = _machine(document, switch, path)
    load_dotenv()
    return build_settings(
        machine,
        switch=switch,
        pkhex_api_url=os.environ.get("PKHEX_API_URL") or None,
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL") or None,
    )


def _check_keys(table: Mapping[str, Any], allowed: set[str], where: str) -> None:
    """写了不认识的项就报错，防止拼错名字的项被悄悄忽略。"""
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise SettingsError(
            f"{where} 里有不认识的项：{'、'.join(unknown)}，可以写 {'、'.join(sorted(allowed))}"
        )


def _choice(table: Mapping[str, Any], key: str, options: tuple[str, ...], where: str) -> str:
    """读一个有固定可选值的项，不分大小写，不写时是第一个。"""
    value = table.get(key, options[0])
    if not isinstance(value, str) or value.lower() not in options:
        raise SettingsError(f"{where} 的 {key} 写的是 {value!r}，可以写 {'、'.join(options)}")
    return value.lower()


def _text(table: Mapping[str, Any], key: str, where: str) -> str | None:
    value = table.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SettingsError(f"{where} 的 {key} 要写成带引号的文字，现在是 {value!r}")
    return value


def _integer(table: Mapping[str, Any], key: str, where: str) -> int | None:
    """读一个不小于 0 的整数，不写时是 None。"""
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SettingsError(f"{where} 的 {key} 要写不小于 0 的整数，现在是 {value!r}")
    return value
