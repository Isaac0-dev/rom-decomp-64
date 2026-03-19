import segment
from context import ctx
from utils import (
    debug_fail,
    debug_print,
    level_name_to_int,
    level_name_to_int_lookup,
    offset_from_segment_addr,
    segment_from_addr,
)
from segment import get_segment, segmented_to_virtual, wait_for_segment_load
import os
import math
import binary_to_png
from byteio import BytesIO
from PIL import Image

from base_processor import BaseProcessor
from enum import IntEnum
from typing import Any, Dict, Optional, Union, List, Set, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


class ImageFormat(IntEnum):
    RGBA = 0
    YUV = 1
    CI = 2
    IA = 3
    I = 4


class ImageSize(IntEnum):
    B4 = 0
    B8 = 1
    B16 = 2
    B32 = 3


@dataclass
class TextureInfo:
    addr: int = 0
    fmt: int = ImageFormat.RGBA
    tile_fmt: Optional[int] = None
    siz: int = ImageSize.B16
    width: int = 0
    height: int = 0
    context_prefix: Optional[str] = None


@dataclass
class TextureMeta:
    fmt: int
    w: int
    h: int
    bpp: int
    offset: int
    seg_num: int
    segment_data: Union[bytearray, bytes, List[int]]
    palette: Optional[Union[bytearray, bytes, List[int]]]
    addr: int
    phys: int
    dl_pos: int


# State for the current texture image set by gsDPSetTextureImage
# It's not reset at the end of processing to allow other display lists
# to reuse the current texture info (like switches in the geo layout)
current_texture_info = TextureInfo()

texture_table: Dict[str, TextureMeta] = {}

# Store the reference to the skybox that we loaded
# So geo layouts can later reference it
current_skybox: Optional[Any] = None


def get_current_skybox() -> Optional[Any]:
    return current_skybox


def set_current_skybox(skybox: Any) -> None:
    global current_skybox
    current_skybox = skybox


current_palette: Optional[Union[bytearray, bytes, List[int]]] = None


def load_tlut(sTxt: Any, count: int, tmem_addr: int, tex_info: Optional[TextureInfo]) -> None:
    global current_palette

    if tex_info is None:
        tex_info = current_texture_info

    addr = tex_info.addr
    if addr == 0:
        debug_print("DEBUG: load_tlut called but tex_info.addr is 0 - TLUT load skipped")
        return

    # Palette is always RGBA16
    # count is number of colors
    size = count * 2  # 2 bytes per color

    segment = get_segment(segment_from_addr(addr))
    if not segment:
        debug_print(f"WARNING: Segment {segment_from_addr(addr)} not loaded for TLUT at 0x{addr:X}")
        wait_for_segment_load(load_tlut, addr, (sTxt, count, tmem_addr, tex_info))
        return

    offset = offset_from_segment_addr(addr)
    segment_data = segment

    if offset + size > len(segment_data):
        debug_print(
            f"WARNING: TLUT data at 0x{addr:08X} exceeds segment bounds (offset: 0x{offset:X}, size: {size}, segment length: {len(segment_data)})"
        )
        return

    current_palette = segment_data[offset : offset + size]
    # debug_print(f"DEBUG: TLUT loaded successfully from 0x{addr:08X}, {count} colors")


image_handlers: Dict[int, Callable[..., None]] = {
    ImageFormat.RGBA: binary_to_png.RGBA,
    ImageFormat.CI: binary_to_png.CI,
    ImageFormat.IA: binary_to_png.IA,
    ImageFormat.I: binary_to_png.I,
}


# Create a thread pool with optimal number of workers
executor = ThreadPoolExecutor(max_workers=os.cpu_count())
_skipped_textures: Set[str] = set()


