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
| `make test` | 跑测试 |
| `make typecheck` | 类型检查 |
| `make coverage` | 跑测试并打印覆盖率 |

## 环境变量

全部变量和说明都在 `.env.example` 里，复制成 `.env` 再改。所有环境变量都在 `src/control_switch/settings.py` 里读，其他地方用传进来的 `Settings`。

`SCREEN`（`botbase`、`capture`）、`CONTROLLER`（`botbase`、`serial`）、`MEMORY`（`botbase`、`none`）决定画面、按键、读写内存各用哪种设备，不写都是 `botbase`，由 `device/factory.py` 创建；选了 `botbase` 的共用同一个连接。`capture` 还没有实现，写了会报错退出。写错值也会报错退出，并说明可以写什么。

连接和通知之外，还有一个开关，只有极巨大冒险用，不写就是关：

| 变量 | 作用 |
|---|---|
| `KEEP_PATH` | 设成 `1` 才开启。一局没刷到闪光、打赢并且倒下次数和用时都在范围内时，重启游戏保留这张图（keep path）。重启要付极矿石，矿石不够时不要开 |

## 启动时的检查

每个脚本在 `__init__.py` 的 `REQUIRES` 里写明要用取图、按键、内存里的哪几样，`TITLE_IDS` 写明能跑的游戏。`control-switch run` 和 `restart` 开始时先检查，没通过就打印报错、以非 0 退出，不发通知。报错开头是哪一类，就是哪一类设备没通过：

| 报错开头 | 意思 |
|---|---|
| `取图、按键、内存：botbase（USB）连接失败` | 连不上 Switch，前面写的是用 botbase 的那几类，括号里是 USB 或 WiFi，后面是原来的报错 |
| `内存：这个脚本要读内存` | 脚本要读内存，`.env` 的 `MEMORY` 不能是 `none`。连接之前就会报 |
| `取图：` | 取不到画面、画面是空的、不是图片，或者宽高比不是 16:9（报错里有实际的宽高）。画面全黑不报错，只在终端打一条警告，可能是没有画面输出 |
| `内存：` | 读不到前台游戏的 Title ID，或者没有游戏在运行，或者前台不是这个脚本的游戏（报错里有读到的 Title ID） |
| `按键：` | 只有 `run` 检查：按一下 HOME，画面没有变化，按键可能没有送到，或者取图和按键接的不是同一台 Switch。检查会按两次 HOME，第一次让画面切到 HOME 或回到游戏，第二次切回来 |

`restart` 不检查游戏，也不按 HOME：重启时游戏可能已经崩了。

## 流程

`control-switch run` 按名字找到脚本，从脚本的起点开始一步一步跑，每一步返回下一步的名字。

### 极巨大冒险 `swsh/lair`

游戏停在科学家面前开始。配置在 `src/control_switch/games/swsh/lair/game_config.py`。

| 步骤 | 文件 | 做什么 |
|---|---|---|
| initialize | `src/control_switch/games/swsh/lair/steps/initialize.py` | 把游戏带到科学家面前 |
| join | `src/control_switch/games/swsh/lair/steps/join.py` | 选神兽，选初始租借宝可梦，读路线图并规划路线 |
| path | `src/control_switch/games/swsh/lair/steps/path.py` | 处理路线上的岔路口、背包客、研究员、树果，直到进入战斗 |
| battle | `src/control_switch/games/swsh/lair/steps/battle.py` | 选招式、决定要不要极巨化、记录天气场地和倒下次数 |
| catch | `src/control_switch/games/swsh/lair/steps/catch.py` | 抓宝可梦，普通关决定换不换 |
| select_pokemon | `src/control_switch/games/swsh/lair/steps/select_pokemon.py` | 查闪光，有闪光就带走，没有就不带走或重启保留路线 |

### 大量出现 `sv/outbreak`

开始前：游戏版本 4.0.0；人站在大量出现的范围里；打开过一次菜单，把光标停在「野餐」上。配置在 `src/control_switch/games/sv/outbreak/config.py`（要找的宝可梦、要不要改击败数）和 `src/control_switch/games/sv/config.py`（每个键按完等几秒）。

步骤都在 `src/control_switch/games/sv/outbreak/steps.py`：

| 步骤 | 做什么 |
|---|---|
| initialize | 找到内存里的存档块表 |
| knockout | 存档，重启游戏，停在标题画面时把所有大量出现的击败数改满，再进游戏。配置里可以关掉 |
| refresh | 开野餐再收起，身边的宝可梦重新生成 |
| scan | 存档，读内存里身边的宝可梦。有要找的闪光就截图、推送并结束，没有就回到 refresh |

