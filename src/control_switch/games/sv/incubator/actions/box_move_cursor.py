import json
from collections import deque
from functools import cache
from importlib.resources import files

from control_switch.flow import capture, press_until

from .. import verify
from ..session import IncubatorSession
from ..types import Cursor


@cache
def _moves() -> dict[str, dict[str, dict]]:
    """盒子里光标的移动表（实测）：每个位置按上下左右各到哪里，切换盒子的那几条带 "box"。"""
    path = files("control_switch.games.sv") / "data" / "box_cursor_moves.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _key(cursor: Cursor) -> str:
    return f"{cursor[0]},{cursor[1]},{cursor[2]}"


def _route(start: Cursor, target: Cursor) -> list[tuple[str, str]]:
    """按移动表从 start 到 target 的最短路线：每一步是（按的键，按完应该到的位置）。不走会切换盒子的那几条。"""
    moves = _moves()
    goal = _key(target)
    queue: deque[tuple[str, list[tuple[str, str]]]] = deque([(_key(start), [])])
    seen = {_key(start)}
    while queue:
        node, route = queue.popleft()
        if node == goal:
            return route
        for button, edge in moves[node].items():
            nxt = edge["to"]
            if "box" in edge or nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, [*route, (button, nxt)]))
    raise RuntimeError(f"移动表里从 {start} 到不了 {target}")


def box_move_cursor(sw: IncubatorSession, place: str, row: int, col: int) -> None:
    """盒子画面里把光标移到队伍或盒子的某一格。place 是 "party" 或 "slots"。

    先按移动表算出最短路线，再一步一步按：每按一下都看光标动了没有，没动就再按。
    走到的位置和路线上的不一样（有几条去向会随光标之前的位置变），就从实际位置重新算路线。
    一共最多按光标能停的位置数那么多下，还没到抛 RuntimeError。
    """
    config = sw.config
    target: Cursor = (place, row, col)
    current = verify.box_cursor(capture(sw, "盒子的光标"), config)
    # 光标能停的位置：队伍、盒子格子、盒子名和「一览」「搜寻」
    max_presses = config.party_rows + config.box_rows * config.box_columns + 3
    presses = 0
    while current != target:
        for button, expected in _route(current, target):
            if presses >= max_presses:
                raise RuntimeError(
                    f"光标按了 {max_presses} 下，还是没到 {target}，现在在 {current}"
                )
            image = press_until(
                sw,
                lambda key=button: sw.click(key, 0),
                lambda s, last=current: verify.box_cursor(s, config) != last,
                "盒子的光标移一格",
            )
            presses += 1
            current = verify.box_cursor(image, config)
            if _key(current) != expected:
                break
