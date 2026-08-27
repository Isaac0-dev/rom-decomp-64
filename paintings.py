import hashlib
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from context import ctx
from rom_database import TextureRecord
from segment import (
    register_segment_load_hook,
    unregister_segment_load_hook,
    where_is_segment_loaded,
)
from texture import ImageFormat, ImageSize, write_texture
from utils import debug_print

PAINTING_STRUCT_SIZE = 0x78

_OFF_ID = 0x00
_OFF_IMAGE_COUNT = 0x02
_OFF_TEXTURE_TYPE = 0x03
_OFF_TEXTURE_ARRAY = 0x60
_OFF_TEXTURE_WIDTH = 0x64
_OFF_TEXTURE_HEIGHT = 0x66
_OFF_RIPPLE_TRIGGER = 0x6C
_OFF_ALPHA = 0x6D
_OFF_SIZE = 0x74

PAINTING_IMAGE = 0
PAINTING_ENV_MAP = 1

_PAINTING_SEG_NUM = 0x07

# vram/rom layout used to convert data addresses in `geo_painting_draw`.
_CODE_VRAM_START = 0x80246000
_CODE_ROM_START = 0x1000
_SEG15_VRAM_START = 0x80400000

_painting_groups_vram: Optional[int] = None
_painting_struct_addrs: List[int] = []
_painting_groups_discovered: bool = False

# Address of geo_painting_draw in the ROM,
# populated as soon as we see it in a geo layout
painting_draw_func_rom_addr: int = 0

_pending_segment: Optional[Tuple[int, Dict[str, Any]]] = None

# Painting id -> course name (matches decomp course paintings).
_PAINTING_NAMES = {
    0x00: "bob",
    0x01: "ccm",
    0x02: "wf",
    0x03: "jrb",
    0x04: "lll",
    0x05: "ssl",
    0x07: "ddd",
    0x08: "wdw",
    0x09: "thi_tiny",
    0x0A: "ttm",
    0x0B: "ttc",
    0x0C: "sl",
    0x0D: "thi_huge",
    0x0E: "hmc",
    0x0F: "ttm_slide",
}

vanilla_painting_tex_hashes = {
    "e819866cf0b3e37b00c40ae089dfdfed0f9a041d6bad0ce83003ee414e0cec64",
    "a7e551655f39cde74d30575fb6e097b27d238dbac8c8ea2f2af5a0c5f5ae3c92",
    "d36116252fc79e9cb0dcd29342997feb77e6fe68422c3b0fafba225a822a7ad9",
    "f381fbc2e681bd694d080c4838b3987d4d6d93e211c498b075dd60d041539c51",
    "0b2805c7d2c5183d0971b3177e0e4254d47c5a2cb06a4ae49e1a96d37af165bc",
    "fdfff59e101014213d35f51d0c5bc9b69f9d0f922516af096b390f895c7ba4c7",
    "5831cc937ea5bbc9e35589d4a2cb46b6cce4959bb84f16b3fbd1d89abb920c1c",
    "d2cdaf4ebf34d456dea5a67887b0392f76227a44080db1a8b9f7958504f6c968",
    "6377e319a9b6786452a2f2b5f764cfce1f2aec53918c9aacf70cc443d9abbf72",
    "6963878aba393ac94efbf23366c63f10aae87efdbf6277846a3cc5f8791b458c",
    "6951c3ce45de5e86cb40f47dbdf988958e88b692218cb9552f7d847aaf092479",
    "809c90fa14659ce79d4dc103639b37ee91229826657e907a44ebf6f13efe8100",
    "8372d0e6774e41938800860bf8ad9dd4136053f3519be7c3701c5b3a671eb0f8",
    "5daea1c6b0588a9744d26c69c4f2d9c6a094f2fd883c57a5dea7a3b63d4b1cd8",
    "472da6fa4fb421869885ebe1f97472c4361a80664bf21fbbed0b963d7665fc7b",
    "d910ef88ca2619290435aedfc5a9330dbbe31b73f875f90cb3aa67e23f44f226",
    "44febbcca64d646885dbcc1ae7081a798ad8a35feaca0b6a00ab03b4422fc3b6",
    "8481a88b0e57c8cd0e93cfdcad7336efd4724f9d3f0696c038b1355dc536a7dc",
    "f641eb226f041fa8869341c6c37dc3b87896b3cb4a9a295534464c26e82be4fd",
    "62f30fab45ae47a63836009c7e1898d9cb8db1242acafae94db978cb960dbaeb",
    "b6fee10badedbf276e59b75d8412bb089e65c7defdf66940dd8245fb1700869e",
    "3433585212d16689dbeaf2418e300ca320dd95ba2ec1c0ca06b6f57e65dc3512",
    "2e8098c66cee43939ee11bc7ba66cb26e8336e4b840a99ac35f0147a87d31d3c",
    "c09523f33d2e88c03302f376f16efb0678fd29d3bbdc766ce05338f26602c3eb",
}

