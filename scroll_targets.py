import vertices
from utils import debug_print, get_rom, struct, to_signed16
from segment import segment_from_addr, where_is_segment_loaded
from context import ctx

_scroll_axis_codes = {
    "x": 4,
    "y": 5,
    "xPos": 0,
    "yPos": 1,
    "zPos": 2,
}

_scroll_type_codes = {
    "normal": 0,
    "sine": 1,
    "jumping": 2,
}

_scroll_counter = 0


def _detect_editor_scroll_alt():
    rom = get_rom()
    if rom is None or len(rom) < 0x1202404:
        return False
    try:
        sig = struct.unpack(">L", rom[0x1202400:0x1202404])[0]
    except Exception:
        return False
    return sig != 0x27BDFFE8


def _decode_rm_scroll(posX, posY, posZ, behParam):
    axis_map = {
        0xA000: "x",
        0x8000: "y",
        0x4000: "xPos",
        0x2000: "yPos",
        0x0000: "zPos",
    }
    type_map = {
        0x000: "normal",
        0x100: "sine",
        0x200: "jumping",
    }
    axis_bits = posY & 0xF000
    type_bits = posY & 0x0F00
    return {
        "variant": "rm",
        "raw_addr": behParam,
        "addr": behParam & 0xFFFFFFF0,
        "axis": axis_map.get(axis_bits, f"unknown(0x{axis_bits:04x})"),
        "type": type_map.get(type_bits, f"unknown(0x{type_bits:04x})"),
        "cycle": posY & 0xFF,
        "num_verts": posX,
        "speed": posZ,
    }


# TODO can replace assumed segment number by checking where vertices are loaded in the level
recursion_safeguard = False


def _decode_editor_scroll(beh_name, posX, posY, posZ, behParam, force_type=None):
    global recursion_safeguard

    def pos_byte(x):
        return struct.pack(">f", float(x))[1]

    use_alt = force_type if force_type is not None else _detect_editor_scroll_alt()

    raw_addr = 0x0E000000 + ((pos_byte(posX) - 2) << 16) + ((behParam >> 16) & 0xFFFF)
    axis = "x" if (raw_addr & 0xF) == 0x8 else "y"
    num_verts = (behParam & 0xFFFF) if use_alt else (pos_byte(posY) * 3 if posY else 0)
    speed = pos_byte(posZ)

    # If the number of vertices is invalid, try a different way
    if not recursion_safeguard and num_verts <= 0 and force_type is None:
        recursion_safeguard = True
        alt_decoded = _decode_editor_scroll(beh_name, posX, posY, posZ, behParam, not use_alt)
        recursion_safeguard = False
        if alt_decoded["num_verts"] > 0:
            return alt_decoded

    return {
        "variant": "editor_alt" if use_alt else "editor",
        "raw_addr": raw_addr,
        "addr": raw_addr & 0xFFFFFFF0,
        "axis": axis,
        "type": "normal",
        "cycle": 0,
        "num_verts": num_verts,
        "speed": speed,
    }


def _find_scroll_vtxs(addr, level_name, expected_num_verts):
    vp = vertices.get_vertex_processor()
    if not vp.parsed_vertices or expected_num_verts <= 0:
        return None

    seg_num = segment_from_addr(addr)
    current_seg_load = where_is_segment_loaded(seg_num)
    if current_seg_load is None:
        return None
    cur_start, cur_end = current_seg_load

    SPAN_BEGIN = addr
    SPAN_END = addr + expected_num_verts * 0x10

    vtx_buffers = []
    collected_verts = 0

    for (seg_addr, count, start, end, parent_dl), (name, actual_count) in sorted(
        vp.parsed_vertices.items(), key=lambda x: x[0][0]
    ):
        # Filter out vertices that don't come from the expected segment
        if start != cur_start:
            continue

        # Check for overlap with the target span
        buf_begin = seg_addr
        buf_end = seg_addr + actual_count * 0x10

        if buf_end <= SPAN_BEGIN or buf_begin >= SPAN_END:
            continue

        overlap_begin = max(buf_begin, SPAN_BEGIN)
        overlap_end = min(buf_end, SPAN_END)
        overlap_bytes = overlap_end - overlap_begin
        if overlap_bytes <= 0:
            continue

        offset_verts = (overlap_begin - buf_begin) // 0x10
        count_verts = overlap_bytes // 0x10

        vtx_buffers.append((seg_addr, count_verts, offset_verts, name, parent_dl))
        collected_verts += count_verts

        if collected_verts >= expected_num_verts:
            break

    if collected_verts != expected_num_verts:
        return vtx_buffers if vtx_buffers else None, collected_verts

    return vtx_buffers, collected_verts


