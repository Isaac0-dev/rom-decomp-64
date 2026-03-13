import struct
from io import BytesIO
from typing import Any, List, Optional, Tuple

from base_processor import BaseProcessor
from context import ctx
from rom_database import TextureRecord
from segment import get_segment
import binary_to_png
from utils import get_rom

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


HUD_CHARACTER_OFFSETS = {
    "texture_hud_char_0": "00000",
    "texture_hud_char_1": "00200",
    "texture_hud_char_2": "00400",
    "texture_hud_char_3": "00600",
    "texture_hud_char_4": "00800",
    "texture_hud_char_5": "00A00",
    "texture_hud_char_6": "00C00",
    "texture_hud_char_7": "00E00",
    "texture_hud_char_8": "01000",
    "texture_hud_char_9": "01200",
    "texture_hud_char_A": "01400",
    "texture_hud_char_B": "01600",
    "texture_hud_char_C": "01800",
    "texture_hud_char_D": "01A00",
    "texture_hud_char_E": "01C00",
    "texture_hud_char_F": "01E00",
    "texture_hud_char_G": "02000",
    "texture_hud_char_H": "02200",
    "texture_hud_char_I": "02400",
    "texture_hud_char_J": "02600",
    "texture_hud_char_K": "02800",
    "texture_hud_char_L": "02A00",
    "texture_hud_char_M": "02C00",
    "texture_hud_char_N": "02E00",
    "texture_hud_char_O": "03000",
    "texture_hud_char_P": "03200",
    "texture_hud_char_Q": "03400",
    "texture_hud_char_R": "03600",
    "texture_hud_char_S": "03800",
    "texture_hud_char_T": "03A00",
    "texture_hud_char_U": "03C00",
    "texture_hud_char_V": "03E00",
    "texture_hud_char_W": "04000",
    "texture_hud_char_X": "04200",
    "texture_hud_char_Y": "04400",
    "texture_hud_char_Z": "04600",
    "texture_hud_char_apostrophe": "04800",
    "texture_hud_char_double_quote": "04A00",
    "texture_hud_char_exclamation": "04C00",
    "texture_hud_char_double_exclamation": "04E00",
    "texture_hud_char_question": "05000",
    "texture_hud_char_ampersand": "05200",
    "texture_hud_char_percent": "05400",
    "texture_hud_char_multiply": "05600",
    "texture_hud_char_coin": "05800",
    "texture_hud_char_mario_head": "05A00",
    "texture_hud_char_star": "05C00",
    "texture_hud_char_decimal_point": "05E00",
    "texture_hud_char_beta_key": "06000",
    "texture_hud_char_umlaut": "umlaut",
    "texture_hud_char_camera": "07B50",
    "texture_hud_char_lakitu": "07D50",
    "texture_hud_char_no_camera": "07F50",
    "texture_hud_char_arrow_up": "08150",
    "texture_hud_char_arrow_down": "081D0",
}

