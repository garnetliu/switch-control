# control-switch

用电脑控制已装大气层的 Switch，在《宝可梦 剑/盾》的极巨大冒险里自动刷闪光神兽。

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
| `make start` | 开始自动刷 |
| `make restart` | 重启游戏，回到游戏里可以操作为止。冒险途中重启，下次和科学家说话要付极矿石罚款 |
| `make format` | 格式化代码 |
| `make lint` | 检查代码 |

## 环境变量

除了 `.env.example` 里的连接设置，还有两个开关，设成 `1` 才开启：

| 变量 | 作用 |
|---|---|
| `SAVE_CHECKS` | 每次画面判定成功，把截图存进 `logs/checks/`，判定用的区域画成红框 |
| `KEEP_PATH` | 一局没刷到闪光、倒下次数和用时都在范围内时，重启游戏保留这张图（keep path）。重启要付极矿石，矿石不够时不要开 |

## 流程

`src/main.py` 按下面的步骤循环，每一步返回下一步的名字：

| 步骤 | 文件 | 做什么 |
|---|---|---|
| initialize | `src/shiny_steps/initialize.py` | 确认前台是剑/盾，把游戏带到科学家面前 |
| join | `src/shiny_steps/join.py` | 选神兽，选初始租借宝可梦，读路线图并规划路线 |
| path | `src/shiny_steps/path.py` | 处理路线上的岔路口、背包客、研究员、树果，直到进入战斗 |
| battle | `src/shiny_steps/battle.py` | 选招式、决定要不要极巨化、记录天气场地和倒下次数 |
| catch | `src/shiny_steps/catch.py` | 抓宝可梦，普通关决定换不换 |
| select_pokemon | `src/shiny_steps/select_pokemon.py` | 查闪光，有闪光就带走，没有就不带走或重启保留路线 |

## 目录

| 目录 | 内容 |
|---|---|
| `src/libs` | 连接 Switch、读内存、看图、打分、游戏数据和配置（`game_config.py`） |
| `src/shiny_steps` | 上面每一步的流程 |
| `src/tools` | 等画面、按键、日志、重启、找 Switch |
| `src/type` | 共用的类型 |
| `data` | 宝可梦、招式、路线和图片数据 |
| `run` | 这一局的状态 `game.yaml`，用来断线恢复和 keep path |
| `logs` | 日志和截图：闪光截图在 `logs/catches/`，其他战果截图在 `logs/results/` |
| `docs` | 实测记录和待测试的事项 |
| `docker` | PKHeX 服务的容器 |
