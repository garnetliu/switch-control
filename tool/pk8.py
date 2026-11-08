"""从 Switch 内存读 PK8 记录，交给 PKHeX 解析、校验并匹配项目里的宝可梦数据。"""

from collections.abc import Iterable, Sequence
from typing import Any

from lib import pkhex, switch
from type.pokemon import Pokemon


def read(
    addresses: Sequence[int], candidates: Iterable[Pokemon]
) -> list[tuple[bytes, dict[str, Any], Pokemon | None]]:
    """读取一组地址上的 PK8 记录，解析并匹配。

    返回 [(原始字节, PKHeX 记录, 匹配到的宝可梦或 None)]，顺序和 addresses 一致。
    """
    raw_records = [switch.get().peek(address, 0x158) for address in addresses]
    candidates = list(candidates)
    parsed = pkhex.parse_pk8_batch(raw_records)
    return [
        (raw, record, pkhex.match_pokemon(record, candidates))
        for raw, record in zip(raw_records, parsed)
    ]
