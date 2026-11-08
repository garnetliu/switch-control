"""项目里的目录。"""

from pathlib import Path

# 数据文件和图片资源
DATA_DIR = Path(__file__).parent.parent / "data"
# 上一局的状态文件，keep path 时下一局用它核对画面、沿用结果，见 lib/run.py
STATE_FILE = Path(__file__).parent.parent / "state" / "run.json"
# 运行状态快照：YAML 文件 run/game.yaml
GAME_STATE_FILE = Path(__file__).parent.parent / "run" / "game.yaml"
# 日志和出错时的截图
LOG_DIR = Path(__file__).parent.parent / "logs"
# 调试用：每次检查截图时框出检查区域的图，环境变量 SAVE_CHECKS=1 时才存，见 lib/debug_checker.py
CHECK_DIR = LOG_DIR / "checks"
# 每局结束时的战果截图（带走界面、资料页），用来事后核对闪光判定
CATCH_DIR = LOG_DIR / "catches"