_paintings_extracted: bool = False
painting_string: str = ""


@dataclass
class PaintingInfo:
    id: int
    image_count: int
    texture_type: int
    texture_array: int
    texture_width: int
    texture_height: int
    ripple_trigger: int
    alpha: int
    size: float

    @property
    def name(self) -> str:
        return _PAINTING_NAMES.get(self.id, f"id{self.id:02X}") + "_painting"


def _vram_to_rom(rom, vram_addr: int) -> Optional[int]:
    if _CODE_VRAM_START <= vram_addr < _CODE_VRAM_START + 0x1000000:
        return vram_addr - _CODE_VRAM_START + _CODE_ROM_START
    if _SEG15_VRAM_START <= vram_addr < _SEG15_VRAM_START + 0x100000:
        info = where_is_segment_loaded(0x15)
        if info:
            return vram_addr - _SEG15_VRAM_START + info[0]
    return None


def _read_u32(rom, off: int) -> int:
    return struct.unpack(">I", rom[off : off + 4])[0]


def _find_data_address_candidates(rom, func_rom: int) -> Set[int]:
    # Disassemble the given function and return candidate
    # addresses for sPaintingGroups that look like the array access
    # Search for lui reg, hi + lw reg, lo(reg) pairs
    candidates: Set[int] = set()
    lui_values: Dict[int, Optional[int]] = {}
    max_inst = 0x1000 // 4
    for i in range(max_inst):
        off = func_rom + i * 4
        if off + 4 > len(rom):
            break
        raw = _read_u32(rom, off)
        opcode = (raw >> 26) & 0x3F
        rs = (raw >> 21) & 0x1F
        rt = (raw >> 16) & 0x1F
        imm16 = raw & 0xFFFF

        if opcode == 0x0F:  # LUI rt, imm
            lui_values[rt] = imm16 << 16
        elif opcode in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27):
            # Loads: LB/LH/LWL/LW/LBU/LHU/LWR use rs as base.
            hi = lui_values.get(rs)
            if hi is not None:
                addr = (hi & 0xFFFF0000) | imm16
                if 0x80000000 <= addr < 0x81000000:
                    candidates.add(addr)
            lui_values[rt] = None
        elif opcode in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E):
            # ALU immediate (addiu/andi/ori/...) writes rt.
            lui_values[rt] = None
        elif opcode == 0x00 and (raw & 0x3F) in (0x08, 0x09):
            break  # jr/jalr ends the function

    return candidates


def _read_group_arrays(rom, groups_vram: int) -> List[Tuple[int, List[int]]]:
    table_rom = _vram_to_rom(rom, groups_vram)
    if table_rom is None:
        return []

    groups: List[Tuple[int, List[int]]] = []
    for k in range(8):
        entry_off = table_rom + k * 4
        if entry_off + 4 > len(rom):
            break
        group_vram = _read_u32(rom, entry_off)
        if not (0x80000000 <= group_vram < 0x81000000):
            continue
        group_rom = _vram_to_rom(rom, group_vram)
        if group_rom is None:
            continue

        addrs: List[int] = []
        for j in range(0x100):
            ptr_off = group_rom + j * 4
            if ptr_off + 4 > len(rom):
                break
            seg_ptr = _read_u32(rom, ptr_off)
            if seg_ptr == 0:
                break
            if (seg_ptr >> 24) in range(1, 0x1F) and 0x01000000 <= seg_ptr < 0x20000000:
                addrs.append(seg_ptr)
            else:
                break
        if addrs:
            groups.append((group_vram, addrs))

    return groups


