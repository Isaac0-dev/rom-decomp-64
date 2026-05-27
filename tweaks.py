from context import ctx
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class StarEntry:
    offsets: tuple[int, ...]
    fmt: str = ">fff"
    editor_offset: int | None = None
    sentinel_check: bool = True

    def read(self, rom_bytes: memoryview, use_editor: bool):

        # Special case: coordinate triples stored as separate shorts
        if self.fmt == ">h":
            return tuple(struct.unpack_from(">h", rom_bytes, offset)[0] for offset in self.offsets)

        # Standard float vec3
        offset = (
            self.editor_offset if use_editor and self.editor_offset is not None else self.offsets[0]
        )

        if self.sentinel_check:
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

        tweaks.append(f"vec3s_set(gLevelValues.starPositions.{name}, {x}, {y}, {z})\n")

    return tweaks


def write_tweaks():
    if ctx.db.meta.hack_type == "SM64 Editor" or ctx.db.meta.hack_type == "SM64 Rom Manager":
        # If we didn't see any modification to the entry level, some hacks
        # put their entry level adjustment at 0x6D6A
        if (
            not ctx.level_values.entry_level.is_modified()
            and ctx.rom[0x6D68 : 0x6D68 + 2] == b"\x24\x05"
        ):
            ctx.level_values.entry_level = int.from_bytes(ctx.rom[0x6D6A : 0x6D6A + 2], "big")

        if not ctx.behavior_values.toad_star_1_requirement.is_modified():
            ctx.behavior_values.toad_star_1_requirement = int.from_bytes(
                ctx.rom[0x3199B : 0x3199B + 1], "big"
            )
        if not ctx.behavior_values.toad_star_2_requirement.is_modified():
            ctx.behavior_values.toad_star_2_requirement = int.from_bytes(
                ctx.rom[0x319CF : 0x319CF + 1], "big"
            )
        if not ctx.behavior_values.toad_star_3_requirement.is_modified():
            ctx.behavior_values.toad_star_3_requirement = int.from_bytes(
                ctx.rom[0x31A03 : 0x31A03 + 1], "big"
            )

        if not ctx.behavior_values.mips_star_1_requirement.is_modified():
            ctx.behavior_values.mips_star_1_requirement = int.from_bytes(
                ctx.rom[0xB34CB : 0xB34CB + 1], "big"
            )
        if not ctx.behavior_values.mips_star_2_requirement.is_modified():
            ctx.behavior_values.mips_star_2_requirement = int.from_bytes(
                ctx.rom[0xB3523 : 0xB3523 + 1], "big"
            )

    tweaks = []
    tweaks += build_star_position_tweaks()
    tweaks += ctx.level_values.get_tweaks_lua()
    tweaks += ctx.behavior_values.get_tweaks_lua()
    if tweaks:
        ctx.txt.write_lua(tweaks, "tweaks.lua")
