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
from gbi_defines import G_TX_RENDERTILE, G_TX_LOADTILE
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
class TileInfo:
    fmt: Optional[int] = None
    siz: Optional[int] = None
    width: int = 0
    height: int = 0
    tmem: int = 0
    config_pos: int = 0


@dataclass
class TextureSource:
    addr: int
    phys: int
    seg_num: int
    offset: int
    fmt: int
    siz: int
    width: int
    height: int
    context_prefix: Optional[str] = None


@dataclass
class TextureInfo:
    addr: int = 0
    phys: int = 0
    fmt: int = ImageFormat.RGBA
    siz: int = ImageSize.B16
    width: int = 0
    height: int = 0
    context_prefix: Optional[str] = None
    tiles: List[TileInfo] = None
    tmem_map: Dict[int, TextureSource] = None

    def __post_init__(self):
        if self.tiles is None:
            self.tiles = [TileInfo() for _ in range(8)]
        if self.tmem_map is None:
            self.tmem_map = {}


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
current_palette: Optional[Union[bytearray, bytes, List[int]]] = None

texture_table: Dict[str, TextureMeta] = {}


def get_current_skybox() -> Optional[str]:
    if ctx.curr_level not in ctx.db.skyboxes:
        return None
    skybox = ctx.db.skyboxes[ctx.curr_level]
    skybox.is_used = True
    return skybox.skybox_name


