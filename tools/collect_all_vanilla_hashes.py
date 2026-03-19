import struct
import hashlib
from compression_util.compression import decompress_by_type, CompressionType


def scan_traj(data):
    hashes = {}
    for i in range(0, len(data) - 8, 2):
        if data[i : i + 2] == b"\x00\x00":
            p = i
            count = 0
            is_valid = False
            raw = []
            while p + 8 <= len(data):
                tid = struct.unpack(">h", data[p : p + 2])[0]
                if tid == -1:
                    if count >= 1:
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
                traj_data = b"".join(raw)
                hashes[hashlib.sha256(traj_data).hexdigest()] = True
    return hashes


def main():
    try:
        f = open("../baserom.us.z64", "rb")
    except Exception:
        f = open("baserom.us.z64", "rb")

    with f:
        rom_bytes = f.read()

    all_hashes = set()

    # 1. Scan raw ROM
    all_hashes.update(scan_traj(rom_bytes).keys())

    # 2. Scan all MIO0 blocks
    pos = 0
    while True:
        pos = rom_bytes.find(b"MIO0", pos)
        if pos == -1:
            break
        try:
            decomp = decompress_by_type(rom_bytes[pos:], CompressionType.MIO0)
            all_hashes.update(scan_traj(decomp).keys())
        except Exception:
            pass
        pos += 4

    print("VANILLA_TRAJECTORY_HASHES = {")
    for h in sorted(list(all_hashes)):
        print(f"    '{h}',")
    print("}")


if __name__ == "__main__":
    main()
