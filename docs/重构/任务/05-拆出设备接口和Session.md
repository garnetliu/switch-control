# 任务 05：拆出设备接口和 Session

## 目标

把 `Switch` 类拆开：取图、按键、读写内存各是一个接口，botbase 是它们的一种实现；配置、当前步骤、这一局的截图、通知放到 `Session` 上。做完后仍然只有 botbase 一种硬件，行为不变。

## 开始前的状态

`src/control_switch/device/botbase.py` 里的 `Switch` 一个类里有四样东西：

- 连接：按环境变量 `SWITCH_CONNECTION` 建 `_WifiConnection` 或 `_UsbConnection`，注册退出时关闭和信号处理。
- 设备的方法：`click`、`stick`、`press_stick`、`release_stick`、`pixel_peek`、`title_id`、`peek`、`peek_main`、`pointer_peek`、`pointer_all`、`peek_absolute`、`poke_absolute`、`close`。
- 运行时的东西：`config`、`step`、`frames`、`notifier`。
- 同一个文件里还有 `Frame`。

两个脚本各有一个继承 `Switch` 的类：

- `games/swsh/lair/switch.py` 的 `LairSwitch`：加了 `game`、`data`、`pkhex`、`ore_count()`、`ball_counts()`、`caught_legends()`。
- `games/sv/outbreak/switch.py` 的 `OutbreakSwitch`：加了 `blocks`。

每个脚本的 `__init__.py` 有 `STEPS`、`START`、`connect()`。

工作区是干净的：上一个任务的改动已经提交，`git status --short` 没有输出。不干净时先停下来问，不要开始。

## 约定

### `device/base.py`：三个接口

用 `typing.Protocol`，加 `@runtime_checkable`。方法的参数和返回值和现在 `Switch` 上的一样。

| 接口 | 方法 |
|---|---|
| `Screen` | `pixel_peek() -> bytes`、`close()` |
| `Controller` | `click(button, delay=0.15)`、`stick(side, x, y, hold)`、`close()` |
| `Memory` | `title_id() -> str`、`peek(offset, size)`、`pointer_all(jumps) -> int`、`peek_absolute(address, size)`、`poke_absolute(address, data)`、`close()` |

`press_stick`、`release_stick`、`peek_main`、`pointer_peek` 这四个方法现在没有地方调用，不放进接口。`Botbase` 上保留这四个方法，代码不变。

### `device/botbase.py`

- 类改名 `Botbase`，三个接口都实现。构造时传入一个连接：`Botbase(connection)`。里面不再有 `config`、`step`、`frames`、`notifier`。
- 同一个文件里新加 `Connection`，用 `typing.Protocol`：方法 `send(cmd: str) -> None`、`request(cmd: str) -> bytes`、`title_id() -> str`、`close() -> None`，属性 `pointer_little_endian: bool`。`Botbase` 的参数类型是 `Connection`，两个连接类和测试里的假连接都要符合它。
- 两个连接类各加一个属性 `pointer_little_endian`：USB 是 `True`，WiFi 是 `False`。`pointer_all` 用它判断字节序，不再用 `isinstance`。
- 新增函数 `connect_botbase() -> Botbase`：做现在 `Switch._connect` 做的事（读环境变量、建连接、注册退出时关闭和信号处理）。
- `close()` 调用多次不出错。

### `session.py`

- `Frame` 搬到这里。
- `Session(config, screen, controller, memory)`，`memory` 可以是 `None`。
- 属性：`config`、`step`（初始 `""`）、`frames`（初始空列表）、`notifier`、`screen`、`controller`。
- 只转发三个方法：`click`、`stick` 转给 `controller`，`pixel_peek` 转给 `screen`。步骤里 `sw.click(...)` 的写法不变。
- `memory` 是一个属性：有就返回，是 `None` 时抛 `RuntimeError`，说明这个脚本要读内存但没有配置。
- 读写内存不在 `Session` 上转发，调用的地方改成 `sw.memory.peek(...)` 这种写法。
- `close()`：三个设备按对象去重，每个不同的对象关一次；是 `None` 的跳过。

### 脚本

