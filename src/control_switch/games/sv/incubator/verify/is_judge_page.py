from control_switch.vision import ImageChecker

from .panel_stats import panel_stats


def is_judge_page(image: ImageChecker) -> bool:
    """盒子画面右边面板在评定页：六项能力里至少 4 项读到「最棒」「非常好」这些判定词。"""
    words = ("最棒", "了不起", "非常好", "相当好", "一般般", "也许不行")
    return sum(any(word in text for word in words) for text in panel_stats(image)) >= 4
