"""项目里的目录。"""

from pathlib import Path

# 数据文件和图片资源
DATA_DIR = Path(__file__).parent.parent / "data"
# 上一局的状态文件，keep path 时下一局用它核对画面、沿用结果，见 lib/run.py
STATE_FILE = Path(__file__).parent.parent / "state" / "run.json"
# 日志和出错时的截图
LOG_DIR = Path(__file__).parent.parent / "logs"
# path 在路上等下一个界面时，认不出的画面截图，见 autostep/path.py 的 _watch
UNKNOWN_DIR = LOG_DIR / "unknown"
# 战斗中每秒一张的截图，文件名以「第几场-第几回合」开头，见 autostep/battle.py 的 _wait_turn
BATTLE_DIR = LOG_DIR / "battle"
# 调试用：每次检查截图时框出检查区域的图，环境变量 SAVE_CHECKS=1 时才存，见 lib/debug_checker.py
CHECK_DIR = LOG_DIR / "checks"
# 冒险开场镜头往上移时的每一帧，文件名写着这一帧认出的属性，见 autostep/join.py 的 _watch_intro_pan
MAP_PAN_DIR = LOG_DIR / "mappan"
# 每局结束时的战果截图（带走界面、资料页），用来事后核对闪光判定
CATCH_DIR = LOG_DIR / "catches"
