import os

from autostep.battle import battle
from autostep.catch import catch
from autostep.initialize import initialize
from autostep.join import join
from autostep.path import path
from autostep.select_pokemon import select_pokemon
from lib import switch
from lib.env import load_env
from lib.log import init_log, log


def main():
    """从 initialize 开始，按每一步返回的名字一步步跑下去，返回 None 就停下。

    开始时游戏要停在科学家面前、没有对话框。
    """
    steps = {
        "initialize": initialize,
        "join": join,
        "path": path,
        "battle": battle,
        "catch": catch,
        "select_pokemon": select_pokemon,
    }
    switch.connect(os.environ["SWITCH_IP"], int(os.environ["SWITCH_PORT"]))
    step = "initialize"
    while step is not None:
        log(f"开始 {step}")
        step = steps[step]()
    log("结束")


if __name__ == "__main__":
    load_env()
    init_log("start")
    main()
