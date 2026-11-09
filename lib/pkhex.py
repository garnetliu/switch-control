"""通过本机 PKHeX.Core API 解析游戏内的 PK8 记录。"""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from typing import Any

from lib.lair import FORM_NAME_IDS
from typedefs.pokemon import Pokemon

DEFAULT_API_URL = "http://127.0.0.1:8787/api/v1/execute"
RETRY_DELAYS = (1, 2, 4, 8)
FORM_IDS_BY_NAME = {name_id: key for key, name_id in FORM_NAME_IDS.items()}
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


def parse_pk8_batch(records: Sequence[bytes]) -> list[dict[str, Any]]:
    """用 PKHeX 解析一批 PK8 原始记录。"""
    if not records:
        return []
    api_url = os.environ.get("PKHEX_API_URL", DEFAULT_API_URL)
    body = json.dumps(
        {"code": PK8_BATCH_SCRIPT, "input": {"records": [record.hex() for record in records]}}
    ).encode()
    request = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                if attempt == len(RETRY_DELAYS):
                    raise
                time.sleep(RETRY_DELAYS[attempt])
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"无法调用 PKHeX API（{api_url}），请确认 switch-pkhex-api 容器正在运行"
        ) from exc
    if "error" in payload:
        raise RuntimeError(f"PKHeX API 解析失败：{payload['error']}")
    result = payload.get("result")
    if not isinstance(result, list) or len(result) != len(records):
        raise RuntimeError("PKHeX API 返回的记录数量不正确")
    return result


def match_pokemon(record: dict[str, Any], candidates: Iterable[Pokemon]) -> Pokemon | None:
    """按游戏 species/form 和四个招式 ID 匹配项目内的宝可梦数据。"""
    if not record.get("checksumValid"):
        return None
    matches = [candidate for candidate in candidates if record_matches_pokemon(record, candidate)]
    if len(matches) > 1:
        raise RuntimeError(
            f"PKHeX 记录无法唯一匹配宝可梦数据：species={record.get('species')} "
            f"form={record.get('form', 0)} moves={record.get('moves')}"
        )
    return matches[0] if matches else None


def record_matches_pokemon(record: dict[str, Any], pokemon: Pokemon) -> bool:
    """比较 PKHeX 的游戏编号与项目数据编号；区域形态编号来自独立的数据集。

    大冒险的最终 boss 有 5 个招式，PK8 记录里只有 4 个招式槽，所以本地招式比记录里多时，
    只要记录里的招式都在本地招式里就算匹配。
    """
    species, form = pokemon_species_form(pokemon)
    if not (
        record.get("checksumValid")
        and record.get("species") == species
        and record.get("form", 0) == form
    ):
        return False
    local_moves = [move.id_num for move in pokemon.moves]
    record_moves = list(record.get("moves", ()))
    if len(local_moves) > len(record_moves):
        return set(record_moves).issubset(local_moves)
    return local_moves == record_moves


def pokemon_species_form(pokemon: Pokemon) -> tuple[int, int]:
    """返回与 PKHeX 一致的基础 species 和 form。"""
    return FORM_IDS_BY_NAME.get(pokemon.name_id, (pokemon.id_num, 0))
