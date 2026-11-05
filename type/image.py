"""截图相关的共用类型。"""

# 区域，比例坐标 ((左, 上), (右, 下))，数值是占图片宽高的比例，和分辨率无关
Rect = tuple[tuple[float, float], tuple[float, float]]
# 颜色，OpenCV 的 HSV：H 取 0 到 180，S、V 取 0 到 255
Hsv = tuple[int, int, int]
