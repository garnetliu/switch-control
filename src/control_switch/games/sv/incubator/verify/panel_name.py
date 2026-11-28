from control_switch.vision import ImageChecker


def panel_name(image: ImageChecker) -> str:
    """盒子画面右边面板顶上的名字：宝可梦名、「蛋」；光标在空格上时是空字符串。"""
    return image.read_text(((0.70, 0.005), (0.86, 0.07)))
