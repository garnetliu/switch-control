"""项目里的目录。"""

from pathlib import Path

# 数据文件和图片资源
DATA_DIR = Path(__file__).parent.parent / "data"
# 上一局的状态文件，keep path 时下一局用它核对画面、沿用结果，见 lib/run.py
STATE_FILE = Path(__file__).parent.parent / "state" / "run.json"
# 日志和出错时的截图
LOG_DIR = Path(__file__).parent.parent / "logs"
# 每局结束时的战果截图（带走界面、资料页），用来事后核对闪光判定
CATCH_DIR = LOG_DIR / "catches"
