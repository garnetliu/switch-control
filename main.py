import traceback

from dotenv import load_dotenv

from autostep.battle import battle
from autostep.catch import catch
from autostep.initialize import initialize
from autostep.join import join
from autostep.path import path
from autostep.select_pokemon import select_pokemon
from config.game import BOSS
from config.timing import STALL_NOTIFY_SECONDS
from lib import switch
from lib.debug_checker import set_step
from lib.game_state import GameState
from lib.log import init_log, last_log, log, log_path
from lib.notify import send, start_watchdog


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
    init_log("start", subdir=True)
    start_watchdog(STALL_NOTIFY_SECONDS)
    last_step = None
    try:
        switch.connect()
        game = GameState(BOSS)
        step = "initialize"
        while step is not None:
            if step == "join" and last_step == "select_pokemon":
                # 上一局结束，开新的一局：每局一个日志文件
                init_log("start", subdir=True, force=True)
            log(f"开始 {step}")
            set_step(step)
            last_step = step
            step = steps[step](game)
        _, reason = last_log()
        log("结束")
        send(f"程序结束，最后一步 {last_step}：{reason}")
    except KeyboardInterrupt:
        send(f"手动停止，最后一步 {last_step}")
        raise
    except Exception as error:
        _, reason = last_log()
        log(traceback.format_exc(), "ERROR")
        send(
            f"脚本出错：{type(error).__name__}: {error}\n"
            f"步骤：{last_step}\n最后日志：{reason}\n日志文件：{log_path()}"
        )
        raise


if __name__ == "__main__":
    load_dotenv()
    main()
