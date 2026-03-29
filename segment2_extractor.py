import struct
from io import BytesIO
from typing import Any, List, Optional, Tuple

from base_processor import BaseProcessor
from context import ctx
from rom_database import TextureRecord
from segment import get_segment
import binary_to_png
from utils import get_rom
import hashlib

seg2_len = 0xBD06  # Standard US
arrays: List[Tuple[int, List[int], str]] = []


def scan_buffer(buffer_bytes, source_name):
    num_words = len(buffer_bytes) // 4
    words = struct.unpack(f">{num_words}I", buffer_bytes[: num_words * 4])

    current_array: List[int] = []
    current_start = 0

    for i, word in enumerate(words):
        is_seg2_ptr = ((word >> 24) == 0x02) and ((word & 0xFFFFFF) < seg2_len)

        if is_seg2_ptr:
            if not current_array:
                current_start = i
            current_array.append(word)
        else:
            if word == 0 and current_array:
                current_array.append(0)
            else:
                if current_array:
                    while current_array and current_array[-1] == 0:
                        current_array.pop()
                    if len(current_array) >= 2:
                        arrays.append((current_start * 4, current_array, source_name))
                    current_array = []

    if current_array:
        while current_array and current_array[-1] == 0:
            current_array.pop()
        if len(current_array) >= 2:
            arrays.append((current_start * 4, current_array, source_name))


