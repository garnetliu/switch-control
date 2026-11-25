# control-switch

用电脑控制已装大气层的 Switch，自动刷闪光宝可梦。现在有三个脚本：

| 脚本 | 游戏 | 刷什么 | 说明 |
|---|---|---|---|
| `swsh/lair` | 《宝可梦 剑/盾》 | 极巨大冒险里的闪光神兽 | [README](src/control_switch/games/swsh/lair/README.md) |
| `sv/outbreak` | 《宝可梦 朱/紫》 | 大量出现里的闪光宝可梦 | [README](src/control_switch/games/sv/outbreak/README.md) |
| `sv/egg` | 《宝可梦 朱/紫》 | 孵蛋刷闪光 | [README](src/control_switch/games/sv/egg/README.md) |

每个脚本开始前要怎么准备、配置在哪、每一步做什么，见脚本目录下的 README。

Switch 上要装 usb-botbase（USB 连接）或 sys-botbase（WiFi 连接，TCP 6000）。

## 安装

以下步骤在 macOS 上操作。

### 第 1 步：准备 Switch

Switch 要装好大气层，并装上 botbase：

- 用 USB 线连接：装 usb-botbase。
- 用 WiFi 连接：装 sys-botbase，Switch 和电脑要在同一个局域网里。

没破解的 Switch 用采集卡和单片机，见下面的「采集卡」和「用单片机按键」，这一步可以跳过。

### 第 2 步：安装 uv 和 Docker

uv 用来装 Python 和依赖，Docker 用来跑 PKHeX 服务。已经装过的跳过。

```bash
brew install uv
brew install --cask docker
```

装完打开一次 Docker Desktop，让它在后台运行。

### 第 3 步：下载代码，安装依赖

```bash
git clone git@github.com:garnetliu/switch-control.git
cd switch-control
uv sync
```

`uv sync` 会自己装好 Python 3.11 以上的版本和全部依赖。

### 第 4 步：写机器配置

打开 `runs/switches.toml`，里面每种接法都有注释掉的例子。照自己的接法取消注释一节 `[switch.名字]`，名字自己起；再在最下面的 `[scripts]` 里写每个脚本用哪台。各项的意思见下面「机器配置」。

```bash
open -e runs/switches.toml
```

要收 Discord 通知的，再复制一份 `.env`，填 `DISCORD_WEBHOOK_URL`：

```bash
cp .env.example .env
open -e .env
```

### 第 5 步：找 Switch 的 ip（只有 WiFi 连接要做）

机器那一节写好 `mac` 之后：

```bash
make find switch=living
```

`switch=` 写机器的名字。找到后会把 ip 写进这台的 `ip`，再 ping 一下打印延迟。

### 第 6 步：启动 PKHeX 服务

`swsh/lair` 和 `sv/outbreak` 要用 PKHeX 服务解析游戏内存里的宝可梦数据，`sv/egg` 不用。

```bash
docker compose -f docker/pkhex-reader/compose.yaml up -d --build
```

服务地址是 `http://127.0.0.1:8787`。服务在别的机器或端口上时，在 `.env` 里写 `PKHEX_API_URL`。接口说明见 `docker/pkhex-reader/API.md`。

### 第 7 步：开始运行

在 Switch 上打开要刷的游戏，按脚本目录下 README 写的准备好，然后：

```bash
make start script=swsh/lair
```

`script=` 换成要跑的脚本：`swsh/lair`、`sv/outbreak`、`sv/egg`，跑在 `[scripts]` 里写的那台机器上。两个脚本用不同的机器时，开两个终端各跑一个，可以分别停止和启动。启动时会先检查设备，没通过会打印报错并退出，报错的意思见「启动时的检查」。按 `Ctrl+C` 停止。

## 命令

命令都写在 `Makefile` 里。

| 命令 | 作用 |
|---|---|
| `make find switch=…` | 按这台机器的 `mac` 找它的 ip，写回 `runs/switches.toml`，再 ping 一下检查延迟 |
| `make start script=…` | 开始自动刷，`script=` 必须写，例如 `make start script=sv/egg` |
| `make restart switch=…` | 重启这台机器上的游戏，回到游戏里可以操作为止。极巨大冒险途中重启，下次和科学家说话要付极矿石罚款 |
| `make format` | 格式化代码 |
| `make lint` | 检查代码 |
| `make test` | 跑测试 |
| `make typecheck` | 类型检查 |
| `make coverage` | 跑测试并打印覆盖率 |

## 机器配置

写在 `runs/switches.toml`，在 `src/control_switch/settings.py` 里读。每台 Switch 一节 `[switch.名字]`，`[scripts]` 里写每个脚本用哪台。写了不在可选值里的值或者不认识的项，启动时报错退出并说明可以写什么。

