"""文字比较。"""

import re
from difflib import SequenceMatcher


def contains(found: str, text: str, min_similarity: float = 0.8) -> bool:
    """识别出的文字 found 里有没有 text。

    去掉空白和标点后，在 found 里滑一个和 text 等长的窗口，
    任何一处相似度达到 min_similarity 就算有。
    """
    found, text = (re.sub(r"[\s，。！？、,.!?…：:]", "", value) for value in (found, text))
    window = len(text)
    return any(
        SequenceMatcher(None, found[start:start + window], text).ratio() >= min_similarity
        for start in range(max(1, len(found) - window + 1))
    )


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
