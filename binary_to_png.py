import png
import struct
from typing import BinaryIO, Iterator, List, Tuple

# Convert bin to png


def I(width: int, height: int, depth: int, file_data: bytes, image: BinaryIO):
    """
    Converts Intensity (I) format to PNG.
    N64 Formats: I4, I8.
    Output: Greyscale + Alpha (IA).
    """
    if depth == 8:
        # I8: 8-bit intensity. 1 byte per pixel.
        # Output as IA8 (Greyscale+Alpha), with Alpha=255.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_i8_rows(width, height, file_data)

    elif depth == 4:
        # I4: 4-bit intensity. 2 pixels per byte.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_i4_rows(width, height, file_data)
    elif depth == 16:
        # I16 doesn't exist on N64 - this is likely a misinterpreted IA16 texture.
        # Treat as IA16 for compatibility with romhack format/size mismatches.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_ia16_rows(width, height, file_data)
    elif depth == 32:
        # I32 doesn't exist on N64 - treat as RGBA32 for romhack compatibility
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba32_rows(width, height, file_data)
    else:
        raise ValueError(f"Unsupported I depth: {depth}")

    w.write(image, rows)


def IA(width: int, height: int, depth: int, file_data: bytes, image: BinaryIO):
    """
    Converts Intensity+Alpha (IA) format to PNG.
    N64 Formats: IA4, IA8, IA16.
    Output: Greyscale + Alpha (IA).
    """
    if depth == 16:
        # IA16: 8-bit I, 8-bit A. 2 bytes per pixel.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_ia16_rows(width, height, file_data)
    elif depth == 8:
        # IA8: 4-bit I, 4-bit A. 1 byte per pixel.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_ia8_rows(width, height, file_data)
    elif depth == 4:
        # IA4: 3-bit I, 1-bit A. 2 pixels per byte.
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_ia4_rows(width, height, file_data)
    elif depth == 32:
        # IA32 doesn't exist on N64 - treat as RGBA32 for romhack compatibility
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba32_rows(width, height, file_data)
    else:
        raise ValueError(f"Unsupported IA depth: {depth}")

    w.write(image, rows)


def RGBA(width: int, height: int, depth: int, file_data: bytes, image: BinaryIO):
    """
    Converts RGBA format to PNG.
    N64 Formats: RGBA16, RGBA32.
    Output: RGBA.
    """
    if depth == 16:
        # RGBA16: 5-5-5-1. 2 bytes per pixel.
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba16_rows(width, height, file_data)
    elif depth == 32:
        # RGBA32: 8-8-8-8. 4 bytes per pixel.
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba32_rows(width, height, file_data)
    elif depth == 8:
        # RGBA8 doesn't exist on N64 - treat as I8 for romhack compatibility
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_i8_rows(width, height, file_data)
    elif depth == 4:
        # RGBA4 doesn't exist on N64 - treat as I4 for romhack compatibility
        w = png.Writer(width, height, greyscale=True, bitdepth=8, alpha=True)
        rows = _create_i4_rows(width, height, file_data)
    else:
        raise ValueError(f"Unsupported RGBA depth: {depth}")

    w.write(image, rows)


def CI(width: int, height: int, depth: int, palette_data: bytes, file_data: bytes, image: BinaryIO):
    """
    Converts Color Index (CI) format to PNG.
    N64 Formats: CI4, CI8.
    Output: Paletted PNG.
    """
    if depth == 16:
        # CI16 doesn't exist on N64 - this is a format/size mismatch.
        # Treat as RGBA16 for compatibility with romhack texture issues.
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba16_rows(width, height, file_data)
        w.write(image, rows)
        return
    elif depth == 32:
        # CI32 doesn't exist on N64 - treat as RGBA32 for romhack compatibility
        w = png.Writer(width, height, greyscale=False, bitdepth=8, alpha=True)
        rows = _create_rgba32_rows(width, height, file_data)
        w.write(image, rows)
        return

    palette = _get_palette(palette_data, depth)
    w = png.Writer(width, height, palette=palette, bitdepth=depth)

    if depth == 8:
        rows = _create_ci8_rows(width, height, file_data)
    elif depth == 4:
        rows = _create_ci4_rows(width, height, file_data)
    else:
        raise ValueError(f"Unsupported CI depth: {depth}")

    w.write(image, rows)


# --- Helper Functions ---


def _create_i8_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    for y in range(height):
        row_start = y * width
        row_data = []
        for x in range(width):
            i_val = data[row_start + x]
            row_data.extend([i_val, 255])  # I, A
        yield row_data


