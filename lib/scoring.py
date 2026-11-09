"""评分：选宝可梦、换不换宝可梦、选招式用到的公式。照搬上游 AutoMaxLair 的 matchup_scoring.py。

上游在计算时会直接改招式的属性（比如天气球、-皮肤类特性把一般系招式变成别的属性），
改动会留在招式对象上，影响之后的每一次计算。这里的招式数据不能改，
算出的属性只在这一次计算里用，所以同样的输入每次结果都一样。
"""

from collections.abc import Iterable
from dataclasses import replace

from lib.log import log
from typedefs.battle import Field
from typedefs.pokemon import Move, Pokemon

TYPES = (
    "normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground",
    "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy",
)  # fmt: skip
# 属性相克表：TYPE_CHART[招式属性][防守方属性] 是伤害倍率，顺序同 TYPES
TYPE_CHART = (
    (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0.5, 0, 1, 1, 0.5, 1),
    (1, 0.5, 0.5, 1, 2, 2, 1, 1, 1, 1, 1, 2, 0.5, 1, 0.5, 1, 2, 1),
    (1, 2, 0.5, 1, 0.5, 1, 1, 1, 2, 1, 1, 1, 2, 1, 0.5, 1, 1, 1),
    (1, 1, 2, 0.5, 0.5, 1, 1, 1, 0, 2, 1, 1, 1, 1, 0.5, 1, 1, 1),
    (1, 0.5, 2, 1, 0.5, 1, 1, 0.5, 2, 0.5, 1, 0.5, 2, 1, 0.5, 1, 0.5, 1),
    (1, 0.5, 0.5, 1, 2, 0.5, 1, 1, 2, 2, 1, 1, 1, 1, 2, 1, 0.5, 1),
    (2, 1, 1, 1, 1, 2, 1, 0.5, 1, 0.5, 0.5, 0.5, 2, 0, 1, 2, 2, 0.5),
    (1, 1, 1, 1, 2, 1, 1, 0.5, 0.5, 1, 1, 1, 0.5, 0.5, 1, 1, 0, 2),
    (1, 2, 1, 2, 0.5, 1, 1, 2, 1, 0, 1, 0.5, 2, 1, 1, 1, 2, 1),
    (1, 1, 1, 0.5, 2, 1, 2, 1, 1, 1, 1, 2, 0.5, 1, 1, 1, 0.5, 1),
    (1, 1, 1, 1, 1, 1, 2, 2, 1, 1, 0.5, 1, 1, 1, 1, 0, 0.5, 1),
    (1, 0.5, 1, 1, 2, 1, 0.5, 0.5, 1, 0.5, 2, 1, 1, 0.5, 1, 2, 0.5, 0.5),
    (1, 2, 1, 1, 1, 2, 0.5, 1, 0.5, 2, 1, 2, 1, 1, 1, 1, 0.5, 1),
    (0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 2, 1, 0.5, 1, 1),
    (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 0.5, 0),
    (1, 1, 1, 1, 1, 1, 0.5, 1, 1, 1, 2, 1, 1, 2, 1, 0.5, 1, 0.5),
    (1, 0.5, 0.5, 0.5, 1, 2, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 0.5, 2),
    (1, 0.5, 1, 1, 1, 1, 2, 0.5, 1, 1, 1, 1, 1, 1, 2, 2, 0.5, 1),
)


def weighted_score(
    rental_score: float, rental_weight: int, boss_score: float, boss_weight: int
) -> float:
    """加权几何平均。

    rental_score: 对其他租借宝可梦对手的平均相性。
    boss_score: 对最终首领的相性。
    两项的权重由还剩几个对手决定，首领更难，权重通常更大。
    """
    total = rental_weight + boss_weight
    return ((rental_score**rental_weight) * (boss_score**boss_weight)) ** (1 / total)


def evaluate_matchup(
    attacker: Pokemon, boss: Pokemon, teammates: Iterable[Pokemon] = (), lives: int = 1
) -> float:
    """attacker 对 boss 的相性分：attacker 用最好的招式，boss 平均地用招式。

    teammates: attacker 的队友。lives: 还剩几条命，命越多，血量的影响越小。
    """
    teammates = list(teammates)
    # 极巨大冒险里的百变怪有变身者特性，一上场就变成对方
    if attacker.name_id == "ditto":
        attacker = transform_ditto(attacker, boss)
    elif boss.name_id == "ditto":
        boss = transform_ditto(boss, attacker)

    field = Field()
    base_score = select_best_move(replace(attacker, dynamax=False), boss, field, teammates)[2]
    dynamax_score = select_best_move(replace(attacker, dynamax=True), boss, field, teammates)[2]
    score = max(base_score, (base_score + dynamax_score) / 2)

    # 上游原来是 assert 1 <= lives <= 4，命数计数多扣时会崩；这里只是打分，按范围钳住
    lives = min(max(int(lives), 1), 4)
    hp_correction = ((5 - lives) * attacker.hp + lives - 1) / 4
    return score * hp_correction


