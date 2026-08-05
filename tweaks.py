import struct
from dataclasses import dataclass
from utils import level_const_name_to_int, level_num_to_const_name
from typing import Dict, List


class TweakValue(int):
    def __new__(cls, value: int, default: int):
        obj = super().__new__(cls, value)
        obj._default = default
        return obj

    def is_modified(self) -> bool:
        return self != self._default


class TweakableValues:
    TWEAKS: Dict[str, Dict] = {}
    LUA_TABLE_NAME: str = ""

    def __init__(self):
        for py_name, tweak_info in self.TWEAKS.items():
            # Expect structured dict format; raise if missing
            default = tweak_info["default"]
            self.__dict__[py_name] = TweakValue(default, default)

    def __setattr__(self, name, value):
        if name in self.TWEAKS:
            tweak_info = self.TWEAKS[name]
            default = tweak_info["default"]
            self.__dict__[name] = TweakValue(value, default)
        else:
            super().__setattr__(name, value)

    def is_modified(self, field_name: str) -> bool:
        val = getattr(self, field_name, None)
        if val is not None and hasattr(val, "is_modified"):
            return val.is_modified()
        return False

    def get_tweaks_lua(self) -> List[str]:
        lines = []
        for py_name, tweak_info in self.TWEAKS.items():
            # Expect structured dict format
            lua_name = tweak_info.get("lua_name") or tweak_info.get("name")
            converter = tweak_info.get("converter")

            current_val = getattr(self, py_name)
            if current_val.is_modified():
                if converter:
                    out_val = converter(int(current_val))
                else:
                    out_val = current_val
                lines.append(f"{self.LUA_TABLE_NAME}.{lua_name} = {out_val}\n")
        return lines


class LevelValues(TweakableValues):
    # This makes it easy to add level-based tweaks that automatically
    # appear in tweaks.lua if their values differ from the default.
    LUA_TABLE_NAME = "gLevelValues"
    TWEAKS = {
        # No ROM backing; manually set by the user when needed.
        "lowest_vtx_height": {
            "default": -11000,
            "lua_name": "floorLowerLimit",
        },
        "highest_vtx_height": {
            "default": 20000,
            "lua_name": "cellHeightLimit",
        },
        # Entry level: read from ROM at 0x6D6A (big-endian u16) when available.
        "entry_level": {
            "default": level_const_name_to_int["LEVEL_CASTLE_GROUNDS"],
            "lua_name": "entryLevel",
            "converter": lambda v: level_num_to_const_name.get(v, f"LEVEL_UNKNOWN_{v}"),
            "type": ">H",
            "addr": 0x6D6A,
            "len": 2,
            # Only read entry_level when the ROM contains the expected marker at 0x6D68
            "guard": {"addr": 0x6D68, "bytes": b"\x24\x05"},
        },
        "wing_cap_duration": {
            "default": 1800,
            "lua_name": "wingCapDuration",
            "type": ">H",
            "addr": 0xAC22,
            "len": 2,
        },
        "metal_cap_duration": {
            "default": 600,
            "lua_name": "metalCapDuration",
            "type": ">H",
            "addr": 0xAC0A,
            "len": 2,
        },
        "vanish_cap_duration": {
            "default": 600,
            "lua_name": "vanishCapDuration",
            "type": ">H",
            "addr": 0xABF2,
            "len": 2,
        },
        "wing_cap_duration_totwc": {
            "default": 1200,
            "lua_name": "wingCapDurationTotwc",
            "type": ">H",
            "addr": 0x4A7A,
            "len": 2,
        },
        "metal_cap_duration_cotmc": {
            "default": 600,
            "lua_name": "metalCapDurationCotmc",
            "type": ">H",
            "addr": 0x4A5E,
            "len": 2,
        },
        "vanish_cap_duration_vcutm": {
            "default": 600,
            "lua_name": "vanishCapDurationVcutm",
            "type": ">H",
            "addr": 0x4A96,
            "len": 2,
        },
        "coins_required_for_coin_star": {
            "default": 100,
            "lua_name": "coinsRequiredForCoinStar",
            "type": ">H",
            "addr": 0x8BBE,
            "len": 2,
        },
    }