| 项 | 可以写 | 不写时 | 作用 |
|---|---|---|---|
| `connection` | `usb`、`wifi` | `wifi` | botbase 用 USB（usb-botbase）还是 WiFi（sys-botbase）连 Switch。取图、按键、内存里写了 `botbase` 的共用这一个连接 |
| `mac` | MAC 地址 | 无 | Switch 的 MAC 地址（Switch 上「设置 → 互联网 → 互联网设置」里看），`make find` 用它在局域网里找 ip |
| `ip` | ip 地址 | 无 | WiFi 连接时 Switch 的 ip，`make find` 自动写入。WiFi 连接没写会报错 |
| `port` | 整数 | 无 | WiFi 连接时 sys-botbase 的端口，一般是 `6000`。WiFi 连接没写会报错 |
| `screen` | `botbase`、`capture` | `botbase` | 用什么取图：botbase 或采集卡（见「采集卡」） |
| `controller` | `botbase`、`serial` | `botbase` | 用什么按键：botbase 或单片机（见「用单片机按键」） |
| `memory` | `botbase`、`none` | `botbase` | 用什么读写内存；`none` 是不读写，只能跑不读内存的脚本（`sv/egg`） |
| `capture_device` | 不小于 0 的整数 | `0` | `screen = "capture"` 时采集卡在 OpenCV 里的序号 |
| `serial_port` | 串口路径 | 无 | `controller = "serial"` 时单片机的串口，例如 `/dev/cu.usbserial-xxxx`，这时必须写 |
| `serial_baud` | 整数 | `9600` | 单片机串口的波特率 |

同时跑两台时，最多只能有一台用 USB 连 botbase：usb-botbase 只会连第一个找到的 USB 设备。

`.env` 里只有两项，`.env.example` 是模板：

| 变量 | 不写时 | 作用 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | 不发通知 | Discord 频道的 Webhook，发每局战报、超时和出错的通知 |
| `PKHEX_API_URL` | `http://127.0.0.1:8787/api/v1/execute` | PKHeX 服务的地址，服务在别的机器或端口上才要改 |

极巨大冒险的 keep path 开关在 `src/control_switch/games/swsh/lair/game_config.py` 的 `keep_path`。

## 采集卡

没破解的 Switch 也能用采集卡取图，画面原样 1920×1080，不缩小。接法：Switch 插在底座上，底座的 HDMI 接采集卡，采集卡的 USB 插电脑。这台机器写：

```toml
screen = "capture"
capture_device = 0   # 采集卡的序号，不写是 0
```

序号由系统排，插着采集卡时一般是 0，有 OBS 虚拟摄像头之类的设备时可能会变，插拔设备后也可能变。要给终端摄像头权限（系统设置 → 隐私与安全性 → 摄像头）。没破解的 Switch 连不了 botbase，要同时写 `controller = "serial"`、`memory = "none"`，这时不会去连 botbase。

常见报错：

| 报错 | 意思 |
|---|---|
| `取图：采集卡打不开` | 采集卡没插好，或者 `capture_device` 的序号不对 |
| `取图：采集卡打开了但读不到画面` | 终端没有摄像头权限 |
| 日志警告 `采集卡的画面是 … 不是 1920×1080` | 序号可能指到了别的摄像头，换个 `capture_device` |

## 用单片机按键

`controller = "serial"` 时，按键由单片机（伊机控固件）发出，没破解的 Switch 也能按。取图、内存不变。

- 单片机的 USB 插 Switch 底座，系统会把它认成手柄。
- TTL 的 TXD 接单片机 1 号口，RXD 接 0 号口，GND 接 GND，TTL 的 USB 插电脑。
- 这台机器写 `controller = "serial"` 和 `serial_port = "/dev/cu.usbserial-xxxx"`（`ls /dev/cu.usbserial-*` 查）。波特率不写是 9600，只有换了固件才要写 `serial_baud`。

| 报错 | 意思 |
|---|---|
| `… 的 controller 是 serial，要写 serial_port` | 没写串口路径 |
| `按键：串口 … 打不开` | 路径写错、TTL 没插好，或者串口被别的程序占着 |
| `按键：单片机没有回应` | 串口打开了但单片机不回话：检查 TTL 的接线（TXD、RXD 有没有接反）、单片机有没有通电、波特率对不对 |
| `单片机回 FE` | 单片机还在跑里面存的脚本。启动时会先发停止命令，运行中出现说明单片机重启过 |

## 启动时的检查

每个脚本在 `__init__.py` 的 `REQUIRES` 里写明要用取图、按键、内存里的哪几样，`TITLE_IDS` 写明能跑的游戏。`control-switch run` 开始时先检查，`restart` 只检查取图，没通过就打印报错、以非 0 退出，不发通知。报错开头是哪一类，就是哪一类设备没通过：

| 报错开头 | 意思 |
|---|---|
| `取图、按键、内存：botbase（USB）连接失败` | 连不上 Switch，前面写的是用 botbase 的那几类，括号里是 USB 或 WiFi，后面是原来的报错 |
| `内存：这个脚本要读内存` | 脚本要读内存，这台机器的 `memory` 不能是 `none`。连接之前就会报 |
| `取图：` | 取不到画面、画面是空的、不是图片，或者宽高比不是 16:9（报错里有实际的宽高）。画面全黑不报错，只在终端打一条警告，可能是没有画面输出 |
| `内存：` | 读不到前台游戏的 Title ID，或者没有游戏在运行，或者前台不是这个脚本的游戏（报错里有读到的 Title ID） |
| `按键：` | 只有 `run` 检查：按一下 HOME，画面没有变化，按键可能没有送到，或者取图和按键接的不是同一台 Switch。检查会按两次 HOME，第一次让画面切到 HOME 或回到游戏，第二次切回来 |

