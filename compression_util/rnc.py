from __future__ import annotations
import struct
from utils import debug_fail

HEADER_SIZE = 0x12


class Huffman:
    def __init__(self):
        self.frequency = 0
        self.entry_ptr = 0xFFFF
        self.code = 0
        self.code_len = 0


class RNCUnpacker:
    def __init__(self, data: bytes):
        self.data = data
        self.input_ptr = HEADER_SIZE
        self.output = bytearray()
        self.bit_buff_bits = 0
        self.bit_buff_m1 = 0
        self.bit_buff_m2 = 0

        self.raw_huffman_table = [Huffman() for _ in range(16)]
        self.pos_huffman_table = [Huffman() for _ in range(16)]
        self.len_huffman_table = [Huffman() for _ in range(16)]

    def read_be32(self, offset: int) -> int:
        return struct.unpack_from(">I", self.data, offset)[0]

    def read_le32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def swap_bits(self, in_bits: int, n: int) -> int:
        out_bits = 0
        for _ in range(n):
            out_bits = (out_bits << 1) | (in_bits & 1)
            in_bits >>= 1
        return out_bits

    def make_huffman_codes(self, table: list[Huffman], n: int):
        huff_bits = 1
        huff_code = 0
        huff_base = 0x80000000

        while huff_bits <= 16:
            for i in range(n):
                if table[i].code_len == huff_bits:
                    table[i].code = self.swap_bits(huff_code // huff_base, huff_bits)
                    huff_code += huff_base
            huff_bits += 1
            huff_base >>= 1

    def input_bits_m1(self, n: int) -> int:
        bits = 0
        bit_mask = 1
        while n > 0:
            if self.bit_buff_bits == 0:
                # The C code reads 4 bytes but only advances by 2
                val = 0
                if self.input_ptr + 4 <= len(self.data):
                    val = self.read_le32(self.input_ptr)
                elif self.input_ptr < len(self.data):
                    remaining = len(self.data) - self.input_ptr
                    tmp = bytearray(self.data[self.input_ptr :]) + bytearray(4 - remaining)
                    val = struct.unpack("<I", tmp)[0]

                self.bit_buff_m1 = val
                # Critical: Only advance 2 bytes
                self.input_ptr += (
                    2 if self.input_ptr + 2 <= len(self.data) else (len(self.data) - self.input_ptr)
                )
                self.bit_buff_bits = 16

            if self.bit_buff_m1 & 1:
                bits |= bit_mask
            bit_mask <<= 1
            self.bit_buff_m1 >>= 1
            self.bit_buff_bits -= 1
            n -= 1
        return bits

    def input_bits_m2(self, n: int) -> int:
        bits = 0
        while n > 0:
            if self.bit_buff_bits == 0:
                # Method 2 reads 1 byte at a time
                if self.input_ptr < len(self.data):
                    self.bit_buff_m2 = self.data[self.input_ptr]
                    self.input_ptr += 1
                else:
                    self.bit_buff_m2 = 0
                self.bit_buff_bits = 8

            bits <<= 1
            if self.bit_buff_m2 & 0x80:
                bits |= 1
            self.bit_buff_m2 = (self.bit_buff_m2 << 1) & 0xFF
            self.bit_buff_bits -= 1
            n -= 1
        return bits

    def input_huffman_table(self, table: list[Huffman]):
        for h in table:
            h.code_len = 0
            h.code = 0

        n = self.input_bits_m1(5)
        if n > 16:
            n = 16
        if n == 0:
            return

        for i in range(n):
            table[i].code_len = self.input_bits_m1(4)

        self.make_huffman_codes(table, n)

    def input_value(self, table: list[Huffman]) -> int:
        idx = 0
        while idx < 16 and (
            table[idx].code_len == 0
            or (self.bit_buff_m1 & ((1 << table[idx].code_len) - 1)) != table[idx].code
        ):
            idx += 1

        if idx >= 16:
            raise Exception("Invalid Huffman code")

        self.input_bits_m1(table[idx].code_len)
        if idx < 2:
            return idx
        return self.input_bits_m1(idx - 1) | (1 << (idx - 1))

    def input_len_m2(self) -> int:
        length = self.input_bits_m2(1) + 4
        if self.input_bits_m2(1) == 0:
            return length
        return ((length - 1) << 1) + self.input_bits_m2(1)

    def input_pos_m2(self) -> int:
        pos = 0
        if self.input_bits_m2(1):
            pos = self.input_bits_m2(1)
            if self.input_bits_m2(1):
                pos = ((pos << 1) + self.input_bits_m2(1)) | 4
                if self.input_bits_m2(1) == 0:
                    pos = (pos << 1) + self.input_bits_m2(1)
            elif pos == 0:
                pos = self.input_bits_m2(1) + 2

        low = 0
        if self.input_ptr < len(self.data):
            low = self.data[self.input_ptr]
            self.input_ptr += 1

        return (pos << 8) + low + 1

    def unpack_method1(self, expected_size: int):
        self.input_bits_m1(2)
        while len(self.output) < expected_size:
            self.input_huffman_table(self.raw_huffman_table)
            self.input_huffman_table(self.pos_huffman_table)
            self.input_huffman_table(self.len_huffman_table)
            loop_count = self.input_bits_m1(16)

            is_first = True
            while loop_count > 0:
                if not is_first:
                    dist = self.input_value(self.pos_huffman_table) + 1
                    length = self.input_value(self.len_huffman_table) + 2
                    for _ in range(length):
                        if len(self.output) < expected_size:
                            self.output.append(self.output[-dist])

                length = self.input_value(self.raw_huffman_table)
                for _ in range(length):
                    if len(self.output) < expected_size and self.input_ptr < len(self.data):
                        self.output.append(self.data[self.input_ptr])
                        self.input_ptr += 1

                next_val = 0
                if self.input_ptr + 3 < len(self.data):
                    next_val = self.read_le32(self.input_ptr)
                elif self.input_ptr < len(self.data):
                    rem = len(self.data) - self.input_ptr
                    tmp = bytearray(self.data[self.input_ptr :]) + bytearray(4 - rem)
                    next_val = struct.unpack("<I", tmp)[0]

                mask = (1 << self.bit_buff_bits) - 1
                self.bit_buff_m1 = (
                    (next_val << self.bit_buff_bits) | (self.bit_buff_m1 & mask)
                ) & 0xFFFFFFFF

                is_first = False
                loop_count -= 1

    def unpack_method2(self, expected_size: int):
        self.input_bits_m2(2)
        while len(self.output) < expected_size:
            while True:
                while (
                    self.input_bits_m2(1) == 0
                    and len(self.output) < expected_size
                    and self.input_ptr < len(self.data)
                ):
                    self.output.append(self.data[self.input_ptr])
                    self.input_ptr += 1

                if self.input_bits_m2(1):
                    if self.input_bits_m2(1) == 0:
                        length = 2
                        pos = self.data[self.input_ptr] if self.input_ptr < len(self.data) else 0
                        self.input_ptr += 1
                        pos += 1
                    else:
                        if self.input_bits_m2(1) == 0:
                            length = 3
                        else:
                            length = (
                                self.data[self.input_ptr] if self.input_ptr < len(self.data) else 0
                            )
                            self.input_ptr += 1
                            length += 8
                            if length == 8:
                                break  # End of block
                        pos = self.input_pos_m2()

                    for _ in range(length):
                        if len(self.output) < expected_size:
                            src_idx = len(self.output) - pos
                            self.output.append(self.output[src_idx])
                else:
                    length = self.input_len_m2()
                    if length == 9:
                        length = (self.input_bits_m2(4) << 2) + 12
                        for _ in range(length):
                            if len(self.output) < expected_size and self.input_ptr < len(self.data):
                                self.output.append(self.data[self.input_ptr])
                                self.input_ptr += 1
                    else:
                        pos = self.input_pos_m2()
                        for _ in range(length):
                            if len(self.output) < expected_size:
                                src_idx = len(self.output) - pos
                                self.output.append(self.output[src_idx])

            self.input_bits_m2(1)


def calculate_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def decompress_rnc(data: bytes) -> bytes:
    if len(data) < HEADER_SIZE:
        return b""

    if data[0:3] != b"RNC":
        return b""

    method = data[3]
    expected_size = struct.unpack_from(">I", data, 4)[0]
    header_crc = struct.unpack(">H", data[12:14])[0]

    if method == 0:
        return data[HEADER_SIZE : HEADER_SIZE + expected_size]

    unpacker = RNCUnpacker(data)
    if method == 1:
        unpacker.unpack_method1(expected_size)
    elif method == 2:
        unpacker.unpack_method2(expected_size)
    else:
        return b""

    if len(unpacker.output) != expected_size:
        debug_fail(f"Size mismatch: got {len(unpacker.output)}, expected {expected_size}")
        return b""

    actual_crc = calculate_crc(bytes(unpacker.output))
    if actual_crc != header_crc:
        debug_fail(f"CRC Mismatch: got {hex(actual_crc)}, expected {hex(header_crc)}")
        return b""

    return bytes(unpacker.output)