def load_tlut(sTxt: Any, count: int, tmem_addr: int, tex_info: Optional[TextureInfo]) -> None:
    global current_palette

    if tex_info is None:
        tex_info = current_texture_info

    addr = tex_info.addr
    if addr == 0:
        debug_print("load_tlut called but tex_info.addr is 0 - TLUT load skipped")
        return

    # Palette is always RGBA16
    # count is number of colors
    size = count * 2  # 2 bytes per color

    seg_num = segment_from_addr(addr)
    segment = get_segment(seg_num)
    if not segment:
        debug_print(f"WARNING: Segment {seg_num} not loaded for TLUT at 0x{addr:X}")
        wait_for_segment_load(load_tlut, addr, (sTxt, count, tmem_addr, tex_info))
        return

    offset = offset_from_segment_addr(addr)
    segment_data = segment

    # Validate mapping if we have a recorded physical address
    if segment_data is not None and tex_info.phys != 0:
        current_phys = segmented_to_virtual(addr)
        if current_phys != tex_info.phys:
            debug_print(
                f"Mapping mismatch for palette at 0x{addr:08X}. "
                f"Expected 0x{tex_info.phys:08X}, got 0x{current_phys:08X}. "
                "Using ROM fallback."
            )
            segment_data = None

    if segment_data is None:
        # ROM Fallback
        phys = tex_info.phys if tex_info.phys != 0 else segmented_to_virtual(addr)
        if ctx.rom:
            try:
                ctx.rom.seek(phys)
                current_palette = ctx.rom.read(size)
                if len(current_palette) != size:
                    current_palette = None
            except Exception as e:
                debug_print(f"TLUT ROM fallback failed: {e}")
                current_palette = None

        if current_palette is None:
            debug_print(f"WARNING: Segment {seg_num} not loaded for TLUT at 0x{addr:X}")
            wait_for_segment_load(load_tlut, addr, (sTxt, count, tmem_addr, tex_info))
            return
    else:
        if offset + size > len(segment_data):
            debug_print(
                f"WARNING: TLUT data at 0x{addr:08X} exceeds segment bounds (offset: 0x{offset:X}, size: {size}, segment length: {len(segment_data)})"
            )
            return
        current_palette = segment_data[offset : offset + size]

    # Mark the record as a palette so we don't try to write it as an image
    phys = segmented_to_virtual(addr)
    name = f"texture_{addr:08X}_{phys:08X}_seg{seg_num}"
    if tex_info.context_prefix:
        name = f"{tex_info.context_prefix}_{name}"

    from rom_database import TextureRecord

    if name in ctx.db.textures:
        rec = ctx.db.textures[name]
        rec.is_palette = True
        rec.palette_data = current_palette
    else:
        ctx.db.textures[name] = TextureRecord(
            addr=addr,
            phys=phys,
            seg_num=seg_num,
            offset=offset,
            name=name,
            context_prefix=tex_info.context_prefix,
            is_palette=True,
            palette_data=current_palette,
        )
    ctx.db.set_symbol(addr, name, "Texture")


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
    phys: Optional[int] = None,
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
                        f"Using alternate segment {seg_num} data for {name} (len 0x{seg_len:X})"
                    )
                    _skipped_textures.add(name)
                data_source = alt_data
            elif phys is not None and ctx.rom:
                # Try physical ROM fallback
                try:
                    ctx.rom.seek(phys)
                    rom_data = ctx.rom.read(required_bytes)
                    if len(rom_data) == required_bytes:
                        if name not in _skipped_textures:
                            debug_print(f"Using physical ROM fallback for {name} at 0x{phys:08X}")
                            _skipped_textures.add(name)
                        data_source = rom_data
                        offset = 0  # We read exactly what we need
                        seg_len = required_bytes
                        available = required_bytes
                except Exception as e:
                    debug_print(f"Physical ROM fallback failed for {name}: {e}")

            if available < required_bytes:
                if name not in _skipped_textures:
                    reason = "offset" if offset >= seg_len else "size"
                    if reason == "offset":
                        debug_print(
                            f"Skipping texture {name}: offset 0x{offset:X} is beyond data (len 0x{seg_len:X})"
                        )
                    else:
                        debug_print(
                            f"Skipping texture {name}: needs 0x{required_bytes:X} bytes but only 0x{available:X} are available"
                        )
                    _skipped_textures.add(name)
                return

        if w <= 0 or h <= 0:
            debug_print(f"Skipping texture {name}: invalid dimensions {w}x{h}")
            return

        tex_data = data_source[offset : offset + required_bytes]
        buffer = BytesIO()
        if fmt == ImageFormat.CI:
            if palette is None:
                debug_print(f"Skipping CI texture {name}: no palette provided")
                return
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
    segment_data: Optional[Union[bytearray, bytes, List[int]]],
    palette: Optional[Union[bytearray, bytes, List[int]]],
    phys: Optional[int] = None,
) -> None:
    """Store raw pixel data on the TextureRecord for deferred writing."""
    if fmt == ImageFormat.CI and palette is None:
        debug_print(
            f"WARNING: Skipping CI texture {name}: CI format requires a palette, but none was loaded."
        )
        return

    if name not in ctx.db.textures:
        debug_print("Failed writing texture, name not in texture database.")
        return

    rec = ctx.db.textures[name]
    # Snapshot the raw bytes now while the segment is loaded
    required_bytes = (w * h * bpp + 7) // 8

    if segment_data is not None:
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

    if rec.segment_data is None and phys is not None and ctx.rom:
        # Fallback to physical ROM reading
        try:
            ctx.rom.seek(phys)
            rom_data = ctx.rom.read(required_bytes)
            if len(rom_data) == required_bytes:
                rec.segment_data = bytes(rom_data)
        except Exception as e:
            debug_print(f"write_texture physical fallback failed for {name}: {e}")

    if palette is not None:
        rec.palette_data = bytes(palette)

    if rec.segment_data is None:
        debug_print(
            f"write_texture failed to snapshot {name} (seg {seg_num}, offset 0x{offset:X}, "
            f"needs {required_bytes} bytes)"
        )


def set_tile_size(
    pos: int, tile: int, uls: int, ult: int, lrs: int, lrt: int, overwrite: bool = True
) -> None:
    global current_texture_info

    # Calculate width and height from tile size
    # Coordinates are 10.2 fixed point (shifted by 2)
    w = ((lrs - uls) >> 2) + 1
    h = ((lrt - ult) >> 2) + 1

    if 0 <= tile < 8:
        tile_info = current_texture_info.tiles[tile]
        if overwrite or tile_info.width <= 0 or tile_info.height <= 0:
            tile_info.width = w
            tile_info.height = h
            tile_info.config_pos = pos


def set_tile_format(pos: int, tile: int, fmt: int, siz: Optional[int], tmem: int) -> None:
    global current_texture_info

    if 0 <= tile < 8:
        current_texture_info.tiles[tile].fmt = fmt
        current_texture_info.tiles[tile].siz = siz
        current_texture_info.tiles[tile].tmem = tmem
        current_texture_info.tiles[tile].config_pos = pos


