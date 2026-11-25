"""和 make start 一样跑刷闪程序，只多一件事：每回合选招之前，把队伍和对手记录所在的那一小段内存存成文件。
只读内存，不写。文件在 battle_dump/ 里：<时分秒>_第几场_第几回合.bin，另有一份同名 .txt 记当时队伍内存里的血量。"""

import logging
import os
import sys
import time

sys.path.insert(0, "/Users/garnet/projects/control-switch/src")
os.chdir("/Users/garnet/projects/control-switch")
from dotenv import load_dotenv

load_dotenv("/Users/garnet/projects/control-switch/.env")
import importlib

import main

battle = importlib.import_module("swsh.lair.steps.battle")

OUT = os.path.dirname(os.path.abspath(__file__)) + "/battle_dump"
START, LENGTH, CHUNK = 0x88690000, 0x40000, 0x4000
turns = {}
last = [0]
original = battle._choose_move


def choose(sw, war):
    try:
        fight = sw.game.num_caught + 1
        if fight < last[0]:
            turns.clear()
        last[0] = fight
        turns[fight] = turns.get(fight, 0) + 1
        name = f"{OUT}/{time.strftime('%H%M%S')}_{fight}_{turns[fight]}"
        with open(name + ".bin", "wb") as f:
            f.writelines(sw.peek(START + offset, CHUNK) for offset in range(0, LENGTH, CHUNK))
        records = sw.pkhex.parse_pk8_batch(
            [sw.peek(a, 0x158) for a in (*sw.config.addresses.party, sw.config.addresses.opponent)]
        )
        with open(name + ".txt", "w") as f:
            f.writelines(
                f"{r['species']} 等级 {r['level']} 血量 {r['hp']}/{r['maxHp']} 个体值 {r['ivs']} 性格 {r['nature']} 校验 {r['checksumValid']}\n"
                for r in records
            )
        logging.info(f"存了战斗内存 {os.path.basename(name)}")
    except Exception:
        logging.exception("存战斗内存出错，不影响继续打")
    return original(sw, war)


battle._choose_move = choose
main.main("swsh/lair")