def _create_i4_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    stride = (width + 1) // 2
    for y in range(height):
        row_start = y * stride
        row_data = []
        for x in range(0, width, 2):
            byte = data[row_start + (x // 2)]

            # Pixel 1 (high nibble)
            i1 = (byte >> 4) & 0xF
            i1_scaled = (i1 * 255 + 7) // 15
            row_data.extend([i1_scaled, 255])

            # Pixel 2 (low nibble) - check if exists (for odd widths)
            if x + 1 < width:
                i2 = byte & 0xF
                i2_scaled = (i2 * 255 + 7) // 15
                row_data.extend([i2_scaled, 255])
        yield row_data


def _create_ia16_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    for y in range(height):
        row_start = y * width * 2
        row_data = []
        for x in range(width):
            # Big-endian short
            idx = row_start + x * 2
            i_val = data[idx]
            a_val = data[idx + 1]
            row_data.extend([i_val, a_val])
        yield row_data


def _create_ia8_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    for y in range(height):
        row_start = y * width
        row_data = []
        for x in range(width):
            byte = data[row_start + x]
            i_val = (byte >> 4) & 0xF
            a_val = byte & 0xF

            i_scaled = (i_val * 255 + 7) // 15
            a_scaled = (a_val * 255 + 7) // 15
            row_data.extend([i_scaled, a_scaled])
        yield row_data


def _create_ia4_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    stride = (width + 1) // 2
    for y in range(height):
        row_start = y * stride
        row_data = []
        for x in range(0, width, 2):
            byte = data[row_start + (x // 2)]

            # Pixel 1 (high nibble)
            p1 = (byte >> 4) & 0xF
            i1 = (p1 >> 1) & 0x7
            a1 = p1 & 0x1
            i1_scaled = (i1 * 255 + 3) // 7
            a1_scaled = 255 if a1 else 0
            row_data.extend([i1_scaled, a1_scaled])

            # Pixel 2 (low nibble)
            if x + 1 < width:
                p2 = byte & 0xF
                i2 = (p2 >> 1) & 0x7
                a2 = p2 & 0x1
                i2_scaled = (i2 * 255 + 3) // 7
                a2_scaled = 255 if a2 else 0
                row_data.extend([i2_scaled, a2_scaled])
        yield row_data


def _create_rgba32_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    for y in range(height):
        row_start = y * width * 4
        # Slice the row directly
        row_bytes = data[row_start : row_start + width * 4]
        yield list(row_bytes)


def _create_rgba16_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    row_fmt = f">{width}H"
    row_size = width * 2

    for y in range(height):
        row_start = y * row_size
        # Unpack the entire row at once
        row_shorts = struct.unpack_from(row_fmt, data, row_start)

        row_data = [
            component
            for val in row_shorts
            for component in (
                (((val >> 11) & 0x1F) * 255 + 15) // 31,
                (((val >> 6) & 0x1F) * 255 + 15) // 31,
                (((val >> 1) & 0x1F) * 255 + 15) // 31,
                255 if (val & 1) else 0,
            )
        ]
        yield row_data


def _create_ci8_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    for y in range(height):
        row_start = y * width
        row_bytes = data[row_start : row_start + width]
        yield list(row_bytes)


def _create_ci4_rows(width: int, height: int, data: bytes) -> Iterator[List[int]]:
    stride = (width + 1) // 2
    for y in range(height):
        row_start = y * stride
        row_data = []
        for x in range(0, width, 2):
            byte = data[row_start + (x // 2)]
            p1 = (byte >> 4) & 0xF
            row_data.append(p1)
            if x + 1 < width:
                p2 = byte & 0xF
                row_data.append(p2)
        yield row_data


def _get_palette(palette_data: bytes, depth: int) -> List[Tuple[int, int, int, int]]:
    # Palette is always RGBA16 (5-5-5-1)
    # 256 entries for CI8, 16 entries for CI4
    num_entries = 2**depth
    palette = []
    for i in range(num_entries):
        idx = i * 2
        if idx + 1 >= len(palette_data):
            break
        val = (palette_data[idx] << 8) | palette_data[idx + 1]

        r = (val >> 11) & 0x1F
        g = (val >> 6) & 0x1F
        b = (val >> 1) & 0x1F
        a = val & 0x1

        r_scaled = (r * 255 + 15) // 31
        g_scaled = (g * 255 + 15) // 31
        b_scaled = (b * 255 + 15) // 31
        a_scaled = 255 if a else 0

        palette.append((r_scaled, g_scaled, b_scaled, a_scaled))
    return palette