def register_scroll_target(txt, beh_name, posX, posY, posZ, angleX, angleY, angleZ, behParam):
    global _scroll_counter
    posX_s = to_signed16(posX)
    posY_s = to_signed16(posY)
    posZ_s = to_signed16(posZ)
    angX_s = to_signed16(angleX)
    angY_s = to_signed16(angleY)
    angZ_s = to_signed16(angleZ)
    behParam_u = behParam & 0xFFFFFFFF

    if "RM_Scroll_Texture" in beh_name:
        decoded = _decode_rm_scroll(posX_s, posY_s, posZ_s, behParam_u)
    else:
        decoded = _decode_editor_scroll(beh_name, posX_s, posY_s, posZ_s, behParam_u)

    variant = decoded.get("variant", beh_name)
    addr = decoded.get("addr", 0) & 0xFFFFFFFF
    raw_addr = decoded.get("raw_addr", addr) & 0xFFFFFFFF
    axis = decoded.get("axis", "?")
    stype = decoded.get("type", "?")
    num_verts = int(decoded.get("num_verts", 0))
    speed = int(decoded.get("speed", 0))
    cycle = int(decoded.get("cycle", 0))

    if num_verts <= 0:
        debug_print(
            f"Invalid vtx count for scroll target in level {ctx.get_cur_level()} "
            f"variant {variant} "
            f"pos({posX_s}, {posY_s}, {posZ_s}) "
            f"angle({angX_s}, {angY_s}, {angZ_s}) "
            f"behParam=0x{behParam_u:08X} -> "
            f"addr=0x{addr:08X} (raw 0x{raw_addr:08X}) "
            f"axis={axis} type={stype} numVerts={num_verts} speed={speed} cycle={cycle} "
        )
        return None

    vtx_buffers, collected_verts = _find_scroll_vtxs(addr, ctx.get_cur_level(), num_verts)
    if vtx_buffers is None or len(vtx_buffers) == 0:
        name = vertices.parse_vertices(addr, num_verts, txt, f"{ctx.get_cur_level()}_scroll")
        if name != "NULL":
            vtx_buffers, collected_verts = _find_scroll_vtxs(addr, ctx.get_cur_level(), num_verts)
        if vtx_buffers is None or len(vtx_buffers) == 0:
            debug_print(
                f"Could not find vertex buffer for scroll target {beh_name} at address 0x{addr:08X} for level {ctx.get_cur_level()} "
                f"variant {variant} "
                f"pos({posX_s}, {posY_s}, {posZ_s}) "
                f"angle({angX_s}, {angY_s}, {angZ_s}) "
                f"behParam=0x{behParam_u:08X} -> "
                f"addr=0x{addr:08X} (raw 0x{raw_addr:08X}) "
                f"axis={axis} type={stype} numVerts={num_verts} speed={speed} cycle={cycle} "
            )
            return None
        else:
            debug_print(
                f"INFO: Manually parsed {num_verts} scroll vertices at 0x{addr:08X} for {ctx.get_cur_level()}"
            )

    if collected_verts != num_verts:
        debug_print(
            f"WARNING: Vertex count mismatch for scroll target {beh_name} at 0x{addr:08X} in {ctx.get_cur_level()}: "
            f"expected {num_verts}, found {collected_verts}. Proceeding with found vertices."
        )

    target_id = _scroll_counter
    _scroll_counter += 1

    lua_lines: list[str] = []

    first_nonempty = next((b for b in vtx_buffers if b[1] > 0), None)
    if first_nonempty is None:
        debug_print(f"Only zero-length vtx buffers for scroll {beh_name} at 0x{addr:08X}")
        return None

    for seg_addr, count_verts, offset_verts, name, parent_dl in vtx_buffers:
        lua_lines.append(
            f"add_scroll_target({target_id}, '{name}', {offset_verts}, {count_verts})\n"
        )
    txt.write_lua_append(lua_lines, "scrolling-textures.lua")

    offset_verts = first_nonempty[2]
    rx = int(offset_verts)
    clamped = False
    if rx > 0xFF:
        rx = 0xFF
        clamped = True

    axis_code = _scroll_axis_codes.get(axis)
    type_code = _scroll_type_codes.get(stype, 0)

    # Scroll parameters are placed in the object's properties:
    #   Xpos = speed
    #   Ypos = scrolling behavior/axis
    #   Zpos = vertices amount
    #   Xrot = offset
    #   Yrot = scrolling type
    #   Zrot = cycle
    #   Behavior param = scroll target index

    return {
        "posX": speed,
        "posY": axis_code if axis_code is not None else posY_s,
        "posZ": num_verts,
        "angleX": rx,
        "angleY": type_code,
        "angleZ": cycle,
        "behParam": target_id,
        "invalid": clamped,
    }