`restart` 不检查游戏，也不按 HOME：重启时游戏可能已经崩了。

## 目录

```
src/control_switch/
├── __main__.py        命令行入口：control-switch run、control-switch restart
├── session.py         Session：步骤里的 sw，带着配置、当前步骤、这一局的截图、通知和三个设备
├── settings.py        Settings：读 runs/switches.toml 和 .env，其他地方不再读
├── config.py          BaseConfig：所有脚本共用的配置（日志目录、重启、摇杆、等画面、启动检查），每个脚本的配置继承它
├── log.py             日志：输出到终端和 runs/logs 下的文件，一局一个文件
├── notifier.py        发 Discord 通知
├── pkhex.py           调本机的 PKHeX 服务解析宝可梦数据
├── types.py           共用的类型：区域 Rect、颜色 Hsv
├── device/            和 Switch 打交道的硬件：取图、按键、读写内存
│   ├── base.py            三个接口：Screen（取图）、Controller（按键）、Memory（读写内存）
│   ├── botbase.py         用 Switch 上的 sys-botbase / usb-botbase 实现这三个接口
│   ├── capture_card.py    用采集卡取图（screen = "capture"）
│   ├── serial_pad.py      用单片机当手柄按键（controller = "serial"）
│   ├── factory.py         按机器配置创建设备，用 botbase 的几样共用一个连接
│   └── check.py           启动时检查设备齐不齐、能不能用、前台是不是这个脚本的游戏
├── vision/            看截图，只判断不操作
│   ├── image.py           ImageChecker：认字、算颜色占比、比对图片、判断光标选中哪一项
│   └── text.py            认出来的文字和要找的文字做比较
├── flow/              所有游戏通用的操作流程：一边按键一边看画面
│   ├── wait.py            截图、等画面变化、一直按某个键直到画面变化，出错时把这一局的截图写进 failed/
│   ├── menu.py            认出菜单选项，把光标移到目标选项
│   ├── restart.py         关掉游戏重新打开，等到开场画面
│   └── check.py           启动时按两次 HOME，确认按键送到了画面上的这台 Switch
└── games/             各个游戏的脚本
    ├── registry.py        脚本表：按「游戏/脚本」的名字找到脚本
    ├── swsh/              《宝可梦 剑/盾》
    │   ├── data/              宝可梦、招式、路线的数据和属性图标
    │   ├── pokemon.py、field.py、scoring.py、pk8.py    剑盾脚本共用：宝可梦和对战类型、对战打分、读 PK8
    │   └── lair/              极巨大冒险刷闪
    │       ├── steps/             步骤：initialize、join、path、battle、catch、select_pokemon
    │       ├── game_config.py     配置：路径、界面区域、游戏参数
    │       ├── session.py         极巨大冒险的 Session，带着这一局的状态和游戏数据
    │       ├── game_state.py      这一局的状态，存成 runs/state/game.yaml
    │       └── 其余文件            按 seed 算对手、读路线图、给首发和路线打分
    └── sv/                《宝可梦 朱/紫》
        ├── data/              图片数据（fly_icon.png）
        ├── config.py          朱紫脚本共用的配置：内存指针、存档块、按键后等多久
        ├── blocks.py          在内存里找到存档块，解密读出、加密写回
        ├── actions.py         存档、开野餐、收野餐
        ├── outbreak/          大量出现刷闪：config、session，steps/ 下每个步骤一个文件
        └── egg/               孵蛋刷闪：config、session，steps/ 下每个步骤一个文件，画面判断 screens.py，盒子里的操作 box.py，飞到闸口 fly.py

runs/                  只有 switches.toml 进 git，其余是运行时生成的
├── switches.toml      每台 Switch 用什么设备，每个脚本用哪台
├── logs/              日志，每个脚本一个目录：swsh-lair/、sv-outbreak/、sv-egg/
│                      出错时这一局的截图写进 failed/；极巨大冒险不是闪光的战果截图在 swsh-lair/results/
├── shinys/            闪光宝可梦的截图
└── state/             极巨大冒险这一局的状态 game.yaml，用来断线恢复和 keep path

scripts/               不属于包的脚本：找 Switch、离线算 seed 和伤害表、路由器查询、测速
tests/                 测试，目录结构和 src/control_switch 对应；images/ 是测试用的真机截图
docs/                  实测记录和待测试的事项
docker/                PKHeX 服务的容器
```

`control-switch run` 按名字在脚本表里找到脚本，从 `START` 开始一步一步跑，每一步返回下一步的名字。

加脚本：在 `games/<游戏>/<脚本>/__init__.py` 里写 `STEPS`、`START`、`SESSION`、`REQUIRES`、`TITLE_IDS`，再在 `games/registry.py` 的脚本表里加一行。