| 原来 | 改成 |
|---|---|
| `games/swsh/lair/switch.py` 的 `LairSwitch(Switch)` | `games/swsh/lair/session.py` 的 `LairSession(Session)` |
| `games/sv/outbreak/switch.py` 的 `OutbreakSwitch(Switch)` | `games/sv/outbreak/session.py` 的 `OutbreakSession(Session)` |
| 脚本 `__init__.py` 里的 `connect()` | 换成 `SESSION`，值是上面的类 |

- `LairSession(screen, controller, memory)`、`OutbreakSession(screen, controller, memory)`，里面自己创建配置。
- `device/__init__.py` 导出 `Screen`、`Controller`、`Memory`。`device` 外面的代码只引用这三个接口；只有 `__main__.py` 可以引用 `connect_botbase`。

### 入口

`__main__.py` 里：先 `script = load_script(name)`，和现在一样，脚本名不对时直接退出、不去连接；然后 `botbase = connect_botbase()`，再 `sw = script.SESSION(botbase, botbase, botbase)`。

## 写测试

只能改 `tests/`。

`tests/` 也在 `make typecheck` 的范围里，要 0 报错。把假对象换到对象的属性上时（比如 `sw.blocks`、`sw.notifier`、`sw.pkhex`），用 `monkeypatch.setattr(sw, "notifier", fake)` 这种写法，不要直接赋值；把假对象传给标了具体类型的参数时（比如假 `Pkhex` 传给 `SaveBlocks`），写成 `typing.cast(类型, fake)`。三个假设备照 `Screen`、`Controller`、`Memory` 的方法签名写，直接传给 `Session` 不用 `cast`。写测试时 `Session` 这些类还没建出来，pyright 查不出这类错误，要自己按上面的写法写。

1. `tests/conftest.py`：把原来假的连接换成三个假设备和一个 `Session`。`Session` 的 `config` 用原来假连接上的那一份，值不变（`interval` 0、`timeout` 1.0 秒、`log_dir` 指到临时目录、`game_title_ids` 里有假 `Memory` 的 `title_id()` 默认返回的值、`load_timeout`/`boot_timeout` 1.0 秒）。
   - 假 `Screen`：按顺序返回给定的图片字节，用完后一直返回最后一张。
   - 假 `Controller`：把按键和摇杆操作记在列表里，不等待。
   - 假 `Memory`：按地址返回事先给定的字节，把写入记下来；`title_id()` 返回事先给定的值。
   - 三个假设备都记下 `close()` 被调了几次。
   - 三个假设备和 `Session` 都通过 fixture 给测试用，要传参数的（比如图片、地址对应的字节）由 fixture 返回一个创建它的函数。测试文件里不能写 `from conftest import ...`，`importlib` 导入方式下找不到 `conftest`。
   - `tests/` 下原来用到假连接的测试（`tests/flow/` 下的、`tests/test_log.py`、`tests/test_main.py`）都改成用 `Session` 加假设备。
   - `tests/` 下其他引用了 `Switch`、`LairSwitch`、`OutbreakSwitch`，从 `control_switch.device.botbase` 引用 `Frame`，或者从两个脚本的 `switch` 模块引用东西的测试（比如 `MapTypeReader` 的测试里 `cast` 用的类型），import 和类型都改成对应的 `Session`、`LairSession`、`OutbreakSession` 和 `session` 模块；`Frame` 改成从 `control_switch.session` 引用。用 `grep -rnE "LairSwitch|OutbreakSwitch|import .*\bSwitch\b|\.switch import|botbase import .*\bFrame\b" tests --include="*.py"` 找，改完这条搜索没有结果。
   - `tests/test_main.py` 的入口测试具体这样改：假脚本的 `connect()` 换成 `SESSION`，是一个不管传进来什么、都返回用上面的假设备建的 `Session` 的函数，`Session` 的 `notifier` 换成记下 `send` 调用的假对象；`control_switch.__main__.connect_botbase` 换成不连接、直接返回一个假设备的函数，这个假设备只是传给 `SESSION`，不会放进 `Session`。原来的断言不变；原来断言 `close()` 被调了一次的地方，改成看建 `Session` 用的三个假设备：每个各被关了一次。`connect_botbase` 返回的那个假设备不会被关，不用看它。
2. `tests/device/test_base.py`
   - `Botbase` 的实例是 `Screen`、`Controller`、`Memory`。
   - 三个假设备各自符合对应的接口。
