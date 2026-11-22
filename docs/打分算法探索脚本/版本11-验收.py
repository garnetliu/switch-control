"""版本 11 的验收数字：基准图前 5 名、哞哞四张图的总分、日志里实际打过的局的 AUC 和相关。

队友一路上怎么变都从 seed 直接算（plan.fate）。
用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本11-验收.py [另外的日志文件...]
可以用 参数名=值 临时改参数看效果，比如 boss_hurt_scale=2.0 stage_weak_turns=1.5。
"""

import ast
import functools
import glob
import re
import statistics
import sys
from pathlib import Path

from swsh.lair import plan
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.lair.lair import Lair

# 每只首领那段时间开头第一次抽数的上限
TOP = {"mewtwo": 24, "tapu-bulu": 23}
BOSS_NAMES = {"超梦": "mewtwo", "卡璞・哞哞": "tapu-bulu"}
BENCHMARK = 3076008315599927110
BENCHMARK_BEST = ("pangoro", ("fraxure", "obstagoon", "sneasel"), (False, False, False))
# 哞哞的四张图：(seed, 实际的首发, 实际的路线)，实测从快到慢
BULU = [
    (9004205710319247536, "centiskorch", ("durant", "kadabra", "weezing")),
    (6986731677711377285, "heatmor", ("durant", "kadabra", "weezing")),
    (16753139388389203475, "relicanth", ("ninjask", "kadabra", "qwilfish")),
    (5938375612842167902, "gurdurr", ("sharpedo", "kadabra", "weezing")),
]


def config_of(boss: str, **params) -> GameConfig:
    config = GameConfig()
    config.lair_first_draw_top = TOP[boss]
    for name, value in params.items():
        setattr(config, name, value)
    return config


@functools.cache
def data_of(boss: str) -> GameData:
    return GameData(config_of(boss))


@functools.cache
def lair_of(boss: str, seed: int) -> Lair:
    return Lair(data_of(boss), seed)


def chinese(boss: str, name: str) -> str:
    return data_of(boss).pokemon_object(name).name("zh-Hans")


def collect(files: list[str]) -> list[dict]:
    """从日志里取出打完的每一局：首领、seed、首发、队友、路线、输赢、倒下次数、用时、每一场的队伍和回合数。"""
    games = []
    seen = set()
    for file in files:
        text = Path(file).read_text(encoding="utf-8", errors="replace")
        marks = list(re.finditer(r"(\d\d:\d\d:\d\d) \| INFO: 读取到的 seed 是 (\d+)", text))
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
            part = text[mark.start() : end]
            picks = re.findall(r"选中了第 \d 项「([^」]*)」", text[: mark.start()])
            boss = BOSS_NAMES.get(picks[-1] if picks else "超梦")
            seed = int(mark[2])
            report = re.search(
                r"第 \d+ 轮战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 \d/4\n路线：(.*)\n",
                part,
            )
            teams = list(re.finditer(r"队伍: (\[.*?\])，自己的 PP", part))
            if boss is None or (seed, mark[1]) in seen or not report or not teams:
                continue
            seen.add((seed, mark[1]))
            data = data_of(boss)
            names = [name for name, _ in ast.literal_eval(teams[0][1])]
            lair = lair_of(boss, seed)
            if names[0] not in lair.candidates()[:3]:
                continue
            encounters = lair.encounters()
            path = []
            for row, name in enumerate((x.strip() for x in report[4].split("→")), 1):
                cols = [
                    col
                    for col, opponent in enumerate(encounters[str(row)])
                    if data.pokemon_object(opponent).name("zh-Hans") == name
                ]
                if cols:
                    path.append((row, cols[0]))
            if len(path) != 3:
                continue
            fights = []
            for number, team in enumerate(teams):
                until = teams[number + 1].start() if number + 1 < len(teams) else len(part)
                piece = part[team.end() : until]
                members = ast.literal_eval(team[1])
                fights.append(
                    {
                        "team": [name for name, _ in members],
                        "hp": [hp for _, hp in members],
                        "turns": len(re.findall(r"INFO: 用第 \d 个招式", piece)),
                        "faints": len(re.findall(r"有一只倒下了", piece)),
                    }
                )
            games.append(
                {
                    "boss": boss,
                    "seed": seed,
                    "starter": names[0],
                    "mates": names[1:],
                    "path": tuple(path),
                    "opponents": tuple(encounters[str(row)][col] for row, col in path),
                    "win": report[1] == "胜",
                    "falls": int(report[2]),
                    "minutes": float(report[3]),
                    "fights": fights,
                }
            )
    return games


def auc(scores: list[float], wins: list[bool]) -> float:
    """随便挑一局赢的和一局输的，赢的那局分数更高的概率。"""
    won = [score for score, win in zip(scores, wins, strict=True) if win]
    lost = [score for score, win in zip(scores, wins, strict=True) if not win]
    if not won or not lost:
        return float("nan")
    return sum((a > b) + 0.5 * (a == b) for a in won for b in lost) / (len(won) * len(lost))


