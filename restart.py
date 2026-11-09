"""重启游戏：关掉再重新打开，一直到回到游戏里、可以操作为止，见 lib/game.py 的 restart。"""

from dotenv import load_dotenv

from lib import switch_v1 as switch
from lib.game import restart
from lib.log import init_log

if __name__ == "__main__":
    load_dotenv()
    init_log("restart")
    switch.connect()
    restart()
