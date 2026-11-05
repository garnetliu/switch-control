import unicodedata


def levenshtein(a: str, b: str) -> int:
    """两个字符串的编辑距离：把 a 改成 b 最少要增、删、改几个字符。"""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def pad(text: str, width: int, fill: str = " ") -> str:
    """在 text 右边补 fill，补到在终端里占 width 列宽。text 已经够宽就原样返回。

    中文等全角字符占 2 列，str.ljust 按字符个数算，中文会对不齐，所以按显示宽度算。
    """
    return text + fill * max(width - display_width(text), 0)


def display_width(text: str) -> int:
    """text 在终端里占几列：全角字符（中文等）算 2 列，其他算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)
