"""一场对战里的场上状态：天气、场地，加上自己、队友、对手和极巨化。"""

from dataclasses import dataclass, field, replace

from swsh.field import Field
from swsh.pokemon import Pokemon
from swsh.scoring import select_best_move, transform_ditto


@dataclass(kw_only=True)
class War(Field):
    """一场对战的场上状态。天气、场地继承自 Field，打分函数照常把它当 Field 用。"""

    own: Pokemon
    opponent: Pokemon
    teammates: list[Pokemon] = field(default_factory=list)
    # 极巨化还剩几回合：-1 这场还没极巨化，0 这场已经极巨化过了
    dynamax_turns: int = -1
    # 这一场倒下了几次（看到一次风暴算一次），打完写进 game.faints
    faints: int = 0

    def __post_init__(self) -> None:
        # 极巨大冒险里的百变怪有变身者特性，一上场就变成对方
        if self.own.name_id == "ditto":
            self.own = transform_ditto(self.own, self.opponent)
        elif self.opponent.name_id == "ditto":
            self.opponent = transform_ditto(self.opponent, self.own)

    def start_turn(self) -> None:
        """新的一回合：极巨化持续 3 回合，最后一回合用完就结束。"""
        if self.dynamax_turns == 1:
            self.dynamax_turns = 0
            self.own.dynamax = False
        elif self.dynamax_turns > 1:
            self.dynamax_turns -= 1

    def best_move(self, can_dynamax: bool) -> tuple[int, float, bool]:
        """这回合用哪个招式：返回招式序号、分数、要不要极巨化。

        can_dynamax 是画面上有没有极巨化按钮；这场已经极巨化过就不再考虑。
        """
        best, _, score = select_best_move(self.own, self.opponent, self, self.teammates)
        if can_dynamax and self.dynamax_turns == -1:
            dynamax_best, _, dynamax_score = select_best_move(
                replace(self.own, dynamax=True), self.opponent, self, self.teammates
            )
            if dynamax_score > score:
                return dynamax_best, dynamax_score, True
        return best, score, False

    def dynamax(self) -> None:
        """自己极巨化了。"""
        self.own.dynamax = True
        self.dynamax_turns = 3

    def faint(self) -> None:
        """自己倒下了，极巨化也结束。"""
        if self.own.dynamax:
            self.own.dynamax = False
            self.dynamax_turns = 0

    def use_move(self, index: int) -> None:
        """用了第 index 个招式，扣 PP。对手有压迫感特性时扣 2 点。"""
        self.own.pp[index] -= 2 if self.opponent.ability_name_id == "pressure" else 1
