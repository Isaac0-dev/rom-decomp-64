from utils import (
    get_rom,
    CMD_HH_unpack,
    CMD_HHHHHH_unpack,
    to_signed16,
)
from typing import Any, Dict, List, Optional, Tuple
from context import ctx
from segment import (
    segment_from_addr,
    offset_from_segment_addr,
    where_is_segment_loaded,
    get_segment,
    get_loaded_segment_numbers,
)
from byteio import CustomBytesIO
import hashlib
from movtex import movtex_extractor
from texture import get_current_skybox, set_current_skybox
import vanilla_matcher
from base_processor import BaseProcessor
from rom_database import GeoRecord, CommandIR

# --- GEO function matching ---
_func_matcher = None
_geo_asm_cache: Dict[int, Optional[str]] = {}

_CODE_VRAM_START = 0x80246000
_CODE_ROM_START = 0x1000


def _get_func_matcher():
    global _func_matcher
    if _func_matcher is None:
        from function_matching.matcher import FunctionMatcher

        _func_matcher = FunctionMatcher()
    return _func_matcher


def resolve_geo_asm(vram_addr: int, context: Optional[List[str]] = None) -> Optional[str]:
    if vram_addr in _geo_asm_cache:
        return _geo_asm_cache[vram_addr]

    rom_offset = -1
    vram_base = _CODE_VRAM_START
    rom_base = _CODE_ROM_START

    if _CODE_VRAM_START <= vram_addr < _CODE_VRAM_START + 0x1000000:
        rom_offset = vram_addr - _CODE_VRAM_START + _CODE_ROM_START
    else:
        for seg_num in get_loaded_segment_numbers():
            if seg_num == 0x15:
                seg15_vram = 0x80400000
                if seg15_vram <= vram_addr < seg15_vram + 0x100000:
                    segment_info = where_is_segment_loaded(seg_num)
                    if segment_info:
                        rom_offset = vram_addr - seg15_vram + segment_info[0]
                        vram_base = seg15_vram
                        rom_base = segment_info[0]
                        break

    if rom_offset < 0:
        return None

    rom = get_rom()
    if rom is None or rom_offset >= len(rom):
        return None

    try:
        matcher = _get_func_matcher()
        result = matcher.match(
            rom,
            rom_offset=rom_offset,
            vram_start=vram_base,
            rom_start=rom_base,
            context=context or "Global",
        )
        if result is not None and result.confidence >= 0.90:
            _geo_asm_cache[vram_addr] = result.best_match
            return result.best_match
    except Exception:
        pass

    _geo_asm_cache[vram_addr] = None
    return None


LAYER_NAMES: Dict[int, str] = {
    0: "LAYER_FORCE",
    1: "LAYER_OPAQUE",
    2: "LAYER_OPAQUE_DECAL",
    3: "LAYER_OPAQUE_INTER",
    4: "LAYER_ALPHA",
    5: "LAYER_TRANSPARENT",
    6: "LAYER_TRANSPARENT_DECAL",
    7: "LAYER_TRANSPARENT_INTER",
}

geo_asm_callbacks: List[str] = [
    "geo_update_projectile_pos_from_parent",
    "geo_update_layer_transparency",
    "geo_offset_klepto_held_object",
    "geo_snufit_move_mask",
    "geo_snufit_scale_body",
    "geo_update_body_rot_from_parent",
    "geo_bits_bowser_coloring",
    "geo_wdw_set_initial_water_level",
    "geo_movtex_pause_control",
    "geo_movtex_draw_water_regions",
    "geo_movtex_draw_nocolor",
    "geo_movtex_draw_colored",
    "geo_movtex_draw_colored_no_update",
    "geo_movtex_draw_colored_2_no_update",
    "geo_movtex_update_horizontal",
    "geo_exec_inside_castle_light",
    "geo_exec_flying_carpet_timer_update",
    "geo_exec_flying_carpet_create",
    "geo_exec_cake_end_screen",
    "geo_envfx_main",
    "geo_cannon_circle_base",
    "geo_draw_mario_head_goddard",
    "geo_mirror_mario_set_alpha",
    "geo_mario_tilt_torso",
    "geo_mario_head_rotation",
    "geo_mario_hand_foot_scaler",
    "geo_mario_rotate_wing_cap_wings",
    "geo_render_mirror_mario",
    "geo_mirror_mario_backface_culling",
    "geo_painting_draw",
    "geo_painting_update",
    "geo_file_select_strings_and_menu_cursor",
    "geo_act_selector_strings",
]

