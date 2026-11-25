# 极巨大冒险刷闪 `swsh/lair`

游戏停在科学家面前开始。配置在 `game_config.py`。

| 步骤 | 文件 | 做什么 |
|---|---|---|
| initialize | `steps/initialize.py` | 把游戏带到科学家面前 |
| join | `steps/join.py` | 选神兽，选初始租借宝可梦，读路线图并规划路线 |
| path | `steps/path.py` | 处理路线上的岔路口、背包客、研究员、树果，直到进入战斗 |
| battle | `steps/battle.py` | 选招式、决定要不要极巨化、记录天气场地和倒下次数 |
| catch | `steps/catch.py` | 抓宝可梦，普通关决定换不换 |
| select_pokemon | `steps/select_pokemon.py` | 查闪光，有闪光就带走，没有就不带走或重启保留路线 |