_HUD_MAP = {
    0: (
        "texture_hud_char_0",
        0x00000,
        "1d9401097bb41a08a89d2704471e50659d22909ed8b5d04acddb0bd9be1a6c9a",
    ),
    1: (
        "texture_hud_char_1",
        0x00200,
        "de0af5c5be168b421eaad980a75b8ea2fbb566ffc888ffd78a6bb871fc941f77",
    ),
    2: (
        "texture_hud_char_2",
        0x00400,
        "0a96e298d14c6eb59df55eedccdab1fa7103ea1492fcaaa76e580e647a667f2d",
    ),
    3: (
        "texture_hud_char_3",
        0x00600,
        "7f1bfec559166b15f529ea9001b5f75f8a23c40998c03fadf15b9aa78a0c8e45",
    ),
    4: (
        "texture_hud_char_4",
        0x00800,
        "764a3c317062ab0f353aa318f29e490fee552d040a6db42b7857a7ae5dcfd341",
    ),
    5: (
        "texture_hud_char_5",
        0x00A00,
        "76ca7e7e23fddbb1b937d62791ca07f0805fe156ee6115351b4a617bfd740b99",
    ),
    6: (
        "texture_hud_char_6",
        0x00C00,
        "91f417aa3d29f31114775a8ea433768d424064347469b5600f8c43253356a478",
    ),
    7: (
        "texture_hud_char_7",
        0x00E00,
        "40bb6002972eb249ce53a9a1ed43849c6b5881639444f1753a78f92b7b257612",
    ),
    8: (
        "texture_hud_char_8",
        0x01000,
        "034669dbaadd56d6e10fae5764ecd26ace9b2fbcab3a2ad92d6b6af70affa238",
    ),
    9: (
        "texture_hud_char_9",
        0x01200,
        "85cde8073ae820706da8d3bb144b4f52b42aba04fce4280ea2b6dcb396725144",
    ),
    10: (
        "texture_hud_char_A",
        0x01400,
        "8e32f1587d1f4b2c2cb3e7a8ea0bc6ee3c5a357858b430c604a2bdcb41f4537d",
    ),
    11: (
        "texture_hud_char_B",
        0x01600,
        "3b517328f03d492caf4423266df4c185766df30fced393f27abb1299d1cadf42",
    ),
    12: (
        "texture_hud_char_C",
        0x01800,
        "e6d2fc7977a2d32002bb6045013b62d57a6364de9f9dfb9c53613d996f31e2e9",
    ),
    13: (
        "texture_hud_char_D",
        0x01A00,
        "452c5200d0639625ae466f2cacb8e86d75b18d8fb37272e42e9ea69891ac7cf6",
    ),
    14: (
        "texture_hud_char_E",
        0x01C00,
        "2860a56176602cc5bbcbaec0faca5a4553ef21cbed93cb9fdd0a696968f253a7",
    ),
    15: (
        "texture_hud_char_F",
        0x01E00,
        "31b3d49d5c91229418f2aac660fdd6f5600ff7b70ae9cc4eeac7ff7943c448d3",
    ),
    16: (
        "texture_hud_char_G",
        0x02000,
        "d4233ba427aa58846a7f5dee1474e09b83f5142ecf99b9c9320c37fb23507292",
    ),
    17: (
        "texture_hud_char_H",
        0x02200,
        "6c1b5f2822d9786797b4e3200a42ec852aeb92ae2594889561494e9e146a1be0",
    ),
    18: (
        "texture_hud_char_I",
        0x02400,
        "c38ffabba79c5589abcca8e32b2d7caeb543d7200d99fdb2fe556b73c115456f",
    ),
    19: None,
    20: (
        "texture_hud_char_K",
        0x02800,
        "205a6a128aa38582ceeab991216e7a09430d6c39017c6adbf6bdec4eaa5c641c",
    ),
    21: (
        "texture_hud_char_L",
        0x02A00,
        "4dd9413601912e12d5af04dee7544557ac097e6ec4a321f215315520edd802f6",
    ),
    22: (
        "texture_hud_char_M",
        0x02C00,
        "ddfd28243c665501dd40a6406a3cdcaad423b5483a841cc748d296e2858a66d0",
    ),
    23: (
        "texture_hud_char_N",
        0x02E00,
        "ffe4306d0b2b93d4ae2c38383912ea46ec2069c091089c1acc2e9b4340775de4",
    ),
    24: (
        "texture_hud_char_O",
        0x03000,
        "1d11bbd8dcbed7ba5572429883010b64fe4131b8be64276c631398f2ce641588",
    ),
    25: (
        "texture_hud_char_P",
        0x03200,
        "1c16f2dedba9c1d5f6f8d2d688c916cbbd14aa9c4afa0fdcf74e3a6fde8a5ed3",
    ),
    26: None,
    27: (
        "texture_hud_char_R",
        0x03600,
        "01508ef8d98b6fd0f5b64bf0f26c657f452a572306cc7b80b0455bb8fda79168",
    ),
    28: (
        "texture_hud_char_S",
        0x03800,
        "9dcee562cb52481a887ec475ef629e4acc113f7c509dd48525765d2865eb75e9",
    ),
    29: (
        "texture_hud_char_T",
        0x03A00,
        "dfafcfa14feb2865ab2d94e6eb6c31dd5b4fba9ae3ef8e10bcbf9268e91e9e07",
    ),
    30: (
        "texture_hud_char_U",
        0x03C00,
        "7b5c5bb9f1fa273ef41570791b780100911f7960e8789b37600e265a738bf739",
    ),
    31: None,
    32: (
        "texture_hud_char_W",
        0x04000,
        "02f4b57c44db77807d89f68fc37be1f7d3a1edf45dafa0bc0bcce5b03543d1d7",
    ),
    33: (
        "texture_hud_char_X",
        0x04400,
        "fdda6247a9b148cfcdcef9f986ac257ca5e16fe4f9dc80662af946a273d92e4f",
    ),
    34: None,
    35: None,
    36: None,
    50: (
        "texture_hud_char_multiply",
        0x05600,
        "973db57587ed4b75c8eabf2ff602512ddde92c23a9884722107cdf4e5a3edae9",
    ),
    51: (
        "texture_hud_char_coin",
        0x05800,
        "e41ebee5502380a64c2df02be75fc27d4b3d07fb1d63366ca84b68e51f3531db",
    ),
    52: (
        "texture_hud_char_mario_head",
        0x05A00,
        "30be0e5d7eaaf4eec77aa6eb7ec7bcc7fdb05bcd9e1fea22443b00798c69a085",
    ),
    53: (
        "texture_hud_char_star",
        0x05C00,
        "6ddd5cb90e03070f2ab06abf9d855b481a5d8c3ecfbe7a4c48b179e055c7b316",
    ),
    56: (
        "texture_hud_char_apostrophe",
        0x04800,
        "7c6bdbd345142c0c8a19faac06255690c66b54257bbb5e41f278bad77fd690a9",
    ),
    57: (
        "texture_hud_char_double_quote",
        0x04A00,
        "75e471319f515e24448da350c943551c762584b66144032a1d60fe9cc7263e9c",
    ),
    58: ("texture_hud_char_umlaut", 0, ""),
}

buffer = {}


def _register_tex(
    name: str,
    tex_data: bytes,
    offset: int,
    fmt: int,
    siz: int,
    width: int,
    height: int,
) -> None:
    """Store raw texture bytes into the database IR without writing any files."""
    if ctx.db is None:
        return
    addr = (0x02 << 24) | offset
    buffer[name] = TextureRecord(
        addr=addr,
        phys=0,
        seg_num=2,
        offset=offset,
        fmt=fmt,
        siz=siz,
        width=width,
        height=height,
        name=name,
        segment_data=bytes(tex_data),
    )


