.PHONY: find start restart format lint

# 查找 Switch 的 ip 并写入 .env，再 ping 一下检查延迟。要用系统自带的 Python，uv 装的 Python 在 macOS 27 上读不到 ARP 表
find:
	/usr/bin/python3 src/tools/find_switch.py

# 要跑的脚本，写成「游戏/脚本」：swsh/lair 是剑盾的极巨大冒险，sv/outbreak 是朱紫的大量出现。
# 例如 make start script=sv/outbreak
script ?= swsh/lair

start:
	uv run python src/main.py $(script)

# 重启游戏，回到游戏里可以操作为止。极巨大冒险途中重启下次要付极矿石罚款
restart:
	uv run python src/restart.py $(script)

format:
	uv run ruff format .

lint:
	uv run ruff check .
