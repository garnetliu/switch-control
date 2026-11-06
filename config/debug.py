"""调试用的配置。"""

# 环境变量 SAVE_CHECKS=1 时，这几步里每次检查截图都会框出检查区域存一张图（见 lib/debug_checker.py）。
# 步骤名就是 main.py 里的 initialize、join、path、battle、catch、select_pokemon。
# 存的图很多（光 join 一步就有几百张、两百多 MB），只开要查的那几步
SAVE_CHECK_STEPS: tuple[str, ...] = ("initialize",)
