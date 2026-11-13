# control-switch

用电脑控制已装大气层的 Switch，自动刷闪光宝可梦。现在有两个脚本：

| 脚本 | 游戏 | 刷什么 |
|---|---|---|
| `swsh/lair` | 《宝可梦 剑/盾》 | 极巨大冒险里的闪光神兽 |
| `sv/outbreak` | 《宝可梦 朱/紫》 | 大量出现里的闪光宝可梦 |

Switch 上要装 usb-botbase（USB 连接）或 sys-botbase（WiFi 连接，TCP 6000）。

## 安装

```bash
uv sync
```

复制 `.env.example` 为 `.env`，按里面的说明填写。用 WiFi 连接时要填 Switch 的 MAC 地址（`SWITCH_MAC`），再用 `make find` 找 ip。

`make find` 要用系统自带的 Python 运行，需要在系统 Python 里装 python-dotenv：

```bash
/usr/bin/python3 -m pip install --user python-dotenv
```

## PKHeX 服务

程序通过本机的 PKHeX 服务解析游戏内存里的宝可梦数据，开始之前要先启动容器：

```bash
docker compose -f docker/pkhex-reader/compose.yaml up -d --build
```

服务地址是 `http://127.0.0.1:8787`，也可以用环境变量 `PKHEX_API_URL` 指定。接口说明见 `docker`。

## 命令

命令都写在 `Makefile` 里。

| 命令 | 作用 |
|---|---|
| `make find` | 查找 Switch 的 ip，写入 `.env` 的 `SWITCH_IP`，再 ping 一下检查延迟 |
| `make start` | 开始自动刷，默认跑 `swsh/lair`。跑别的脚本写 `make start script=sv/outbreak` |
| `make restart` | 重启游戏，回到游戏里可以操作为止，同样用 `script=` 指定脚本。极巨大冒险途中重启，下次和科学家说话要付极矿石罚款 |
| `make format` | 格式化代码 |
| `make lint` | 检查代码 |

## 环境变量

全部变量和说明都在 `.env.example` 里，复制成 `.env` 再改。连接和通知之外，还有一个开关，只有极巨大冒险用，不写就是关：

| 变量 | 作用 |
|---|---|
| `KEEP_PATH` | 设成 `1` 才开启。一局没刷到闪光、打赢并且倒下次数和用时都在范围内时，重启游戏保留这张图（keep path）。重启要付极矿石，矿石不够时不要开 |

## 流程

`src/main.py` 按名字找到脚本，从脚本的起点开始一步一步跑，每一步返回下一步的名字。

### 极巨大冒险 `swsh/lair`

游戏停在科学家面前开始。配置在 `src/swsh/lair/game_config.py`。

| 步骤 | 文件 | 做什么 |
|---|---|---|
| initialize | `src/swsh/lair/steps/initialize.py` | 确认前台是剑/盾，把游戏带到科学家面前 |
| join | `src/swsh/lair/steps/join.py` | 选神兽，选初始租借宝可梦，读路线图并规划路线 |
| path | `src/swsh/lair/steps/path.py` | 处理路线上的岔路口、背包客、研究员、树果，直到进入战斗 |
| battle | `src/swsh/lair/steps/battle.py` | 选招式、决定要不要极巨化、记录天气场地和倒下次数 |
| catch | `src/swsh/lair/steps/catch.py` | 抓宝可梦，普通关决定换不换 |
| select_pokemon | `src/swsh/lair/steps/select_pokemon.py` | 查闪光，有闪光就带走，没有就不带走或重启保留路线 |

### 大量出现 `sv/outbreak`

开始前：游戏版本 4.0.0；人站在大量出现的范围里；打开过一次菜单，把光标停在「野餐」上。配置在 `src/sv/outbreak/config.py`（要找的宝可梦、要不要改击败数）和 `src/sv/config.py`（每个键按完等几秒）。

步骤都在 `src/sv/outbreak/steps.py`：

| 步骤 | 做什么 |
|---|---|
| initialize | 确认前台是朱/紫，找到内存里的存档块表 |
| knockout | 存档，重启游戏，停在标题画面时把所有大量出现的击败数改满，再进游戏。配置里可以关掉 |
| refresh | 开野餐再收起，身边的宝可梦重新生成 |
| scan | 存档，读内存里身边的宝可梦。有要找的闪光就截图、推送并结束，没有就回到 refresh |

刷到闪光时已经存过档，那只宝可梦在存档里，没抓到重启游戏它还在。还没有做三明治这一步。

## 目录

| 目录 | 内容 |
|---|---|
| `src/main.py`、`src/scripts.py` | 入口和脚本表。加脚本时在脚本表里加一行 |
| `src/libs` | 所有游戏共用：连接 Switch、读写内存、看图、推送、PKHeX 请求、通用配置（`config.py`） |
| `src/tools` | 所有游戏共用：等画面、菜单、日志、存截图、重启、找 Switch |
| `src/type` | 所有游戏共用的类型 |
| `src/swsh` | 剑盾的脚本共用的东西：对战打分、宝可梦类型、PK8 读取 |
| `src/swsh/lair` | 极巨大冒险：步骤、配置、状态、数据加载和路线图 |
| `src/sv` | 朱紫的脚本共用的东西：指针、读写存档块（`blocks.py`）、存档和野餐的操作（`actions.py`） |
| `src/sv/outbreak` | 大量出现刷闪：步骤和配置 |
| `data/swsh` | 剑盾的宝可梦、招式、路线和图片数据 |
| `run` | 极巨大冒险这一局的状态 `game.yaml`，用来断线恢复和 keep path |
| `catches` | 闪光宝可梦的截图 |
| `logs` | 日志和截图，每个脚本一个目录：`logs/swsh-lair/`、`logs/sv-outbreak/`。截图平时只放在内存里，程序出错时才把这一局的截图写进这个目录下的 `failed/`。极巨大冒险不是闪光的战果截图在 `logs/swsh-lair/results/` |
| `docs` | 实测记录和待测试的事项 |
| `docker` | PKHeX 服务的容器 |
