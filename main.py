import os

from lib import switch
from lib.env import load_env


def main():
    switch.connect(os.environ["SWITCH_IP"], int(os.environ["SWITCH_PORT"]))
    pass


if __name__ == "__main__":
    load_env()
    main()
