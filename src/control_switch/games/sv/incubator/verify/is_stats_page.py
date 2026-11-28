from control_switch.vision import ImageChecker


def is_stats_page(image: ImageChecker) -> bool:
    """盒子画面右边面板在能力页：特性那一行的标签是「特性」（评定页这里是「性格」）。"""
    return "特性" in image.read_text(((0.655, 0.53), (0.74, 0.585)))
