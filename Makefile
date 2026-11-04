.PHONY: find start format lint

# 查找 Switch 的 ip 并写入 .env。要用系统自带的 Python，uv 装的 Python 在 macOS 27 上读不到 ARP 表
find:
	/usr/bin/python3 tool/find_switch.py

start:
	uv run python main.py

format:
	uv run ruff format .

lint:
	uv run ruff check .
