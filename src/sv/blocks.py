"""朱紫的存档块：在内存里找到块、解密读出来、加密写回去。

游戏运行时整个存档在内存里，按块存放，每块有一个 key，内容用 key 加密。
找块和读写的做法照 Eppin/Sysbot.NET 的 SearchSaveKey、ReadEncryptedBlock 和
PokeViewer.NET 的 WriteEncryptedBlockUint；加解密和解析宝可梦交给 PKHeX 服务。
key 的值来自 PKHeX.Core 的 SaveBlockAccessor9SV。
"""

from typing import Any

from libs import Pkhex, Switch

# 身边已经生成的宝可梦，存档时写入。一共 OVERWORLD_SLOTS 格，每格 OVERWORLD_SLOT_SIZE 字节，开头是 PK9
OVERWORLD = 0x173304D8
OVERWORLD_SLOTS = 20
OVERWORLD_SLOT_SIZE = 0x1D4

# 大量出现，按地图分：正在发生几个（1 字节），以及每一个的击败数和总数（各 4 字节）。
# 帕底亚最多 8 个，北上乡 4 个，蓝莓学园 5 个
OUTBREAK_ACTIVE = {
    "帕底亚": 0x6C375C8A,
    "北上乡": 0xBD7C2A04,
    "蓝莓学园": 0x19A98811,
}
OUTBREAK_KO = {
    "帕底亚": (
        0x4B16FBC2,
        0x4B14BF1F,
        0x4B1CA6E4,
        0x4B1A77D9,
        0x4B23391E,
        0x4B208FBB,
        0x4B28E440,
        0x4B256EF5,
    ),
    "北上乡": (0xB29D7978, 0xB29ADDAD, 0xB298A7D6, 0xB294B833),
    "蓝莓学园": (0x4EF9BC25, 0x4EFBEB30, 0x4EF4036B, 0x4EF6400E, 0x4EED7EC9),
}
OUTBREAK_TOTAL = {
    "帕底亚": (
        0xB7DC495A,
        0xB7DA0CB7,
        0xB7E1F47C,
        0xB7DFC571,
        0xB7E886B6,
        0xB7E49713,
        0xB7EE31D8,
        0xB7EABC8D,
    ),
    "北上乡": (0x9E16873C, 0x9E12A531, 0x9E10DC1A, 0x9E0CEC77),
    "蓝莓学园": (0x4385E0AD, 0x43887C78, 0x437FBB33, 0x4383AAD6, 0x437A1011),
}

# 块表里每一项的长度；项的开头 4 字节是 key，偏移 8 的地方是数据的地址
_ENTRY_SIZE = 48
# 每块数据开头有 1 字节的类型；整块宝可梦数据在类型后面还有 4 字节的长度
_TYPE_SIZE = 1
_OBJECT_HEADER_SIZE = 5

# 加密和解密是同一个操作：和 SCXorShift32（种子是 key）产生的字节逐个异或
_CRYPT = """
byte[] Crypt(uint key, byte[] data)
{
    var rng = new SCXorShift32(key);
    for (var i = 0; i < data.Length; i++)
        data[i] = (byte)(data[i] ^ rng.Next());
    return data;
}
"""
_CRYPT_SCRIPT = (
    _CRYPT
    + """
return Convert.ToHexString(Crypt(
    Input.GetProperty("key").GetUInt32(),
    Convert.FromHexString(Input.GetProperty("data").GetString()!)));
"""
)
_OVERWORLD_SCRIPT = (
    _CRYPT
    + """
var block = Crypt(
    Input.GetProperty("key").GetUInt32(),
    Convert.FromHexString(Input.GetProperty("data").GetString()!));
var header = Input.GetProperty("header").GetInt32();
var slot = Input.GetProperty("slot").GetInt32();
var strings = GameInfo.GetStrings("zh-Hans");
var pokemon = Enumerable.Range(0, (block.Length - header) / slot)
    .Select(i => new PK9(block[(header + i * slot)..(header + i * slot + 0x158)]))
    .Where(pk => pk.Species != 0)
    .Select(pk => new
    {
        species = pk.Species,
        name = strings.specieslist[pk.Species],
        form = pk.Form,
        shiny = pk.IsShiny,
        nature = strings.natures[(int)pk.Nature],
        ivs = new[] { pk.IV_HP, pk.IV_ATK, pk.IV_DEF, pk.IV_SPA, pk.IV_SPD, pk.IV_SPE },
    })
    .ToArray();
return new { size = BitConverter.ToInt32(block, 1), pokemon };
"""
)


