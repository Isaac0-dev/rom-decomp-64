import level_script
import struct
from context import ctx
from utils import level_num_to_str, level_num_to_const_name
from segment import (
    push_pool_state,
    pop_pool_state,
    load_segment,
    segmented_to_virtual,
    get_segment,
    segment_from_addr,
)
from rom_database import CommandIR


def format_param_hex(name, value, length):
    if isinstance(value, str):
        return f"/* {name} */ {value}"
    return f"/* {name} */ 0x{value:0{length * 2}x}"


def format_param_string(name, value, length):
    # Choose the format string based on the provided length
    if length == 1:
        format_str = "b"  # 1 byte for signed char
    elif length == 2:
        format_str = "h"  # 2 bytes for signed short
    elif length == 4:
        format_str = "i"  # 4 bytes for signed int
    elif length == 8:
        format_str = "q"  # 8 bytes for signed long long
    else:
        raise ValueError(f"Unsupported length: {length} bytes")

    # Pack and unpack the value using the chosen format string
    packed_value = struct.pack("!i", value)
    offset = 4 - length
    signed_value = struct.unpack("!" + format_str, packed_value[offset:])[0]

    return f"/* {name} */ {signed_value}"


def format_output(cmd, params, no_print=False):
    return CommandIR(opcode=0, params=params, name=cmd, indent=ctx.indent)


###############


def CMD_BBBB(values):
    value = values.pop(0)
    return (
        (value & 0xFF000000) >> 24,
        (value & 0x00FF0000) >> 16,
        (value & 0x0000FF00) >> 8,
        (value & 0x000000FF) >> 0,
    )


def CMD_BBH(values):
    value = values.pop(0)
    return (value & 0xFF000000) >> 24, (value & 0x00FF0000) >> 16, (value & 0x0000FFFF) >> 0


def CMD_HH(values):
    value = values.pop(0)
    return (value & 0xFFFF0000) >> 16, (value & 0x0000FFFF) >> 0


def CMD_HHHHHH(values):
    v1, v2 = CMD_HH(values)
    v3, v4 = CMD_HH(values)
    v5, v6 = CMD_HH(values)
    return v1, v2, v3, v4, v5, v6


def CMD_W(values):
    if not values:
        return 0
    value = values.pop(0)
    return value


def CMD_PTR(values):
    if not values:
        return 0
    value = values.pop(0)
    return value


###############


def EXECUTE(values):
    from level_script import pending_parse

    _, _, seg = CMD_BBH(values)
    start = CMD_PTR(values)
    end = CMD_PTR(values)
    entry = CMD_PTR(values)

    seg &= 0xFF

    push_pool_state()
    load_segment(seg, start, end, False)

    entry_name = pending_parse(entry)
    params = [
        format_param_hex("seg", seg, 2),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
        entry_name,
    ]
    return format_output("EXECUTE", params)


def EXIT_AND_EXECUTE(values):
    _, _, seg = CMD_BBH(values)
    start = CMD_PTR(values) if values else 0
    end = CMD_PTR(values) if values else 0
    entry = CMD_PTR(values) if values else 0

    seg &= 0xFF

    pop_pool_state()
    push_pool_state()

    load_segment(seg, start, end, False)

    entry_name = "NULL"
    from level_script import pending_parse

    if entry != 0:
        entry_name = pending_parse(entry)

    params = [
        format_param_hex("seg", seg, 2),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
        entry_name,
    ]
    return format_output("EXIT_AND_EXECUTE", params), False


def EXIT(values):
    pop_pool_state()
    return format_output("EXIT", []), False


def SLEEP(values):
    _, _, frames = CMD_BBH(values)

    params = [
        format_param_hex("frames", frames, 2),
    ]
    return format_output("SLEEP", params)


def SLEEP_BEFORE_EXIT(values):
    _, _, frames = CMD_BBH(values)

    params = [
        format_param_hex("frames", frames, 2),
    ]
    return format_output("SLEEP_BEFORE_EXIT", params)


def JUMP(values):
    _, _, _ = CMD_BBH(values)
    location = CMD_PTR(values) if values else 0

    if location == 0:
        return format_output("JUMP", ["NULL"]), False

    from level_script import pending_parse

    location_name = pending_parse(location)
    return format_output("JUMP", [location_name]), False


