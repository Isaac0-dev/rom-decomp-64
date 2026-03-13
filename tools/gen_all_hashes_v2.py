import struct
import hashlib
from compression_util.compression import decompress_by_type, CompressionType


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

    # Search for all MIO0 headers
    pos = 0
    while True:
        pos = rom_bytes.find(b"MIO0", pos)
        if pos == -1:
            break

        try:
            # We don't know the size, but decompress_mio0 only reads what it needs
            decomp = decompress_by_type(rom_bytes[pos:], CompressionType.MIO0)
            for raw in scan_traj(decomp):
                hashes.add(hashlib.sha256(raw).hexdigest())
        except Exception:
            pass
        pos += 4

    print("VANILLA_TRAJECTORY_HASHES = {")
    for h in sorted(list(hashes)):
        print(f"    '{h}',")
    print("}")


if __name__ == "__main__":
    main()
