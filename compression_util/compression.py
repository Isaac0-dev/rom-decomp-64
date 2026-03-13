from enum import Enum, auto
from compression_util.rnc import decompress_rnc


class Endianness(Enum):
    LITTLE = "little"
    BIG = "big"


class CompressionType(Enum):
    NONE = auto()
    MIO0 = auto()
    YAY0 = auto()
    RNC = auto()


compression_types = [
    b"MIO0",
    b"YAY0",
    b"RNC",
]


def get_compression_types():
    return compression_types


def detect_compression_type(data: bytes) -> CompressionType:
    if not data or len(data) < 4:
        return CompressionType.NONE

    header = data[:4]
    if header == b"MIO0":
        return CompressionType.MIO0
    if header == b"YAY0":
        return CompressionType.YAY0
    if header[:3] == b"RNC":
        return CompressionType.RNC
    return CompressionType.NONE


def decompress_mio0(data: bytes, endianness: Endianness):
    header = str(data[0x0:0x4], "ascii")

    if header != "MIO0":
        raise ValueError('Invalid header, not starting with "MIO0"')

    # length of decompressed contents
    dl = int.from_bytes(data[4:8], endianness.value)

    # offset of compressed data
    co = int.from_bytes(data[8:12], endianness.value)

    # offset of uncompressed data
    uo = int.from_bytes(data[12:16], endianness.value)

    output_byte_array = bytearray()
    output_index = 0

    layout_cursor = 0x10  # Header size
    current_layout_byte = data[layout_cursor]
    bits_left = 8

    ci = 0
    ui = 0

    if uo - co == 2 and data[co : co + 2] == b"\x00\x00":
        # Not always an error, but sometimes is
        # debug_print('decompress_mio0: Invalid header')
        return data[uo : uo + dl], uo + dl

    while output_index < dl:
        if bits_left == 0:
            layout_cursor += 1
            current_layout_byte = data[layout_cursor]
            bits_left = 8

        is_uncompressed = current_layout_byte & 0x80
        current_layout_byte <<= 1
        bits_left -= 1

        if output_index >= dl:
            break

        if is_uncompressed:
            output_byte_array.append(data[uo + ui])
            ui += 1
            output_index += 1
        else:
            # bytes formated for length and index of where to read from uncompressed
            # 1 0 1 0 0 0 0 1   0 0 0 0 0 0 0 0
            # [     ] [                       ]
            #    \ Length   \_ Lookback Index
            len_idx_bytes = data[co + ci : co + ci + 2]
            ci += 2

            length = ((len_idx_bytes[0] & 0xF0) >> 4) + 3
            index = ((len_idx_bytes[0] & 0xF) << 8) + (len_idx_bytes[1] + 1)

            if length < 3 or length > 18:
                raise Exception(f"unplausible length value: {length}")

            if index < 1 or index > 4096:
                raise Exception(f"unplausible index value: {index}")

            start = output_index - index
            if index >= length:
                output_byte_array.extend(output_byte_array[start : start + length])
                output_index += length
            else:
                for i in range(length):
                    output_byte_array.append(output_byte_array[output_index - index])
                    output_index += 1

    end = uo + ui

    return bytes(output_byte_array), end


def decompress_yay0(data: bytes) -> bytes:
    if data[:4] != b"YAY0":
        raise ValueError('Invalid header, not starting with "YAY0"')

    decoded_length = int.from_bytes(data[4:8], "big")
    link_offset = int.from_bytes(data[8:12], "big")
    chunk_offset = int.from_bytes(data[12:16], "big")
    mask_offset = 0x10

    dest = bytearray()
    mask = 0
    bits_left = 0

    while len(dest) < decoded_length:
        if bits_left == 0:
            mask = int.from_bytes(data[mask_offset : mask_offset + 4], "big")
            mask_offset += 4
            bits_left = 32

        if mask & 0x80000000:
            dest.append(data[chunk_offset])
            chunk_offset += 1
        else:
            link_val = int.from_bytes(data[link_offset : link_offset + 2], "big")
            link_offset += 2

            count = link_val >> 12
            disp = (link_val & 0x0FFF) + 1

            if count == 0:
                count = data[chunk_offset] + 0x10
                chunk_offset += 1
            else:
                count += 2

            copy_src = len(dest) - disp
            if copy_src < 0:
                raise ValueError("Invalid displacement in YAY0 stream.")
            for _ in range(count):
                dest.append(dest[copy_src])
                copy_src += 1

        mask = (mask << 1) & 0xFFFFFFFF
        bits_left -= 1

    return bytes(dest)


def decompress_by_type(data: bytes, compression: CompressionType) -> bytes:
    if compression == CompressionType.MIO0:
        output, _ = decompress_mio0(data, Endianness.BIG)
        return output
    if compression == CompressionType.YAY0:
        return decompress_yay0(data)
    if compression == CompressionType.RNC:
        return decompress_rnc(data)
    return data
