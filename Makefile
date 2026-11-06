.PHONY: find start restart format lint

# 查找 Switch 的 ip 并写入 .env，再 ping 一下检查延迟。要用系统自带的 Python，uv 装的 Python 在 macOS 27 上读不到 ARP 表
find:
	/usr/bin/python3 tool/find_switch.py

start:
	uv run python main.py

# 重启游戏，回到游戏里可以操作为止。冒险途中重启下次要付极矿石罚款
restart:
	uv run python restart.py

format:
	uv run ruff format .

lint:
	uv run ruff check .
