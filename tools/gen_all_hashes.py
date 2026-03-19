import struct
import hashlib
from compression_util.compression import (
    decompress_by_type,
    detect_compression_type,
    CompressionType,
)

VANILLA_LEVELS = {
    "bbh": (0x371C40, 0x383950),
    "ccm": (0x383950, 0x396340),
    "castle_inside": (0x396340, 0x3D0DC0),
    "hmc": (0x3D0DC0, 0x3E76B0),
    "ssl": (0x3E76B0, 0x3FC2B0),
    "bob": (0x3FC2B0, 0x405A60),
    "sl": (0x405FB0, 0x40ED70),
    "wdw": (0x40ED70, 0x41A760),
    "jrb": (0x41A760, 0x4246D0),
    "thi": (0x4246D0, 0x42CF20),
    "ttc": (0x42CF20, 0x437870),
    "rr": (0x437870, 0x44ABC0),
    "castle_grounds": (0x44ABC0, 0x454E00),
    "bitdw": (0x454E00, 0x45C600),
    "vcutm": (0x45C600, 0x4614D0),
    "bitfs": (0x4614D0, 0x46B090),
    "sa": (0x46B090, 0x46C3A0),
    "bits": (0x46C3A0, 0x4784A0),
    "lll": (0x4784A0, 0x48D930),
    "ddd": (0x48D930, 0x496090),
    "wf": (0x496090, 0x49E710),
    "ending": (0x49E710, 0x4AC570),
    "castle_courtyard": (0x4AC570, 0x4AF930),
    "pss": (0x4AF930, 0x4B80D0),
    "cotmc": (0x4B80D0, 0x4BEC30),
    "totwc": (0x4BEC30, 0x4C2920),
    "bowser_1": (0x4C2920, 0x4C4320),
    "wmotr": (0x4C4320, 0x4CDBD0),
    "bowser_2": (0x4CDBD0, 0x4CEC00),
    "bowser_3": (0x4CEC00, 0x4D1910),
    "ttm": (0x4D1910, 0x4D5AE0),
}


def scan_traj(data):
    found = []
    for i in range(0, len(data) - 8, 2):
        if data[i : i + 2] == b"\x00\x00":
            p = i
            count = 0
            is_valid = False
            raw = []
            while p + 8 <= len(data):
                tid = struct.unpack(">h", data[p : p + 2])[0]
                if tid == -1:
                    if count >= 1:  # even 1 point is fine if terminated
                        is_valid = True
                        raw.append(b"\xff\xff")
                    break
                if tid != count:
                    break
                raw.append(data[p : p + 8])
                p += 8
                count += 1
                if p + 2 <= len(data):
                    if struct.unpack(">h", data[p : p + 2])[0] == -1:
                        is_valid = True
                        raw.append(b"\xff\xff")
                        break
                if count > 1000:
                    break
            if is_valid:
                found.append(b"".join(raw))
    return found


def main():
    try:
        f = open("../baserom.us.z64", "rb")
    except Exception:
        f = open("baserom.us.z64", "rb")

    with f:
        rom_bytes = f.read()

    hashes = set()

    # Global segments (Seg 2)
    # Common 0
    c0_start, c0_end = 0x1F2200, 0x1F72D0
    c0_decomp = decompress_by_type(rom_bytes[c0_start:c0_end], CompressionType.MIO0)
    for raw in scan_traj(c0_decomp):
        hashes.add(hashlib.sha256(raw).hexdigest())

    # Levels (Seg 7)
    for level, (start, end) in VANILLA_LEVELS.items():
        data = rom_bytes[start:end]
        ctype = detect_compression_type(data)
        if ctype == CompressionType.MIO0:
            decomp = decompress_by_type(data, CompressionType.MIO0)
        else:
            decomp = data
        for raw in scan_traj(decomp):
            hashes.add(hashlib.sha256(raw).hexdigest())

    print("VANILLA_TRAJECTORY_HASHES = {")
    for h in sorted(list(hashes)):
        print(f"    '{h}',")
    print("}")


if __name__ == "__main__":
    main()