geo_held_object_callbacks: List[str] = ["geo_switch_mario_hand_grab_pos"]

geo_switch_case_callbacks: List[str] = [
    "geo_switch_anim_state",
    "geo_switch_area",
    "geo_switch_bowser_eyes",
    "geo_switch_mario_stand_run",
    "geo_switch_mario_eyes",
    "geo_switch_mario_hand",
    "geo_switch_mario_cap_effect",
    "geo_switch_mario_cap_on_off",
]

geo_background_callbacks: List[str] = ["geo_skybox_main"]
geo_camera_callbacks: List[str] = ["geo_camera_main"]
geo_camera_frustum_callbacks: List[str] = ["geo_camera_fov"]


def get_dl_name(addr: int, sTxt: Any, context_prefix: Optional[str]) -> Any:
    if not addr:
        return "NULL"
    from display_list import get_display_list_processor

    return get_display_list_processor().parse(addr, txt=sTxt, context_prefix=context_prefix)


# --- Command Sizing Functions ---
def geo_size_1(w0: int) -> int:
    return 1


def geo_size_2(w0: int) -> int:
    return 2


def geo_size_3(w0: int) -> int:
    return 3


def geo_size_4(w0: int) -> int:
    return 4


def geo_size_5(w0: int) -> int:
    return 5


def geo_size_8(w0: int) -> int:
    return 8


def geo_size_camera_frustum(w0: int) -> int:
    return 3 if (w0 & 0x00010000) else 2


def geo_size_translate_rotate(w0: int) -> int:
    param = (w0 >> 16) & 0xFF
    p = param & 0x70
    if p == 0x30:
        return 3 if (param & 0x80) else 2  # GEO_ROTATE_Y
    if p == 0x20:
        return 4 if (param & 0x80) else 3  # GEO_ROTATE
    if p == 0x10:
        return 4 if (param & 0x80) else 3  # GEO_TRANSLATE
    return 5 if (param & 0x80) else 4  # GEO_TRANSLATE_ROTATE


def geo_size_dl(w0: int) -> int:
    return 3 if ((w0 >> 16) & 0xFF) & 0x80 else 2


def geo_size_scale(w0: int) -> int:
    return 3 if ((w0 >> 16) & 0xFF) & 0x80 else 2


def geo_size_translate_node(w0: int) -> int:
    return 3 if ((w0 >> 16) & 0xFF) & 0x80 else 2


def geo_size_rotation_node(w0: int) -> int:
    return 3 if ((w0 >> 16) & 0xFF) & 0x80 else 2


# --- Structural Hashing ---
def _build_geo_structural_repr(
    commands_data: List[Tuple[int, int, List[int]]],
    mode: str = "precise",
    script_start: int = 0,
) -> str:
    structural_repr = []
    current_seg = (script_start >> 24) & 0xFF

    for opcode, size, words in commands_data:
        parts = [f"{opcode:02X}"]
        if opcode == 0x02:  # GEO_BRANCH
            target = words[1]
            target_seg = (target >> 24) & 0xFF
            if mode == "fuzzy" and target_seg == current_seg and script_start != 0:
                parts.append(f"REL:{target - script_start:08X}")
            else:
                parts.append(f"{target:08X}")
        elif opcode == 0x00:  # GEO_BRANCH_AND_LINK
            parts.append(f"{words[1]:08X}")
        elif opcode in [0x18, 0x0E, 0x0F]:  # ASM, SWITCH_CASE, CAMERA
            func_addr = words[1]
            ctx_list = (
                geo_asm_callbacks
                if opcode == 0x18
                else (geo_switch_case_callbacks if opcode == 0x0E else geo_camera_callbacks)
            )
            func_name = resolve_geo_asm(func_addr, context=ctx_list)
            if func_name:
                parts.append(func_name)
            elif mode == "fuzzy":
                parts.append("UNKNOWN_FUNC")
            else:
                parts.append(f"{func_addr:08X}")
        elif opcode == 0x15:  # GEO_DISPLAY_LIST
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x20:  # GEO_CULLING_RADIUS
            parts.append(f"{words[0] & 0xFFFF:04X}")
        elif opcode == 0x08:  # GEO_NODE_SCREEN_AREA
            if len(words) >= 3:
                parts.append(f"{words[1]:08X}:{words[2]:08X}")
        structural_repr.append("-".join(parts))
    return "|".join(structural_repr)


