"""通过 PKHeX.Core API 解析游戏内的 PK8 记录。"""

import time
from collections.abc import Callable, Sequence
from typing import Any

from libs import Pkhex


class Pk8Reader:
    """从内存读 PK8 记录并解析。"""

    PK8_SIZE = 0x158
    READ_ATTEMPTS = 16
    READ_INTERVAL = 0.5
    PK8_BATCH_SCRIPT = """
return Input.GetProperty("records").EnumerateArray()
    .Select((record, index) =>
    {
        var pk = new PK8(Convert.FromHexString(record.GetString()!));
        return new
        {
            index,
            species = pk.Species,
            form = pk.Form,
            moves = new[] { pk.Move1, pk.Move2, pk.Move3, pk.Move4 },
            pp = new[] { pk.Move1_PP, pk.Move2_PP, pk.Move3_PP, pk.Move4_PP },
            hp = pk.Stat_HPCurrent,
            maxHp = pk.Stat_HPMax,
            level = pk.CurrentLevel,
            ivs = new[] { pk.IV_HP, pk.IV_ATK, pk.IV_DEF, pk.IV_SPA, pk.IV_SPD, pk.IV_SPE },
            evs = new[] { pk.EV_HP, pk.EV_ATK, pk.EV_DEF, pk.EV_SPA, pk.EV_SPD, pk.EV_SPE },
            checksumValid = pk.ChecksumValid,
            encryptionConstant = pk.EncryptionConstant.ToString("X8"),
        };
    })
    .ToArray();
"""

    def __init__(self, pkhex: Pkhex, peek: Callable[[int, int], bytes]):
        self._pkhex = pkhex
        self._peek = peek

    def read_pk8(self, addresses: Sequence[int]) -> list[dict[str, Any]]:
        """按地址读取一批 PK8；校验和不对就隔一会儿重读。"""
        for attempt in range(self.READ_ATTEMPTS):
            records = self.parse_pk8_batch(
                [self._peek(address, self.PK8_SIZE) for address in addresses]
            )
            if all(record["checksumValid"] for record in records):
                return records
            if attempt < self.READ_ATTEMPTS - 1:
                time.sleep(self.READ_INTERVAL)
        raise RuntimeError("PK8 内存记录校验失败")

    def parse_pk8_batch(self, records: Sequence[bytes]) -> list[dict[str, Any]]:
        """用 PKHeX 解析一批 PK8 原始记录。"""
        if not records:
            return []
        result = self._pkhex.execute(
            self.PK8_BATCH_SCRIPT, {"records": [record.hex() for record in records]}
        )
        if not isinstance(result, list) or len(result) != len(records):
            raise RuntimeError("PKHeX API 返回的记录数量不正确")
        return result
