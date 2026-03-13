import hashlib
from compression_util.compression import decompress_by_type, CompressionType


def main():
    # bob_seg7_metal_ball_path0
    # 18 points * 8 bytes + 2 bytes for -1 = 146 bytes
    needle = b"\x00\x00\x05\xff\x0e\xff\xea\x47"  # Waypoint 0
    try:
        f = open("../baserom.us.z64", "rb")
    except Exception:
        f = open("baserom.us.z64", "rb")

    with f:
        rom_bytes = f.read()

    pos = 0
    found_any = False
    while True:
        pos = rom_bytes.find(b"MIO0", pos)
        if pos == -1:
            break

        try:
            decomp = decompress_by_type(rom_bytes[pos:], CompressionType.MIO0)
            start_idx = 0
            while True:
                idx = decomp.find(needle, start_idx)
                if idx == -1:
                    break

                data = decomp[idx : idx + 146]
                if data[-2:] == b"\xff\xff":
                    print(f"Found! Hash: {hashlib.sha256(data).hexdigest()}")
                    found_any = True
                start_idx = idx + 1
        except Exception:
            pass
        pos += 4
    if not found_any:
        print("Not found")


if __name__ == "__main__":
    main()
