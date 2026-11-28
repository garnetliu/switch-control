import numpy as np

from control_switch.vision import ImageChecker


def panel_shiny(image: ImageChecker) -> bool:
    """盒子画面右边面板上有闪光的星星：星星那一小块三个通道的标准差加起来超过 80。"""
    area = image.crop(((0.878, 0.081), (0.906, 0.127))).reshape(-1, 3)
    return float(np.std(area, axis=0).sum()) > 80.0
