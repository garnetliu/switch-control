"""通过本机 PKHeX.Core API 解析游戏内的 PK8 记录。"""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any


class Pkhex:
    """调用 PKHeX.Core API 解析 PK8 记录。"""

    DEFAULT_API_URL = "http://127.0.0.1:8787/api/v1/execute"
    RETRY_DELAYS = (1, 2, 4, 8)
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
            checksumValid = pk.ChecksumValid,
            encryptionConstant = pk.EncryptionConstant.ToString("X8"),
        };
    })
    .ToArray();
"""

    def __init__(self, peek: Callable[[int, int], bytes], api_url: str | None = None):
        self._peek = peek
        self._api_url = api_url or os.environ.get("PKHEX_API_URL", self.DEFAULT_API_URL)

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
        body = json.dumps(
            {
                "code": self.PK8_BATCH_SCRIPT,
                "input": {"records": [record.hex() for record in records]},
            }
        ).encode()
        request = urllib.request.Request(
            self._api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            for attempt in range(len(self.RETRY_DELAYS) + 1):
                try:
                    with urllib.request.urlopen(request, timeout=15) as response:
                        payload = json.load(response)
                    break
                except (
                    urllib.error.URLError,
                    TimeoutError,
                    ConnectionError,
                    json.JSONDecodeError,
                ):
                    if attempt == len(self.RETRY_DELAYS):
                        raise
                    time.sleep(self.RETRY_DELAYS[attempt])
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                f"无法调用 PKHeX API（{self._api_url}），请确认 switch-pkhex-api 容器正在运行"
            ) from exc
        if "error" in payload:
            raise RuntimeError(f"PKHeX API 解析失败：{payload['error']}")
        result = payload.get("result")
        if not isinstance(result, list) or len(result) != len(records):
            raise RuntimeError("PKHeX API 返回的记录数量不正确")
        return result
