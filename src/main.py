"""新的入口：创建 switch，把连接传给每一步。"""

from dotenv import load_dotenv

from libs import Switch
from shiny_steps import initialize, join
from tools.log import init_log


def main() -> None:
    sw = Switch()
    init_log(sw, "start")
    steps = {"initialize": initialize, "join": join}
    step = "initialize"
    while step in steps:
        step = steps[step](sw)


if __name__ == "__main__":
    load_dotenv()
    main()