class BehaviorValues(TweakableValues):
    LUA_TABLE_NAME = "gBehaviorValues"
    TWEAKS = {
        "koopa_bob_agility": {
            "default": 4,
            "lua_name": "KoopaBobAgility",
            "type": ">f",
            "addr": 0xB821A,
            "len": 4,
        },
        "koopa_thi_agility": {
            "default": 6,
            "lua_name": "KoopaThiAgility",
            "type": ">f",
            "addr": 0xB8202,
            "len": 4,
        },
        "koopa_catchup_agility": {
            "default": 8,
            "lua_name": "KoopaCatchupAgility",
            "type": ">f",
            "addr": 0xB81D6,
            "len": 4,
        },
        "toad_star_1_requirement": {
            "default": 12,
            "lua_name": "ToadStar1Requirement",
            "type": ">H",
            "addr": 0x3199A,
            "len": 2,
        },
        "toad_star_2_requirement": {
            "default": 25,
            "lua_name": "ToadStar2Requirement",
            "type": ">H",
            "addr": 0x319CE,
            "len": 2,
        },
        "toad_star_3_requirement": {
            "default": 35,
            "lua_name": "ToadStar3Requirement",
            "type": ">H",
            "addr": 0x31A02,
            "len": 2,
        },
        "mips_star_1_requirement": {
            "default": 15,
            "lua_name": "MipsStar1Requirement",
            "type": ">B",
            "addr": 0xB34CB,
            "len": 1,
        },
        "mips_star_2_requirement": {
            "default": 50,
            "lua_name": "MipsStar2Requirement",
            "type": ">B",
            "addr": 0xB3523,
            "len": 1,
        },
    }


@dataclass(frozen=True)
class StarEntry:
    offsets: tuple[int, ...]
    fmt: str = ">fff"
    editor_offset: int | None = None
    sentinel_check: bool = True

    def read(self, rom_bytes: memoryview, use_editor: bool):
        rom_len = len(rom_bytes)

        # Special case: coordinate triples stored as separate shorts
        if self.fmt == ">h":
            values = []
            for offset in self.offsets:
                if offset < 0 or offset + 2 > rom_len:
                    return None
                values.append(struct.unpack_from(">h", rom_bytes, offset)[0])
            return tuple(values)

        # Standard float vec3
        offset = (
            self.editor_offset if use_editor and self.editor_offset is not None else self.offsets[0]
        )

        fmt_size = struct.calcsize(self.fmt)
        if offset < 0 or offset + fmt_size > rom_len:
            return None

        if self.sentinel_check:
            if offset + 4 > rom_len:
                return None
            marker = struct.unpack_from(">L", rom_bytes, offset)[0]
            if marker == 0x01010101:
                return None

        return struct.unpack_from(self.fmt, rom_bytes, offset)


