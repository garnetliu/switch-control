from control_switch.vision import ImageChecker


def panel_ability(image: ImageChecker) -> str:
    """盒子画面右边面板能力页上的特性。"""
    return image.read_text(((0.76, 0.53), (0.95, 0.585)))