def fate_of(boss: str, seed: int, path: plan.Path):
    """返回 fate(换法)：三关按这种换法时队友会怎么变（11-20 起队友怎么变要看自己换没换）。"""
    lair = lair_of(boss, seed)
    events = data_of(boss).lair_events(lair.map_type(), lair.layout())
    return lambda swaps: plan.fate(lair, path, events, boss, swaps)


def all_plans(boss: str, seed: int, **params) -> list[tuple]:
    """这张图所有首发加路线：(总分, 三关, 首领, 首发, 对手, 换不换)，从高到低。"""
    planner = plan.Planner(data_of(boss), config_of(boss, **params), boss)
    lair = lair_of(boss, seed)
    encounters = lair.encounters()
    rows = []
    for starter, name in enumerate(lair.candidates()[:3]):
        for path in plan.paths(lair.map_type()):
            opponents = tuple(encounters[str(row)][col] for row, col in path)
            score = planner.score(
                name, lair.teammates(starter), opponents, fate_of(boss, seed, path)
            )
            rows.append((*score[:3], name, opponents, score[3]))
    return sorted(rows, key=lambda row: -row[0])


def describe(boss: str, row: tuple) -> str:
    total, stage, boss_score, starter, opponents, swaps = row
    route = " → ".join(chinese(boss, name) for name in opponents)
    marks = "".join("换" if swap else "不" for swap in swaps)
    return f"{total:.3f}（三关 {stage:.3f}，首领 {boss_score:.3f}）{chinese(boss, starter)}：{route}，{marks}"


def metrics(
    games: list[dict], use_fate: bool, **params
) -> dict[str, tuple[int, float, float, float]]:
    """每只首领：(局数, 总分对输赢的 AUC, 赢的局里总分和用时的相关, 总分和倒下次数的相关)。"""
    result = {}
    for boss in TOP:
        planner = plan.Planner(data_of(boss), config_of(boss, **params), boss)
        mine = [game for game in games if game["boss"] == boss]
        totals = [
            planner.score(
                game["starter"],
                game["mates"],
                game["opponents"],
                fate_of(boss, game["seed"], game["path"]) if use_fate else None,
            )[0]
            for game in mine
        ]
        won = [(total, game) for total, game in zip(totals, mine, strict=True) if game["win"]]
        result[boss] = (
            len(mine),
            auc(totals, [game["win"] for game in mine]),
            statistics.correlation([t for t, _ in won], [game["minutes"] for _, game in won]),
            statistics.correlation(totals, [game["falls"] for game in mine]),
        )
    return result


def main() -> None:
    params = {}
    files = sorted(glob.glob("logs/swsh-lair/start/*.log"))
    for argument in sys.argv[1:]:
        if "=" in argument:
            name, value = argument.split("=", 1)
            params[name] = ast.literal_eval(value)
        else:
            files.append(argument)
    games = collect(files)
    print(f"日志 {len(files)} 个，打完的 {len(games)} 局；临时改的参数 {params or '无'}")

    rows = all_plans("mewtwo", BENCHMARK, **params)
    right = (rows[0][3], rows[0][4], rows[0][5]) == BENCHMARK_BEST
    print(
        f"\n基准图 {BENCHMARK}：{'选对了' if right else '选错了'}，第 1 名比第 2 名高 {rows[0][0] / rows[1][0] - 1:.1%}"
    )
    for row in rows[:5]:
        print("  " + describe("mewtwo", row))

    print("\n哞哞四张图（实测从快到慢）")
    actual = []
    for seed, starter, opponents in BULU:
        rows = all_plans("tapu-bulu", seed, **params)
        mine = next(row for row in rows if row[3] == starter and row[4] == opponents)
        actual.append(mine[0])
        print(f"  {seed}")
        print("    算法选的：" + describe("tapu-bulu", rows[0]))
        print("    实际打的：" + describe("tapu-bulu", mine))
    # 9004 用算法选的（和实际打的一样），16753 用实际打的路线
    order = actual[0] > max(actual[1], actual[2]) and min(actual[1], actual[2]) > actual[3]
    print(
        f"  按实际打的方案，先后{'对' if order else '不对'}："
        + " / ".join(f"{x:.3f}" for x in actual)
    )

    for label, use_fate in (("带 fate", True), ("不带 fate", False)):
        print(f"\n日志里实际打过的局，{label}")
        for boss, (count, area, minutes, falls) in metrics(games, use_fate, **params).items():
            print(
                f"  {boss} {count} 局：对输赢的 AUC {area:.3f}，赢的局里和用时的相关 {minutes:+.2f}，"
                f"和倒下次数的相关 {falls:+.2f}"
            )


if __name__ == "__main__":
    main()
