"""游戏相关的配置。"""

# 游戏的语言，对应数据文件里 names、abilities 的键
LANGUAGE = "zh-Hans"
# 要找的传说宝可梦，数据文件里的 name_id。不在传说菜单里时改成刷菜单的第一项（见 join._select_target）
BOSS = "solgaleo"
# 抓普通对手用的球、抓首领用的球，写游戏里显示的球名
BASE_BALL = "究极球"
LEGENDARY_BALL = "究极球"
# 要不要抓首领。不抓就选「不捕捉」，省一个球
CATCH_BOSS = True
# keep path：锁定一张好打的路线图，每局结束没有闪光可带走就重启游戏，回到存档里同一张图重打。
# 一局打赢、倒下不超过 LOCK_MAX_FAINTS 次、用时不超过 LOCK_MAX_MINUTES 分钟，就保持/锁定这张图
LOCK_MAX_FAINTS = 1
LOCK_MAX_MINUTES = 12.0
# 锁定的图：打满 LOCK_WINDOW_ROUNDS 局之前只算失败次数，失败 LOCK_EARLY_FAILS 次就解锁；
# 打满之后看最近 LOCK_WINDOW_ROUNDS 局的胜率，低于 LOCK_MIN_WIN_RATE 也解锁。
# 失败指最后的首领没打过，不需要连续失败
LOCK_WINDOW_ROUNDS = 10
LOCK_EARLY_FAILS = 2
LOCK_MIN_WIN_RATE = 0.9
# 打赢之后科学家问要不要记录位置时：True 记录；False 停下来，游戏留在这一步，等人决定
RECORD_LOCATION = True
