from control_switch.vision import ImageChecker


def panel_stats(image: ImageChecker) -> list[str]:
    """盒子画面右边面板上六项能力的文字：在评定页是「最棒」「非常好」这些判定词，在能力页是数值。

    顺序是 HP、攻击、防御、速度、特防、特攻。
    """
    areas = (
        ((0.82, 0.195), (0.90, 0.24)),
        ((0.885, 0.305), (0.96, 0.35)),
        ((0.885, 0.405), (0.96, 0.45)),
        ((0.82, 0.47), (0.90, 0.515)),
        ((0.70, 0.405), (0.78, 0.45)),
        ((0.70, 0.305), (0.78, 0.35)),
    )
    return [image.read_text(area) for area in areas]
