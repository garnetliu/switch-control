"""新的入口：创建 switch，把连接传给每一步。"""

import logging

from dotenv import load_dotenv

from libs import Switch
from shiny_steps import battle, catch, initialize, join, path, select_pokemon
from tools.log import init_log


def main() -> None:
    sw = Switch()
    init_log(sw, "start")
    steps = {
        "initialize": initialize,
        "join": join,
        "path": path,
        "battle": battle,
        "catch": catch,
        "select_pokemon": select_pokemon,
    }
    step = "initialize"
    try:
        while step in steps:
            step = steps[step](sw)
    except Exception as error:
        logging.exception(f"程序出错，步骤 {step}")
        sw.notifier.send(f"程序出错：{type(error).__name__}: {error}\n步骤：{step}")
        raise


if __name__ == "__main__":
    load_dotenv()
    main()