刷到闪光时已经存过档，那只宝可梦在存档里，没抓到重启游戏它还在。还没有做三明治这一步。

### 用单片机按键

`CONTROLLER=serial` 时，按键由单片机（伊机控固件）发出，没破解的 Switch 也能按。取图、内存不变。

- 单片机的 USB 插 Switch 底座，系统会把它认成手柄。
- TTL 的 TXD 接单片机 1 号口，RXD 接 0 号口，GND 接 GND，TTL 的 USB 插电脑。
- `.env` 里写 `CONTROLLER=serial` 和 `SERIAL_PORT=/dev/cu.usbserial-xxxx`（`ls /dev/cu.usbserial-*` 查）。波特率不写是 9600，只有换了固件才要写 `SERIAL_BAUD`。

| 报错 | 意思 |
|---|---|
| `CONTROLLER=serial 时要在 .env 里写 SERIAL_PORT` | 没写串口路径 |
| `按键：串口 … 打不开` | 路径写错、TTL 没插好，或者串口被别的程序占着 |
| `按键：单片机没有回应` | 串口打开了但单片机不回话：检查 TTL 的接线（TXD、RXD 有没有接反）、单片机有没有通电、波特率对不对 |
| `单片机回 FE` | 单片机还在跑里面存的脚本。启动时会先发停止命令，运行中出现说明单片机重启过 |

## 目录

| 目录 | 内容 |
|---|---|
| `src/control_switch/__main__.py` | 命令行入口：`control-switch run`、`control-switch restart` |
| `src/control_switch/session.py` | `Session`：配置、当前步骤、这一局的截图、通知，以及取图、按键、读写内存的设备 |
| `src/control_switch/settings.py` | `Settings`：集中读环境变量和 `.env`，其他地方不再读 |
| `src/control_switch/device/factory.py` | `create_devices`：按 `SCREEN`、`CONTROLLER`、`MEMORY` 创建设备 |
| `src/control_switch/device/serial_pad.py` | `SerialPad`、`open_serial_pad`：用单片机按键，`CONTROLLER=serial` 时用 |
| `src/control_switch/device/check.py` | `check_requires`、`check_devices`：启动时检查设备 |
| `src/control_switch/flow/check.py` | `check_controller_reaches_screen`：启动时按两次 HOME，确认按键送到了画面上的这台 Switch |
| `src/control_switch/device/base.py` | 设备的三个接口：`Screen`（取图）、`Controller`（按键）、`Memory`（读写内存）；`botbase.py` 是它们的实现 |
| `src/control_switch` | 所有游戏共用：连接 Switch（`device`）、看图（`vision`）、等画面、菜单、重启（`flow`）、日志、推送、PKHeX 请求、通用配置、类型 |
| `src/control_switch/games/registry.py` | 脚本表。加脚本时要在脚本的 `__init__.py` 里写 `STEPS`、`START`、`SESSION`、`REQUIRES`、`TITLE_IDS`，再在脚本表里加一行 |
| `src/control_switch/games/swsh` | 剑盾的脚本共用的东西：对战打分、宝可梦类型、PK8 读取 |
| `src/control_switch/games/swsh/lair` | 极巨大冒险：步骤、配置、状态、数据加载和路线图 |
| `src/control_switch/games/sv` | 朱紫的脚本共用的东西：指针、读写存档块（`blocks.py`）、存档和野餐的操作（`actions.py`） |
| `src/control_switch/games/sv/outbreak` | 大量出现刷闪：步骤和配置 |
| `scripts` | 不属于包的脚本：找 Switch、离线算 seed 和伤害表 |
| `data/swsh` | 剑盾的宝可梦、招式、路线和图片数据 |
| `run` | 极巨大冒险这一局的状态 `game.yaml`，用来断线恢复和 keep path |
| `catches` | 闪光宝可梦的截图 |
| `logs` | 日志和截图，每个脚本一个目录：`logs/swsh-lair/`、`logs/sv-outbreak/`。截图平时只放在内存里，程序出错时才把这一局的截图写进这个目录下的 `failed/`。极巨大冒险不是闪光的战果截图在 `logs/swsh-lair/results/` |
| `docs` | 实测记录和待测试的事项 |
| `docker` | PKHeX 服务的容器 |
