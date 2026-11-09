
from typing import Literal, TypedDict


class GameConfig(TypedDict):
    boss: str


game_config = GameConfig(
    boss="solgaleo",
)