def structural_hash_geo(commands_data, script_start=0):
    return hashlib.sha256(
        _build_geo_structural_repr(commands_data, mode="precise", script_start=script_start).encode(
            "utf-8"
        )
    ).hexdigest()[:16]


def structural_hash_geo_fuzzy(commands_data, script_start=0):
    return hashlib.sha256(
        _build_geo_structural_repr(commands_data, mode="fuzzy", script_start=script_start).encode(
            "utf-8"
        )
    ).hexdigest()[:16]


# Stack for movtex extraction
_geo_segment_stack: List[int] = []


class GeoProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)
        self.parsed_geos: Dict[Tuple[int, int], Any] = {}

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        sTxt = kwargs.get("txt")
        context_prefix = kwargs.get("context_prefix")
        if not segmented_addr:
            return "NULL"

        seg_num = segment_from_addr(segmented_addr)
        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            return f"geo_fail_0x{segmented_addr:08X}"

        start = segment_info[0]
        db_key = (segmented_addr, start)

        # Check database for already assigned name for this exact address + segment load
        if self.ctx.db and db_key in self.ctx.db.geos:
            return self.ctx.db.geos[db_key]

        offset = offset_from_segment_addr(segmented_addr)
        cache_key = (offset, start)
        if cache_key in self.parsed_geos:
            return self.parsed_geos[cache_key]

        data = get_segment(seg_num)
        if data is None:
            return f"geo_fail_0x{segmented_addr:08X}"

        _geo_segment_stack.append(seg_num)
        movtex_extractor.scan_segment(seg_num)

        rom = CustomBytesIO(data)
        rom.seek(offset)
        commands_ir = []
        commands_data = []
        found_end = False
        cur_indent = 0

        while not found_end:
            if rom.tell() + 4 > len(rom.getvalue()):
                print(f"WARNING: Hit end of buffer at 0x{segmented_addr + rom.tell():08X}")
                break

            pos = rom.tell()
            w0 = rom.read_u32()
            opcode = (w0 >> 24) & 0xFF
            if opcode not in geo_command_table:
                print(
                    f"DEBUG: UNRECOGNISED GEO OP {opcode:02X} at 0x{segmented_addr + pos - offset:08X}"
                )
                break

            try:
                info = geo_command_table[opcode]
                size_words = info["size"](w0)
                words = [w0]
                for _ in range(size_words - 1):
                    words.append(rom.read_u32())

                commands_data.append((opcode, size_words * 4, words))
                ir, is_end, next_indent = info["func"](words, cur_indent, sTxt, context_prefix)
                ir.address = segmented_addr + pos - offset
                ir.indent = cur_indent
                commands_ir.append(ir)
                cur_indent = next_indent
                if is_end:
                    found_end = True
            except Exception:
                print(f"Error while parsing geo layout at 0x{segmented_addr:08X}")
                break

        _geo_segment_stack.pop()

        h = structural_hash_geo(commands_data, script_start=segmented_addr)

        # Identity logic
        final_name = vanilla_matcher.match_geo_precisely(h)
        if not final_name:
            final_name = f"{context_prefix + '_' if context_prefix else ''}geo_{segmented_addr:08X}"

        if self.ctx.db:
            self.ctx.db.geos[db_key] = GeoRecord(
                seg_addr=segmented_addr,
                name=final_name,
                commands=commands_ir,
                location=self.ctx.level_area,
            )
            self.ctx.db.set_symbol(segmented_addr, final_name, "GeoLayout")
        self.parsed_geos[cache_key] = self.ctx.db.geos[db_key] if self.ctx.db else final_name
        return self.parsed_geos[cache_key]

    def serialize(self, record: GeoRecord) -> str:
        output = f"const GeoLayout {record.name}[] = {{\n"
        for ir in record.commands:
            prefix = "    " * (ir.indent + 1)
            params_str = ", ".join(map(str, ir.params))
            output += f"{prefix}{ir.name}({params_str}),\n"
        output += "};\n"
        if self.ctx.txt:
            self.ctx.txt.write(self.ctx, "geo", record.name, output)
        return output