class SaveBlocks:
    """读写内存里的存档块。"""

    def __init__(self, sw: Switch, pkhex: Pkhex, pointer: tuple[int, ...]):
        self._sw = sw
        self._pkhex = pkhex
        self._pointer = pointer
        self._table = 0
        # 找到过的块：{key: 数据的地址}
        self._addresses: dict[int, int] = {}

    def locate(self) -> None:
        """按指针链找到块表。游戏重启之后地址会变，要重新找一次。"""
        self._table = self._sw.pointer_all(list(self._pointer))
        self._addresses.clear()

    def _address(self, key: int) -> int:
        """块表按 key 从小到大排，二分找到 key 这一项，返回它的数据的地址。"""
        if key in self._addresses:
            return self._addresses[key]
        if not self._table:
            self.locate()
        bounds = self._sw.peek_absolute(self._table + 8, 16)
        start = int.from_bytes(bounds[:8], "little")
        end = int.from_bytes(bounds[8:], "little")
        while start < end:
            middle = start + ((end - start) // _ENTRY_SIZE // 2) * _ENTRY_SIZE
            found = int.from_bytes(self._sw.peek_absolute(middle, 4), "little")
            if found == key:
                address = int.from_bytes(self._sw.peek_absolute(middle + 8, 8), "little")
                self._addresses[key] = address
                return address
            if found > key:
                end = middle
            else:
                start = middle + _ENTRY_SIZE
        raise RuntimeError(f"存档块表里找不到 {key:#010x}，指针链可能和游戏版本对不上")

    def _crypt(self, key: int, data: bytes) -> bytes:
        return bytes.fromhex(self._pkhex.execute(_CRYPT_SCRIPT, {"key": key, "data": data.hex()}))

    def _read_value(self, key: int, size: int) -> int:
        """读一个数值块：1 字节类型后面跟着 size 字节的小端数。"""
        raw = self._sw.peek_absolute(self._address(key), _TYPE_SIZE + size)
        return int.from_bytes(self._crypt(key, raw)[_TYPE_SIZE:], "little")

    def read_byte(self, key: int) -> int:
        return self._read_value(key, 1)

    def read_int(self, key: int) -> int:
        return self._read_value(key, 4)

    def write_int(self, key: int, value: int) -> None:
        """把一个 4 字节的数值块改成 value。类型那 1 字节照原样写回去。"""
        address = self._address(key)
        plain = self._crypt(key, self._sw.peek_absolute(address, _TYPE_SIZE + 4))
        changed = plain[:_TYPE_SIZE] + value.to_bytes(4, "little")
        self._sw.poke_absolute(address, self._crypt(key, changed))

    def read_overworld(self) -> list[dict[str, Any]]:
        """读身边已经生成的宝可梦，空的格子不算。要先存档，游戏存档时才把它们写进这个块。

        每只是 {species, name, form, shiny, nature, ivs}，name 和 nature 是简体中文。
        """
        size = OVERWORLD_SLOTS * OVERWORLD_SLOT_SIZE
        raw = self._sw.peek_absolute(self._address(OVERWORLD), _OBJECT_HEADER_SIZE + size)
        result = self._pkhex.execute(
            _OVERWORLD_SCRIPT,
            {
                "key": OVERWORLD,
                "data": raw.hex(),
                "header": _OBJECT_HEADER_SIZE,
                "slot": OVERWORLD_SLOT_SIZE,
            },
        )
        if result["size"] != size:
            raise RuntimeError(
                f"身边宝可梦的数据块长度是 {result['size']}，应该是 {size}，"
                "指针链可能和游戏版本对不上"
            )
        return result["pokemon"]
