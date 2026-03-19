import struct
import re
from typing import Dict, List, Optional
from utils import (
    debug_print,
    get_rom,
    level_name_to_int_lookup,
    level_name_to_int,
    level_num_to_const_name,
)
from dataclasses import dataclass
from typing import Tuple, Any

from segment import (
    get_loaded_segment_numbers,
    get_segment,
    where_is_segment_loaded,
    segment_from_addr,
    offset_from_segment_addr,
)
from function_matching.mips_utils import MipsInstruction

ROTATE_DIRECTION: Dict[int, str] = {
    0: "ROTATE_CLOCKWISE",
    1: "ROTATE_COUNTER_CLOCKWISE",
}

MOV_TEX_RECT_TEXTURE_ID: Dict[int, str] = {
    0: "TEXTURE_WATER",
    1: "TEXTURE_MIST",
    2: "TEXTURE_JRB_WATER",
    3: "TEXTURE_UNK_WATER",
    4: "TEXTURE_LAVA",
    5: "TEX_QUICKSAND_SSL",
    6: "TEX_PYRAMID_SAND_SSL",
    7: "TEX_YELLOW_TRI_TTC",
}


class MovtexEntry:
    def __init__(
        self, entry_offset: int, movtex_id: int, movtex_ptr: int, values: List[int]
    ) -> None:
        self.entry_offset: int = entry_offset
        self.movtex_id: int = movtex_id
        self.movtex_ptr: int = movtex_ptr
        self.values: List[int] = values


class MovtexCollection:
    def __init__(self, seg_num: int, start_offset: int, entries: List[MovtexEntry]) -> None:
        self.seg_num: int = seg_num
        self.start_offset: int = start_offset
        self.entries: List[MovtexEntry] = entries

    @property
    def segmented_addr(self) -> int:
        return (self.seg_num << 24) | self.start_offset


