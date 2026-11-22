"""control_switch.vision.text：编辑距离、相似度、文字包含判断。期望值取自搬迁前 tools.text 的运行结果。"""

from control_switch.vision.text import contains, levenshtein, similarity


def test_levenshtein_identical_strings_is_zero() -> None:
    """相同的字符串编辑距离是 0。"""
    assert levenshtein("要走哪条路", "要走哪条路") == 0


def test_levenshtein_one_char_different_is_one() -> None:
    """差一个字，编辑距离是 1。"""
    assert levenshtein("要走哪条路", "要走那条路") == 1


def test_levenshtein_empty_string_equals_other_length() -> None:
    """一边是空字符串，编辑距离等于另一边的长度。"""
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "") == 0


def test_contains_exact_substring_is_true() -> None:
    """found 里完整包含 text。"""
    assert contains("你要走哪条路？", "要走哪条路") is True


def test_contains_one_wrong_char_still_true() -> None:
    """识别错一个字（哪 -> 那，相似度 0.8）仍然算包含。"""
    assert contains("要走那条路", "要走哪条路") is True


def test_contains_unrelated_text_is_false() -> None:
    """完全无关的文字不算包含。"""
    assert contains("要走哪条路", "今天天气不错") is False


def test_contains_ignores_whitespace_and_punctuation() -> None:
    """found 里带空白和标点，清掉之后能匹配。"""
    assert contains("  要走，哪条路！", "要走哪条路") is True


def test_contains_found_shorter_than_text_and_too_different_is_false() -> None:
    """found 比 text 短、整体相似度不够（2 个字对 5 个字，约 0.57）时不算包含。"""
    assert contains("走哪", "要走哪条路") is False


def test_contains_found_shorter_than_text_but_similar_is_true() -> None:
    """found 比 text 短、但缺得不多（4 个字对 5 个字，约 0.89）时算包含。"""
    assert contains("要走哪条", "要走哪条路") is True


def test_contains_five_chars_one_wrong_is_exactly_threshold_and_true() -> None:
    """5 个字错 1 个，相似度正好 0.8，达到默认门槛，算包含。"""
    assert contains("abcde", "abcdx") is True


def test_contains_same_pair_with_min_similarity_09_is_false() -> None:
    """同一对字符串，门槛提高到 0.9 时不算包含。"""
    assert contains("abcde", "abcdx", min_similarity=0.9) is False


def test_similarity_identical_is_one() -> None:
    """相同的文字相似度是 1。"""
    assert similarity("abc", "abc") == 1.0


def test_similarity_completely_different_is_zero() -> None:
    """完全不同的文字相似度是 0。"""
    assert similarity("abc", "xyz") == 0.0