class Segment2Processor(BaseProcessor):
    """
    Discovers and stores global (Segment 2) textures into db.textures.

    parse()     — scans ROM + seg2, populates TextureRecord entries (no I/O).
    serialize() — converts each stored TextureRecord to a PNG and writes it.
    """

    def parse(self, segmented_addr: int, **kwargs: Any) -> None:
        global seg2_len, arrays

        rom = get_rom()

        seg2 = get_segment(2)
        if not seg2:
            return
        seg2_len = len(seg2)
        arrays = []

        scan_buffer(rom, "ROM")
        scan_buffer(seg2, "SEG2")

        for _file_off, arr, _src in arrays:
            valid_ptrs = [p for p in arr if p != 0]
            if len(valid_ptrs) < 2:
                continue

            for idx, ptr in enumerate(arr):
                if ptr == 0:
                    continue
                offset = ptr & 0xFFFFFF

                # Look ahead for gap detection
                next_ptr = 0
                for k in range(idx + 1, min(idx + 5, len(arr))):
                    if arr[k] != 0:
                        next_ptr = arr[k] & 0xFFFFFF
                        break

                gap = (next_ptr - offset) if next_ptr else 0

                # HUD Logic: Large gaps (0x200) or early in the master table
                if (gap == 0x200) or (idx < 58 and offset < 0x5900):
                    if offset + 0x200 <= seg2_len and offset % 0x200 == 0:
                        tex_data = seg2[offset : offset + 0x200]
                        hud_value = _HUD_MAP.get(idx)
                        if hud_value is None:
                            continue
                        hash_val = hashlib.sha256(tex_data).hexdigest()
                        if hash_val == hud_value[2]:
                            continue
                        name = f"segment2.{hud_value[1]:05X}.rgba16"
                        _register_tex(name, tex_data, offset, fmt=0, siz=2, width=16, height=16)

                """
                # Main Font Logic: Small gaps (0x40) or in the font data area
                elif (gap == 0x40) or (0x5900 <= offset < 0x8000):
                    if offset + 0x40 <= seg2_len and offset % 0x40 == 0:
                        tex_data = seg2[offset : offset + 0x40]
                        name = f"font_graphics.{offset:05X}.ia4"
                        _register_tex(name, tex_data, offset, fmt=3, siz=0, width=8, height=16)

                # IA8 8x16 Fonts
                elif (gap == 0x80) or (offset >= 0x8000 and offset < 0xBD00 and gap == 0):
                    if offset + 0x80 <= seg2_len and offset % 0x80 == 0:
                        tex_data = seg2[offset : offset + 0x80]
                        name = f"segment2.{offset:05X}.ia8"
                        _register_tex(name, tex_data, offset, fmt=3, siz=1, width=8, height=16)

                # IA4 8x8 Fonts
                elif gap == 0x20:
                    if offset + 0x20 <= seg2_len and offset % 0x20 == 0:
                        tex_data = seg2[offset : offset + 0x20]
                        name = f"segment2.{offset:05X}.ia4"
                        _register_tex(name, tex_data, offset, fmt=3, siz=0, width=8, height=8)

                # Transitions/Waterbox logic
                elif (gap == 0x800) or (offset >= 0x8000):
                    if offset + 0x800 <= seg2_len and offset % 0x800 == 0:
                        tex_data = seg2[offset : offset + 0x800]
                        if offset < 0x11000:  # Likely transitions area
                            name = f"segment2.{offset:05X}.ia8"
                            _register_tex(name, tex_data, offset, fmt=3, siz=1, width=32, height=64)
                        else:  # Likely waterboxes
                            name = f"segment2.{offset:05X}.rgba16"
                            _register_tex(name, tex_data, offset, fmt=0, siz=2, width=32, height=32)
                """

    def serialize(self, record: TextureRecord) -> str:
        """Write one segment-2 texture record to the output as a PNG."""

        for name, record in buffer.items():
            if not record.segment_data:
                return ""

            buf = BytesIO()
            fmt = record.fmt
            w, h = record.width, record.height

            # ImageFormat constants: RGBA=0, IA=3, I=4
            if fmt == 0:  # RGBA
                binary_to_png.RGBA(w, h, 16, record.segment_data, buf)
            elif fmt == 3:  # IA
                if record.siz == 0:
                    bpp = 4
                elif record.siz == 2:
                    bpp = 16
                else:
                    bpp = 8
                binary_to_png.IA(w, h, bpp, record.segment_data, buf)
            else:
                binary_to_png.RGBA(w, h, 16, record.segment_data, buf)

            png_bytes = buf.getvalue()
            self.txt.write(ctx, "segment2", record.name, png_bytes)

        return ""


_seg2_processor: Optional[Segment2Processor] = None


def get_segment2_processor() -> Segment2Processor:
    global _seg2_processor
    if _seg2_processor is None:
        _seg2_processor = Segment2Processor(ctx)
    return _seg2_processor
