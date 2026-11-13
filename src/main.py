"""入口：python src/main.py <游戏/脚本>。按名字找到脚本，创建连接，一步一步跑。"""

import logging
import sys

from dotenv import load_dotenv

from scripts import load_script
from tools import save_frames
from tools.log import init_log


def main(name: str) -> None:
    script = load_script(name)
    sw = script.connect()
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


if __name__ == "__main__":
    load_dotenv()
    main(sys.argv[1] if len(sys.argv) > 1 else "swsh/lair")