def _validate_candidate(rom, groups_vram: int) -> List[Tuple[int, List[int]]]:
    # A valid sPaintingGroups candidate is an array whose entries point to
    # arrays of segmented pointers, and where at least one group looks
    # like a real `struct Painting` object
    groups = _read_group_arrays(rom, groups_vram)
    if not groups:
        return []

    # The picked candidate is the one with the most valid entries.
    best: List[Tuple[int, List[int]]] = []
    best_score = 0
    for group_vram, addrs in groups:
        score = 0

        # Require entries to be spaced ~0x78 (struct Painting size) for >=3.
        if len(addrs) >= 3:
            stride = addrs[1] - addrs[0] if len(addrs) > 1 else 0
            if stride == 0x78:
                score = len(addrs)

        if score > best_score:
            best_score = score
            best = [(group_vram, addrs)]
        elif score == best_score and score > 0:
            best.append((group_vram, addrs))
    return best


def _discover_painting_groups(rom, func_rom: int) -> None:
    global _painting_groups_vram, _painting_struct_addrs, _painting_groups_discovered
    if _painting_groups_discovered:
        return

    candidates = _find_data_address_candidates(rom, func_rom)
    best = None
    for cand in sorted(candidates):
        groups = _validate_candidate(rom, cand)
        if groups:
            best = groups
            _painting_groups_vram = cand
            break
    if best is None:
        debug_print("paintings: could not deterministically locate sPaintingGroups")
        return

    for _, addrs in best:
        for a in addrs:
            if a not in _painting_struct_addrs:
                _painting_struct_addrs.append(a)

    _painting_groups_discovered = True
    debug_print(
        f"paintings: discovered sPaintingGroups vram=0x{_painting_groups_vram:08X} "
        f"({len(_painting_struct_addrs)} painting structs)"
    )


def read_painting(data: bytes, offset: int) -> Optional[PaintingInfo]:
    if offset + PAINTING_STRUCT_SIZE > len(data):
        return None
    pid = struct.unpack_from(">h", data, offset + _OFF_ID)[0]
    if not (0 <= pid <= 0xFF):
        # Reached the end of the array / garbage.
        return None
    assert pid in _PAINTING_NAMES, f"painting id 0x{pid:02X} not in known course list"
    image_count = data[offset + _OFF_IMAGE_COUNT]
    if not (0 <= image_count <= 4):
        return None
    texture_type = data[offset + _OFF_TEXTURE_TYPE]
    texture_array = struct.unpack_from(">I", data, offset + _OFF_TEXTURE_ARRAY)[0]
    tex_w, tex_h = struct.unpack_from(">hh", data, offset + _OFF_TEXTURE_WIDTH)
    if not (16 <= tex_w <= 256 and 16 <= tex_h <= 256):
        return None
    ripple_trigger = data[offset + _OFF_RIPPLE_TRIGGER]
    alpha = data[offset + _OFF_ALPHA]
    size = struct.unpack_from(">f", data, offset + _OFF_SIZE)[0]
    return PaintingInfo(
        pid,
        image_count,
        texture_type,
        texture_array,
        tex_w,
        tex_h,
        ripple_trigger,
        alpha,
        size,
    )


def read_painting_array(data: bytes, array_offset: int, max_count: int = 16) -> List[PaintingInfo]:
    paintings: List[PaintingInfo] = []
    for i in range(max_count):
        info = read_painting(data, array_offset + i * PAINTING_STRUCT_SIZE)
        if info is None:
            break
        paintings.append(info)
    return paintings