def evaluate_average_matchup(
    attacker: Pokemon, bosses: Iterable[Pokemon], teammates: Iterable[Pokemon] = (), lives: int = 1
) -> float:
    """attacker 对一组对手的平均相性分，没有对手时是 1。"""
    bosses = list(bosses)
    if not bosses:
        return 1
    return sum(evaluate_matchup(attacker, boss, teammates, lives) for boss in bosses) / len(bosses)


def select_best_move(
    attacker: Pokemon, defender: Pokemon, field: Field, teammates: Iterable[Pokemon] = ()
) -> tuple[int, str, float]:
    """attacker 对 defender 用哪个招式最好：返回招式的序号、name_id、分数。没 PP 的招式不算。

    极巨化时分数是按极巨招式算的，日志里的名字也用极巨招式的名字。
    """
    teammates = list(teammates)
    moves = attacker.max_moves if attacker.dynamax else attacker.moves
    best_index, best_name_id, best_score = 0, "", -100.0
    for index, move in enumerate(moves):
        if attacker.pp[index] > 0:
            score = move_score(attacker, index, defender, teammates, field)
            log(f"第 {index + 1} 个招式 {move.name()}（得分 {score:.2f}）")
            if score > best_score:
                best_index, best_name_id, best_score = index, move.name_id, score
    return best_index, best_name_id, best_score


def move_score(
    attacker: Pokemon,
    move_index: int,
    defender: Pokemon,
    teammates: Iterable[Pokemon],
    field: Field,
) -> float:
    """attacker 对 defender 用第 move_index 个招式的分数：打出的伤害除以受到的伤害。"""
    # 队友里不算 attacker 和 defender 自己
    teammates = [
        member for member in teammates if member is not attacker and member is not defender
    ]

    # 打出的伤害：自己这一招，加上三个队友的平均伤害（首领极巨化了，伤害都按一半算）。
    # 队友的伤害多半被低估了：变化类招式也有用，电脑选招也比随机好，所以乘 1.5
    teammate_factor = 1.5
    dealt = damage(attacker, move_index, defender, field) / 2
    dealt += 3 * average_damage(teammates, [defender], field) / 2 * teammate_factor

    # 受到的伤害：首领用普通招式和极巨招式的加权平均。首领用极巨招式的概率是估计的
    max_move_probability = 0.3
    attacker_move = attacker.moves[move_index]
    regular = replace(defender, dynamax=False)
    received_regular = 0.0
    for index, move in enumerate(regular.moves):
        count = len(regular.moves)
        if move.is_spread:
            # 广域防守能挡住范围招式，但极巨化之后用不了
            if attacker_move.name_id != "wide-guard" or attacker.dynamax:
                received_regular += damage(regular, index, attacker, field, True) / count
                received_regular += 3 * average_damage([regular], teammates, field, True) / count
        else:
            received_regular += _received(regular, index, attacker, teammates, field) / count
    dynamaxed = replace(defender, dynamax=True)
    count = min(4, len(dynamaxed.max_moves))
    received_max = sum(
        _received(dynamaxed, index, attacker, teammates, field) / count for index in range(count)
    )
    received = received_regular * (1 - max_move_probability) + received_max * max_move_probability
    # 受到的伤害是 0 时分数没有意义，照上游记为 1
    return dealt / received if received else 1.0