class MovtexExtractor:
    def __init__(self) -> None:
        # segments like 0x07 are reloaded with different level data during parsing,
        # so all movtex caches must be keyed by the active load range, not just by segment id.
        self._collections: Dict[Tuple[int, int, int], List[MovtexCollection]] = {}
        self._assignments: Dict[Tuple[Tuple[int, int, int], int], MovtexCollection] = {}
        self._next_index: Dict[Tuple[int, int, int], int] = {}
        self._registry: Dict[int, str] = {}
        self._movtex_object_tables: Dict[str, Dict[int, "MovtexExtractor.MovtexObject"]] = {}
        self._emitted_movtex_objects: set[Tuple[str, int]] = set()

        # TODO: this should be dynamic
        self._code_vram_base: int = 0x80246000
        self._code_rom_base: int = 0x1000

    def _segment_cache_key(self, seg_num: int) -> Optional[Tuple[int, int, int]]:
        loc = where_is_segment_loaded(seg_num)
        if loc is None:
            return None
        start, end = loc
        return (seg_num, start, end)

    def scan_segment(self, seg_num: int) -> List[MovtexCollection]:
        seg_key = self._segment_cache_key(seg_num)
        if seg_key is not None and seg_key in self._collections:
            return self._collections[seg_key]

        data = get_segment(seg_num)
        collections: List[MovtexCollection] = []
        if data is None:
            debug_print(f"MovtexExtractor: segment {seg_num:02X} not loaded, skipping scan")
            return collections

        data_len = len(data)
        offset = 0

        # Look for arrays of {s16 id, u16 pad, u32 ptr} terminated with an id of -1.
        while offset + 8 <= data_len:
            entry_id = struct.unpack_from(">h", data, offset)[0]
            _pad = struct.unpack_from(">H", data, offset + 2)[0]
            ptr = struct.unpack_from(">I", data, offset + 4)[0]

            # Expect positive ids and a pointer to a valid movtex quad array.
            # Hacks may place the quad arrays in a different segment than the collection table.
            if entry_id >= 0 and entry_id <= 0x7FFF and ptr != 0:
                ptr_seg = segment_from_addr(ptr)
                ptr_data = get_segment(ptr_seg)
                if ptr_data is None:
                    offset += 2
                    continue
                ptr_off = offset_from_segment_addr(ptr)
                if ptr_off >= len(ptr_data):
                    offset += 2
                    continue
                if not self._parse_movtex_values(ptr_data, ptr_off):
                    offset += 2
                    continue

                entries: List[MovtexEntry] = []
                cursor = offset
                valid = True
                terminated = False
                while cursor + 8 <= data_len:
                    cid = struct.unpack_from(">h", data, cursor)[0]
                    cpad = struct.unpack_from(">H", data, cursor + 2)[0]
                    cptr = struct.unpack_from(">I", data, cursor + 4)[0]

                    if cid == -1:
                        # Vanilla uses {-1, NULL}, but some hacks leave padding/ptr uninitialized.
                        terminated = True
                        cursor += 8
                        break

                    if cid < 0 or cid > 0x7FFF or cptr == 0:
                        valid = False
                        break

                    _ = cpad  # padding is typically 0; ignore for parsing

                    movtex_seg = segment_from_addr(cptr)
                    movtex_data = get_segment(movtex_seg)
                    if movtex_data is None:
                        valid = False
                        break

                    movtex_offset = offset_from_segment_addr(cptr)
                    if movtex_offset >= len(movtex_data):
                        valid = False
                        break

                    values = self._parse_movtex_values(movtex_data, movtex_offset)
                    if not values:
                        valid = False
                        break

                    entries.append(MovtexEntry(cursor, cid, cptr, values))
                    cursor += 8

                if valid and terminated and entries:
                    coll = MovtexCollection(seg_num, offset, entries)
                    collections.append(coll)
                    offset = cursor
                    continue

            offset += 2  # slide window to catch unaligned data

        collections.sort(key=lambda c: c.start_offset)
        if seg_key is not None:
            self._collections[seg_key] = collections
        return collections

    def _parse_movtex_values(self, data: bytes, start: int) -> Optional[List[int]]:
        data_len = len(data)
        if start + 2 > data_len:
            return None

        count = struct.unpack_from(">h", data, start)[0]
        if count <= 0 or count > 0x40:
            return None

        required_s16 = 1 + (count * 14)
        required_bytes = required_s16 * 2
        if start + required_bytes > data_len:
            return None

        values = list(struct.unpack_from(f">{required_s16}h", data, start))

        cursor = start + required_bytes
        if cursor + 2 <= data_len:
            tail = struct.unpack_from(">h", data, cursor)[0]
            if tail == 0:
                values.append(tail)

        return values

    def _deduce_paths(
        self, context_prefix: Optional[str]
    ) -> Tuple[str, Optional[str], Optional[str]]:
        level = None
        area = None

        if context_prefix:
            for lvl in level_name_to_int_lookup:
                if (
                    context_prefix == lvl
                    or context_prefix.startswith(lvl + "_")
                    or f"_{lvl}_" in context_prefix
                ):
                    level = lvl
                    break
            m = re.search(r"area_(\d+)", context_prefix)
            if m:
                area = m.group(1)

        if level and area:
            rel_path = f"levels/{level}/areas/{area}/movtex.inc.c"
        elif level:
            rel_path = f"levels/{level}/movtex.inc.c"
        else:
            rel_path = "misc/movtex.inc.c"
        return rel_path, level, area

    def _vram_to_rom_offset(self, vram: int) -> Optional[int]:
        rom = get_rom()
        if rom is None:
            return None
        rom_offset = vram - self._code_vram_base + self._code_rom_base
        if rom_offset < 0 or rom_offset >= len(rom):
            return None
        return rom_offset

    def _get_rom_bytes(self) -> Optional[bytes]:
        rom = get_rom()
        if rom is None:
            return None
        # CustomBytesIO stores the immutable backing buffer on `_data`.
        data = getattr(rom, "_data", None)
        return data if isinstance(data, (bytes, bytearray)) else None

    @dataclass
    class MovtexObject:
        geo_id: int
        texture_id: int
        vtx_count: int
        movtex_verts: int
        begin_dl: int
        end_dl: int
        tri_dl: int
        r: int
        g: int
        b: int
        a: int
        layer: int

    def _parse_movtex_object_table_at_vram(
        self, table_vram: int
    ) -> Optional[Dict[int, "MovtexExtractor.MovtexObject"]]:
        rom_bytes = self._get_rom_bytes()
        if rom_bytes is None:
            return None

        table_rom = self._vram_to_rom_offset(table_vram)
        if table_rom is None:
            return None

        out: Dict[int, MovtexExtractor.MovtexObject] = {}
        entry_size = 36

        # Safety cap: vanilla has a small list, but hacks might extend.
        for i in range(0, 512):
            off = table_rom + i * entry_size
            if off + entry_size > len(rom_bytes):
                break

            geo_id, texture_id, vtx_count, movtex_verts, begin_dl, end_dl, tri_dl = (
                struct.unpack_from(">7I", rom_bytes, off)
            )
            r, g, b, a = struct.unpack_from(">4B", rom_bytes, off + 28)
            layer = struct.unpack_from(">I", rom_bytes, off + 32)[0]

            if movtex_verts == 0:
                break

            # Basic sanity checks to avoid false positives when scanning candidates.
            if vtx_count == 0 or vtx_count > 0x40:
                return None
            if texture_id > 0x40:
                return None

            out[geo_id] = self.MovtexObject(
                geo_id=geo_id,
                texture_id=texture_id,
                vtx_count=vtx_count,
                movtex_verts=movtex_verts,
                begin_dl=begin_dl,
                end_dl=end_dl,
                tri_dl=tri_dl,
                r=r,
                g=g,
                b=b,
                a=a,
                layer=layer,
            )

        if not out:
            return None
        return out

    def _find_movtex_object_table_vram_from_func(self, func_rom: int) -> Optional[int]:
        rom_bytes = self._get_rom_bytes()
        if rom_bytes is None:
            return None

        scan_len = 0x400
        end = min(func_rom + scan_len, len(rom_bytes))
        insts: List[MipsInstruction] = []
        for off in range(func_rom, end, 4):
            inst_raw = struct.unpack_from(">I", rom_bytes, off)[0]
            insts.append(MipsInstruction(inst_raw))

        candidates: List[int] = []
        for idx, inst in enumerate(insts):
            if inst.opcode != 0x0F:  # LUI
                continue
            rt = inst.rt
            hi = inst.immediate << 16

            # Find the low-half add within a small window.
            for j in range(1, 8):
                if idx + j >= len(insts):
                    break
                inst2 = insts[idx + j]

                # ADDIU rt, rt, imm
                if inst2.opcode == 0x09 and inst2.rs == rt and inst2.rt == rt:
                    lo = inst2.immediate
                    if lo >= 0x8000:
                        lo -= 0x10000
                    candidates.append((hi + lo) & 0xFFFFFFFF)
                    break

                # ORI rt, rt, imm
                if inst2.opcode == 0x0D and inst2.rs == rt and inst2.rt == rt:
                    lo = inst2.immediate
                    candidates.append((hi + lo) & 0xFFFFFFFF)
                    break

        best_vram = None
        best_len = 0
        for vram in candidates:
            table = self._parse_movtex_object_table_at_vram(vram)
            if not table:
                continue
            if len(table) > best_len:
                best_vram = vram
                best_len = len(table)

        return best_vram

    def ensure_movtex_object_table(self, kind: str, func_rom: int) -> bool:
        if kind in self._movtex_object_tables:
            return True

        table_vram = self._find_movtex_object_table_vram_from_func(func_rom)
        if table_vram is None:
            return False

        table = self._parse_movtex_object_table_at_vram(table_vram)
        if not table:
            return False

        self._movtex_object_tables[kind] = table
        return True

    def get_movtex_object(self, kind: str, geo_id: int) -> Optional["MovtexExtractor.MovtexObject"]:
        table = self._movtex_object_tables.get(kind)
        if not table:
            return None
        return table.get(geo_id)

    def _read_s16_from_segment(self, segmented_addr: int, count: int) -> Optional[List[int]]:
        seg_num = segment_from_addr(segmented_addr)
        offset = offset_from_segment_addr(segmented_addr)
        data = get_segment(seg_num)
        if data is None:
            return None
        need = offset + (count * 2)
        if need > len(data):
            return None
        return list(struct.unpack_from(f">{count}h", data, offset))

    def _fmt_rotate_dir(self, rot_dir: int) -> str:
        return ROTATE_DIRECTION.get(rot_dir, str(rot_dir))

    def _fmt_rect_texture_id(self, texture_id: int) -> str:
        return MOV_TEX_RECT_TEXTURE_ID.get(texture_id, str(texture_id))

    def _format_movtex_tris_array(
        self, obj: "MovtexExtractor.MovtexObject", kind: str
    ) -> Optional[str]:
        if kind == "nocolor":
            stride = 5
        elif kind in ("colored", "colored2"):
            stride = 8
        else:
            return None

        # Read enough data for the vertices plus optional terminator(s).
        required = 1 + (obj.vtx_count * stride)
        read_count = required + 2
        values = self._read_s16_from_segment(obj.movtex_verts, read_count)
        if values is None:
            values = self._read_s16_from_segment(obj.movtex_verts, required)
        if values is None or len(values) < required:
            return None

        speed = values[0]
        parts: List[str] = [f"    MOV_TEX_SPD({speed}),\n"]

        cursor = 1
        for _ in range(obj.vtx_count):
            chunk = values[cursor : cursor + stride]
            cursor += stride
            if stride == 5:
                x, y, z, p1, p2 = chunk
                parts.append(f"    MOV_TEX_TRIS({x}, {y}, {z}, {p1}, {p2}),\n")
            else:
                x, y, z, r, g, b, p1, p2 = chunk
                if r == 0 and b == 0:
                    parts.append(f"    MOV_TEX_LIGHT_TRIS({x}, {y}, {z}, {g}, {p1}, {p2}),\n")
                else:
                    parts.append(
                        f"    MOV_TEX_ROT_TRIS({x}, {y}, {z}, {r}, {g}, {b}, {p1}, {p2}),\n"
                    )

        # Prefer matching the ROM's terminator style if present.
        end1 = values[required] if len(values) > required else None
        end2 = values[required + 1] if len(values) > required + 1 else None
        if stride == 8 and end1 == 0 and end2 == 0:
            parts.append("    MOV_TEX_ROT_END(),\n")
        elif end1 == 0:
            parts.append("    MOV_TEX_END(),\n")
        else:
            parts.append("    MOV_TEX_END(),\n")

        return "".join(parts)

    def emit_movtex_object(
        self, kind: str, geo_id: int, func_rom: int, context_prefix: Optional[str], txt: Any
    ) -> Optional[str]:
        if not self.ensure_movtex_object_table(kind, func_rom):
            return None

        obj = self.get_movtex_object(kind, geo_id)
        if obj is None:
            return None

        key = (kind, geo_id)
        if key in self._emitted_movtex_objects:
            return None
        self._emitted_movtex_objects.add(key)

        rel_path, level, area = self._deduce_paths(context_prefix)
        seg_num = segment_from_addr(obj.movtex_verts)
        seg_off = offset_from_segment_addr(obj.movtex_verts)
        arr_name = (
            f"{context_prefix}_movtex_tris_{seg_num:02X}{seg_off:06X}"
            if context_prefix
            else f"movtex_tris_{seg_num:02X}{seg_off:06X}"
        )

        values = self._format_movtex_tris_array(obj, kind)
        if values is None:
            return None

        # Best-effort: also force parsing the referenced display lists so they get emitted.
        try:
            from display_list import parse_display_list

            parse_display_list(obj.begin_dl, txt, context_prefix)
            parse_display_list(obj.end_dl, txt, context_prefix)
            parse_display_list(obj.tri_dl, txt, context_prefix)
        except Exception:
            pass

        content = f"Movtex {arr_name}[] = {{\n{values}}};\n\n"

        txt.create_file(rel_path, content, mode="a")
        return arr_name

    def assign_collection(self, seg_num: int, param: int) -> Optional[MovtexCollection]:
        seg_key = self._segment_cache_key(seg_num)
        if seg_key is None:
            return None

        key: Tuple[Tuple[int, int, int], int] = (seg_key, param)
        if key in self._assignments:
            return self._assignments[key]

        collections = self.scan_segment(seg_num)
        idx = self._next_index.get(seg_key, 0)
        if idx >= len(collections):
            return None

        coll = collections[idx]
        self._assignments[key] = coll
        self._next_index[seg_key] = idx + 1
        return coll

    def assign_from_candidates(
        self, seg_candidates: List[int], param: int
    ) -> Optional[MovtexCollection]:
        for seg in seg_candidates:
            coll = self.assign_collection(seg, param)
            if coll:
                return coll
        return None

    @dataclass
    class MovtexQuad:
        rotspeed: int
        scale: int
        x1: int
        z1: int
        x2: int
        z2: int
        x3: int
        z3: int
        x4: int
        z4: int
        rotDir: int
        alpha: int
        textureId: int

    def values_to_struct(self, values: List[int]) -> str:
        # Quad arrays start with a count, followed by count * 14 s16 fields.
        if not values:
            raise ValueError("empty movtex values")

        count = values[0]
        if count <= 0:
            raise ValueError(f"invalid movtex quad count: {count}")

        needed = 1 + (count * 14)
        if len(values) < needed:
            raise ValueError(
                f"movtex quad array too short: need {needed} values, got {len(values)}"
            )

        parts: List[str] = []
        parts.append(f"    MOV_TEX_INIT_LOAD({count}),\n")

        for i in range(count):
            base = 1 + (i * 14)
            # NOTE: values[base + 0] is the initial rotation for this quad. The MOV_TEX_* macros
            # always initialize it to 0 via MOV_TEX_INIT_LOAD / MOV_TEX_END padding, so we ignore it.
            quad = self.MovtexQuad(*values[base + 1 : base + 14])
            parts.append(f"    MOV_TEX_ROT_SPEED({quad.rotspeed}),\n")
            parts.append(f"    MOV_TEX_ROT_SCALE({quad.scale}),\n")
            parts.append(f"    MOV_TEX_4_BOX_TRIS({quad.x1}, {quad.z1}),\n")
            parts.append(f"    MOV_TEX_4_BOX_TRIS({quad.x2}, {quad.z2}),\n")
            parts.append(f"    MOV_TEX_4_BOX_TRIS({quad.x3}, {quad.z3}),\n")
            parts.append(f"    MOV_TEX_4_BOX_TRIS({quad.x4}, {quad.z4}),\n")
            parts.append(f"    MOV_TEX_ROT({self._fmt_rotate_dir(quad.rotDir)}),\n")
            parts.append(f"    MOV_TEX_ALPHA({quad.alpha}),\n")
            parts.append(f"    MOV_TEX_DEFINE({self._fmt_rect_texture_id(quad.textureId)}),\n")
            parts.append("    MOV_TEX_END(),\n")

        return "".join(parts)

    def emit_water_collection(
        self, seg_candidates: List[int], param: int, context_prefix: Optional[str], txt: Any
    ) -> Optional[str]:
        coll = self.assign_from_candidates(seg_candidates, param)
        if not coll:
            debug_print(
                f"MovtexExtractor: failed to assign collection for context={context_prefix!r} "
                f"segs={seg_candidates} param=0x{param:04X}"
            )
            for seg in seg_candidates:
                loc = where_is_segment_loaded(seg)
                data = get_segment(seg)
                debug_print(
                    f"  seg {seg:02X}: loaded={loc is not None} "
                    f"range={loc} bytes={len(data) if data is not None else None} "
                    f"collections={len(self.scan_segment(seg)) if data is not None else None}"
                )
            loaded_segs = sorted(get_loaded_segment_numbers())
            debug_print(f"  loaded segs: {[f'{s:02X}' for s in loaded_segs]}")
            debug_print(
                f"WARNING: MovtexExtractor: no collection available for segs {seg_candidates} param 0x{param:04X}"
            )
            return None

        rel_path, level, area = self._deduce_paths(context_prefix)
        base_name = (
            f"{context_prefix}_movtex_{coll.start_offset:06X}"
            if context_prefix
            else f"movtex_{coll.start_offset:06X}"
        )

        parts: List[str] = []
        for idx, entry in enumerate(coll.entries):
            arr_name = f"{base_name}_quad_{idx}"
            values = self.values_to_struct(entry.values)
            parts.append(f"static Movtex {arr_name}[] = {{\n{values}}};\n")

        coll_name = f"{base_name}_collection"
        parts.append(f"const struct MovtexQuadCollection {coll_name}[] = {{")
        for idx, entry in enumerate(coll.entries):
            arr_name = f"{base_name}_quad_{idx}"
            parts.append(f"    {{{entry.movtex_id}, {arr_name}}},")
        parts.append("    {-1, NULL},")
        parts.append("};")

        content = "\n".join(parts) + "\n"

        txt.create_file(rel_path, content, mode="a")

        if level:
            level_num = level_name_to_int[level]
            level_name = level_num_to_const_name.get(level_num, "LEVEL_NONE")
        else:
            level_num = 0
            level_name = "LEVEL_NONE"

        txt.write_lua_append(
            f"movtexqc_register('{coll_name}', {level_name}, {area}, {param})\n", "main.lua"
        )

        # Record mapping for helper generation (only first mapping per param)
        if param not in self._registry:
            self._registry[param] = coll_name
        return coll_name


movtex_extractor: MovtexExtractor = MovtexExtractor()