def _write_png_worker(
    sTxt: Any,
    name: str,
    fmt: int,
    w: int,
    h: int,
    bpp: int,
    offset: int,
    seg_num: int,
    segment_data: Union[bytearray, bytes, List[int]],
    palette: Optional[Union[bytearray, bytes, List[int]]],
) -> None:

    # TODO This is a hack!
    try:
        required_bytes = (w * h * bpp + 7) // 8
        seg_len = len(segment_data)
        data_source = segment_data

        available = seg_len - offset

        if offset >= seg_len or available < required_bytes:
            # Try to find an alternate cached load of this segment with enough data
            alt_data = None
            for key, cached in segment._segment_cache.items():
                # key: (mode, seg_num, start, end, should_decompress)
                if len(key) < 2 or key[1] != seg_num:
                    continue
                data = cached.get("data")
                if not data:
                    continue
                if offset < len(data) and len(data) - offset >= required_bytes:
                    alt_data = data
                    seg_len = len(data)
                    available = seg_len - offset
                    break

            if alt_data is not None:
                if name not in _skipped_textures:
                    debug_print(
                        f"INFO: Using alternate segment {seg_num} data for {name} (len 0x{seg_len:X})"
                    )
                    _skipped_textures.add(name)
                data_source = alt_data
            else:
                if name not in _skipped_textures:
                    reason = "offset" if offset >= seg_len else "size"
                    if reason == "offset":
                        debug_print(
                            f"WARNING: Skipping texture {name}: offset 0x{offset:X} is beyond segment data (len 0x{seg_len:X})"
                        )
                    else:
                        debug_print(
                            f"WARNING: Skipping texture {name}: needs 0x{required_bytes:X} bytes but only 0x{available:X} are available"
                        )
                    _skipped_textures.add(name)
                return

        tex_data = data_source[offset : offset + required_bytes]
        buffer = BytesIO()
        if palette is not None:
            image_handlers[fmt](w, h, bpp, palette, tex_data, buffer)
        else:
            image_handlers[fmt](w, h, bpp, tex_data, buffer)

        sTxt.write(ctx, "texture", name, buffer)
    except Exception as e:
        debug_fail(f"Error in texture worker for {name}: {e}")


def write_texture(
    sTxt: Any,
    name: str,
    fmt: int,
    w: int,
    h: int,
    bpp: int,
    offset: int,
    seg_num: int,
    segment_data: Union[bytearray, bytes, List[int]],
    palette: Optional[Union[bytearray, bytes, List[int]]],
) -> None:
    """Store raw pixel data on the TextureRecord for deferred writing."""
    if fmt == ImageFormat.CI and palette is None:
        debug_print(
            f"WARNING: Skipping CI texture {name}: CI format requires a palette, but none was loaded."
        )
        return

    if ctx.db is not None and name in ctx.db.textures:
        rec = ctx.db.textures[name]
        # Snapshot the raw bytes now while the segment is loaded
        required_bytes = (w * h * bpp + 7) // 8
        available = len(segment_data) - offset
        if offset < len(segment_data) and available >= required_bytes:
            rec.segment_data = bytes(segment_data[offset : offset + required_bytes])
        else:
            # Try alternate segment cache
            for key, cached in segment._segment_cache.items():
                if len(key) < 2 or key[1] != seg_num:
                    continue
                data = cached.get("data")
                if not data:
                    continue
                if offset < len(data) and len(data) - offset >= required_bytes:
                    rec.segment_data = bytes(data[offset : offset + required_bytes])
                    break
        if palette is not None:
            rec.palette_data = bytes(palette)


def set_tile_size(tile: int, uls: int, ult: int, lrs: int, lrt: int) -> None:
    # Calculate width and height from tile size
    # Coordinates are 10.2 fixed point (shifted by 2)
    w = ((lrs - uls) >> 2) + 1
    h = ((lrt - ult) >> 2) + 1

    current_texture_info.width = w
    current_texture_info.height = h


def set_tile_format(tile: int, fmt: int, siz: Optional[int]) -> None:
    global current_texture_info

    # Skip TX_LOADTILE (0x7)
    if tile == 0x7:
        return

    # Only process TX_RENDERTILE (0x0)
    if tile == 0x0:
        current_texture_info.tile_fmt = fmt
        # Also update siz if provided
        if siz is not None:
            current_texture_info.siz = siz


