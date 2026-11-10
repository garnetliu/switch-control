"""重启游戏，回到游戏里可以操作为止。冒险途中重启下次要付极矿石罚款。"""

from dotenv import load_dotenv

from libs import Switch
from tools import restart
from tools.log import init_log


def main() -> None:
    sw = Switch()
    init_log(sw, "restart")
    try:
        restart(sw)
    finally:
        sw.close()


if __name__ == "__main__":
    load_dotenv()
    main()
