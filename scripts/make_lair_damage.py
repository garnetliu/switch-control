"""生成选首发和路线用的两张表：uv run python scripts/make_lair_damage.py。

只做计算，不连 Switch。结果写到 data/swsh/：
- rental_damage_LUT.json：{进攻的: {防守的: [普通, 极巨, 平均]}}，租借宝可梦两两之间，进攻的一回合打掉
  防守方血量的比例。防守方按路上的对手算，战斗里的血量是不极巨化的 stage_hp 倍。
  普通和极巨是没极巨化、极巨化了各用伤害最高的招式（scoring.evaluate_damage），
  平均是普通招式每个用的机会一样（scoring.evaluate_average_damage，估队友用）。前三关查这张表。
- boss_attack_defense_LUT.json：{租借宝可梦: {首领: [普通进攻, 极巨进攻, 挨打]}}。进攻是自己最好的招式
  一回合打掉首领血量的比例（scoring.evaluate_damage，首领战斗里的血量是不极巨化的 boss_hp 倍），
  挨打是首领平均一回合打掉它血量的比例（scoring.evaluate_received）。首领战查这张表。
用法见 swsh/lair/plan.py。
"""

import json

from control_switch.games.swsh.lair.game_config import GameConfig
from control_switch.games.swsh.lair.game_data import GameData
from control_switch.games.swsh.scoring import (
    evaluate_average_damage,
    evaluate_damage,
    evaluate_received,
)

DIRECTORY = GameConfig().data_dir


def main() -> None:
    config = GameConfig()
    data = GameData(config)
    stage_hp, boss_hp = config.stage_hp, config.boss_hp
    pokemon = {name: data.pokemon_object(name) for name in data.rental_matchups()}
    damages = {
        attacker: {
            defender: [
                evaluate_damage(pokemon[attacker], pokemon[defender], False, stage_hp),
                evaluate_damage(pokemon[attacker], pokemon[defender], True, stage_hp),
                evaluate_average_damage(pokemon[attacker], pokemon[defender], stage_hp),
            ]
            for defender in pokemon
        }
        for attacker in pokemon
    }
    _write("rental_damage_LUT.json", damages)
    values = sorted(value for row in damages.values() for pair in row.values() for value in pair)
    print(
        f"租借之间的伤害：{len(damages)} 只，最小 {values[0]:.4f}，"
        f"中位 {values[len(values) // 2]:.4f}，最大 {values[-1]:.4f}"
    )

    bosses = {name: data.pokemon_object(name) for name in data.boss_pokemon()}
    against = {
        name: {
            boss_name: [
                evaluate_damage(rental, boss, False, boss_hp),
                evaluate_damage(rental, boss, True, boss_hp),
                evaluate_received(rental, boss),
            ]
            for boss_name, boss in bosses.items()
        }
        for name, rental in pokemon.items()
    }
    _write("boss_attack_defense_LUT.json", against)
    attacks = sorted(
        value for row in against.values() for item in row.values() for value in item[:2]
    )
    received = sorted(item[2] for row in against.values() for item in row.values())
    print(
        f"对首领：{len(bosses)} 只首领，进攻 {attacks[0]:.4f} 到 {attacks[-1]:.4f}，"
        f"挨打 {received[0]:.4f} 到 {received[-1]:.4f}"
    )


def _write(name: str, table: dict) -> None:
    (DIRECTORY / name).write_text(json.dumps(table, indent=4), encoding="utf-8")


if __name__ == "__main__":
    main()