def set_texture_image(
    segmented_addr: int, fmt: int, siz: int, width: int, context_prefix: Optional[str] = None
) -> str:
    global current_texture_info

    current_texture_info.addr = segmented_addr
    current_texture_info.fmt = fmt  # Fallback only
    current_texture_info.siz = siz
    if current_texture_info.width == 0:
        current_texture_info.width = width
    current_texture_info.context_prefix = context_prefix
    # Don't reset tile_fmt here - it's set by G_SETTILE

    phys = segmented_to_virtual(segmented_addr)
    seg_num = segment_from_addr(segmented_addr)

    name = f"texture_{segmented_addr:08X}_{phys:08X}_seg{seg_num}"
    if context_prefix:
        name = f"{context_prefix}_{name}"

    if name not in ctx.db.textures:
        from rom_database import TextureRecord

        ctx.db.textures[name] = TextureRecord(
            addr=segmented_addr,
            phys=phys,
            seg_num=seg_num,
            offset=offset_from_segment_addr(segmented_addr),
            fmt=fmt,
            siz=siz,
            width=width,
            height=0,  # Unknown yet
            name=name,
        )
        ctx.db.set_symbol(segmented_addr, name, "Texture")

    return ctx.db.textures[name]


def load_block(
    sTxt: Any,
    pos: int,
    tile: int,
    uls: int,
    ult: int,
    lrs: int,
    dxt: int,
    tex_info: Optional[TextureInfo],
) -> None:
    global current_texture_info

    if tex_info is None:
        tex_info = current_texture_info

    addr = tex_info.addr
    # Use tile_fmt if set (from G_SETTILE), otherwise fallback to fmt (from G_SETTIMG)
    fmt = tex_info.tile_fmt if tex_info.tile_fmt is not None else tex_info.fmt
    siz = tex_info.siz
    width = tex_info.width
    context_prefix = tex_info.context_prefix

    if addr == 0:
        return

    phys = segmented_to_virtual(addr)
    seg_num = segment_from_addr(addr)

    name = f"texture_{addr:08X}_{phys:08X}_seg{seg_num}"
    if context_prefix:
        name = f"{context_prefix}_{name}"

    offset = offset_from_segment_addr(addr)
    segment_data = get_segment(seg_num)
    if segment_data is None:
        debug_print(f"WARNING: Segment {seg_num} for texture 0x{addr:08X} not loaded")
        wait_for_segment_load(load_block, addr, (sTxt, pos, tile, uls, ult, lrs, dxt, tex_info))
        return

    # bits per pixel
    image_size_type_to_bpp = [4, 8, 16, 32]
    bpp = image_size_type_to_bpp[siz]

    texels = lrs + 1

    # Calculate actual width from dxt parameter if available
    w = width
    if dxt > 0:
        calculated_width = (2048 * 64) // (dxt * bpp)
        if calculated_width > 0:
            w = calculated_width

    if w <= 1:
        w = int(math.sqrt(texels))

    h = (texels + w - 1) // w

    palette = current_palette if fmt == ImageFormat.CI else None

    texture_table[name] = TextureMeta(
        fmt=fmt,
        w=w,
        h=h,
        bpp=bpp,
        offset=offset,
        seg_num=seg_num,
        segment_data=segment_data,
        palette=palette,
        addr=addr,
        phys=phys,
        dl_pos=pos,
    )

    if ctx.db is not None:
        from rom_database import TextureRecord

        ctx.db.textures[name] = TextureRecord(
            addr=addr,
            phys=phys,
            seg_num=seg_num,
            offset=offset,
            fmt=fmt,
            siz=siz,
            width=w,
            height=h,
            name=name,
        )
        ctx.db.set_symbol(addr, name, "Texture")

    write_texture(sTxt, name, fmt, w, h, bpp, offset, seg_num, segment_data, palette)


