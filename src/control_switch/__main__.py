"""命令行入口：control-switch run <游戏/脚本>、control-switch restart <游戏/脚本>。

run 按名字找到脚本，创建连接，一步一步跑。
restart 重启游戏，回到游戏里可以操作为止，极巨大冒险途中重启下次要付极矿石罚款。
脚本名不写时是 swsh/lair。
"""

import logging
import sys

from control_switch.device import create_devices
from control_switch.flow import restart, save_frames
from control_switch.games.registry import load_script
from control_switch.log import init_log
from control_switch.settings import load_settings

DEFAULT_SCRIPT = "swsh/lair"
USAGE = "用法：control-switch run|restart [游戏/脚本]，脚本不写时是 swsh/lair"


def run(name: str) -> None:
    """跑脚本：从脚本的起点开始一步一步跑，每一步返回下一步的名字。"""
    script = load_script(name)
    settings = load_settings()
    devices = create_devices(settings)
    sw = script.SESSION(settings, devices)
    init_log(sw, "start")
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


def restart_game(name: str) -> None:
    """重启游戏，回到游戏里可以操作为止。"""
    script = load_script(name)
    settings = load_settings()
    devices = create_devices(settings)
    sw = script.SESSION(settings, devices)
    init_log(sw, "restart")
    try:
        restart(sw)
    finally:
        sw.close()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    commands = {"run": run, "restart": restart_game}
    if not args or args[0] not in commands:
        print(USAGE)
        raise SystemExit(2)
    commands[args[0]](args[1] if len(args) > 1 else DEFAULT_SCRIPT)


if __name__ == "__main__":
    main()
