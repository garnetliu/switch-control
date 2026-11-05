"""游戏相关的配置。"""

# 游戏的语言，对应数据文件里 names、abilities 的键
LANGUAGE = "zh-Hans"
# 要找的传说宝可梦，数据文件里的 name_id
BOSS = "tapu-koko"
# 抓普通对手用的球、抓首领用的球，写游戏里显示的球名
BASE_BALL = "究极球"
LEGENDARY_BALL = "究极球"
# 要不要抓首领。不抓就选「不捕捉」，省一个球
CATCH_BOSS = True
# keep path：锁定一张好打的路线图，每局结束没有闪光可带走就重启游戏，回到存档里同一张图重打。
# 没锁定时，一局打赢、倒下不超过 LOCK_MAX_FAINTS 次、用时不超过 LOCK_MAX_MINUTES 分钟，就锁定这张图
LOCK_MAX_FAINTS = 2
LOCK_MAX_MINUTES = 20.0
# 打赢之后科学家问要不要记录位置时：True 记录；False 停下来，游戏留在这一步，等人决定
RECORD_LOCATION = True
