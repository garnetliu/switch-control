import numpy as np

# 区域，比例坐标 ((左, 上), (右, 下))
Rect = tuple[tuple[float, float], tuple[float, float]]
# 颜色，OpenCV 的 HSV：H 取 0 到 180，S、V 取 0 到 255
Hsv = tuple[int, int, int]
# 一张画面：botbase 给的是 JPEG 字节；采集卡给的是读到的那一帧（BGR 数组），不编码
Picture = bytes | np.ndarray