def load_tile(sTxt: Any, pos: int, tile: int, uls: int, ult: int, lrs: int, lrt: int) -> None:
    global current_texture_info

    addr = current_texture_info.addr
    # Use tile_fmt if set (from G_SETTILE), otherwise fallback to fmt (from G_SETTIMG)
    fmt = (
        current_texture_info.tile_fmt
        if current_texture_info.tile_fmt is not None
        else current_texture_info.fmt
    )
    siz = current_texture_info.siz
    context_prefix = current_texture_info.context_prefix

    if addr == 0:
        return

    phys = segmented_to_virtual(addr)

    seg_num = segment_from_addr(addr)
    offset = offset_from_segment_addr(addr)
    segment_data = get_segment(seg_num)
    if segment_data is None:
        debug_print(f"WARNING: Segment {seg_num} for texture 0x{addr:08X} not loaded")
        return

    name = f"texture_{addr:08X}_{phys:08X}_seg{seg_num}"
    if context_prefix:
        name = f"{context_prefix}_{name}"

    image_size_type_to_bpp = [4, 8, 16, 32]
    bpp = image_size_type_to_bpp[siz]

    w = ((lrs - uls) >> 2) + 1
    h = ((lrt - ult) >> 2) + 1

    palette = current_palette if fmt == ImageFormat.CI else None

    texture_table[name] = TextureMeta(
        fmt=fmt,
        w=w,
        h=h,
        bpp=bpp,
        offset=offset,
        seg_num=seg_num,
        segment_data=segment_data,
        palette=palette,
        addr=addr,
        phys=phys,
        dl_pos=pos,
    )

    if ctx.db is not None:
        from rom_database import TextureRecord

        ctx.db.textures[name] = TextureRecord(
            addr=addr,
            phys=phys,
            seg_num=seg_num,
            offset=offset,
            fmt=fmt,
            siz=siz,
            width=w,
            height=h,
            name=name,
        )
        ctx.db.set_symbol(addr, name, "Texture")

    write_texture(sTxt, name, fmt, w, h, bpp, offset, seg_num, segment_data, palette)


