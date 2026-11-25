"""命令行入口：control-switch run <游戏/脚本>、restart <机器>、find <机器>。

run 按名字找到脚本，按 runs/switches.toml 找到它用的机器，创建连接，一步一步跑。
restart 重启这台机器上的游戏，回到游戏里可以操作为止，极巨大冒险途中重启下次要付极矿石罚款。
find 按这台机器的 mac 在局域网里找 ip，写回 runs/switches.toml。
"""

import logging
import subprocess
import sys
from collections.abc import Callable
from typing import TypeVar

from control_switch.config import BaseConfig
from control_switch.device import (
    DeviceCheckError,
    Devices,
    check_devices,
    check_requires,
    create_devices,
)
from control_switch.flow import restart, save_frames
from control_switch.flow.check import check_controller_reaches_screen
from control_switch.games.registry import load_script
from control_switch.log import init_console, init_log
from control_switch.session import Session
from control_switch.settings import (
    Settings,
    SettingsError,
    load_script_settings,
    load_switch_settings,
    set_switch_ip,
    switch_mac,
)

T = TypeVar("T")


def _load_settings(load: Callable[[], T]) -> T:
    """读 runs/switches.toml，写错时打印报错退出。"""
    try:
        return load()
    except SettingsError as error:
        sys.exit(str(error))


def _create_devices(settings: Settings) -> Devices:
    """创建设备，连不上或配置不对时打印报错退出，不打印 traceback。"""
    try:
        return create_devices(settings)
    except (DeviceCheckError, ValueError, NotImplementedError) as error:
        sys.exit(str(error))


def _check(action: Callable[[], None]) -> None:
    """跑一项启动检查，没通过时打印报错退出。"""
    try:
        action()
    except DeviceCheckError as error:
        sys.exit(str(error))


def run(name: str) -> None:
    """跑脚本：从脚本的起点开始一步一步跑，每一步返回下一步的名字。"""
    init_console()
    script = load_script(name)
    settings = _load_settings(lambda: load_script_settings(name))
    _check(lambda: check_requires(settings, script.REQUIRES))
    devices = _create_devices(settings)
    _check(lambda: check_devices(devices, script.REQUIRES, script.TITLE_IDS))
    sw = script.SESSION(settings, devices)
    init_log(sw, "start")
    _check(lambda: check_controller_reaches_screen(sw))
    step = script.START
    try:
        while step in script.STEPS:
            # 记下现在是哪一步，截图时会带上
            sw.step = step
            step = script.STEPS[step](sw)
    except Exception as error:
        logging.exception(f"程序出错，步骤 {step}")
        # 截图平时只在内存里，出错了才把这一局的都写进日志目录，最后一张跟着通知一起发
        paths = save_frames(sw)
        sw.notifier.send(
            f"程序出错：{type(error).__name__}: {error}\n步骤：{step}", files=paths[-1:]
        )
        raise


def restart_game(switch: str) -> None:
    """重启这台机器上的游戏，回到游戏里可以操作为止。只用取图和按键，不看是哪个游戏。"""
    init_console()
    settings = _load_settings(lambda: load_switch_settings(switch))
    requires = frozenset({"screen", "controller"})
    devices = _create_devices(settings)
    # 重启时游戏可能已经崩了，不检查游戏
    _check(lambda: check_devices(devices, requires, None))
    sw = Session(BaseConfig(), settings, devices)
    init_log(sw, "restart")
    try:
        restart(sw)
    finally:
        sw.close()


def find(switch: str) -> None:
    """按这台机器的 mac 在局域网里找 ip，写回 runs/switches.toml 这台的 ip。

    macOS 上只有系统自带的 /usr/bin/python3 读得到 ARP 表，扫网络交给 scripts/find_switch.py，
    它找到后把 ip 打印到标准输出。
    """
    mac = _load_settings(lambda: switch_mac(switch))
    script = BaseConfig.root / "scripts" / "find_switch.py"
    result = subprocess.run(
        ["/usr/bin/python3", str(script), mac], stdout=subprocess.PIPE, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(result.returncode)
    ip = result.stdout.strip()
    set_switch_ip(switch, ip)
    print(f"已写入 runs/switches.toml 的 [switch.{switch}]：ip = {ip}")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    commands = {"run": run, "restart": restart_game, "find": find}
    if len(args) != 2 or args[0] not in commands:
        print(
            "用法：control-switch run 游戏/脚本 | restart 机器 | find 机器\n"
            "例如 control-switch run sv/egg、control-switch restart living，"
            "机器是 runs/switches.toml 里 [switch.名字] 的名字"
        )
        raise SystemExit(2)
    commands[args[0]](args[1])


if __name__ == "__main__":
    main()