def damage(
    attacker: Pokemon,
    move_index: int,
    defender: Pokemon,
    field: Field,
    multiple_targets: bool = False,
) -> float:
    """attacker 用第 move_index 个招式打 defender 的伤害，以 defender 的最大 HP 为 1。

    attacker 正在极巨化时用对应的极巨招式。伤害取随机数的平均，不算会心一击。
    """
    move = attacker.max_moves[move_index] if attacker.dynamax else attacker.moves[move_index]
    # 随机数在 0.85 到 1 之间，取平均
    modifier = 0.925 * move.accuracy
    if multiple_targets and move.is_spread:
        modifier *= 0.75
    # 天气、场地、特性可能改变招式属性，要在算本系加成和相克之前处理
    weather_modifier, move_type = _weather_modifier(move, move.type_id, field)
    terrain_modifier, move_type = _terrain_modifier(attacker, move, move_type, defender, field)
    modifier *= weather_modifier * terrain_modifier
    skins = {
        "refrigerate": "ice",
        "aerilate": "flying",
        "galvanize": "electric",
        "pixilate": "fairy",
    }
    if move_type == "normal" and attacker.ability_name_id in skins:
        move_type = skins[attacker.ability_name_id]
        modifier *= 1.2
    elif move_type != "normal" and attacker.ability_name_id == "normalize":
        move_type = "normal"
        modifier *= 1.2

    if move_type in attacker.type_ids:  # 本系加成。适应力在特性倍率里算
        modifier *= 1.5
    if move.name_id != "thousand-arrows" or "flying" not in defender.type_ids:
        modifier *= type_multiplier(move_type, defender.type_ids)
    if move.category == "physical" and attacker.status == "burn":
        modifier *= 0.5
    # 上游判断特性时用的是普通招式的属性，极巨化时也是
    ability_type = attacker.moves[move_index].type_id if attacker.dynamax else move_type
    modifier *= _ability_modifier(attacker, move_index, ability_type, defender)
    for aura, aura_type in (("fairy-aura", "fairy"), ("dark-aura", "dark")):
        if move_type == aura_type and aura in (attacker.ability_name_id, defender.ability_name_id):
            modifier *= 1.33

    attacker_stats, defender_stats = attacker.stats, defender.stats
    if move.category == "physical":
        if move.name_id == "body-press":
            numerator = attacker_stats[2]
        elif move.name_id == "foul-play":
            numerator = defender_stats[1]
        else:
            numerator = attacker_stats[1]
        denominator = defender_stats[2]
    else:
        numerator = attacker_stats[3]
        if move.name_id in ("psystrike", "psyshock"):
            denominator = defender_stats[2]
        else:
            denominator = defender_stats[4]
            if field.weather == "sandstorm" and "rock" in defender.type_ids:
                denominator *= 1.5
    level_factor = 2 / 5 * attacker.level + 2
    base = level_factor * move.power * numerator / denominator / 50 + 2
    return base * modifier / defender_stats[0]


def average_damage(
    attackers: Iterable[Pokemon],
    defenders: Iterable[Pokemon],
    field: Field,
    multiple_targets: bool = False,
) -> float:
    """每个 attacker 对每个 defender 用各个招式的平均伤害，再对所有组合取平均。没有组合时是 0。"""
    pairs = [(attacker, defender) for attacker in attackers for defender in defenders]
    if not pairs:
        return 0
    total = 0.0
    for attacker, defender in pairs:
        count = len(attacker.moves)
        total += (
            sum(
                damage(attacker, index, defender, field, multiple_targets) for index in range(count)
            )
            / count
        )
    return total / len(pairs)


def type_multiplier(move_type: str, defender_types: Iterable[str]) -> float:
    """招式属性打防守方属性的相克倍率，双属性时两个倍率相乘。"""
    factor = 1.0
    for defender_type in defender_types:
        factor *= TYPE_CHART[TYPES.index(move_type)][TYPES.index(defender_type)]
    return factor


def transform_ditto(ditto: Pokemon, template: Pokemon) -> Pokemon:
    """百变怪变身成 template：属性、能力（HP 除外）、特性、招式都照抄，招式最多 4 个、每个 5 PP。

    剩余血量也照抄 template 的，和上游一致。
    """
    return replace(
        template,
        name_id=ditto.name_id,
        names=ditto.names,
        base_stats=(ditto.base_stats[0], *template.base_stats[1:]),
        moves=template.moves[:4],
        max_moves=template.max_moves[:4],
        pp=[5] * len(template.moves[:4]),
    )


def _received(
    defender: Pokemon,
    move_index: int,
    attacker: Pokemon,
    teammates: list[Pokemon],
    field: Field,
) -> float:
    """首领用第 move_index 个单体招式时我方平均受到的伤害：1/4 的概率打自己，3/4 打队友。

    自己极巨化时 HP 翻倍，受到的伤害按一半算。
    """
    to_self = damage(defender, move_index, attacker, field) / (2 if attacker.dynamax else 1)
    return 0.25 * to_self + 0.75 * average_damage([defender], teammates, field)