SCALE_5_8 = [x * 255 // 31 for x in range(32)]


def extract_skybox(seg: int, txt: Any, level_name: str) -> None:
    """Snapshot the skybox segment data into a SkyboxRecord for deferred rendering."""
    if (seg & 0xFF) != 0x0A:
        return

    level_prefix = level_name
    for known_level in level_name_to_int:
        if level_name.startswith(known_level + "_"):
            level_prefix = known_level
            break

    seg_data = get_segment(0x0A)
    if seg_data is None:
        return

    # Set current_skybox so geo layout can reference it immediately
    global current_skybox
    current_skybox = f"{level_prefix}_skybox_ptrlist"

    if ctx.db is not None:
        from rom_database import SkyboxRecord

        ctx.db.skyboxes[level_prefix] = SkyboxRecord(
            level_prefix=level_prefix,
            seg_data=bytes(seg_data),
        )


def convert_skybox_to_c(image, skybox_name, txt):
    # Constants from skyconv.c IMAGE_PROPERTIES[Skybox]
    TILE_WIDTH = 32
    TILE_HEIGHT = 32
    NUM_COLS = 8
    NUM_ROWS = 8
    IMAGE_WIDTH = 248
    IMAGE_HEIGHT = 248

    # Allocate tiles
    tiles: List[Dict[str, Any]] = []
    for _ in range(NUM_ROWS * NUM_COLS):
        tiles.append({"px": None, "useless": False, "pos": 0})

    pixels = image.load()

    # Split tiles (split_tile + init_tiles logic)
    for row in range(NUM_ROWS):
        for col in range(NUM_COLS):
            tile_data = []
            for y in range(31):  # 248x248 uses 31x31 per tile
                for x in range(31):
                    ny = row * 31 + y
                    nx = col * 31 + x
                    if nx < IMAGE_WIDTH and ny < IMAGE_HEIGHT:
                        pixel = pixels[nx, ny]
                        tile_data.append(pixel)
                    else:
                        tile_data.append((0, 0, 0, 255))

            # Store as 32x32 (will be expanded)
            tile_px = [[(0, 0, 0, 255) for _ in range(TILE_WIDTH)] for _ in range(TILE_HEIGHT)]
            for y in range(31):
                for x in range(31):
                    tile_px[y][x] = tile_data[y * 31 + x]

            tiles[row * NUM_COLS + col]["px"] = tile_px

    # Expand tiles (expand_tiles logic - add edge pixels)
    # Copy each tile's left edge to the previous tile's right edge
    for row in range(NUM_ROWS):
        for col in range(NUM_COLS):
            next_col = (col + 1) % NUM_COLS
            for y in range(TILE_HEIGHT - 1):
                tiles[row * NUM_COLS + col]["px"][y][TILE_WIDTH - 1] = tiles[
                    row * NUM_COLS + next_col
                ]["px"][y][0]

    # Copy each tile's top edge to the previous tile's bottom edge
    for row in range(NUM_ROWS):
        if row < NUM_ROWS - 1:
            for col in range(NUM_COLS):
                next_row = row + 1
                for x in range(TILE_WIDTH):
                    tiles[row * NUM_COLS + col]["px"][TILE_HEIGHT - 1][x] = tiles[
                        next_row * NUM_COLS + col
                    ]["px"][0][x]
        else:
            # Last row: duplicate second-to-last row
            for col in range(NUM_COLS):
                for x in range(TILE_WIDTH):
                    tiles[row * NUM_COLS + col]["px"][TILE_HEIGHT - 1][x] = tiles[
                        row * NUM_COLS + col
                    ]["px"][TILE_HEIGHT - 2][x]

    # Assign tile positions (optimize duplicates)
    new_pos = 0
    for i in range(NUM_ROWS * NUM_COLS):
        # Check if this tile is duplicate of a previous one
        for j in range(i):
            if not tiles[j]["useless"] and tiles[j]["px"] == tiles[i]["px"]:
                tiles[i]["useless"] = True
                tiles[i]["pos"] = j
                break

        if not tiles[i]["useless"]:
            tiles[i]["pos"] = new_pos
            new_pos += 1

    # Generate C code (write_skybox_c logic)
    c_output = []

    # Write texture data for each unique tile
    for i in range(NUM_ROWS * NUM_COLS):
        if not tiles[i]["useless"]:
            pos = tiles[i]["pos"]

            # Create PNG for the tile
            tile_img = Image.new("RGBA", (TILE_WIDTH, TILE_HEIGHT))
            pixels = []
            for y in range(TILE_HEIGHT):
                for x in range(TILE_WIDTH):
                    r, g, b, a = tiles[i]["px"][y][x]
                    pixels.append((r, g, b, a))
            tile_img.putdata(pixels)

            png_buffer = BytesIO()
            tile_img.save(png_buffer, format="PNG")
            png_buffer.seek(0)

            tile_filename = f"{skybox_name}_skybox_texture_tile.{pos}.rgba16"
            txt.write(ctx, "skybox_texture_tile", tile_filename, png_buffer)

            c_output.append(
                f'ALIGNED8 static const Texture {skybox_name}_skybox_texture_{pos:05X}[] = "../textures/skybox_tiles/{tile_filename}";\n'
            )

    # Write pointer list (8x10 table)
    def get_index(tiles, i):
        if tiles[i]["useless"]:
            i = tiles[i]["pos"]
        return tiles[i]["pos"]

    c_output.append(f"\nconst Texture *const {skybox_name}_skybox_ptrlist[] = {{\n")
    for row in range(8):
        for col in range(10):
            idx = get_index(tiles, row * 8 + (col % 8))
            c_output.append(f"    {skybox_name}_skybox_texture_{idx:05X},\n")
    c_output.append("};\n\n")

    # Write to output
    c_code = "".join(c_output)
    txt.write(ctx, "skybox_tiles", f"{skybox_name}_tiles_c", c_code)


# ---------------------------------------------------------------------------
# TextureProcessor
# ---------------------------------------------------------------------------


class TextureProcessor(BaseProcessor):
    """
    Serializes TextureRecord instances to PNG + C struct output.

    parse() is not used here (texture discovery happens inside display-list
    processing via load_block / load_tile, which already populate db.textures).
    serialize() is the main entry point called from pass_serialize.
    """

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        # Discovery is handled by load_block / load_tile; nothing extra to do.
        return ""

    def serialize(self, record: Any) -> str:
        """Write PNG + C struct for one TextureRecord."""
        from rom_database import TextureRecord as _TextureRecord

        if not isinstance(record, _TextureRecord):
            return ""

        name = record.name
        fmt = record.fmt
        w = record.width
        h = record.height
        siz = record.siz
        bpp = [4, 8, 16, 32][siz]
        palette = record.palette_data

        if fmt == ImageFormat.CI and palette is None:
            debug_print(f"WARNING: Skipping CI texture {name} at serialize: no palette.")
            return ""

        # Level-specific path prefix for DynOS
        path = ""
        for level in level_name_to_int_lookup:
            if name.startswith(level + "_") or name == level:
                path = f"{level}/"
                if "_area_" in name:
                    area_num_str = name.split("_area_")[1].split("_")[0]
                    if area_num_str.isdigit():
                        path += f"areas/{area_num_str}/"
                break

        # PNG is written asynchronously
        if record.segment_data:
            executor.submit(
                _write_png_worker,
                self.txt,
                name,
                fmt,
                w,
                h,
                bpp,
                0,  # offset already applied at snapshot time
                record.seg_num,
                record.segment_data,  # pre-sliced bytes
                palette,
            )

        u8_buffer = f'ALIGNED8 Texture {name} = {{\n#include "{path}{name}.inc.c"\n}};\n\n'

        # Write to raw.log and model.inc.c cached handle
        if self.txt:
            self.txt.write(ctx, "texture_dl", name.replace("texture", "dl"), u8_buffer)

        if palette is not None:
            pal_str = ", ".join(f"0x{b:02X}" for b in palette)
            u8_palette = f"ALIGNED8 const u8 {name}_pal[] = {{\n    {pal_str}\n}};\n\n"
            if self.txt:
                self.txt.write(ctx, "texture_dl", name.replace("texture", "dl"), u8_palette)
            u8_buffer += u8_palette

        return u8_buffer


_texture_processor: Optional[TextureProcessor] = None


def get_texture_processor() -> TextureProcessor:
    global _texture_processor
    if _texture_processor is None:
        _texture_processor = TextureProcessor(ctx)
    return _texture_processor


# ---------------------------------------------------------------------------
# SkyboxProcessor
# ---------------------------------------------------------------------------


class SkyboxProcessor(BaseProcessor):
    """
    Converts a snapshotted SkyboxRecord to a full PNG + C tile output.

    parse() is not used (snapshot is taken in extract_skybox).
    serialize() is called from pass_serialize.
    """

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        return ""

    def serialize(self, record: Any) -> str:
        """Reassemble skybox tiles from raw seg_data and write PNG + C."""
        from rom_database import SkyboxRecord as _SkyboxRecord

        if not isinstance(record, _SkyboxRecord):
            return ""

        seg_data = record.seg_data
        level_prefix = record.level_prefix
        seg_len = len(seg_data)

        final_image = Image.new("RGBA", (248, 248))

        for tile_idx in range(0x40):  # 64 tiles
            tile_offset = tile_idx * 0x800
            tile = Image.new("RGBA", (32, 32))
            if tile_offset + 0x800 > seg_len:
                pixels = [(0, 0, 0, 0xFF)] * (32 * 32)
            else:
                pixels = []
                for pixel_idx in range(32 * 32):
                    off = tile_offset + pixel_idx * 2
                    rgba16 = (seg_data[off] << 8) | seg_data[off + 1]
                    r = SCALE_5_8[(rgba16 >> 11) & 0x1F]
                    g = SCALE_5_8[(rgba16 >> 6) & 0x1F]
                    b = SCALE_5_8[(rgba16 >> 1) & 0x1F]
                    pixels.append((r, g, b, 0xFF))
            tile.putdata(pixels)
            x = (tile_idx * 31) % 248
            y = int((tile_idx * 31) / 248) * 31
            final_image.paste(tile, (x, y))

        # Write composite skybox PNG
        buffer = BytesIO()
        final_image.save(buffer, format="PNG")
        buffer.seek(0)
        if self.txt:
            self.txt.write(ctx, "skybox_texture", f"{level_prefix}_skybox_texture", buffer)

        # Build tiles + C code synchronously (can be threaded if slow)
        convert_skybox_to_c(final_image, level_prefix, self.txt)

        return ""


_skybox_processor: Optional[SkyboxProcessor] = None


def get_skybox_processor() -> SkyboxProcessor:
    global _skybox_processor
    if _skybox_processor is None:
        _skybox_processor = SkyboxProcessor(ctx)
    return _skybox_processor