3. `tests/device/test_botbase.py`，用一个假的连接（记下发出的命令，按命令返回给定的字节）：
   - `click("A", 0)` 发出 `click A`。
   - `stick` 先发推摇杆的命令，再发回中的命令。
   - `pixel_peek`：第一次返回空、第二次有数据时返回数据；连着三次空抛 `ConnectionError`。
   - `peek(0x10, 0x4)` 发出的命令是 `peek 0x10 0x4`；`peek_absolute`、`pointer_peek` 同样检查命令文本。
   - `pointer_all`：连接的 `pointer_little_endian` 是 `True` 时按小端算，`False` 时按大端算。
   - `poke_absolute` 发出的命令里数据是十六进制。
   - `close()` 调两次不出错。
   - `connect_botbase()`：用 `monkeypatch` 设好环境变量，把两个连接类换成假的，把 `atexit.register`、`signal.signal` 换成记下参数的函数。`SWITCH_CONNECTION=usb` 时建的是 USB 连接，否则建的是 WiFi 连接，用的是 `SWITCH_IP`、`SWITCH_PORT`；注册了一个退出时调用的函数，调用它会关掉返回的 `Botbase`；`SIGTERM`、`SIGHUP` 都注册了处理函数，调用处理函数抛 `SystemExit`，退出码是 128 加信号值。
4. `tests/test_session.py`
   - `click`、`stick` 转到了假 `Controller`；`pixel_peek` 返回假 `Screen` 的图。
   - `memory` 给了就能用；给 `None` 时取 `memory` 抛 `RuntimeError`。
   - `step` 初始是空字符串，`frames` 初始是空列表。
   - 三个设备是同一个对象时，`close()` 只关一次；是三个不同对象时各关一次；`screen` 和 `controller` 是同一个对象、`memory` 是另一个时，两个对象各关一次；`memory` 是 `None` 时 `close()` 不出错，另外两个照常关。
5. `tests/games/test_registry.py`
   - 两个脚本的模块都有 `SESSION`，是 `Session` 的子类；没有 `connect`。
6. `tests/device/test_connection.py`，不连真机。WiFi：把 `socket.create_connection` 换成返回假 socket 的函数（记下 `sendall` 的内容，`recv` 按顺序返回给定的块）。USB：不调 `__init__`，直接给连接放上假的 `out`、`into` 端点（`into.read` 按顺序返回给定的字节）和 `timeout_ms`（随便一个整数，收发都要用它，不放会报 `AttributeError`）；`time.sleep` 换成不等待的函数；`_reconnect` 换成记下调用次数的函数。真的 `_reconnect` 会调 `usb.core.find` 找真设备，找不到时会一直找满 30 秒。
   - `_hex(5)` 是 `"0x5"`，`_hex(0)` 是 `"0x0"`，`_hex(-5)` 是 `"-0x5"`。
   - WiFi：`send("click A")` 发出的是 `b"click A\r\n"`；`request` 读到 `\n` 为止，返回分几块到达也能拼成一行，把这一行十六进制文本解成字节；`recv` 返回空时抛 `ConnectionError`；`title_id()` 返回去掉首尾空白的那一行；`close()` 调两次不出错；`pointer_little_endian` 是 `False`。
   - USB：`send("click A")` 先写 4 字节小端的 9（命令长度加 2），再写命令本身；`request` 先读 4 字节长度，数据分几次到达时读满为止；`send` 第一次抛 `usb.core.USBError` 时重连一次再发；`request` 读返回时 `into.read` 连着两次抛 `USBError`：抛 `ConnectionError`，报错里有「反复断开」，`_reconnect` 被调了 1 次；`usb.core.find` 返回 `None` 时 `_open` 抛 `ConnectionError`，报错里有「找不到 usb-botbase」；`title_id()` 读超时（`usb.core.USBTimeoutError`）返回空字符串，正常时返回 16 位大写十六进制；`pointer_little_endian` 是 `True`。
   - USB 连接的创建和关闭，这几条要调 `__init__`：用 `monkeypatch` 把 `usb.core.find` 换成返回假 USB 设备的函数，`usb.util.dispose_resources` 换成什么都不做的函数。假 USB 设备记下 `reset()` 被调了几次，`set_configuration()` 什么都不做，`get_active_configuration()[(0, 0)]` 返回两个端点，`bEndpointAddress` 分别是 `0x01`（发）和 `0x81`（收）。
     - 创建 USB 连接后，`reset()` 被调了 1 次（创建时先复位一次再打开），发和收的端点都有。
     - `close()` 调了一次 `reset()`，之后 `device` 是 `None`；再调一次 `close()` 不出错，`reset()` 的次数不再增加。
     - `usb.core.find` 一直返回 `None`：创建时抛 `ConnectionError`。创建时会反复找 5 秒，把 `time.monotonic` 换成每次调用都往后走几秒的函数，不要真的等。