def _register_painting_textures(
    paintings: List[PaintingInfo], segment_data: bytes, seg_base: int
) -> int:
    global painting_string

    registered: int = 0
    seen: Set[int] = set()
    for painting in paintings:
        if painting.texture_array == 0 or painting.image_count <= 0:
            continue

        # The textureArray points to imageCount segmented texture pointers.
        arr_offset = painting.texture_array & 0xFFFFFF
        if arr_offset + painting.image_count * 4 > len(segment_data):
            debug_print(
                f"paintings: textureArray 0x{painting.texture_array:08X} beyond segment (skipping id {painting.id})"
            )
            continue
        ptrs = segment_data[arr_offset : arr_offset + painting.image_count * 4]

        for frame in range(painting.image_count):
            tex_addr = struct.unpack_from(">I", ptrs, frame * 4)[0]
            if tex_addr == 0 or tex_addr in seen:
                continue
            seen.add(tex_addr)

            # NOTE: "texture" must stay in the name; OutputManager routes PNG
            # output to "{name}.png" only for contexts containing "texture".
            name = f"castle_inside_texture_painting_{painting.name.replace('_painting', '')}"
            if painting.image_count > 1:
                name += f"_{frame}"

            if tex_addr & 0xFF000000 == 0:
                # Not a segmented address; skip to avoid garbage records.
                debug_print(
                    f"paintings: texture pointer 0x{tex_addr:08X} is not segmented, skipped"
                )
                continue

            tex_offset = tex_addr & 0xFFFFFF
            phys = seg_base + tex_offset
            fmt = ImageFormat.RGBA
            siz = ImageSize.B16
            bpp = 16

            ctx.db.textures[name] = TextureRecord(
                addr=tex_addr,
                phys=phys,
                seg_num=_PAINTING_SEG_NUM,
                offset=tex_offset,
                fmt=fmt,
                siz=siz,
                width=painting.texture_width,
                height=painting.texture_height,
                name=name,
                context_prefix="texture_painting",
                skip_definition_write=True,  # skip to make sure DynOS generates .tex
            )
            ctx.db.set_symbol(tex_addr, name, "Texture")

            # Snapshot the raw pixels now (falls back to a physical ROM read).
            write_texture(
                None,
                name,
                fmt,
                painting.texture_width,
                painting.texture_height,
                bpp,
                tex_offset,
                _PAINTING_SEG_NUM,
                segment_data,
                None,
                phys,
            )
            rec = ctx.db.textures[name]
            if not rec.segment_data:
                continue

            # Don't dump vanilla sm64 paintings
            if hashlib.sha256(rec.segment_data).hexdigest() in vanilla_painting_tex_hashes:
                del ctx.db.textures[name]
                continue

            registered += 1
            painting_string += (
                f"gPaintingValues.{painting.name}.textureArray[{frame + 1}] = "
                f'get_texture_info("{name}").texture\n'
            )

    return registered


def _extract_from_segment(seg_num: int, seg: Dict[str, Any]) -> None:
    global _paintings_extracted
    if _paintings_extracted or not _painting_groups_discovered:
        return

    data = seg.get("data")
    seg_base = seg.get("start")
    if not data or seg_base is None:
        return

    # Resolve segmented `struct Painting *` addresses against this
    # segment. Only accept addresses pointing into the segment we expect.
    addrs = [a for a in _painting_struct_addrs if (a >> 24) == seg_num]
    if not addrs:
        return

    # Extract the painting data
    paintings: List[PaintingInfo] = []
    for addr in addrs:
        off = addr & 0xFFFFFF
        info = read_painting(data, off)
        if info is not None:
            paintings.append(info)
        else:
            debug_print(f"paintings: struct at 0x{addr:08X} failed validation, skipped")
    if not paintings:
        return

    # Valid painting table found. Snapshot once and stop hooking.
    _paintings_extracted = True
    unregister_segment_load_hook(_try_extract_paintings)
    registered = _register_painting_textures(paintings, data, seg_base)
    debug_print(
        f"paintings: extracted {registered} textures from {len(paintings)} structs "
        f"(seg 0x{seg_num:02X} base 0x{seg_base:08X})"
    )


def _try_extract_paintings(seg_num: int, seg: Dict[str, Any]) -> None:
    global _pending_segment
    if _paintings_extracted or seg_num != _PAINTING_SEG_NUM:
        return
    if not _painting_groups_discovered:
        _pending_segment = (seg_num, seg)
        return
    _extract_from_segment(seg_num, seg)


def notify_painting_draw_discovered(func_rom: int) -> None:
    global _pending_segment, painting_draw_func_rom_addr
    from utils import get_rom

    if painting_draw_func_rom_addr != 0:
        assert painting_draw_func_rom_addr == func_rom
        return  # Already have the address
    painting_draw_func_rom_addr = func_rom

    # Get the rom data
    rom = get_rom()
    if rom is None:
        return

    # Disassemble the function to find the sPaintingGroups array
    # because it's only reference sits inside geo_painting_draw
    # and this method allows for deterministic discovery
    _discover_painting_groups(rom, func_rom)
    if not _painting_groups_discovered:
        return

    # Now that we know where the array is, extract it's data
    if _pending_segment is not None:
        seg_num, seg = _pending_segment
        _pending_segment = None
        _extract_from_segment(seg_num, seg)


def register_painting_extraction() -> None:
    register_segment_load_hook(_try_extract_paintings, run_existing=True)


def get_painting_string() -> str:
    return painting_string
