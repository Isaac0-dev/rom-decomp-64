import struct
import hashlib
from segment import segments_load_rom
from byteio import CustomBytesIO
from compression_util.compression import (
    decompress_by_type,
    detect_compression_type,
    CompressionType,
)

# Level offsets from a reliable SM64 decompiler source for vanilla US
VANILLA_LEVEL_SEG7_OFFSETS = {
    "rr": (0x2A21B0, 0x1E090),
    "ccm": (0x140150, 0x13380),
    "bitfs": (0x303E40, 0x3930),
    "hmc": (0x1B86F0, 0x11740),
    "lll": (0x3490F0, 0xE710),
    "ttm": (0x480D60, 0x41E0),
    "bob": (0x1F72D0, 0x76B0),
    "thi": (0x272480, 0xB0F0),
    "castle_inside": (0x170040, 0x2B920),
}

VANILLA_TRAJECTORY_ADDRS = {
    0x0702EC3C: "rr_seg7_trajectory_0702EC3C",
    0x0702ECC0: "rr_seg7_trajectory_0702ECC0",
    0x0701669C: "ccm_seg7_trajectory_0701669C",
    0x070159AC: "bitfs_seg7_trajectory_070159AC",
    0x0702B86C: "hmc_seg7_trajectory_0702B86C",
    0x0702856C: "lll_seg7_trajectory_0702856C",
    0x07028660: "lll_seg7_trajectory_07028660",
    0x0702ED9C: "rr_seg7_trajectory_0702ED9C",
    0x0702EEE0: "rr_seg7_trajectory_0702EEE0",
    0x070165A8: "ccm_seg7_trajectory_snowman",
    0x0700B01C: "bob_seg7_trajectory_koopa",
    0x07005C98: "thi_seg7_trajectory_koopa",
    0x07004A20: "ccm_seg7_trajectory_penguin_race",
    0x07078EF8: "inside_castle_seg7_trajectory_mips_0",
    0x07078F2C: "inside_castle_seg7_trajectory_mips_1",
    0x07078F68: "inside_castle_seg7_trajectory_mips_2",
    0x07078F7C: "inside_castle_seg7_trajectory_mips_3",
    0x07078FA8: "inside_castle_seg7_trajectory_mips_4",
    0x07078FD4: "inside_castle_seg7_trajectory_mips_5",
    0x07078FE8: "inside_castle_seg7_trajectory_mips_6",
    0x07079004: "inside_castle_seg7_trajectory_mips_7",
    0x07079020: "inside_castle_seg7_trajectory_mips_8",
    0x07079044: "inside_castle_seg7_trajectory_mips_9",
    0x070170A0: "ttm_seg7_trajectory_070170A0",
}


def get_traj_raw_bytes(data, offset):
    pos = offset
    chunks = []
    while pos + 2 <= len(data):
        tid = struct.unpack(">h", data[pos : pos + 2])[0]
        if tid == -1:
            chunks.append(b"\xff\xff")
            return b"".join(chunks)
        if pos + 8 > len(data):
            break
        chunks.append(data[pos : pos + 8])
        pos += 8
    return None


def main():
    try:
        f = open("baserom.us.z64", "rb")
    except FileNotFoundError:
        f = open("../baserom.us.z64", "rb")

    with f:
        rom_bytes = f.read()
        rom = CustomBytesIO(rom_bytes)

    segments_load_rom(rom)

    # Load Seg 2
    s2_data = rom_bytes[0x108A40:0x114750]
    s2_decomp = decompress_by_type(s2_data, CompressionType.MIO0)

    hashes = {}

    # Check Seg 2 trajectories
    for addr, name in VANILLA_TRAJECTORY_ADDRS.items():
        if (addr >> 24) == 2:
            offset = addr & 0xFFFFFF
            raw = get_traj_raw_bytes(s2_decomp, offset)
            if raw:
                h = hashlib.sha256(raw).hexdigest()
                hashes[h] = name

    # Check Seg 7 trajectories
    for level, (off, size) in VANILLA_LEVEL_SEG7_OFFSETS.items():
        s7_data = rom_bytes[off : off + size]
        ctype = detect_compression_type(s7_data)
        if ctype != CompressionType.NONE:
            try:
                s7_decomp = decompress_by_type(s7_data, ctype)
            except Exception:
                continue
        else:
            s7_decomp = s7_data

        for addr, name in VANILLA_TRAJECTORY_ADDRS.items():
            if (addr >> 24) == 7:
                offset = addr & 0xFFFFFF
                raw = get_traj_raw_bytes(s7_decomp, offset)
                if raw:
                    h = hashlib.sha256(raw).hexdigest()
                    hashes[h] = name

    print("VANILLA_TRAJECTORY_HASHES = {")
    for h, name in sorted(hashes.items(), key=lambda x: x[1]):
        print(f"    '{h}': '{name}',")
    print("}")


if __name__ == "__main__":
    main()