_geo_processor = None


def get_geo_processor():
    global _geo_processor
    if _geo_processor is None:
        _geo_processor = GeoProcessor(ctx)
    return _geo_processor


def parse_geo_layout(segmented_addr, sTxt, indent=0, context_prefix=None, is_level=False):
    return get_geo_processor().parse(
        segmented_addr, txt=sTxt, indent=indent, context_prefix=context_prefix
    )


# --- Handlers ---


def G_B_L(ls, i, s, c):
    geo_rec = get_geo_processor().parse(ls[1], txt=s, indent=i, context_prefix=c)
    return CommandIR(0x00, [geo_rec], name="GEO_BRANCH_AND_LINK"), False, i


def G_END(ls, i, s, c):
    return CommandIR(0x01, [], name="GEO_END"), True, i


def G_BRANCH(ls, i, s, c):
    arg = (ls[0] >> 16) & 0xFF
    geo_rec = get_geo_processor().parse(ls[1], txt=s, indent=i, context_prefix=c)
    return CommandIR(0x02, [arg, geo_rec], name="GEO_BRANCH"), arg != 1, i


def G_RET(ls, i, s, c):
    return CommandIR(0x03, [], name="GEO_RETURN"), True, i


def G_OPEN(ls, i, s, c):
    return CommandIR(0x04, [], name="GEO_OPEN_NODE"), False, i + 1


def G_CLOSE(ls, i, s, c):
    return CommandIR(0x05, [], name="GEO_CLOSE_NODE"), False, max(0, i - 1)


def G_SCREEN(ls, i, s, c):
    x, y = CMD_HH_unpack(ls[1])
    w, h = CMD_HH_unpack(ls[2])
    return CommandIR(0x08, [ls[0] & 0xFFFF, x, y, w, h], name="GEO_NODE_SCREEN_AREA"), False, i


def G_ORTHO(ls, i, s, c):
    return CommandIR(0x09, [ls[0] & 0xFFFF], name="GEO_NODE_ORTHO"), False, i


def G_FRUST(ls, i, s, c):
    fov = ls[0] & 0xFFFF
    near, far = CMD_HH_unpack(ls[1])
    if len(ls) > 2:
        func = resolve_geo_asm(ls[2], geo_camera_frustum_callbacks) or "NULL"
        return (
            CommandIR(0x0A, [fov, near, far, func], name="GEO_CAMERA_FRUSTUM_WITH_FUNC"),
            False,
            i,
        )
    return CommandIR(0x0A, [fov, near, far], name="GEO_CAMERA_FRUSTUM"), False, i


def G_START(ls, i, s, c):
    return CommandIR(0x0B, [], name="GEO_NODE_START"), False, i


def G_ZBUF(ls, i, s, c):
    return CommandIR(0x0C, [(ls[0] >> 16) & 0xFF], name="GEO_ZBUFFER"), False, i


def G_RANGE(ls, i, s, c):
    min_d, max_d = CMD_HH_unpack(ls[1])
    return (
        CommandIR(0x0D, [to_signed16(min_d), to_signed16(max_d)], name="GEO_RENDER_RANGE"),
        False,
        i,
    )


def G_SWITCH(ls, i, s, c):
    count = ls[0] & 0xFFFF
    func = resolve_geo_asm(ls[1], geo_switch_case_callbacks) or "NULL"
    return CommandIR(0x0E, [count, func], name="GEO_SWITCH_CASE"), False, i


def G_CAM(ls, i, s, c):
    t = ls[0] & 0xFFFF
    x1, y1, z1, x2, y2, z2 = map(to_signed16, CMD_HHHHHH_unpack(ls[1:4]))
    func = resolve_geo_asm(ls[4], geo_camera_callbacks) or "NULL"
    return CommandIR(0x0F, [t, x1, y1, z1, x2, y2, z2, func], name="GEO_CAMERA"), False, i


