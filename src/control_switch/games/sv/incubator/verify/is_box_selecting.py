from control_switch.vision import ImageChecker


def is_box_selecting(image: ImageChecker) -> bool:
    """盒子里的选择模式（按过减号、Y，或者拿起了一整列）：底栏中间那些按键提示都没有了，只剩右边的「返回」。

    底栏中间白色像素占比低于 0.01 就算。
    """
    return image.color_ratio(((0.391, 0.939), (0.791, 0.986)), (0, 0, 200), (180, 40, 255)) < 0.01
