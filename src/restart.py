"""重启游戏，回到游戏里可以操作为止：python src/restart.py <游戏/脚本>。

极巨大冒险途中重启下次要付极矿石罚款。
"""

import sys

from dotenv import load_dotenv

from scripts import load_script
from tools import restart
from tools.log import init_log


def main(name: str) -> None:
    sw = load_script(name).connect()
    init_log(sw, "restart")
    try:
        restart(sw)
    finally:
        sw.close()


if __name__ == "__main__":
    load_dotenv()
    main(sys.argv[1] if len(sys.argv) > 1 else "swsh/lair")