def JUMP_LINK(values):
    _, _, offset = CMD_BBH(values)
    location = CMD_PTR(values)

    seg_phys = segmented_to_virtual(location)

    caller_name = None
    if ctx.level_script_tracker:
        caller_name = ctx.level_script_tracker[-1]

    record_candidate = False
    if caller_name and caller_name.startswith("level_") and caller_name.endswith("_entry"):
        record_candidate = True

    location_name = None

    matched_name = None
    if ctx.curr_area == -1:
        from level_script import match_script_func_global

        matched_name = match_script_func_global(location)

    from level_script import pending_parse

    if matched_name:
        pending_parse(location)
        location_name = matched_name
    elif record_candidate and ctx.curr_area == -1:
        if caller_name is not None:
            ctx.callers_map.setdefault(seg_phys, set()).add(caller_name)
        # fallback to deferred candidate placeholder and record for later processing
        ctx.global_candidates.add(location)
        placeholder = ctx.candidate_placeholders.get(seg_phys)
        if placeholder is None:
            placeholder = f"script_candidate_0x{seg_phys:x}"
            ctx.candidate_placeholders[seg_phys] = placeholder
        location_name = placeholder
    else:
        location_name = pending_parse(location)

    params = [location_name]
    return format_output("JUMP_LINK", params)


def RETURN(values):
    return format_output("RETURN", []), False


def JUMP_LINK_PUSH_ARG(values):
    _, _, arg = CMD_BBH(values)

    params = [
        format_param_hex("arg", arg, 2),
    ]
    return format_output("JUMP_LINK_PUSH_ARG", params)


def JUMP_N_TIMES(values):
    return format_output("JUMP_N_TIMES", [])


def LOOP_BEGIN(values):
    ret = format_output("LOOP_BEGIN", [])
    ctx.indent += 1
    return ret


def LOOP_UNTIL(values):
    _, _, op, _ = CMD_BBBB(values)
    arg = CMD_W(values)

    ctx.indent -= 1

    params = [
        format_param_hex("op", op, 1),
        format_param_hex("arg", arg, 4),
    ]
    return format_output("LOOP_UNTIL", params)


def JUMP_IF(values):
    from level_script import pending_parse

    _, _, op, _ = CMD_BBBB(values)
    arg = CMD_W(values)
    target = CMD_PTR(values)

    target_label = None

    # Check if we are jumping to a level
    is_level = (
        ctx.level_script_tracker and ctx.level_script_tracker[-1] == "script_exec_level_table"
    )
    if is_level:
        target_label = level_num_to_str.get(arg, f"level_{arg}")
        ctx.curr_level = arg
        print(f"Processing level: {target_label}")

    target_name = pending_parse(target, label=target_label)

    if is_level:
        ctx.curr_level = -1

    params = [format_param_hex("op", op, 1), format_param_hex("arg", arg, 4), target_name]
    return format_output("JUMP_IF", params)


def JUMP_LINK_IF(values):
    _, _, op, _ = CMD_BBBB(values)
    arg = CMD_W(values)
    target = CMD_PTR(values)

    from level_script import pending_parse

    target_name = pending_parse(target)
    params = [format_param_hex("op", op, 1), format_param_hex("arg", arg, 4), target_name]
    return format_output("JUMP_LINK_IF", params)


def SKIP_IF(values):
    _, _, op, _ = CMD_BBBB(values)
    arg = CMD_W(values)

    params = [
        format_param_hex("op", op, 1),
        format_param_hex("arg", arg, 4),
    ]
    return format_output("SKIP_IF", params)


def SKIP(values):
    return format_output("SKIP", [])


def SKIP_NOP(values):
    return format_output("SKIP_NOP", [])


def CALL(values):
    _, _, arg = CMD_BBH(values)
    ptr = CMD_PTR(values)

    func_name = "NULL"

    # If it's the main level, we take an educated guess that it's lvl_init_or_update
    if arg == 0 and level_script.ctx.get_cur_level():
        func_name = "lvl_init_or_update"

    if func_name == "NULL" and ptr:
        func_name = format_param_hex("func", ptr, 4)

    params = [format_param_hex("arg", arg, 2), func_name]
    return format_output("CALL", params)


def CALL_LOOP(values):
    _, _, arg = CMD_BBH(values)
    ptr = CMD_PTR(values)

    func_name = "NULL"

    # If it's the main level, we take an educated guess that it's lvl_init_or_update
    if arg == 1 and level_script.ctx.get_cur_level():
        func_name = "lvl_init_or_update"

    if func_name == "NULL" and ptr:
        func_name = format_param_hex("func", ptr, 4)

    params = [format_param_hex("arg", arg, 2), func_name]
    return format_output("CALL_LOOP", params)