def set_texture_image(
    segmented_addr: int,
    fmt: int,
    siz: int,
    width: int,
    context_prefix: Optional[str] = None,
    phys_override: Optional[int] = None,
) -> str:
    global current_texture_info

    phys = phys_override if phys_override is not None else segmented_to_virtual(segmented_addr)
    seg_num = segment_from_addr(segmented_addr)

    current_texture_info.addr = segmented_addr
    current_texture_info.phys = phys
    current_texture_info.fmt = fmt
    current_texture_info.siz = siz
    current_texture_info.width = width
    current_texture_info.height = 0
    current_texture_info.context_prefix = context_prefix

    name = f"texture_{segmented_addr:08X}_{phys:08X}_seg{seg_num}"
    if context_prefix:
        name = f"{context_prefix}_{name}"

    from rom_database import TextureRecord

    if name not in ctx.db.textures:
        ctx.db.textures[name] = TextureRecord(
            addr=segmented_addr,
            phys=phys,
            seg_num=seg_num,
            offset=offset_from_segment_addr(segmented_addr),
            fmt=fmt,
            siz=siz,
            width=width,
            name=name,
            context_prefix=context_prefix,
        )

    rec = ctx.db.textures[name]
    ctx.db.set_symbol(segmented_addr, name, "Texture")

    return rec


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
    phys = tex_info.phys

    # Get formats from the tile doing the loading (usually G_TX_LOADTILE)
    tile_info = tex_info.tiles[tile] if 0 <= tile <= G_TX_LOADTILE else None

    fmt = tile_info.fmt if tile_info and tile_info.fmt is not None else tex_info.fmt
    siz = tile_info.siz if tile_info and tile_info.siz is not None else tex_info.siz
    width = tex_info.width
    context_prefix = tex_info.context_prefix

    if addr == 0:
        return

    seg_num = segment_from_addr(addr)
    offset = offset_from_segment_addr(addr)

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

    # Store into TMEM map for the specific TMEM address of the loading tile
    tmem_addr = tile_info.tmem if tile_info else 0
    tex_info.tmem_map[tmem_addr] = TextureSource(
        addr=addr,
        phys=phys,
        seg_num=seg_num,
        offset=offset,
        fmt=fmt,
        siz=siz,
        width=w,
        height=h,
        context_prefix=context_prefix,
    )


def load_tile(sTxt: Any, pos: int, tile: int, uls: int, ult: int, lrs: int, lrt: int) -> None:
    global current_texture_info

    addr = current_texture_info.addr
    phys = current_texture_info.phys
    tile_info = current_texture_info.tiles[tile] if 0 <= tile < 8 else None
    fmt = tile_info.fmt if tile_info and tile_info.fmt is not None else current_texture_info.fmt
    siz = tile_info.siz if tile_info and tile_info.siz is not None else current_texture_info.siz
    context_prefix = current_texture_info.context_prefix

    if addr == 0:
        return

    seg_num = segment_from_addr(addr)
    offset = offset_from_segment_addr(addr)

    w = ((lrs - uls) >> 2) + 1
    h = ((lrt - ult) >> 2) + 1

    tmem_addr = tile_info.tmem if tile_info else 0
    current_texture_info.tmem_map[tmem_addr] = TextureSource(
        addr=addr,
        phys=phys,
        seg_num=seg_num,
        offset=offset,
        fmt=fmt,
        siz=siz,
        width=w,
        height=h,
        context_prefix=context_prefix,
    )