7. `tests/games/swsh/lair/test_session.py`：`GameConfig.game_state_file` 指到 pytest 的临时目录，用假设备创建 `LairSession`。假 `Memory` 在 `addresses.items + addresses.item_pouch_offset`、`addresses.items + addresses.ball_pouch_offset` 各放一段道具口袋，每格 4 字节小端，按 `道具编号 | 数量 << 15` 拼：
   - 口袋里有极矿石（道具编号 `dynite_ore_item`，数量 37）时 `ore_count()` 是 37；口袋里没有时是 0。
   - `caught_legends()`：假 `Memory` 在 `addresses.caught_table` 放存档数据块的表（每项 0x20 字节：开头 4 字节编号、`+8` 处 8 字节数据地址），`peek_absolute` 按地址返回打乱过的开关值（用模块里的 `_scramble` 算）。正常读出已抓的神兽和究极异兽解锁了没有；表里找不到某只神兽的编号抛 `RuntimeError`；`ultra_beasts_entry` 那一项编号不对抛 `RuntimeError`；开关值还原后不是 1 或 2 抛 `RuntimeError`。读内存都走 `sw.memory`（假 `Memory` 记下了读的地址）。
   - `ball_counts()`：`base_ball` 和 `legendary_ball` 一样时只有一项；不一样时两项，数量和口袋里的一样；球名不在 `ball_items` 里时不在结果里。
8. 朱紫这次只跟着改、不写测试：`games/sv/blocks.py`、`games/sv/actions.py`、`games/sv/outbreak/steps.py` 不写测试，也不在测试 8 的覆盖率要求里。改动靠 `make typecheck` 和 `load_script("sv/outbreak")` 能加载来确认。
10. `tests/games/swsh/lair/steps/` 下每个步骤一个测试文件（`initialize`、`join`、`path`、`battle`、`catch`、`select_pokemon`）。用 `monkeypatch` 把 `GameConfig` 的 `game_state_file`、`log_dir`、`result_dir`、`catch_dir` 都指到 pytest 的临时目录，同样把 `GameConfig` 的 `timeout` 设成 1.0、`interval` 和 `press_interval` 都设成 0，`data_dir` 指到临时目录（用 `shutil.copytree` 把 `data/swsh` 复制过去；`path` 步骤会写 `lair_event_LUT.json`，不能写仓库里的）（`timeout` 不要比 1 秒短，第一次建 `ImageChecker` 要初始化 OCR），步骤模块里的 `time.sleep` 换成不等待的函数，再用假设备建 `LairSession`，不能读写仓库里真实的文件（`initialize` 会删 `log_dir` 下的文件）。`steps/__init__.py` 用 `from .battle import battle` 这样导出了和模块同名的函数（`battle`、`catch`、`initialize`、`join`、`path`、`select_pokemon`），`control_switch.games.swsh.lair.steps.battle` 这个名字拿到的是函数不是模块：按字符串路径 `monkeypatch.setattr("control_switch.games.swsh.lair.steps.battle.time.sleep", ...)`、`from control_switch.games.swsh.lair.steps import battle`、`import control_switch.games.swsh.lair.steps.battle as battle` 都会出错或拿到函数。要替换步骤模块里的名字时，先用 `模块 = importlib.import_module("control_switch.games.swsh.lair.steps.battle")` 拿到模块对象，再 `monkeypatch.setattr(模块, "名字", ...)`；`time.sleep` 写成 `monkeypatch.setattr(模块.time, "sleep", ...)`。六个步骤模块都一样。`pkhex`、`notifier` 换成假对象，读内存的地方用假 `Memory` 按地址返回给定的字节。判断画面的地方用真机截图（从 `logs/keep/` 里挑，复制到 `tests/images/`）。`logs/keep/` 里只有地图类型、岔路口、路线上的界面、背包客、研究员、树果这些截图，没有战斗、抓宝可梦、选宝可梦界面的截图。没有截图的画面，把 `ImageChecker` 上用到的判断换成按事先给定的顺序返回结果。期望值用改之前的代码跑出来的结果。每个步骤至少测：
    - 正常走完时按过的键和返回的下一步名字。
    - 每个抛错的分支各一条，包括等画面超时抛 `TimeoutError`。
    - `select_pokemon`：只有一只闪光时带走它；多只闪光时发 @全体 的通知后抛 `SystemExit`。
    - `battle`：招式被封住时换一个招式。
    - `join`：读内存走的是 `sw.memory`；`_select_boss` 的四种情况（`target` 是 `None`、在菜单里、不在菜单里、菜单是空的）；选「不指定」时用 `Lair.boss()`；`_check_map_type` 读到的类型和 seed 算的不一样时重新选路线；锁定的图沿用路线；`_read_legends` 读不出来（`caught_legends` 抛 `RuntimeError`）时退回用配置。
    - `path`：旧存档的 `maps` 没有 `layout` 时按 seed 补上；`_save_map`；`_record_events` 走了岔路和没走各一条；`_handle_scientist` 的三种情况（`walker` 是 `None`；下一个事件不是研究员；名字对不上不换）。`path.py` 用 `from ...steps.catch import walker_now` 引用了别的步骤，要换 `walker_now` 时替换 `path` 模块上的名字。
    - `catch`：`_decide` 的几种情况（`walker_now` 返回 `None`；跳过没遇到的研究员；对手对不上只记警告）；`walker_now` 出异常时返回 `None`。
    - `battle`：`Messages`；`_dynamax` 按 A 后没反应时重试；`_loss` 区分超回合和全倒；`_log_turn` 读内存走 `sw.memory`。`_dynamax` 里 `act_until` 的 `interval` 写死了 2.0，这条超时用例至少要等 2 秒，可以接受。假 `pkhex` 的记录要带 `itemName`、`item`、`abilityName`、`abilityNumber`、`nature`、`gender`。
    - `select_pokemon`：战报里的「负（超回合）」，以及有 `stage_score` 时的括号。
