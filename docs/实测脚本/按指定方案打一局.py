"""把 seed 写进内存，按指定的首发、路线、三关换法、研究员换法打一局，打完回到大厅就停。

用法：uv run python docs/实测脚本/按指定方案打一局.py
方案写在下面的 PLAN 里；PLAN 里没写 path 的，首发和路线用程序自己选的，只强制每一关的选法（swaps）。
2026-11-21：克雷色利亚 seed 16238065963362826354（新算法第 1 名）；
2026-11-22：seed 31727804189680776 第 1 关强制不抓，看队友会不会照样拿走（后面没有研究员）。其它和 make start 一样。
"""

import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

import swsh.lair as LAIR  # noqa: E402
from swsh.lair import upstream  # noqa: E402
from swsh.lair.plan import Plan  # noqa: E402
import importlib  # noqa: E402

# steps 包里同名的函数会盖住模块，要按模块名取
CATCH = importlib.import_module("swsh.lair.steps.catch")
JOIN = importlib.import_module("swsh.lair.steps.join")

TARGET = 31727804189680776
PLAN = {
    # 每一关：True 换、False 不换（2026-11-22 测不抓时第 1 关是 None，不抓的代码已经去掉）
    "swaps": (False, False, False),
}
state = {"written": False, "played": 0}


def active(sw) -> bool:
    return sw.game.seed == TARGET


_plan = JOIN._upstream_plan


def upstream_plan(sw, lair, map_type, layout, starters):
    plan = _plan(sw, lair, map_type, layout, starters)
    if not active(sw) or "path" not in PLAN:
        return plan
    if list(sw.game.candidates[:3]) != PLAN["candidates"] or map_type != "2x2":
        logging.warning(f"测试：候选 {sw.game.candidates} 或地图 {map_type} 和方案对不上，按程序自己选的打")
        return plan
    logging.info(f"测试：按新算法的方案打（分 {PLAN['score']}），下面日志里的首发分、路线分是程序自己那套的")
    return Plan(
        PLAN["starter"],
        PLAN["path"],
        PLAN["opponents"],
        tuple(lair.teammates(PLAN["starter"])),
        plan.total,
        plan.stage,
        0.0,
        PLAN["swaps"],
    )


JOIN._upstream_plan = upstream_plan

_decide = CATCH._decide


def decide(sw):
    """方案里每一关是 True（换）或 False（不换）。决定在抓之前，num_caught 就是第几关（从 0 数）。"""
    if active(sw) and sw.game.num_caught < 3:
        take = PLAN["swaps"][sw.game.num_caught]
        logging.info(f"测试：按方案，第 {sw.game.num_caught + 1} 关{'换' if take else '不换'}")
        sw.game.choices.append(take)
        return take
    return _decide(sw)


CATCH._decide = decide

_decide_scientist = upstream.decide_scientist
current = {"sw": None}


def decide_scientist(scorer, walker):
    sw = current["sw"]
    if sw is not None and active(sw) and "scientist" in PLAN:
        logging.info(f"测试：按方案，研究员{'换' if PLAN['scientist'] else '不换'}")
        return PLAN["scientist"]
    return _decide_scientist(scorer, walker)


upstream.decide_scientist = decide_scientist

_initialize = LAIR.STEPS["initialize"]


def initialize(sw):
    current["sw"] = sw
    if state["written"]:
        logging.info("测试：这一局打完了，停下")
        return "stop"
    address = sw.config.addresses.seed
    sw._send(f"poke {address:#x} 0x{TARGET.to_bytes(8, 'little').hex()}")
    now = int.from_bytes(sw.peek(address, 8), "little")
    logging.info(f"测试：seed 写成 {now}（{'一致' if now == TARGET else '不一致'}）")
    if now != TARGET:
        return "stop"
    state["written"] = True
    return _initialize(sw)


LAIR.STEPS["initialize"] = initialize

import main  # noqa: E402

main.main("swsh/lair")
