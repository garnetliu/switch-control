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

- `games/swsh/lair/switch.py` 的 `LairSwitch`：加了 `game`、`data`、`pkhex`、`ore_count()`、`ball_counts()`。
- `games/sv/outbreak/switch.py` 的 `OutbreakSwitch`：加了 `blocks`。

每个脚本的 `__init__.py` 有 `STEPS`、`START`、`connect()`。

## 约定

### `device/base.py`：三个接口

用 `typing.Protocol`，加 `@runtime_checkable`。方法的参数和返回值和现在 `Switch` 上的一样。

| 接口 | 方法 |
|---|---|
| `Screen` | `pixel_peek() -> bytes`、`close()` |
| `Controller` | `click(button, delay=0.15)`、`stick(side, x, y, hold)`、`press_stick(side, x, y)`、`release_stick(side)`、`close()` |
| `Memory` | `title_id() -> str`、`peek(offset, size)`、`peek_main(offset, size)`、`pointer_peek(jumps, size)`、`pointer_all(jumps) -> int`、`peek_absolute(address, size)`、`poke_absolute(address, data)`、`close()` |

### `device/botbase.py`

- 类改名 `Botbase`，三个接口都实现。构造时传入一个连接：`Botbase(connection)`。里面不再有 `config`、`step`、`frames`、`notifier`。
- 两个连接类各加一个属性 `pointer_little_endian`：USB 是 `True`，WiFi 是 `False`。`pointer_all` 用它判断字节序，不再用 `isinstance`。
- 新增函数 `connect_botbase() -> Botbase`：做现在 `Switch._connect` 做的事（读环境变量、建连接、注册退出时关闭和信号处理）。
- `close()` 调用多次不出错。

### `session.py`

- `Frame` 搬到这里。
- `Session(config, screen, controller, memory)`，`memory` 可以是 `None`。
- 属性：`config`、`step`（初始 `""`）、`frames`（初始空列表）、`notifier`、`screen`、`controller`。
- `click`、`stick`、`press_stick`、`release_stick` 转给 `controller`；`pixel_peek` 转给 `screen`。步骤里 `sw.click(...)` 的写法不变。
- `memory` 是一个属性：有就返回，是 `None` 时抛 `RuntimeError`，说明这个脚本要读内存但没有配置。
- 读写内存不在 `Session` 上转发，调用的地方改成 `sw.memory.peek(...)` 这种写法。
- `close()`：三个设备是同一个对象时只关一次。

### 脚本

| 原来 | 改成 |
|---|---|
| `games/swsh/lair/switch.py` 的 `LairSwitch(Switch)` | `games/swsh/lair/session.py` 的 `LairSession(Session)` |
| `games/sv/outbreak/switch.py` 的 `OutbreakSwitch(Switch)` | `games/sv/outbreak/session.py` 的 `OutbreakSession(Session)` |
| 脚本 `__init__.py` 里的 `connect()` | 换成 `SESSION`，值是上面的类 |

- `LairSession(screen, controller, memory)`、`OutbreakSession(screen, controller, memory)`，里面自己创建配置。
- `device/__init__.py` 导出 `Screen`、`Controller`、`Memory`。`device` 外面的代码只引用这三个接口；只有 `__main__.py` 可以引用 `connect_botbase`。

### 入口

`__main__.py` 里：`botbase = connect_botbase()`，然后 `sw = script.SESSION(botbase, botbase, botbase)`。

## 写测试

只能改 `tests/`。

1. `tests/conftest.py`：把原来假的连接换成三个假设备和一个 `Session`。
   - 假 `Screen`：按顺序返回给定的图片字节，用完后一直返回最后一张。
   - 假 `Controller`：把按键和摇杆操作记在列表里，不等待。
   - 假 `Memory`：按地址返回事先给定的字节，把写入记下来。
   - 三个假设备都记下 `close()` 被调了几次。
   - `tests/flow/` 下现有的测试改成用 `Session` 加假设备。
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
4. `tests/test_session.py`
   - `click`、`stick` 转到了假 `Controller`；`pixel_peek` 返回假 `Screen` 的图。
   - `memory` 给了就能用；给 `None` 时取 `memory` 抛 `RuntimeError`。
   - `step` 初始是空字符串，`frames` 初始是空列表。
   - 三个设备是同一个对象时，`close()` 只关一次；是三个不同对象时各关一次。
5. `tests/games/test_registry.py`
   - 两个脚本的模块都有 `SESSION`，是 `Session` 的子类；没有 `connect`。

## 实现

不能改 `tests/`。

1. 新建 `device/base.py`、`session.py`，按「约定」写。
2. 改 `device/botbase.py`，`device/__init__.py` 导出三个接口。
3. `flow/`、`log.py` 里参数的类型从 `Switch` 改成 `Session`；`flow/wait.py` 的 `Frame` 改成从 `session` 引用。
4. 两个脚本的 `switch.py` 用 `git mv` 改名成 `session.py`，类改名，`__init__.py` 里 `connect()` 换成 `SESSION`。步骤文件里的类型标注跟着改名。
5. 读写内存的调用改成走 `sw.memory`：
   - `games/swsh/lair/session.py`：`_item_count` 里的 `self.peek`，以及传给 `Pk8Reader` 的 `self.peek`。
   - `games/swsh/lair/steps/join.py`：两处 `sw.peek`。
   - `games/sv/blocks.py`：`SaveBlocks` 接收的改成 `Memory`，创建时传 `sw.memory`。
   - `title_id()`：`games/swsh/lair/steps/initialize.py`、`games/sv/outbreak/steps.py`、`flow/restart.py` 的 `_game_running`。
6. `__main__.py` 按「入口」改。
7. `README.md` 里提到 `connect()` 或 `LairSwitch` 的地方跟着改。

除了上面这些，不改游戏逻辑。

## 测试

下面是至少要过的检查，逐条写出结果。这些之外还要按用户的用法自己找问题。

1. `make test` 全部通过。
2. `make lint` 没有新增的报错。
3. `make typecheck` 0 报错。
4. 下面的搜索都没有结果：
   - `grep -rnE "LairSwitch|OutbreakSwitch|class Switch|def connect\(" src tests`
   - `grep -rnE "from control_switch\.device\.botbase" src --include="*.py" | grep -v "__main__.py"`
   - `grep -rnE "\bsw\.(peek|peek_main|pointer_peek|pointer_all|peek_absolute|poke_absolute|title_id)\(" src`
5. `grep -rn "isinstance" src/control_switch/device/botbase.py` 里没有用来判断连接类型的。
6. `uv run control-switch run 没有/这个` 退出并列出可以用的脚本名。

## 要在真机上确认的

- `make start` 跑完一局极巨大冒险，战报里的极矿石和球的数量正常。
- `make start script=sv/outbreak` 能读到身边的宝可梦。
- `make restart` 能把游戏重启回来。
- WiFi 和 USB 两种连接方式各试一次。