# SM64Lib/SM64Lib/Objects/StarPositionAddress.py
STAR_SCHEMA: dict[str, StarEntry] = {
    # Koopa exceptions (stored as individual shorts)
    "KoopaBobStarPos": StarEntry(
        offsets=(0xED868, 0xED86A, 0xED86C),
        fmt=">h",
        sentinel_check=False,
    ),
    "KoopaThiStarPos": StarEntry(
        offsets=(0xED878, 0xED87A, 0xED87C),
        fmt=">h",
        sentinel_check=False,
    ),
    # Standard boss / event stars
    "KingBobombStarPos": StarEntry((0x1204F00,)),
    "KingWhompStarPos": StarEntry((0x1204F10,)),
    "EyerockStarPos": StarEntry((0x1204F20,)),
    "BigBullyStarPos": StarEntry((0x1204F30,)),
    "ChillBullyStarPos": StarEntry((0x1204F40,)),
    "BigPiranhasStarPos": StarEntry((0x1204F50,)),
    "TuxieMotherStarPos": StarEntry((0x1204F60,)),
    "WigglerStarPos": StarEntry((0x1204F70,)),
    "PssSlideStarPos": StarEntry((0x1204F80,)),
    "RacingPenguinStarPos": StarEntry((0x1204F90,)),
    "TreasureChestStarPos": StarEntry((0x1204FA0,)),
    "GhostHuntBooStarPos": StarEntry((0x1204FAC,)),
    "KleptoStarPos": StarEntry((0x1204FC4,)),
    "MerryGoRoundStarPos": StarEntry((0x1204FB8,)),
    "MrIStarPos": StarEntry((0x1204FD0,)),
    "BigBullyTrioStarPos": StarEntry((0x1204FE4,)),
    # Different offsets between ROM Manager and Editor
    "BalconyBooStarPos": StarEntry(
        offsets=(0x1204FDC,),
        editor_offset=0x1204FD8,
    ),
    # Other stars (not currently implemented)
    # "TreasureJrbStarPos": StarEntry((0x00000000,)),
    # "MantaRayStarPos": StarEntry((0x00000000,)),
    # "SnowmanHeadStarPos": StarEntry((0x00000000,)),
    # "CcmSlideStarPos": StarEntry((0x00000000,)),
    # "UkikiCageStarPos": StarEntry((0x00000000,)),
    # "UnagiStarPos": StarEntry((0x00000000,)),
    # "JetstreamRingStarPos": StarEntry((0x00000000,)),
}


def build_star_position_tweaks():
    from context import ctx

    assert ctx.rom is not None

    # Avoid copying ROM data
    rom_bytes = ctx.rom.getbuffer()

    use_editor = ctx.db.meta.hack_type != "SM64 Rom Manager"

    tweaks = []

    for name, entry in STAR_SCHEMA.items():
        coords = entry.read(rom_bytes, use_editor)

        if coords is None:
            continue

        x, y, z = coords

        tweaks.append(f"vec3f_set(gLevelValues.starPositions.{name}, {x}, {y}, {z})\n")

    return tweaks


def write_tweaks():
    tweaks = []

    from context import ctx

    assert ctx.rom is not None
    rom_buf = ctx.rom.getbuffer()

    def _read_from_rom(addr: int, fmt: str | None, length: int | None):
        rom_len = len(rom_buf)
        if fmt:
            needed = struct.calcsize(fmt)
            if addr < 0 or addr + needed > rom_len:
                return None
            return struct.unpack_from(fmt, rom_buf, addr)[0]
        if length is not None:
            if addr < 0 or addr + length > rom_len:
                return None
            return int.from_bytes(ctx.rom[addr : addr + length], "big")

    def _apply_tweaks_from_dict(tweaks_dict, target_obj):
        for py_name, tweak in tweaks_dict.items():
            cur = getattr(target_obj, py_name, None)
            if cur is None or getattr(cur, "is_modified", lambda: False)():
                continue

            guard = tweak.get("guard")
            if guard is not None:
                gaddr = guard.get("addr")
                gbytes = guard.get("bytes")
                if gaddr is None or gbytes is None:
                    continue
                if gaddr < 0 or gaddr + len(gbytes) > len(rom_buf):
                    continue
                if rom_buf[gaddr : gaddr + len(gbytes)] != gbytes:
                    continue

            addr = tweak.get("addr")
            if addr is None:
                continue

            fmt = tweak.get("type")
            length = tweak.get("len")
            val = _read_from_rom(addr, fmt, length)
            if val is None:
                continue
            try:
                setattr(target_obj, py_name, val)
            except Exception:
                pass

    _apply_tweaks_from_dict(ctx.behavior_values.TWEAKS, ctx.behavior_values)
    _apply_tweaks_from_dict(ctx.level_values.TWEAKS, ctx.level_values)

    tweaks += build_star_position_tweaks()
    tweaks += ctx.level_values.get_tweaks_lua()
    tweaks += ctx.behavior_values.get_tweaks_lua()

    if tweaks:
        ctx.txt.write_lua(tweaks, "tweaks.lua")
