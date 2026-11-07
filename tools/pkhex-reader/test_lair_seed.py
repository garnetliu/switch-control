"""Compare Sword/Shield Lair seed predictions with one live adventure.

Algorithm reference: Decryptu/pokeldn, pokeldn/swsh/lair.py. The table records the
Sword/Shield 1.3.2 RomFS data distributed by that project.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from lib import data, pkhex, switch

SEED_ADDRESS = 0x4514A4B0
NOTE_ADDRESSES = (0x50B12278, 0x50B122B0, 0x50B122E8, 0x50B12320)
CANDIDATE_ADDRESSES = (0x83E93070, 0x83E93300, 0x83E93590)
OPPONENT_ADDRESS = 0x886A95B8
BOSS_POINTER = [0x26365B8, 0x68, 0x78, 0x88, 0xD08, 0x950, 0xD0]
PK8_SIZE = 0x158
PARTNERS = 3  # single-player adventure: three computer teammates
OUTPUT = Path("/private/tmp/lair-seed-test.json")
PRIOR_CAPTURE = Path("/private/tmp/switch-lair-pkhex.json")
TABLE_FILE = ROOT / "data" / "lair_pokemon.json"
MASK64 = (1 << 64) - 1


class Xoroshiro:
    def __init__(self, seed: int):
        self.s0 = seed & MASK64
        self.s1 = 0x82A2B175229D6A5B

    def next_u32(self) -> int:
        s0, s1 = self.s0, self.s1
        result = (s0 + s1) & 0xFFFFFFFF
        s1 ^= s0
        self.s0 = ((s0 << 24 | s0 >> 40) ^ s1 ^ (s1 << 16)) & MASK64
        self.s1 = (s1 << 37 | s1 >> 27) & MASK64
        return result

    def draw(self, top: int) -> int:
        mask = (1 << top.bit_length()) - 1
        while True:
            value = self.next_u32() & mask
            if value <= top:
                return value


def mt19937(seed: int):
    state = [seed]
    for index in range(1, 624):
        previous = state[-1]
        state.append((1812433253 * (previous ^ (previous >> 30)) + index) & 0xFFFFFFFF)
    while True:
        for index in range(624):
            y = (state[index] & 0x80000000) | (state[(index + 1) % 624] & 0x7FFFFFFF)
            state[index] = state[(index + 397) % 624] ^ (y >> 1)
            if y & 1:
                state[index] ^= 0x9908B0DF
        for value in state:
            value ^= value >> 11
            value ^= (value << 7) & 0x9D2C5680
            value ^= (value << 15) & 0xEFC60000
            yield (value ^ (value >> 18)) & 0xFFFFFFFF


def predict(seed: int, rows: list[list]) -> tuple[list[list], list[list]]:
    rng = Xoroshiro(seed)
    picked: list[list] = []

    def pick() -> list:
        random = mt19937(rng.next_u32())
        order = list(range(len(rows)))
        for index in range(len(order)):
            while True:
                offset = next(random) & 0x1FF
                if offset <= len(order) - index - 1:
                    break
            other = index + offset
            order[index], order[other] = order[other], order[index]
        used = {(row[0], row[1]) for row in picked}
        chosen = next(
            rows[index]
            for index in order
            if not rows[index][2] and (rows[index][0], rows[index][1]) not in used
        )
        picked.append(chosen)
        return chosen

    def draw(top: int) -> int:
        return rng.draw(top)

    if PARTNERS > 2:
        draw(27)
    for _ in range(4):
        pick()
    for threshold in (2, 1, 0):
        if PARTNERS > threshold:
            draw(2)
        if threshold:
            pick()
    draw(2)
    draw(9)

    for _ in range(10):
        row = pick()
        if row[4] != picked[-1][5]:
            rng.next_u32()
    return picked[:6], picked[6:]


def row_summary(row: list) -> dict:
    return {
        "species": row[0],
        "form": row[1],
        "boss_row": row[2],
        "level": row[3],
        "types": [row[4], row[5]],
        "moves": row[6:10],
    }


def row_key(record: dict) -> tuple:
    return record["species"], record["form"], tuple(record["moves"])


def get_matches(sw, addresses, rows_by_key):
    raw = [sw.peek(address, PK8_SIZE) for address in addresses]
    parsed = pkhex.parse_pk8_batch(raw)
    output = []
    for index, record in enumerate(parsed):
        if not record.get("checksumValid"):
            output.append({"slot": index + 1, "checksum_valid": False, "raw": raw[index].hex()})
            continue
        key = (record["species"], record["form"], tuple(record["moves"]))
        row = rows_by_key.get(key)
        output.append(
            {
                "slot": index + 1,
                "checksum_valid": True,
                "species": record["species"],
                "form": record["form"],
                "moves": record["moves"],
                "encryption_constant": record["encryptionConstant"],
                "matches_seed_table": row is not None,
                "raw": raw[index].hex(),
            }
        )
    return output


def capture_prior_pool(seed: int, rows_by_key: dict) -> dict | None:
    if not PRIOR_CAPTURE.exists():
        return None
    samples = json.loads(PRIOR_CAPTURE.read_text(encoding="utf-8"))
    matching_samples = [
        sample
        for sample in samples
        if sample.get("seed_le")
        and int.from_bytes(bytes.fromhex(sample["seed_le"]), "little") == seed
    ]
    if not matching_samples:
        return {"matching_seed_samples": 0, "actual_rental_pool": [], "matches_seed": None}
    raw_records = [
        bytes.fromhex(slot["raw"])
        for sample in matching_samples
        for name, slot in sample.get("slots", {}).items()
        if name.startswith("候选 ") and slot.get("raw")
    ]
    parsed = pkhex.parse_pk8_batch(raw_records)
    pool = {
        (record["species"], record["form"], tuple(record["moves"]))
        for record in parsed
        if record.get("checksumValid")
    }
    predicted = {
        (row[0], row[1], tuple(row[6:10]))
        for row in predict(seed, json.loads(TABLE_FILE.read_text(encoding="utf-8"))["rows"])[0]
    }
    return {
        "matching_seed_samples": len(matching_samples),
        "actual_rental_pool": [
            {"species": species, "form": form, "moves": list(moves)}
            for species, form, moves in sorted(pool)
        ],
        "matches_predicted_six": pool == predicted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--continue-sampling",
        action="store_true",
        help="按 A 选择当前默认候选，再读取补位槽，直到收齐六只或超时",
    )
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()

    table = json.loads(TABLE_FILE.read_text(encoding="utf-8"))["rows"]
    sw = switch.connect()
    title_id = sw.title_id()
    seed_raw = sw.peek(SEED_ADDRESS, 8)
    if len(seed_raw) != 8:
        raise RuntimeError(f"seed 读取长度错误：{len(seed_raw)}")
    seed = int.from_bytes(seed_raw, "little")
    rentals, encounters = predict(seed, table)
    rows_by_key = {(row[0], row[1], tuple(row[6:10])): row for row in table}
    initial = get_matches(sw, CANDIDATE_ADDRESSES, rows_by_key)
    opponent_record = pkhex.parse_pk8_batch([sw.peek(OPPONENT_ADDRESS, PK8_SIZE)])[0]
    opponent_key = (
        opponent_record["species"],
        opponent_record["form"],
        tuple(opponent_record["moves"]),
    )
    encounter_keys = {(row[0], row[1], tuple(row[6:10])) for row in encounters}
    actual_opponent = {
        "checksum_valid": opponent_record.get("checksumValid"),
        "species": opponent_record["species"],
        "form": opponent_record["form"],
        "moves": opponent_record["moves"],
        "matches_possible_opponent_pool": opponent_key in encounter_keys,
    }
    try:
        boss_raw = sw.pointer_peek(BOSS_POINTER, PK8_SIZE)
        boss_record = pkhex.parse_pk8_batch([boss_raw])[0]
        actual_boss = {
            "checksum_valid": boss_record.get("checksumValid"),
            "species": boss_record["species"],
            "name_id": next(
                (
                    name
                    for name, pokemon in data.boss_pokemon().items()
                    if pokemon.id_num == boss_record["species"]
                ),
                None,
            ),
            "form": boss_record["form"],
            "moves": boss_record["moves"],
        }
    except Exception as exc:
        actual_boss = {"error": f"{type(exc).__name__}: {exc}"}
    notes = []
    for slot, address in enumerate(NOTE_ADDRESSES, 1):
        raw = sw.peek(address, 2)
        species = int.from_bytes(raw, "little")
        boss_name = next(
            (name for name, pokemon in data.boss_pokemon().items() if pokemon.id_num == species),
            None,
        )
        notes.append(
            {"slot": slot, "address": hex(address), "species": species, "boss_name": boss_name}
        )

    result = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title_id": title_id,
        "seed_address": hex(SEED_ADDRESS),
        "seed_raw": seed_raw.hex(),
        "seed_u64": f"{seed:016X}",
        "cpu_teammates": PARTNERS,
        "predicted_rental_pool": [row_summary(row) for row in rentals],
        "predicted_possible_opponents": [row_summary(row) for row in encounters],
        "predicted_boss_from_seed": None,
        "lair_species_notes": notes,
        "initial_candidate_memory": initial,
        "initial_three_match_prediction": (
            all(item.get("checksum_valid") and item.get("matches_seed_table") for item in initial)
            and [row_key(item) for item in initial]
            == [row_key(row_summary(row)) for row in rentals[:3]]
            if all(item.get("checksum_valid") for item in initial)
            else None
        ),
        "actual_battle_opponent": actual_opponent,
        "actual_final_boss_memory": actual_boss,
        "prior_rental_capture_same_seed": capture_prior_pool(seed, rows_by_key),
        "actual_rental_pool": [],
    }

    if args.continue_sampling:
        sw.click("A", 0)
        last_raw = [bytes.fromhex(item["raw"]) for item in initial]
        seen = {
            (item["species"], item["form"], tuple(item["moves"]))
            for item in initial
            if item.get("checksum_valid")
        }
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and len(seen) < 6:
            current_raw = [sw.peek(address, PK8_SIZE) for address in CANDIDATE_ADDRESSES]
            changed = [
                (index, raw) for index, raw in enumerate(current_raw) if raw != last_raw[index]
            ]
            last_raw = current_raw
            if changed:
                parsed = pkhex.parse_pk8_batch([raw for _, raw in changed])
                for (_, raw), record in zip(changed, parsed):
                    if not record.get("checksumValid"):
                        continue
                    key = (record["species"], record["form"], tuple(record["moves"]))
                    seen.add(key)
            result["actual_rental_pool"] = [
                {
                    "species": species,
                    "form": form,
                    "moves": list(moves),
                    "matches_seed_table": (species, form, moves) in rows_by_key,
                }
                for species, form, moves in sorted(seen)
            ]
            OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(0.2)
        predicted_keys = {row_key(row_summary(row)) for row in rentals}
        result["rental_pool_matches_seed"] = seen == predicted_keys

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in ("initial_candidate_memory",)
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"完整记录：{OUTPUT}")


if __name__ == "__main__":
    main()