def _weather_modifier(move: Move, move_type: str, field: Field) -> tuple[float, str]:
    """天气对招式的倍率，以及天气改变后的招式属性（天气球）。"""
    modifier = 1.0
    if field.weather == "sunlight":
        if move.name_id == "solar-beam":
            modifier *= 2
        elif move.name_id in ("thunder", "hurricane"):
            modifier *= 0.5 / 0.7
        elif move.name_id == "weather-ball":
            move_type = "fire"
            modifier *= 2
        if move_type == "fire":
            modifier *= 1.5
        elif move_type == "water":
            modifier *= 0.5
    elif field.weather == "rain":
        if move.name_id == "solar-beam":
            modifier *= 0.5
        elif move.name_id in ("thunder", "hurricane"):
            modifier *= 1.0 / 0.7
        elif move.name_id == "weather-ball":
            move_type = "water"
            modifier *= 2
        if move_type == "water":
            modifier *= 1.5
        elif move_type == "fire":
            modifier *= 0.5
    elif field.weather == "hail":
        if move.name_id == "solar-beam":
            modifier *= 0.5
        elif move.name_id == "blizzard":
            modifier *= 1.0 / 0.7
        elif move.name_id == "weather-ball":
            move_type = "ice"
            modifier *= 2
    elif field.weather == "sandstorm":
        if move.name_id == "solar-beam":
            modifier *= 0.5
        elif move.name_id == "weather-ball":
            move_type = "rock"
            modifier *= 2
    elif move.name_id == "weather-ball":
        move_type = "normal"
    return modifier, move_type


def _terrain_modifier(
    attacker: Pokemon, move: Move, move_type: str, defender: Pokemon, field: Field
) -> tuple[float, str]:
    """场地对招式的倍率，以及场地改变后的招式属性（大地波动）。

    「是否在地面上」的判断照搬上游：飞行系且特性是飘浮才算不在地面上。
    """
    modifier = 1.0
    terrain_types = {"electric": "electric", "grassy": "grass", "psychic": "psychic"}
    if "flying" not in attacker.type_ids or attacker.ability_name_id != "levitate":
        if field.terrain in terrain_types:
            if move.name_id == "terrain-pulse":
                move_type = terrain_types[field.terrain]
                modifier *= 1.5
            elif field.terrain == "psychic" and move.name_id == "expanding-force":
                modifier *= 1.5
            if move_type == terrain_types[field.terrain]:
                modifier *= 1.3
        elif field.terrain == "misty":
            if move.name_id == "terrain-pulse":
                move_type = "fairy"
                modifier *= 1.5
            if move_type == "dragon":
                modifier *= 0.5
    defender_grounded = "flying" not in defender.type_ids or defender.ability_name_id != "levitate"
    if defender_grounded and field.terrain == "electric" and move.name_id == "rising-voltage":
        modifier *= 2
    return modifier, move_type


def _ability_modifier(
    attacker: Pokemon, move_index: int, move_type: str, defender: Pokemon
) -> float:
    """特性带来的伤害倍率。吸收这一属性的特性返回 -1，表示打过去反而给对方回血。

    判断照搬上游，包括它的写法造成的两处效果：
    有色眼镜写在「攻击方没有破格类特性」的 elif 里，实际永远不会生效；
    适应力的判断写成了比较特性名和一个布尔值，实际也永远不会生效。
    """
    move_name_id = (
        attacker.max_moves[move_index].name_id
        if attacker.dynamax
        else attacker.moves[move_index].name_id
    )
    ability, defender_ability = attacker.ability_name_id, defender.ability_name_id
    modifier = 1.0
    if ability not in ("mold-breaker", "turboblaze", "teravolt"):
        if move_type == "ground" and defender_ability == "levitate":
            modifier = 1.0 if move_name_id == "thousand-arrows" else 0.0
        elif move_type == "water" and defender_ability in (
            "water-absorb",
            "storm-drain",
            "dry-skin",
        ):
            modifier = -1.0
        elif move_type == "fire":
            if defender_ability == "flash-fire":
                modifier = -1.0
            elif defender_ability in ("fluffy", "dry-skin"):
                modifier = 2.0
            elif defender_ability in ("thick-fat", "heatproof"):
                modifier = 0.5
        elif (
            move_type == "grass"
            and defender_ability == "sap-sipper"
            or move_type == "electric"
            and defender_ability in ("lightning-rod", "motor-drive", "volt-absorb")
        ):
            modifier = -1.0
        elif move_type == "ice" and defender_ability == "thick-fat":
            modifier = 0.5

    punches = (
        "bullet-punch", "comet-punch", "dizzy-punch", "double-iron-bash", "drain-punch",
        "dynamic-punch", "fire-punch", "focus-punch", "hammer-arm", "ice-hammer", "ice-punch",
        "mach-punch", "mega-punch", "meteor-mash", "plasma-fists", "power-up-punch",
        "shadow-punch", "sky-uppercut", "surging-strikes", "thunder-punch", "wicked-blow",
    )  # fmt: skip
    bites = (
        "bite", "crunch", "fire-fang", "fishious-rend", "hyper-fang", "ice-fang", "jaw-lock",
        "poison-fang", "psychic-fangs", "thunder-fang",
    )  # fmt: skip
    if ability == "iron-fist" and move_name_id in punches:
        modifier *= 1.2
    elif ability == "strong-jaw" and move_name_id in bites:
        modifier *= 1.5
    return modifier