def SET_REG(values):
    _, _, value = CMD_BBH(values)

    # Recognise entry level
    if ctx.first_cmd == 0x1B:
        from level_script import level_script_check_match

        match = level_script_check_match(ctx.script_cmd_history[-1])
        if match == "level_main_menu_entry_1":
            ctx.txt.write_lua(
                [
                    f"gLevelValues.entryLevel = {level_num_to_const_name.get(value, f'LEVEL_UNKNOWN_{value}')}\n"
                ],
                "tweaks.lua",
            )

    params = [
        format_param_hex("value", value, 2),
    ]
    return format_output("SET_REG", params)


def PUSH_POOL(values):
    push_pool_state()
    return format_output("PUSH_POOL", [])


def POP_POOL(values):
    pop_pool_state()
    return format_output("POP_POOL", [])


def FIXED_LOAD(values):
    _, _, _ = CMD_BBH(values)
    loadAddr = CMD_PTR(values)
    start = CMD_PTR(values)
    end = CMD_PTR(values)

    params = [
        format_param_hex("loadAddr", loadAddr, 4),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
    ]
    ir = format_output("FIXED_LOAD", params)
    ir.comment = "// "
    return ir


def LOAD_RAW(values):
    from texture import extract_skybox

    _, _, seg = CMD_BBH(values)
    start = CMD_PTR(values)
    end = CMD_PTR(values)

    seg_num = seg & 0xFF

    params = [
        format_param_hex("seg", seg_num, 2),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
    ]

    formatted_output = format_output("LOAD_RAW", params)

    load_segment(seg_num, start, end, False)

    if (
        len(ctx.level_script_tracker) > 3
        and ctx.level_script_tracker[-3] == "script_exec_level_table"
    ):
        if seg_num == 0x0A:
            extract_skybox(seg_num, ctx.txt, ctx.level_script_tracker[-1])

    formatted_output.comment = "// "
    return formatted_output


def LOAD_MIO0(values):
    from texture import extract_skybox

    _, _, seg = CMD_BBH(values)
    start = CMD_PTR(values)
    end = CMD_PTR(values)

    seg &= 0xFF

    params = [
        format_param_hex("seg", seg, 2),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
    ]

    formatted_output = format_output("LOAD_MIO0", params)
    load_segment(seg, start, end, True)

    if (
        len(ctx.level_script_tracker) > 3
        and ctx.level_script_tracker[-3] == "script_exec_level_table"
    ):
        if seg == 0x0A:
            extract_skybox(seg, ctx.txt, ctx.level_script_tracker[-1])

    formatted_output.comment = "// "
    return formatted_output


def LOAD_MARIO_HEAD(values):
    _, _, sethead = CMD_BBH(values)

    params = [
        format_param_hex("sethead", sethead, 2),
    ]
    return format_output("LOAD_MARIO_HEAD", params)


def LOAD_MIO0_TEXTURE(values):
    _, _, seg = CMD_BBH(values)
    start = CMD_PTR(values)
    end = CMD_PTR(values)

    seg &= 0xFF

    load_segment(seg, start, end, True)

    params = [
        format_param_hex("seg", seg, 1),
        format_param_hex("start", start, 4),
        format_param_hex("end", end, 4),
    ]
    return format_output("LOAD_MIO0_TEXTURE", params)


def INIT_LEVEL(values):
    push_pool_state()
    return format_output("INIT_LEVEL", [])


def CLEAR_LEVEL(values):
    pop_pool_state()
    return format_output("CLEAR_LEVEL", [])


def ALLOC_LEVEL_POOL(values):
    return format_output("ALLOC_LEVEL_POOL", [])


def FREE_LEVEL_POOL(values):
    return format_output("FREE_LEVEL_POOL", [])


def is_per_area_bank_0e(segData):
    if len(segData) < 0x6000:
        return False
    offset = 0x5FFC
    return (
        segData[0 + offset] << 24
        | segData[1 + offset] << 16
        | segData[2 + offset] << 8
        | segData[3 + offset]
    ) == 0x4BC9189A


def set_area_segmented_0e(areaID, segData):
    if not is_per_area_bank_0e(segData):
        return

    offset = 0x5F00 + areaID * 0x10
    start = (
        (segData[offset] << 24)
        | (segData[offset + 1] << 16)
        | (segData[offset + 2] << 8)
        | segData[offset + 3]
    )

    offset += 4
    end = (
        (segData[offset] << 24)
        | (segData[offset + 1] << 16)
        | (segData[offset + 2] << 8)
        | segData[offset + 3]
    )

    load_segment(0x0E, start, end, False)


