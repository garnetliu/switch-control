.PHONY: find start restart view format lint test typecheck coverage

# 机器的名字是 runs/switches.toml 里 [switch.名字] 的名字。

# 按这台机器的 mac 找它的 ip，写回 runs/switches.toml，再 ping 一下检查延迟。例如 make find switch=living
find:
	uv run control-switch find $(switch)

# 跑脚本，写成「游戏/脚本」：swsh/lair 是剑盾的极巨大冒险，sv/outbreak 是朱紫的大量出现，sv/egg 是朱紫孵蛋。
# 跑在哪台机器上看 runs/switches.toml 的 [scripts]，也可以用 switch 指定。
# 例如 make start script=sv/egg、make start script=sv/egg switch=living
start:
	uv run control-switch run $(script) $(switch)

# 重启这台机器上的游戏，回到游戏里可以操作为止。极巨大冒险途中重启下次要付极矿石罚款。例如 make restart switch=living
restart:
	uv run control-switch restart $(switch)

# 开一个窗口实时显示采集卡的画面，在窗口里按 q 关掉
view:
	uv run python scripts/view_capture.py

format:
	uv run ruff format .

lint:
	uv run ruff check .

test:
	uv run pytest

typecheck:
	uv run pyright

coverage:
	uv run pytest --cov=control_switch --cov-report=term-missing
