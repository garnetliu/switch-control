"""把屏幕上识别出的文字匹配到具体的宝可梦。"""

from config.game import LANGUAGE
from lib import data
from tool.text import levenshtein
from typedefs.pokemon import Match


def identify(
    name: str,
    ability: str = "",
    moves: str = "",
    type_ids: list[str] | None = None,
    language: str = LANGUAGE,
) -> Match:
    """把识别出的文字匹配到最像的租借宝可梦。

    name、ability、moves 是屏幕上识别出的文字，某一项没有读就传空字符串。
    type_ids: 屏幕上读到的属性。给了就只在属性完全相同的宝可梦里找，同名的地区形态
    （比如雷丘和阿罗拉雷丘，中文名都是「雷丘」）只能靠它区分；一只都对不上就不按属性筛。
    做法：把识别出的文字拼成一串，和每只租借宝可梦的「名字 + 特性 + 全部招式名」拼出的
    标准文字比编辑距离，取最小的；距离相同取靠前的。
    """
    text = (name + ability + moves).replace("\n", "")
    best: Match | None = None
    candidates = list(data.rental_pokemon().values())
    if type_ids:
        same_types = [p for p in candidates if sorted(p.type_ids) == sorted(type_ids)]
        candidates = same_types or candidates
    for pokemon in candidates:
        expected = pokemon.name(language)
        if ability:
            expected += pokemon.ability(language)
        if moves:
            expected += "".join(move.name(language) for move in pokemon.moves)
        distance = levenshtein(text, expected)
        if best is None or distance < best.distance:
            best = Match(pokemon, distance, text)
    if best is None:
        raise ValueError("没有租借宝可梦数据")
    return best