def AREA(values):
    _, _, index, _ = CMD_BBBB(values)
    geo = CMD_PTR(values)

    if level_script.ctx.get_cur_level() is not None:
        seg = get_segment(0x19)
        if seg is not None:
            set_area_segmented_0e(index, seg)

    area_label = f"area_{index}"
    ctx.level_script_tracker.append(area_label)
    ctx.curr_area = index

    # Update context prefix for children (DLs, Geos, etc)
    # If we have a level name (e.g. 'bbh'), prefix becomes 'bbh_area_1'
    if ctx.current_context_prefix:
        from utils import level_name_to_int_lookup

        # Check if it already has the level name but not the area
        parts = ctx.current_context_prefix.split("_")
        if parts[0] in level_name_to_int_lookup and "area" not in ctx.current_context_prefix:
            ctx.current_context_prefix = f"{parts[0]}_{area_label}"
        else:
            ctx.current_context_prefix = f"{ctx.current_context_prefix}_{area_label}"
    else:
        ctx.current_context_prefix = area_label

    geo_prefix = ctx.current_context_prefix

    from geo_layout import parse_geo_layout

    geo_rec = parse_geo_layout(geo, ctx.txt, context_prefix=geo_prefix, is_level=True)

    params = [
        index,
        geo_rec,
    ]
    ret = format_output("AREA", params)
    ctx.indent += 1
    return ret


def END_AREA(values):
    ctx.indent -= 1
    if ctx.level_script_tracker and ctx.level_script_tracker[-1].startswith("area_"):
        ctx.level_script_tracker.pop()
    ctx.curr_area = -1
    return format_output("END_AREA", [])


def LOAD_MODEL_FROM_DL(values):
    _, _, merged = CMD_BBH(values)
    layer = int(merged) >> 12
    model = int(merged) & 0xFF
    dl = CMD_PTR(values)

    from display_list import parse_display_list

    dl_rec = parse_display_list(dl, ctx.txt, ctx.current_context_prefix)

    from model_ids import resolve_model_id

    model_param = resolve_model_id(model, ctx.get_cur_level()) or f"0x{model:02x}"

    params = [
        model_param,
        dl_rec,
        f"0x{layer:02x}",
    ]

    from deferred_output import ScriptRecord, RecordType

    ctx._pending_record = ScriptRecord(
        record_type=RecordType.LOAD_MODEL_FROM_DL,
        data={"model": model, "layer": layer, "dl_name": str(dl_rec), "dl_addr": dl},
    )

    formatted_output = format_output("LOAD_MODEL_FROM_DL", params)
    formatted_output.comment = "// "
    return formatted_output


def LOAD_MODEL_FROM_GEO(values):
    _, _, model = CMD_BBH(values)
    geo = CMD_PTR(values)

    from geo_layout import parse_geo_layout

    geo_rec = parse_geo_layout(geo, ctx.txt, context_prefix=ctx.current_context_prefix)

    comment = ""
    seg_num = segment_from_addr(geo)
    if seg_num == 0x12:
        comment = "// "

    from model_ids import resolve_model_id

    model_param = resolve_model_id(model, ctx.get_cur_level()) or f"0x{model:02x}"

    params = [
        model_param,
        geo_rec,
    ]

    from deferred_output import ScriptRecord, RecordType

    ctx._pending_record = ScriptRecord(
        record_type=RecordType.LOAD_MODEL_FROM_GEO,
        data={"model": model, "geo_name": str(geo_rec), "geo_addr": geo},
    )

    formatted_output = format_output("LOAD_MODEL_FROM_GEO", params)
    formatted_output.comment = comment
    return formatted_output


def CMD23(values):
    _, _, model = CMD_BBH(values)
    ptr = CMD_PTR(values)
    params = [format_param_hex("model", model, 1), format_param_hex("ptr", ptr, 4)]
    return format_output("CMD23", params)


