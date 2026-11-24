"""集中读配置：环境变量只在这里读，其他地方用传进来的 Settings。

先读仓库根目录的 .env（不覆盖已经有的环境变量），再读环境变量。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

from control_switch.config import ROOT

SCREENS = ("botbase", "capture")
CONTROLLERS = ("botbase", "serial")
MEMORIES = ("botbase", "none")
CONNECTIONS = ("wifi", "usb")


@dataclass(frozen=True)
class Settings:
    """一次运行用到的全部配置，字段对应的环境变量见 load_settings。"""

    # 画面、按键、内存各自用哪种设备
    screen: str
    controller: str
    memory: str
    # 连接 Switch：wifi 或 usb，wifi 要 ip 和端口
    switch_connection: str
    switch_ip: str | None
    switch_port: int | None
    # 单片机的串口路径和波特率，CONTROLLER=serial 时用
    serial_port: str | None
    serial_baud: int
    # 采集卡在 OpenCV 里的序号，SCREEN=capture 时用
    capture_device: int
    pkhex_api_url: str | None
    discord_webhook_url: str | None
    keep_path: bool


def _choice(env: Mapping[str, str], name: str, options: tuple[str, ...]) -> str:
    """读一个有固定可选值的变量，不分大小写，不写时是第一个。"""
    value = env.get(name) or options[0]
    value = value.lower()
    if value not in options:
        raise ValueError(f"{name} 写的是 {value}，可以写 {'、'.join(options)}")
    return value


def _port(env: Mapping[str, str]) -> int | None:
    text = env.get("SWITCH_PORT")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"SWITCH_PORT 要写整数，现在是 {text}") from None


def _baud(env: Mapping[str, str]) -> int:
    text = env.get("SERIAL_BAUD")
    if not text:
        return 9600
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"SERIAL_BAUD 要写整数，现在是 {text}") from None


def _capture_device(env: Mapping[str, str]) -> int:
    text = env.get("CAPTURE_DEVICE")
    if not text:
        return 0
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"CAPTURE_DEVICE 要写不小于 0 的整数，现在是 {text}") from None
    if value < 0:
        raise ValueError(f"CAPTURE_DEVICE 要写不小于 0 的整数，现在是 {text}")
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """读配置。env 不传时读 .env 和 os.environ；传了只读传进来的字典。空字符串当作没写。"""
    if env is None:
        load_dotenv(ROOT / ".env")
        env = os.environ
    return Settings(
        screen=_choice(env, "SCREEN", SCREENS),
        controller=_choice(env, "CONTROLLER", CONTROLLERS),
        memory=_choice(env, "MEMORY", MEMORIES),
        switch_connection=_choice(env, "SWITCH_CONNECTION", CONNECTIONS),
        switch_ip=env.get("SWITCH_IP") or None,
        switch_port=_port(env),
        serial_port=env.get("SERIAL_PORT") or None,
        serial_baud=_baud(env),
        capture_device=_capture_device(env),
        pkhex_api_url=env.get("PKHEX_API_URL") or None,
        discord_webhook_url=env.get("DISCORD_WEBHOOK_URL") or None,
        keep_path=env.get("KEEP_PATH") == "1",
    )