def commit_textures(sTxt: Any, pos: int, tile_indices: List[int]) -> None:
    global current_texture_info

    # Process tiles in order of most recently configured
    # G_TX_RENDERTILE (0) always takes priority over other tiles.
    # Process tile 0 last so its format always wins.
    sorted_tile_indices = sorted(
        tile_indices, key=lambda i: (1 if i == G_TX_RENDERTILE else 0, current_texture_info.tiles[i].config_pos)
    )

    for tile_idx in sorted_tile_indices:
        if not (0 <= tile_idx < 8):
            continue

        tile_cfg = current_texture_info.tiles[tile_idx]
        tile_is_configured = (
            tile_cfg.fmt is not None
            or tile_cfg.siz is not None
            or tile_cfg.width > 0
            or tile_cfg.height > 0
        )
        if not tile_is_configured and tile_idx != G_TX_RENDERTILE:
            continue

        # Find what source is in this tile's TMEM
        source = current_texture_info.tmem_map.get(tile_cfg.tmem)
        if not source:
            # Fallback if tmem_map is incomplete
            # Find the most recently added source or assume TMEM 0
            source = current_texture_info.tmem_map.get(0)
            if not source:
                continue

        # Use rendering time metadata if available, otherwise source
        fmt = tile_cfg.fmt if tile_cfg.fmt is not None else source.fmt
        siz = tile_cfg.siz if tile_cfg.siz is not None else source.siz
        w = tile_cfg.width if tile_cfg.width > 0 else source.width
        h = tile_cfg.height if tile_cfg.height > 0 else source.height

        if w <= 0 or h <= 0:
            debug_print(f"Skipping tile {tile_idx} because calculated w={w}, h={h}")
            continue

        image_size_type_to_bpp = [4, 8, 16, 32]
        bpp = image_size_type_to_bpp[siz]

        phys = source.phys
        name = f"texture_{source.addr:08X}_{phys:08X}_seg{source.seg_num}"
        if source.context_prefix:
            name = f"{source.context_prefix}_{name}"

        palette = current_palette if fmt == ImageFormat.CI else None

        segment_data = get_segment(source.seg_num)

        # Check that the current segment mapping matches the
        # physical address we are committing. If they don't match,
        # it means we are re-simulating a display list in a context where
        # the segment is mapped to a different location.
        if segment_data is not None:
            current_phys = segmented_to_virtual(source.addr)
            if current_phys != phys:
                segment_data = None

        # Create or update TextureRecord
        from rom_database import TextureRecord

        if name in ctx.db.textures:
            rec = ctx.db.textures[name]
            rec.fmt = fmt
            rec.siz = siz
            rec.width = w
            rec.height = h
        else:
            ctx.db.textures[name] = TextureRecord(
                addr=source.addr,
                phys=phys,
                seg_num=source.seg_num,
                offset=source.offset,
                fmt=fmt,
                siz=siz,
                width=w,
                height=h,
                name=name,
                context_prefix=source.context_prefix,
            )
        ctx.db.set_symbol(source.addr, name, "Texture")

        # Explicitly pass the physical address for the rom fallback
        write_texture(
            sTxt, name, fmt, w, h, bpp, source.offset, source.seg_num, segment_data, palette, phys
        )


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

    skybox_name = f"{level_prefix}_skybox_ptrlist"

    if ctx.db is not None:
        from rom_database import SkyboxRecord

        ctx.db.skyboxes[ctx.curr_level] = SkyboxRecord(
            level_prefix=level_prefix,
            level_num=ctx.curr_level,
            skybox_name=skybox_name,
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

    return "".join(c_output)


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

    def __init__(self, context):
        super().__init__(context)
        self.submitted_count = 0
        self.skipped_count = 0

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        # Discovery is handled by load_block / load_tile; nothing extra to do.
        return ""

    def serialize(self, record: Any) -> str:
        """Write PNG + C struct for one TextureRecord."""
        from rom_database import TextureRecord as _TextureRecord

        if not isinstance(record, _TextureRecord):
            debug_fail(f"Texture record is wrong type {type(record)}")
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
        if record.is_palette:
            pal_str = ""
            if record.palette_data:
                pal_str = ", ".join(f"0x{b:02X}" for b in record.palette_data)
            u8_palette = f"ALIGNED8 const u8 {name}[] = {{\n    {pal_str}\n}};\n\n"
            if self.txt:
                self.txt.write(ctx, "texture_dl", name.replace("texture", "dl"), u8_palette)
            return u8_palette

        if record.segment_data:
            self.submitted_count += 1
            future = executor.submit(
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
                record.phys,
            )
            if self.txt:
                self.txt.register_future(future)
        else:
            self.skipped_count += 1
            if not record.is_palette:
                debug_print(f"Texture {name} has no segment_data, skipping PNG write.")

        u8_buffer = f'ALIGNED8 Texture {name} = {{\n#include "{path}{name}.inc.c"\n}};'

        # Write to raw.log and model.inc.c cached handle
        if self.txt:
            self.txt.write(ctx, "texture_dl", name.replace("texture", "dl"), u8_buffer)

        if palette is not None:
            pal_str = ", ".join(f"0x{b:02X}" for b in palette)
            u8_palette = f"ALIGNED8 const u8 {name}_pal[] = {{\n    {pal_str}\n}};"
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

        # Skip unused skyboxes (these are probably from vanilla)
        if not record.is_used:
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
        return convert_skybox_to_c(final_image, level_prefix, self.txt)


_skybox_processor: Optional[SkyboxProcessor] = None


def get_skybox_processor() -> SkyboxProcessor:
    global _skybox_processor
    if _skybox_processor is None:
        _skybox_processor = SkyboxProcessor(ctx)
    return _skybox_processor
