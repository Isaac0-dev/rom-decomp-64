import binascii
import enum
import io
from utils import debug_print


class Action(enum.IntEnum):
    SourceRead = 0
    TargetRead = 1
    SourceCopy = 2
    TargetCopy = 3


def read_number_io(b: io.BytesIO) -> int:
    data, shift = 0, 1
    while True:
        x_bytes = b.read(1)
        if not x_bytes:
            return -1
        x = x_bytes[0]
        data += (x & 0x7F) * shift
        if x & 0x80:
            break
        shift <<= 7
        data += shift
    return data


class InvalidPatch(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(self.msg)


class BPSPatch:
    MAGIC_HEADER = b"BPS1"

    def __init__(self, patch_data: bytes):
        if not patch_data.startswith(self.MAGIC_HEADER):
            raise InvalidPatch("Invalid BPS magic header")

        # Footer is 12 bytes: [Source CRC32][Target CRC32][Patch CRC32]
        self.source_checksum = int.from_bytes(patch_data[-12:-8], "little")
        self.target_checksum = int.from_bytes(patch_data[-8:-4], "little")
        self.patch_checksum = int.from_bytes(patch_data[-4:], "little")

        calc_patch_crc = binascii.crc32(patch_data[:-4]) & 0xFFFFFFFF
        if self.patch_checksum != calc_patch_crc:
            raise InvalidPatch(
                f"Patch CRC32 mismatch: {self.patch_checksum:08X} vs {calc_patch_crc:08X}"
            )

        bio = io.BytesIO(patch_data[4:-12])
        self.source_size = read_number_io(bio)
        self.target_size = read_number_io(bio)
        self.metadata_size = read_number_io(bio)
        self.metadata = bio.read(self.metadata_size).decode("utf-8", errors="ignore")
        self.actions_data = bio.read()

    def apply(self, source: bytes) -> bytes:
        if len(source) != self.source_size:
            debug_print(
                f"Warning: Source size mismatch. Expected {self.source_size}, got {len(source)}"
            )

        source_crc = binascii.crc32(source) & 0xFFFFFFFF
        if source_crc != self.source_checksum:
            debug_print(
                f"Warning: Source CRC32 mismatch. Patch expects {self.source_checksum:08X}, ROM is {source_crc:08X}"
            )

        target = bytearray(self.target_size)
        actions = io.BytesIO(self.actions_data)

        output_offset = 0
        source_relative_offset = 0
        target_relative_offset = 0

        while True:
            action_header = read_number_io(actions)
            if action_header == -1:
                break

            command = action_header & 3
            length = (action_header >> 2) + 1

            if command == Action.SourceRead:
                target[output_offset : output_offset + length] = source[
                    output_offset : output_offset + length
                ]
                output_offset += length
            elif command == Action.TargetRead:
                target[output_offset : output_offset + length] = actions.read(length)
                output_offset += length
            elif command == Action.SourceCopy:
                data = read_number_io(actions)
                source_relative_offset += (-1 if data & 1 else 1) * (data >> 1)
                target[output_offset : output_offset + length] = source[
                    source_relative_offset : source_relative_offset + length
                ]
                output_offset += length
                source_relative_offset += length
            elif command == Action.TargetCopy:
                data = read_number_io(actions)
                target_relative_offset += (-1 if data & 1 else 1) * (data >> 1)
                # Must be byte-by-byte for overlapping copies (RLE)
                for _ in range(length):
                    target[output_offset] = target[target_relative_offset]
                    output_offset += 1
                    target_relative_offset += 1

        final_crc = binascii.crc32(target) & 0xFFFFFFFF
        if final_crc != self.target_checksum:
            raise InvalidPatch(
                f"Target CRC32 mismatch: {final_crc:08X} vs {self.target_checksum:08X}"
            )

        return bytes(target)


def apply_patch(patch_path: str, source_rom_path: str, output_rom_path: str):
    with open(patch_path, "rb") as f:
        patch_data = f.read()
    with open(source_rom_path, "rb") as f:
        source_data = f.read()

    patcher = BPSPatch(patch_data)
    patched_rom = patcher.apply(source_data)

    with open(output_rom_path, "wb") as f:
        f.write(patched_rom)
    return output_rom_path