def G_TRANS_ROT(ls, i, s, c):
    param = (ls[0] >> 16) & 0xFF
    layer = param & 0xF
    p = param & 0x70
    if p == 0x30:  # ROT_Y
        ry = ls[1] & 0xFFFF
        if param & 0x80:
            dl = get_dl_name(ls[2], s, c)
            return CommandIR(0x10, [layer, ry, dl], name="GEO_ROTATE_Y_WITH_DL"), False, i
        return CommandIR(0x10, [layer, ry], name="GEO_ROTATE_Y"), False, i
    if p == 0x20:  # ROT
        rx = ls[1] & 0xFFFF
        ry, rz = CMD_HH_unpack(ls[2])
        if param & 0x80:
            dl = get_dl_name(ls[3], s, c)
            return CommandIR(0x10, [layer, rx, ry, rz, dl], name="GEO_ROTATE_WITH_DL"), False, i
        return CommandIR(0x10, [layer, rx, ry, rz], name="GEO_ROTATE"), False, i
    if p == 0x10:  # TRANS
        tx, ty = CMD_HH_unpack(ls[1])
        tz = to_signed16((ls[2] >> 16) & 0xFFFF)
        if param & 0x80:
            dl = get_dl_name(ls[3], s, c)
            return CommandIR(0x10, [layer, tx, ty, tz, dl], name="GEO_TRANSLATE_WITH_DL"), False, i
        return CommandIR(0x10, [layer, tx, ty, tz], name="GEO_TRANSLATE"), False, i
    # TRANS_ROT
    tx, ty, tz, rx, ry, rz = CMD_HHHHHH_unpack(ls[1:4])
    if param & 0x80:
        dl = get_dl_name(ls[4], s, c)
        return (
            CommandIR(
                0x10, [layer, tx, ty, tz, rx, ry, rz, dl], name="GEO_TRANSLATE_ROTATE_WITH_DL"
            ),
            False,
            i,
        )
    return (
        CommandIR(0x10, [layer, tx, ty, tz, rx, ry, rz], name="GEO_TRANSLATE_ROTATE"),
        False,
        i,
    )


def G_TRANS_NODE(ls, i, s, c):
    param = (ls[0] >> 16) & 0xFF
    layer = param & 0xF
    x, y = CMD_HH_unpack(ls[1])
    z = to_signed16((ls[2] >> 16) & 0xFFFF) if len(ls) > 2 else 0
    if param & 0x80 and len(ls) > 2:
        dl = get_dl_name(ls[2], s, c)
        return (
            CommandIR(0x11, [layer, x, y, z, dl], name="GEO_TRANSLATE_NODE_WITH_DL"),
            False,
            i,
        )
    return CommandIR(0x11, [layer, x, y, z], name="GEO_TRANSLATE_NODE"), False, i


def G_ROT_NODE(ls, i, s, c):
    param = (ls[0] >> 16) & 0xFF
    layer = param & 0xF
    x, y = CMD_HH_unpack(ls[1])
    z = to_signed16((ls[2] >> 16) & 0xFFFF) if len(ls) > 2 else 0
    if param & 0x80 and len(ls) > 2:
        dl = get_dl_name(ls[2], s, c)
        return (
            CommandIR(0x12, [layer, x, y, z, dl], name="GEO_ROTATION_NODE_WITH_DL"),
            False,
            i,
        )
    return CommandIR(0x12, [layer, x, y, z], name="GEO_ROTATION_NODE"), False, i


def G_ANIM(ls, i, s, c):
    layer = (ls[0] >> 16) & 0xFF
    tx = to_signed16(ls[0] & 0xFFFF)
    ty, tz = CMD_HH_unpack(ls[1])
    dl = get_dl_name(ls[2], s, c)
    return CommandIR(0x13, [layer, tx, ty, tz, dl], name="GEO_ANIMATED_PART"), False, i


def G_BILL_PARAMS(ls, i, s, c):
    layer = ((ls[0] >> 16) & 0xFF) & 0xF
    tx = to_signed16(ls[0] & 0xFFFF)
    ty, tz = CMD_HH_unpack(ls[1])
    dl = get_dl_name(ls[2], s, c) if len(ls) > 2 else "NULL"
    if dl != "NULL":
        return (
            CommandIR(0x14, [layer, tx, ty, tz, dl], name="GEO_BILLBOARD_WITH_PARAMS_AND_DL"),
            False,
            i,
        )
    return CommandIR(0x14, [layer, tx, ty, tz], name="GEO_BILLBOARD_WITH_PARAMS"), False, i


def G_DL(ls, i, s, c):
    layer = (ls[0] >> 16) & 0xFF
    dl = get_dl_name(ls[1], s, c)
    return CommandIR(0x15, [layer, dl], name="GEO_DISPLAY_LIST"), False, i