_HUD_MAP = {
    0: "texture_hud_char_0",
    1: "texture_hud_char_1",
    2: "texture_hud_char_2",
    3: "texture_hud_char_3",
    4: "texture_hud_char_4",
    5: "texture_hud_char_5",
    6: "texture_hud_char_6",
    7: "texture_hud_char_7",
    8: "texture_hud_char_8",
    9: "texture_hud_char_9",
    10: "texture_hud_char_A",
    11: "texture_hud_char_B",
    12: "texture_hud_char_C",
    13: "texture_hud_char_D",
    14: "texture_hud_char_E",
    15: "texture_hud_char_F",
    16: "texture_hud_char_G",
    17: "texture_hud_char_H",
    18: "texture_hud_char_I",
    19: "0x0",
    20: "texture_hud_char_K",
    21: "texture_hud_char_L",
    22: "texture_hud_char_M",
    23: "texture_hud_char_N",
    24: "texture_hud_char_O",
    25: "texture_hud_char_P",
    26: "0x0",
    27: "texture_hud_char_R",
    28: "texture_hud_char_S",
    29: "texture_hud_char_T",
    30: "texture_hud_char_U",
    31: "texture_hud_char_V",
    32: "texture_hud_char_W",
    33: "0x0",
    34: "texture_hud_char_Y",
    35: "texture_hud_char_Z",
    36: "0x0",
    37: "0x0",
    38: "0x0",
    39: "0x0",
    40: "0x0",
    41: "0x0",
    42: "0x0",
    43: "0x0",
    44: "0x0",
    45: "0x0",
    46: "0x0",
    47: "0x0",
    48: "0x0",
    49: "0x0",
    50: "texture_hud_char_multiply",
    51: "texture_hud_char_coin",
    52: "texture_hud_char_mario_head",
    53: "texture_hud_char_star",
    54: "0x0",
    55: "0x0",
    56: "texture_hud_char_apostrophe",
    57: "texture_hud_char_double_quote",
    58: "texture_hud_char_umlaut",
}


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
    ctx.db.textures[name] = TextureRecord(
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
    ctx.db.set_symbol(addr, name, "Texture")


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
                    if offset + 0x200 <= seg2_len:
                        tex_data = seg2[offset : offset + 0x200]
                        char_name = _HUD_MAP.get(idx, "0x0")
                        offset_str = HUD_CHARACTER_OFFSETS.get(char_name, f"{offset:05X}")
                        name = f"segment2.{offset_str}.rgba16"
                        _register_tex(name, tex_data, offset, fmt=0, siz=2, width=16, height=16)

                # Main Font Logic: Small gaps (0x40) or in the font data area
                elif (gap == 0x40) or (0x5900 <= offset < 0x8000):
                    if offset + 0x40 <= seg2_len:
                        tex_data = seg2[offset : offset + 0x40]
                        name = f"font_graphics.{offset:05X}.ia4"
                        _register_tex(name, tex_data, offset, fmt=3, siz=0, width=8, height=16)

                # IA8 8x16 Fonts
                elif (gap == 0x80) or (offset >= 0x8000 and offset < 0xBD00 and gap == 0):
                    if offset + 0x80 <= seg2_len:
                        tex_data = seg2[offset : offset + 0x80]
                        name = f"segment2.{offset:05X}.ia8"
                        _register_tex(name, tex_data, offset, fmt=3, siz=1, width=8, height=16)

                # IA4 8x8 Fonts
                elif gap == 0x20:
                    if offset + 0x20 <= seg2_len:
                        tex_data = seg2[offset : offset + 0x20]
                        name = f"segment2.{offset:05X}.ia4"
                        _register_tex(name, tex_data, offset, fmt=3, siz=0, width=8, height=8)

                # Transitions/Waterbox logic
                elif (gap == 0x800) or (offset >= 0x8000):
                    if offset + 0x800 <= seg2_len:
                        tex_data = seg2[offset : offset + 0x800]
                        if offset < 0x11000:  # Likely transitions area
                            name = f"segment2.{offset:05X}.ia8"
                            _register_tex(name, tex_data, offset, fmt=3, siz=1, width=32, height=64)
                        else:  # Likely waterboxes
                            name = f"segment2.{offset:05X}.rgba16"
                            _register_tex(name, tex_data, offset, fmt=0, siz=2, width=32, height=32)

    def serialize(self, record: TextureRecord) -> str:
        """Write one segment-2 texture record to the output as a PNG."""
        if not record.segment_data:
            return ""

        buf = BytesIO()
        fmt = record.fmt
        w, h = record.width, record.height

        # ImageFormat constants: RGBA=0, IA=3, I=4
        if fmt == 0:  # RGBA
            binary_to_png.RGBA(w, h, 16, record.segment_data, buf)
        elif fmt == 3:  # IA
            bpp = 4 if record.siz == 0 else 8
            binary_to_png.IA(w, h, bpp, record.segment_data, buf)
        else:
            binary_to_png.RGBA(w, h, 16, record.segment_data, buf)

        if self.txt:
            self.txt.write(ctx, "segment2", record.name, buf)

        return ""


_seg2_processor: Optional[Segment2Processor] = None


def get_segment2_processor() -> Segment2Processor:
    global _seg2_processor
    if _seg2_processor is None:
        _seg2_processor = Segment2Processor(ctx)
    return _seg2_processor