def OBJECT_WITH_ACTS(values):
    _, _, acts, model = CMD_BBBB(values)
    posX, posY, posZ, angleX, angleY, angleZ = CMD_HHHHHH(values)
    behParam = CMD_W(values)
    beh = CMD_PTR(values)

    from behavior import KNOWN_BEHAVIOR_HASHES, get_behavior_processor

    bhv_rec = get_behavior_processor().parse(
        beh, txt=ctx.txt, context_prefix=ctx.current_context_prefix
    )
    beh_name = str(bhv_rec)
    beh_name_hash = getattr(bhv_rec, "hash", "") if not isinstance(bhv_rec, str) else ""

    if beh_name == "editor_Scroll_Texture2":
        beh_name = "editor_Scroll_Texture"

    if ("editor_Scroll_Texture" in beh_name or "RM_Scroll_Texture" in beh_name) and acts != 0:
        from scroll_targets import register_scroll_target

        converted_scroll = register_scroll_target(
            ctx.txt, beh_name, posX, posY, posZ, angleX, angleY, angleZ, behParam
        )
        if converted_scroll:
            posX = converted_scroll["posX"]
            posY = converted_scroll["posY"]
            posZ = converted_scroll["posZ"]
            angleX = converted_scroll["angleX"]
            angleY = converted_scroll["angleY"]
            angleZ = converted_scroll["angleZ"]
            behParam = converted_scroll["behParam"]
            if converted_scroll["invalid"]:
                if beh_name_hash in KNOWN_BEHAVIOR_HASHES:
                    known_name = KNOWN_BEHAVIOR_HASHES[beh_name_hash]
                    beh_name = (
                        known_name
                        if not (
                            known_name.startswith("bhv_unknown") or "_bhv_unknown_" in known_name
                        )
                        else f"/* Hash: {beh_name_hash} */ {beh_name}"
                    )
                else:
                    beh_name = f"/* Hash: {beh_name_hash} */ {beh_name}"

    from model_ids import resolve_model_id

    model_param = resolve_model_id(model, ctx.get_cur_level()) or f"0x{model:02x}"

    params = [
        model_param,
        format_param_string("posX", posX, 2),
        format_param_string("posY", posY, 2),
        format_param_string("posZ", posZ, 2),
        format_param_string("angleX", angleX, 2),
        format_param_string("angleY", angleY, 2),
        format_param_string("angleZ", angleZ, 2),
        format_param_hex("behParam", behParam, 4),
        bhv_rec,
    ]

    from deferred_output import ScriptRecord, RecordType

    is_object = acts == 0x1F
    ctx._pending_record = ScriptRecord(
        record_type=RecordType.OBJECT if is_object else RecordType.OBJECT_WITH_ACTS,
        data={
            "model": model,
            "beh_name": beh_name,
            "pos": (posX, posY, posZ),
            "angle": (angleX, angleY, angleZ),
            "behParam": behParam,
            "acts": acts,
            "level": ctx.get_cur_level(),
        },
    )

    if is_object:
        return format_output("OBJECT", params)
    else:
        params.append(format_param_hex("acts", acts, 1))
        return format_output("OBJECT_WITH_ACTS", params)


def MARIO(values):
    from behavior import parse_behavior

    _, _, _, model = CMD_BBBB(values)
    behParam = CMD_W(values)
    beh_ptr = CMD_PTR(values)  # TODO: pointer to behavior script

    # I've never seen this NOT as Mario
    beh_name = "bhvMario" or parse_behavior(beh_ptr, ctx.txt)

    params = [
        format_param_hex("model", model, 1),
        format_param_hex("behParam", behParam, 4),
        beh_name,
    ]
    return format_output("MARIO", params)


def WARP_NODE(values):
    _, _, destId, destLevel = CMD_BBBB(values)
    destArea, destNode, flags, _ = CMD_BBBB(values)

    destLevelName = level_num_to_const_name.get(destLevel, f"{destLevel}")

    params = [
        format_param_hex("id", destId, 1),
        format_param_hex("destLevel", destLevelName, 1),
        format_param_hex("destArea", destArea, 1),
        format_param_hex("destNode", destNode, 1),
        format_param_hex("flags", flags, 1),
    ]
    return format_output("WARP_NODE", params)


def PAINTING_WARP_NODE(values):
    ir = WARP_NODE(values)
    ir.name = "PAINTING_WARP_NODE"
    return ir


def INSTANT_WARP(values):
    _, _, index, destArea = CMD_BBBB(values)
    displaceX, displaceY = CMD_HH(values)
    displaceZ, _ = CMD_HH(values)

    params = [
        format_param_hex("index", index, 1),
        format_param_hex("destArea", destArea, 1),
        format_param_string("displaceX", displaceX, 2),
        format_param_string("displaceY", displaceY, 2),
        format_param_string("displaceZ", displaceZ, 2),
    ]
    return format_output("INSTANT_WARP", params)