def G_SHAD(ls, i, s, c):
    t = ls[0] & 0xFFFF
    solidity, scale = CMD_HH_unpack(ls[1])
    return CommandIR(0x16, [t, solidity, scale], name="GEO_SHADOW"), False, i


def G_OBJ(ls, i, s, c):
    return CommandIR(0x17, [], name="GEO_RENDER_OBJ"), False, i


def G_ASM(ls, i, s, c):
    param = ls[0] & 0xFFFF
    func_addr = ls[1]
    func_name = resolve_geo_asm(func_addr, context=geo_asm_callbacks) or "NULL"

    # Movtex extraction
    func_rom = func_addr
    if func_addr & 0xFF000000 == 0x80000000:
        func_rom = func_addr - _CODE_VRAM_START + _CODE_ROM_START

    if func_name == "geo_movtex_draw_water_regions":
        seg = _geo_segment_stack[-1] if _geo_segment_stack else None
        if seg:
            movtex_extractor.emit_water_collection([0x07, seg], param, c, s)
    elif func_name == "geo_movtex_draw_nocolor":
        movtex_extractor.emit_movtex_object("nocolor", param, func_rom, c, s)
    elif func_name in ("geo_movtex_draw_colored", "geo_movtex_draw_colored_no_update"):
        movtex_extractor.emit_movtex_object("colored", param, func_rom, c, s)
    elif func_name == "geo_movtex_draw_colored_2_no_update":
        movtex_extractor.emit_movtex_object("colored2", param, func_rom, c, s)

    return CommandIR(0x18, [param, func_name], name="GEO_ASM"), False, i


def G_BG(ls, i, s, c):
    bg_id = ls[0] & 0xFFFF
    func_addr = ls[1]
    if func_addr == 0:
        return CommandIR(0x19, [f"0x{bg_id:04X}"], name="GEO_BACKGROUND_COLOR"), False, i

    func_name = resolve_geo_asm(func_addr, geo_background_callbacks) or "NULL"
    if func_name == "NULL" and any(
        "script_exec_level_table" in str(t) for t in ctx.level_script_tracker
    ):
        func_name = "geo_skybox_main"

    bg_name = f"0x{bg_id:04X}"
    if get_current_skybox():
        bg_name = str(get_current_skybox())
        set_current_skybox(None)

    return CommandIR(0x19, [bg_name, func_name], name="GEO_BACKGROUND"), False, i


def G_NOP_1A(ls, i, s, c):
    return CommandIR(0x1A, [], name="GEO_NOP_1A"), False, i


def G_COPY_VIEW(ls, i, s, c):
    return CommandIR(0x1B, [], name="GEO_COPY_VIEW"), False, i


def G_HELD_OBJECT(ls, i, s, c):
    layer = (ls[0] >> 16) & 0xFF
    tx, ty = CMD_HH_unpack(ls[1])
    tz = to_signed16((ls[2] >> 16) & 0xFFFF)
    func_addr = ls[2]
    func_name = resolve_geo_asm(func_addr, context=geo_held_object_callbacks) or "NULL"
    return (
        CommandIR(0x1C, [layer, tx, ty, tz, func_name], name="GEO_HELD_OBJECT"),
        False,
        i,
    )


def G_SCALE(ls, i, s, c):
    param = (ls[0] >> 16) & 0xFF
    layer = param & 0xF
    scale = ls[1]
    if param & 0x80:
        dl = get_dl_name(ls[2], s, c)
        return CommandIR(0x1D, [layer, f"0x{scale:08X}", dl], name="GEO_SCALE_WITH_DL"), False, i
    return CommandIR(0x1D, [layer, f"0x{scale:08X}"], name="GEO_SCALE"), False, i


def G_CULL(ls, i, s, c):
    return CommandIR(0x20, [ls[0] & 0xFFFF], name="GEO_CULLING_RADIUS"), False, i


def G_NOP_1E(ls, i, s, c):
    return CommandIR(0x1E, [], name="GEO_NOP_1E"), False, i


def G_NOP_1F(ls, i, s, c):
    return CommandIR(0x1F, [], name="GEO_NOP_1F"), False, i


