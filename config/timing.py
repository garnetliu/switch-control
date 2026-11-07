"""时间相关的配置，单位都是秒。"""

# 游戏里一个 tick 的时长（每秒 12.5 个），按键和摇杆的时长用 tick 数表示
TICK_SECONDS = 0.08
# 两次截图之间的间隔。截图本身要 0.2 秒以上，所以这里可以很小
POLL_INTERVAL = 0.3
# 等一次画面变化的默认超时
DEFAULT_TIMEOUT = 10.0
# 等读盘（进入新界面）的超时
LOAD_TIMEOUT = 30.0
# 一直做一个操作（按键、推摇杆）直到画面满足条件的超时
ACT_TIMEOUT = 60.0
# 超过这么多秒没有日志，发通知提醒可能卡住
STALL_NOTIFY_SECONDS = 600.0