def LOAD_AREA(values):
    _, _, area, _ = CMD_BBBB(values)
    return format_output("LOAD_AREA", [format_param_hex("area", area, 1)])


def CMD2A(values):
    _, _, unk2, _ = CMD_BBBB(values)
    return format_output("CMD2A", [format_param_hex("unk2", unk2, 1)])


def MARIO_POS(values):
    _, _, area, _ = CMD_BBBB(values)
    yaw, posX = CMD_HH(values)
    posY, posZ = CMD_HH(values)

    params = [
        format_param_hex("area", area, 1),
        format_param_string("yaw", yaw, 2),
        format_param_string("posX", posX, 2),
        format_param_string("posY", posY, 2),
        format_param_string("posZ", posZ, 2),
    ]
    return format_output("MARIO_POS", params)


def CMD2C(values):
    return format_output("CMD2C", [])


def CMD2D(values):
    return format_output("CMD2D", [])


def TERRAIN(values):
    from collision import parse_collision

    _, _, _ = CMD_BBH(values)
    collision = CMD_PTR(values)

    collision_rec = parse_collision(collision, ctx.txt, context_prefix=ctx.current_context_prefix)
    params = [collision_rec]
    return format_output("TERRAIN", params)


def ROOMS(values):
    from rooms import get_rooms_processor

    _, _, _ = CMD_BBH(values)
    surfaceRooms = CMD_PTR(values)

    res = get_rooms_processor().parse(surfaceRooms)
    if res == "NULL":
        return format_output("ROOMS", [f"0x{surfaceRooms:08x}"])

    return format_output("ROOMS", [res])


def SHOW_DIALOG(values):
    _, _, index, dialogId = CMD_BBBB(values)
    params = [format_param_hex("index", index, 1), format_param_hex("dialogId", dialogId, 1)]
    return format_output("SHOW_DIALOG", params)


def TERRAIN_TYPE(values):
    _, _, terrainType = CMD_BBH(values)
    return format_output("TERRAIN_TYPE", [format_param_hex("terrainType", terrainType, 2)])


def NOP(values):
    return format_output("NOP", [])


def TRANSITION(values):
    _, _, transType, time = CMD_BBBB(values)
    colorR, colorG, colorB, _ = CMD_BBBB(values)
    params = [
        format_param_hex("transType", transType, 1),
        format_param_hex("time", time, 1),
        format_param_hex("colorR", colorR, 1),
        format_param_hex("colorG", colorG, 1),
        format_param_hex("colorB", colorB, 1),
    ]
    return format_output("TRANSITION", params)


def BLACKOUT(values):
    _, _, active, _ = CMD_BBBB(values)
    return format_output("BLACKOUT", [format_param_hex("active", active, 1)])


def GAMMA(values):
    _, _, enabled, _ = CMD_BBBB(values)
    return format_output("GAMMA", [format_param_hex("enabled", enabled, 1)])


def SET_BACKGROUND_MUSIC(values):
    _, _, settingsPreset = CMD_BBH(values)
    seq, _ = CMD_HH(values)
    params = [
        format_param_hex("settingsPreset", settingsPreset, 2),
        format_param_hex("seq", seq, 2),
    ]
    return format_output("SET_BACKGROUND_MUSIC", params)


def SET_MENU_MUSIC(values):
    _, _, seq = CMD_BBH(values)
    return format_output("SET_MENU_MUSIC", [format_param_hex("seq", seq, 2)])


def STOP_MUSIC(values):
    _, _, fadeOutTime = CMD_BBH(values)
    return format_output("STOP_MUSIC", [format_param_hex("fadeOutTime", fadeOutTime, 2)])


def MACRO_OBJECTS(values):
    from macro_objects import parse_macro_object_list

    (_, _, _) = CMD_BBH(values)
    objList = CMD_PTR(values)
    macro_list_rec = parse_macro_object_list(
        objList, ctx.txt, context_prefix=ctx.current_context_prefix
    )
    return format_output("MACRO_OBJECTS", [macro_list_rec])


def CMD3A(values):
    _, _, unk2 = CMD_BBH(values)
    unk6, unk8 = CMD_HH(values)
    unk10, _ = CMD_HH(values)
    params = [
        format_param_hex("unk2", unk2, 2),
        format_param_hex("unk4", 0, 2),
        format_param_hex("unk6", unk6, 2),
        format_param_hex("unk8", unk8, 2),
        format_param_hex("unk10", unk10, 2),
    ]
    return format_output("CMD3A", params)