11. `tests/test_main.py` 补：把 `control_switch.__main__.connect_botbase` 换成记下调用次数的函数，`main(["run", "没有/这个"])`、`main(["restart", "没有/这个"])` 都抛 `SystemExit`，连接函数一次都没被调用。

## 实现

不能改 `tests/`。

1. 新建 `device/base.py`、`session.py`，按「约定」写。
2. 改 `device/botbase.py`，`device/__init__.py` 导出三个接口。
3. `flow/`、`log.py`、`games/sv/actions.py` 里参数的类型从 `Switch` 改成 `Session`（`games/sv/actions.py` 不要标成 `OutbreakSession`，函数里已有的 `cast(SvConfig, sw.config)` 保留：`actions.py` 引用 `games/sv/outbreak/` 下的东西会造成循环 import）；`flow/wait.py` 的 `Frame` 改成从 `session` 引用。
4. 两个脚本的 `switch.py` 用 `git mv` 改名成 `session.py`，类改名，`__init__.py` 里 `connect()` 换成 `SESSION`。所有引用 `LairSwitch`、`OutbreakSwitch` 或这两个 `switch` 模块的文件，import 的模块路径和类型标注都跟着改。用 `grep -rnE "LairSwitch|OutbreakSwitch|\.switch import" src/control_switch --include="*.py"` 找，现在有这些：
   - `games/swsh/lair/`：`__init__.py`、`map_type_reader.py`、`game_config.py`（第 50 行左右注释里的 `LairSwitch.caught_legends`），`steps/` 下的 `initialize.py`、`join.py`、`path.py`、`battle.py`、`catch.py`、`select_pokemon.py`。
   - `games/sv/outbreak/`：`__init__.py`、`steps.py`。