def G_BONE(ls, i, s, c):
    layer = (ls[0] >> 16) & 0xFF
    tx = to_signed16((ls[1] >> 16) & 0xFFFF)
    ty = to_signed16(ls[1] & 0xFFFF)
    tz = to_signed16((ls[2] >> 16) & 0xFFFF)
    rx = to_signed16(ls[2] & 0xFFFF)
    ry = to_signed16((ls[3] >> 16) & 0xFFFF)
    rz = to_signed16(ls[3] & 0xFFFF)
    dl = get_dl_name(ls[4], s, c)
    return CommandIR(0x21, [layer, tx, ty, tz, rx, ry, rz, dl], name="GEO_BONE"), False, i


# --- Command Table ---
geo_command_table: Dict[int, Dict[str, Any]] = {
    0x00: {"name": "GEO_BRANCH_AND_LINK", "func": G_B_L, "size": geo_size_2},
    0x01: {"name": "GEO_END", "func": G_END, "size": geo_size_1},
    0x02: {"name": "GEO_BRANCH", "func": G_BRANCH, "size": geo_size_2},
    0x03: {"name": "GEO_RETURN", "func": G_RET, "size": geo_size_1},
    0x04: {"name": "GEO_OPEN_NODE", "func": G_OPEN, "size": geo_size_1},
    0x05: {"name": "GEO_CLOSE_NODE", "func": G_CLOSE, "size": geo_size_1},
    0x08: {"name": "GEO_NODE_SCREEN_AREA", "func": G_SCREEN, "size": geo_size_3},
    0x09: {"name": "GEO_NODE_ORTHO", "func": G_ORTHO, "size": geo_size_1},
    0x0A: {"name": "GEO_CAMERA_FRUSTUM", "func": G_FRUST, "size": geo_size_camera_frustum},
    0x0B: {"name": "GEO_NODE_START", "func": G_START, "size": geo_size_1},
    0x0C: {"name": "GEO_ZBUFFER", "func": G_ZBUF, "size": geo_size_1},
    0x0D: {"name": "GEO_RENDER_RANGE", "func": G_RANGE, "size": geo_size_2},
    0x0E: {"name": "GEO_SWITCH_CASE", "func": G_SWITCH, "size": geo_size_2},
    0x0F: {"name": "GEO_CAMERA", "func": G_CAM, "size": geo_size_5},
    0x10: {"name": "GEO_TRANSLATE_ROTATE", "func": G_TRANS_ROT, "size": geo_size_translate_rotate},
    0x11: {"name": "GEO_TRANSLATE_NODE", "func": G_TRANS_NODE, "size": geo_size_translate_node},
    0x12: {"name": "GEO_ROTATION_NODE", "func": G_ROT_NODE, "size": geo_size_rotation_node},
    0x13: {"name": "GEO_ANIMATED_PART", "func": G_ANIM, "size": geo_size_3},
    0x14: {"name": "GEO_BILLBOARD_WITH_PARAMS", "func": G_BILL_PARAMS, "size": geo_size_dl},
    0x15: {"name": "GEO_DISPLAY_LIST", "func": G_DL, "size": geo_size_2},
    0x16: {"name": "GEO_SHADOW", "func": G_SHAD, "size": geo_size_2},
    0x17: {"name": "GEO_RENDER_OBJ", "func": G_OBJ, "size": geo_size_1},
    0x18: {"name": "GEO_ASM", "func": G_ASM, "size": geo_size_2},
    0x19: {"name": "GEO_BACKGROUND", "func": G_BG, "size": geo_size_2},
    0x1A: {"name": "GEO_NOP_1A", "func": G_NOP_1A, "size": geo_size_2},
    0x1B: {"name": "GEO_COPY_VIEW", "func": G_COPY_VIEW, "size": geo_size_1},
    0x1C: {"name": "GEO_HELD_OBJECT", "func": G_HELD_OBJECT, "size": geo_size_3},
    0x1D: {"name": "GEO_SCALE", "func": G_SCALE, "size": geo_size_scale},
    0x1E: {"name": "GEO_NOP_1E", "func": G_NOP_1E, "size": geo_size_2},
    0x1F: {"name": "GEO_NOP_1F", "func": G_NOP_1F, "size": geo_size_4},
    0x20: {"name": "GEO_CULLING_RADIUS", "func": G_CULL, "size": geo_size_1},
    0x21: {"name": "GEO_BONE", "func": G_BONE, "size": geo_size_5},
}