def WHIRLPOOL(values):
    _, _, index, condition = CMD_BBBB(values)
    posX, posY = CMD_HH(values)
    posZ, strength = CMD_HH(values)
    params = [
        format_param_hex("index", index, 1),
        format_param_hex("condition", condition, 1),
        format_param_string("posX", posX, 2),
        format_param_string("posY", posY, 2),
        format_param_string("posZ", posZ, 2),
        format_param_string("strength", strength, 2),
    ]
    return format_output("WHIRLPOOL", params)


def GET_OR_SET(values):
    _, _, op, var = CMD_BBBB(values)
    return format_output(
        "GET_OR_SET", [format_param_hex("op", op, 1), format_param_hex("var", var, 1)]
    )


def ADV_DEMO(values):
    return format_output("ADV_DEMO", [])


def CLEAR_DEMO_PTR(values):
    return format_output("CLEAR_DEMO_PTR", [])


parse_command_table = [
    {"name": "EXECUTE", "function": EXECUTE, "opcode": 0x00, "size": (0x10, 0x18)},
    {
        "name": "EXIT_AND_EXECUTE",
        "function": EXIT_AND_EXECUTE,
        "opcode": 0x01,
        "size": (0x10, 0x18),
    },
    {"name": "EXIT", "function": EXIT, "opcode": 0x02, "size": 0x04},
    {"name": "SLEEP", "function": SLEEP, "opcode": 0x03, "size": 0x04},
    {"name": "SLEEP_BEFORE_EXIT", "function": SLEEP_BEFORE_EXIT, "opcode": 0x04, "size": 0x04},
    {"name": "JUMP", "function": JUMP, "opcode": 0x05, "size": 0x08},
    {"name": "JUMP_LINK", "function": JUMP_LINK, "opcode": 0x06, "size": 0x08},
    {"name": "RETURN", "function": RETURN, "opcode": 0x07, "size": 0x04},
    {"name": "JUMP_LINK_PUSH_ARG", "function": JUMP_LINK_PUSH_ARG, "opcode": 0x08, "size": 0x04},
    {"name": "JUMP_N_TIMES", "function": JUMP_N_TIMES, "opcode": 0x09, "size": 0x04},
    {"name": "LOOP_BEGIN", "function": LOOP_BEGIN, "opcode": 0x0A, "size": 0x04},
    {"name": "LOOP_UNTIL", "function": LOOP_UNTIL, "opcode": 0x0B, "size": 0x08},
    {"name": "JUMP_IF", "function": JUMP_IF, "opcode": 0x0C, "size": 0x0C},
    {"name": "JUMP_LINK_IF", "function": JUMP_LINK_IF, "opcode": 0x0D, "size": 0x0C},
    {"name": "SKIP_IF", "function": SKIP_IF, "opcode": 0x0E, "size": 0x08},
    {"name": "SKIP", "function": SKIP, "opcode": 0x0F, "size": 0x04},
    {"name": "SKIP_NOP", "function": SKIP_NOP, "opcode": 0x10, "size": -1},
    {"name": "CALL", "function": CALL, "opcode": 0x11, "size": 0x08},
    {"name": "CALL_LOOP", "function": CALL_LOOP, "opcode": 0x12, "size": 0x08},
    {"name": "SET_REG", "function": SET_REG, "opcode": 0x13, "size": 0x04},
    {"name": "PUSH_POOL", "function": PUSH_POOL, "opcode": 0x14, "size": 0x04},
    {"name": "POP_POOL", "function": POP_POOL, "opcode": 0x15, "size": 0x04},
    {"name": "FIXED_LOAD", "function": FIXED_LOAD, "opcode": 0x16, "size": 0x10},
    {"name": "LOAD_RAW", "function": LOAD_RAW, "opcode": 0x17, "size": (0x0C, 0x14)},
    {"name": "LOAD_MIO0", "function": LOAD_MIO0, "opcode": 0x18, "size": 0x0C},
    {"name": "LOAD_MARIO_HEAD", "function": LOAD_MARIO_HEAD, "opcode": 0x19, "size": 0x04},
    {"name": "LOAD_MIO0_TEXTURE", "function": LOAD_MIO0_TEXTURE, "opcode": 0x1A, "size": 0x0C},
    {"name": "INIT_LEVEL", "function": INIT_LEVEL, "opcode": 0x1B, "size": 0x04},
    {"name": "CLEAR_LEVEL", "function": CLEAR_LEVEL, "opcode": 0x1C, "size": 0x04},
    {"name": "ALLOC_LEVEL_POOL", "function": ALLOC_LEVEL_POOL, "opcode": 0x1D, "size": 0x04},
    {"name": "FREE_LEVEL_POOL", "function": FREE_LEVEL_POOL, "opcode": 0x1E, "size": 0x04},
    {"name": "AREA", "function": AREA, "opcode": 0x1F, "size": 0x08},
    {"name": "END_AREA", "function": END_AREA, "opcode": 0x20, "size": 0x04},
    {"name": "LOAD_MODEL_FROM_DL", "function": LOAD_MODEL_FROM_DL, "opcode": 0x21, "size": 0x08},
    {"name": "LOAD_MODEL_FROM_GEO", "function": LOAD_MODEL_FROM_GEO, "opcode": 0x22, "size": 0x08},
    {"name": "CMD23", "function": CMD23, "opcode": 0x23, "size": 0x08},
    {
        "name": "OBJECT_WITH_ACTS",
        "function": OBJECT_WITH_ACTS,
        "opcode": 0x24,
        "size": (0x18, 0x1C),
    },
    {"name": "MARIO", "function": MARIO, "opcode": 0x25, "size": 0x0C},
    {"name": "WARP_NODE", "function": WARP_NODE, "opcode": 0x26, "size": 0x08},
    {"name": "PAINTING_WARP_NODE", "function": PAINTING_WARP_NODE, "opcode": 0x27, "size": 0x08},
    {"name": "INSTANT_WARP", "function": INSTANT_WARP, "opcode": 0x28, "size": 0x0C},
    {"name": "LOAD_AREA", "function": LOAD_AREA, "opcode": 0x29, "size": 0x04},
    {"name": "CMD2A", "function": CMD2A, "opcode": 0x2A, "size": 0x04},
    {"name": "MARIO_POS", "function": MARIO_POS, "opcode": 0x2B, "size": 0x0C},
    {"name": "CMD2C", "function": CMD2C, "opcode": 0x2C, "size": 0x04},
    {"name": "CMD2D", "function": CMD2D, "opcode": 0x2D, "size": 0x04},
    {"name": "TERRAIN", "function": TERRAIN, "opcode": 0x2E, "size": 0x08},
    {"name": "ROOMS", "function": ROOMS, "opcode": 0x2F, "size": 0x08},
    {"name": "SHOW_DIALOG", "function": SHOW_DIALOG, "opcode": 0x30, "size": 0x04},
    {"name": "TERRAIN_TYPE", "function": TERRAIN_TYPE, "opcode": 0x31, "size": 0x04},
    {"name": "NOP", "function": NOP, "opcode": 0x32, "size": -1},
    {"name": "TRANSITION", "function": TRANSITION, "opcode": 0x33, "size": 0x08},
    {"name": "BLACKOUT", "function": BLACKOUT, "opcode": 0x34, "size": 0x04},
    {"name": "GAMMA", "function": GAMMA, "opcode": 0x35, "size": 0x04},
    {
        "name": "SET_BACKGROUND_MUSIC",
        "function": SET_BACKGROUND_MUSIC,
        "opcode": 0x36,
        "size": 0x08,
    },
    {"name": "SET_MENU_MUSIC", "function": SET_MENU_MUSIC, "opcode": 0x37, "size": 0x04},
    {"name": "STOP_MUSIC", "function": STOP_MUSIC, "opcode": 0x38, "size": 0x04},
    {"name": "MACRO_OBJECTS", "function": MACRO_OBJECTS, "opcode": 0x39, "size": 0x08},
    {"name": "CMD3A", "function": CMD3A, "opcode": 0x3A, "size": 0x0C},
    {"name": "WHIRLPOOL", "function": WHIRLPOOL, "opcode": 0x3B, "size": 0x0C},
    {"name": "GET_OR_SET", "function": GET_OR_SET, "opcode": 0x3C, "size": 0x04},
    {"name": "ADV_DEMO", "function": ADV_DEMO, "opcode": 0x3D, "size": 0x04},
    {"name": "CLEAR_DEMO_PTR", "function": CLEAR_DEMO_PTR, "opcode": 0x3E, "size": 0x04},
]