5. 读写内存的调用改成走 `sw.memory`：
   - `games/swsh/lair/session.py`：`_item_count` 里的 `self.peek`，传给 `Pk8Reader` 的 `self.peek`，`caught_legends` 里的两处 `self.peek` 和两处 `self.peek_absolute`。这几处是 `self.`，下面测试 4 的 grep 搜不到，要逐个确认。
   - `games/swsh/lair/steps/join.py`：两处 `sw.peek`。
   - `games/swsh/lair/steps/battle.py`：`_log_turn` 里的 `sw.peek`。
   - `games/sv/blocks.py`：`SaveBlocks` 接收的改成 `Memory`，创建时传 `sw.memory`。
   - `title_id()`：`games/swsh/lair/steps/initialize.py`、`games/sv/outbreak/steps.py`、`flow/restart.py` 的 `_game_running`。
6. `__main__.py` 按「入口」改。
7. `games/registry.py` 里 `SCRIPTS` 上面的注释，把 `connect()（创建连接）` 改成 `SESSION`（这个脚本的 `Session` 子类）。
8. `README.md` 的「目录」表补上 `session.py`、`device/base.py`；表里「加脚本时在脚本表里加一行」改成写明加脚本时要在脚本的 `__init__.py` 里写 `STEPS`、`START`、`SESSION`，再在脚本表里加一行。

除了上面这些，不改游戏逻辑。

## 测试

下面是至少要过的检查，逐条写出结果。这些之外还要按用户的用法自己找问题。自己找问题时，不运行 `make start`、`make restart`，也不运行不写脚本名或者写了能用的脚本名的 `control-switch run`、`control-switch restart`（包括 `uv run` 和 `python -m control_switch` 的写法），它们会连接 Switch；也不运行 `make find`，它会改写 `.env`。这一节里明确写出的命令除外。命令前面加上 `SWITCH_CONNECTION=wifi SWITCH_IP=127.0.0.1 SWITCH_PORT=1` 的可以运行：命令行上设的环境变量优先于 `.env`，就算去连，也只会连到本机一个没有程序在听的端口，马上报 `Connection refused`。需要连着 Switch 才能确认的，在结果里列出来，交给人在真机上确认。

1. `make test` 全部通过。
2. `make lint` 没有新增的报错。
3. `make typecheck` 0 报错。
4. 下面的搜索都没有结果：
   - `grep -rnE "LairSwitch|OutbreakSwitch|class Switch|def connect\(" src tests --include="*.py"`
   - `grep -rniE "^\s*(from|import)\s.*botbase" src/control_switch --include="*.py" | grep -vE "^src/control_switch/(device/|__main__\.py)"`
   - `grep -rnE "\bsw\.(peek|peek_main|pointer_peek|pointer_all|peek_absolute|poke_absolute|title_id)\(" src --include="*.py"`
   - `grep -rnE "\bself\.(peek|peek_main|pointer_peek|pointer_all|peek_absolute|poke_absolute|title_id)\(" src/control_switch/games --include="*.py"`
5. `grep -rn "isinstance" src/control_switch/device/botbase.py` 里没有用来判断连接类型的。
6. `uv run control-switch run 没有/这个` 退出并列出可以用的脚本名。
7. 先 `git add -A`（只暂存，不提交），然后 `git diff -M HEAD -- src/control_switch/games` 逐个文件看：除了「实现」里写明的改动，没有改坐标、阈值、地址、等待时间、步骤顺序、打分。`git diff -M HEAD -- src/control_switch/games | grep -E '^[-+][^-+].*([0-9]+\.[0-9]+|0x[0-9A-Fa-f]+)'` 列出的每一行都要能对上「实现」里写明的改动。
8. `make coverage` 的输出里，`device/base.py`、`device/botbase.py`、`session.py`、`games/swsh/lair/session.py`、`games/swsh/lair/steps/` 下所有文件，以及「实现」5 改过的其他文件（`games/sv/` 下的除外），没覆盖到的行，要么补上测试，要么逐处写明为什么测不了。`device/botbase.py` 之前没有测全，这次整个文件都要查；`games/swsh/lair/steps/` 之前没有测过，也是整个文件都要查。

## 要在真机上确认的

- `make start` 跑完一局极巨大冒险，战报里的极矿石和球的数量正常。
- `make restart` 能把游戏重启回来。
- WiFi 和 USB 两种连接方式各试一次。
- Switch 没连上（USB 线拔掉，或 WiFi 连不到）时运行 `uv run control-switch run 没有/这个`：马上退出并列出可以用的脚本名，不报连接错误，也不等待连接。
