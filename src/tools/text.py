"""文字比较。"""


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
