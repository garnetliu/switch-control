"""按租借相性和首领相性给宝可梦打分。"""

from libs import Switch


def score(sw: Switch, name: str, boss: str, floor: int) -> float:
    """算 name 对 boss 的总分。

    floor 是当前层数，每过一层少一个普通对手要打，首领权重固定为 2。
    两项按权重做几何平均。
    """
    rental_weight = max(3 - floor, 0)
    boss_weight = 2
    rental_score = sw.data.rental_scores()[name]
    boss_score = sw.data.boss_matchups()[name][boss]
    total = rental_weight + boss_weight
    return (
        rental_score**rental_weight * boss_score**boss_weight
    ) ** (1 / total)
