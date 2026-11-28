import cv2

from control_switch.vision import ImageChecker


def operation_row(image: ImageChecker) -> int:
    """盒子里按 A 出来的操作菜单（移动、查看能力、携带持有物、标记、放生、取消）选中的是第几行；认不出返回 -1。

    选中那行左边有个向右的渐变箭头，黄绿色那一段是又窄又高的长条（宽高比不超过 0.8）。
    菜单在格子右边，横向位置跟着格子变，所以只看箭头在哪一行：第 0 行中心在 0.222，每行隔 0.0556。
    """
    area = ((0.20, 0.19), (0.95, 0.53))
    image.mark(area)
    height, width = image.bgr.shape[:2]
    (left, top), (right, bottom) = area
    x0, y0, x1, y1 = (
        round(left * width),
        round(top * height),
        round(right * width),
        round(bottom * height),
    )
    mask = cv2.inRange(
        cv2.cvtColor(image.bgr[y0:y1, x0:x1], cv2.COLOR_BGR2HSV), (32, 150, 200), (48, 255, 255)
    )
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    # 箭头黄绿色那一段至少占整个画面的 0.0001
    min_area = 0.0001 * height * width
    best: tuple[int, float] | None = None
    for i in range(1, count):
        _, _, w, h, size = (int(value) for value in stats[i])
        if size < min_area or w / h > 0.8:
            continue
        if best is None or size > best[0]:
            best = (size, (y0 + float(centroids[i][1])) / height)
    if best is None:
        return -1
    row = round((best[1] - 0.222) / 0.0556)
    return row if 0 <= row < 6 else -1
