from typing import List
from rom_database import CommandIR, RomDatabase
from context import LevelAreaContext

# Mapping of opcodes to formatting functions for Geo Layouts
GEO_OPCODE_NAMES = {
    0x00: "GEO_BRANCH_AND_LINK",
    0x01: "GEO_END",
    0x02: "GEO_BRANCH",
    0x03: "GEO_RETURN",
    0x04: "GEO_OPEN_NODE",
    0x05: "GEO_CLOSE_NODE",
    0x08: "GEO_NODE_SCREEN_AREA",
    0x09: "GEO_NODE_ORTHO",
    0x0A: "GEO_CAMERA_FRUSTUM",
    0x0B: "GEO_NODE_START",
    0x0C: "GEO_ZBUFFER",
    0x0D: "GEO_RENDER_RANGE",
    0x0E: "GEO_SWITCH_CASE",
    0x0F: "GEO_CAMERA",
    0x10: "GEO_TRANSLATE_ROTATE",
    0x11: "GEO_TRANSLATE_NODE",
    0x12: "GEO_ROTATION_NODE",
    0x13: "GEO_ANIMATED_PART",
    0x14: "GEO_BILLBOARD_WITH_PARAMS",
    0x15: "GEO_DISPLAY_LIST",
    0x16: "GEO_SHADOW",
    0x17: "GEO_RENDER_OBJ",
    0x18: "GEO_ASM",
    0x19: "GEO_BACKGROUND",
    0x1A: "GEO_NOP_1A",
    0x1B: "GEO_COPY_VIEW",
    0x1C: "GEO_HELD_OBJECT",
    0x1D: "GEO_SCALE",
    0x1E: "GEO_NOP_1E",
    0x1F: "GEO_NOP_1F",
    0x20: "GEO_CULLING_RADIUS",
    0x21: "GEO_BONE",
}


def serialize_geo_command(cmd: CommandIR, db: RomDatabase) -> str:
    """Convert a Geo CommandIR back into a C macro string."""
    name = GEO_OPCODE_NAMES.get(cmd.opcode, f"GEO_UNKNOWN_{cmd.opcode:02X}")
    indent_str = "    " * (cmd.indent + 1)

    # Special handling for commands with symbol resolution
    if cmd.opcode == 0x0E:  # GEO_SWITCH_CASE
        count, func = cmd.params
        if isinstance(func, str):
            func_name = func
        else:
            func_name = db.resolve_symbol(func, "func")
        comment = "// " if func_name == "NULL" else ""
        return f"{indent_str}{comment}GEO_SWITCH_CASE({count}, {func_name})"

    if cmd.opcode == 0x18:  # GEO_ASM
        param, func = cmd.params
        if isinstance(func, str):
            func_name = func
        else:
            func_name = db.resolve_symbol(func, "func")
        comment = "// " if func_name == "NULL" else ""
        return f"{indent_str}{comment}GEO_ASM({param}, {func_name})"

    if cmd.opcode == 0x0A:  # GEO_CAMERA_FRUSTUM
        if len(cmd.params) == 4:  # WITH_FUNC
            fov, near, far, func = cmd.params
            if isinstance(func, str):
                func_name = func
            else:
                func_name = db.resolve_symbol(func, "func")
            return f"{indent_str}GEO_CAMERA_FRUSTUM_WITH_FUNC({fov}, {near}, {far}, {func_name})"
        fov, near, far = cmd.params
        return f"{indent_str}GEO_CAMERA_FRUSTUM({fov}, {near}, {far})"

    if cmd.opcode == 0x15:  # GEO_DISPLAY_LIST
        layer, dl = cmd.params
        if hasattr(dl, "name"):
            dl_name = dl.name
        elif isinstance(dl, str):
            dl_name = dl
        else:
            dl_name = db.resolve_symbol(dl, "dl")
        return f"{indent_str}GEO_DISPLAY_LIST({layer}, {dl_name})"

    # Fallback: simple comma-separated params
    param_str = ", ".join(str(p) for p in cmd.params)
    return f"{indent_str}{name}({param_str})"


def serialize_geo_layout(geo_name: str, commands: List[CommandIR], db: RomDatabase) -> str:
    """Serialize a full GeoRecord into a C file string."""
    lines = [f"const GeoLayout {geo_name}[] = {{"]
    for cmd in commands:
        lines.append(serialize_geo_command(cmd, db) + ",")
    lines.append("};")
    return "\n".join(lines)


# Collision opcodes (internal to our IR)
COL_OP_INIT = 0x40
COL_OP_VERTEX_INIT = 0x41
COL_OP_VERTEX = 0x42
COL_OP_TRI_INIT = 0x43
COL_OP_TRI = 0x44
COL_OP_TRI_SPECIAL = 0x45
COL_OP_TRI_STOP = 0x46
COL_OP_END = 0x47
COL_OP_SPECIAL_INIT = 0x48
COL_OP_SPECIAL_OBJECT = 0x49
COL_OP_SPECIAL_OBJECT_WITH_YAW = 0x4A
COL_OP_SPECIAL_OBJECT_WITH_YAW_AND_PARAM = 0x4B
COL_OP_SPECIAL_OBJECT_SPECIAL = 0x4E  # Corrected enum
COL_OP_WATER_BOX_INIT = 0x4C
COL_OP_WATER_BOX = 0x4D

COL_OPCODE_NAMES = {
    COL_OP_INIT: "COL_INIT",
    COL_OP_VERTEX_INIT: "COL_VERTEX_INIT",
    COL_OP_VERTEX: "COL_VERTEX",
    COL_OP_TRI_INIT: "COL_TRI_INIT",
    COL_OP_TRI: "COL_TRI",
    COL_OP_TRI_SPECIAL: "COL_TRI_SPECIAL",
    COL_OP_TRI_STOP: "COL_TRI_STOP",
    COL_OP_END: "COL_END",
    COL_OP_SPECIAL_INIT: "COL_SPECIAL_INIT",
    COL_OP_SPECIAL_OBJECT: "SPECIAL_OBJECT",
    COL_OP_SPECIAL_OBJECT_WITH_YAW: "SPECIAL_OBJECT_WITH_YAW",
    COL_OP_SPECIAL_OBJECT_WITH_YAW_AND_PARAM: "SPECIAL_OBJECT_WITH_YAW_AND_PARAM",
    COL_OP_SPECIAL_OBJECT_SPECIAL: "SPECIAL_OBJECT_SPECIAL",
    COL_OP_WATER_BOX_INIT: "COL_WATER_BOX_INIT",
    COL_OP_WATER_BOX: "COL_WATER_BOX",
}


def serialize_collision_command(cmd: CommandIR, db: RomDatabase) -> str:
    """Convert a Collision CommandIR back into a C macro string."""
    name = COL_OPCODE_NAMES.get(cmd.opcode, f"COL_UNKNOWN_{cmd.opcode:02X}")
    indent_str = "    "

    # Special handling for names/constants if needed
    params = []
    for p in cmd.params:
        if isinstance(p, int) and name == "COL_TRI_SPECIAL":
            params.append(f"0x{p:04X}")
        elif (
            isinstance(p, int)
            and name.startswith("SPECIAL_OBJECT_WITH_YAW_AND_PARAM")
            and len(params) == 5
        ):
            # Param is usually hex
            params.append(f"0x{p:04X}")
        else:
            params.append(str(p))

    return f"{indent_str}{name}({', '.join(params)})"


def serialize_collision(col_name: str, commands: List[CommandIR], db: RomDatabase) -> str:
    """Serialize a full CollisionRecord into a C file string."""
    lines = [f"const Collision {col_name}[] = {{"]
    for cmd in commands:
        lines.append(serialize_collision_command(cmd, db) + ",")
    lines.append("};")
    return "\n".join(lines)


# Behavior opcodes (match BEHAVIOR_COMMANDS in behavior.py)
BEH_OPCODE_NAMES = {
    0x00: "BEGIN",
    0x01: "DELAY",
    0x02: "CALL",
    0x03: "RETURN",
    0x04: "GOTO",
    0x05: "BEGIN_REPEAT",
    0x06: "END_REPEAT",
    0x07: "END_REPEAT_CONTINUE",
    0x08: "BEGIN_LOOP",
    0x09: "END_LOOP",
    0x0A: "BREAK",
    0x0B: "BREAK_UNUSED",
    0x0C: "CALL_NATIVE",
    0x0D: "ADD_FLOAT",
    0x0E: "SET_FLOAT",
    0x0F: "ADD_INT",
    0x10: "SET_INT",
    0x11: "OR_INT",
    0x12: "BIT_CLEAR",
    0x13: "SET_INT_RAND_RSHIFT",
    0x14: "SET_RANDOM_FLOAT",
    0x15: "SET_RANDOM_INT",
    0x16: "ADD_RANDOM_FLOAT",
    0x17: "ADD_INT_RAND_RSHIFT",
    0x18: "CMD_NOP_1",
    0x19: "CMD_NOP_2",
    0x1A: "CMD_NOP_3",
    0x1B: "SET_MODEL",
    0x1C: "SPAWN_CHILD",
    0x1D: "DEACTIVATE",
    0x1E: "DROP_TO_FLOOR",
    0x1F: "SUM_FLOAT",
    0x20: "SUM_INT",
    0x21: "BILLBOARD",
    0x22: "HIDE",
    0x23: "SET_HITBOX",
    0x24: "CMD_NOP_4",
    0x25: "DELAY_VAR",
    0x26: "BEGIN_REPEAT_UNUSED",
    0x27: "LOAD_ANIMATIONS",
    0x28: "ANIMATE",
    0x29: "SPAWN_CHILD_WITH_PARAM",
    0x2A: "LOAD_COLLISION_DATA",
    0x2B: "SET_HITBOX_WITH_OFFSET",
    0x2C: "SPAWN_OBJ",
    0x2D: "SET_HOME",
    0x2E: "SET_HURTBOX",
    0x2F: "SET_INTERACT_TYPE",
    0x30: "SET_OBJ_PHYSICS",
    0x31: "SET_INTERACT_SUBTYPE",
    0x32: "SCALE",
    0x33: "PARENT_BIT_CLEAR",
    0x34: "ANIMATE_TEXTURE",
    0x35: "DISABLE_RENDERING",
    0x36: "SET_INT_UNUSED",
    0x37: "SPAWN_WATER_DROPLET",
    0x3B: "CMD_3B",
    0x57: "CMD_57",
}


def serialize_behavior_command(cmd: CommandIR, db: RomDatabase) -> str:
    """Convert a Behavior CommandIR back into a C macro string."""
    name = BEH_OPCODE_NAMES.get(cmd.opcode, f"BEH_UNKNOWN_{cmd.opcode:02X}")
    indent_str = "    "

    # Special handling for symbol resolution
    if cmd.opcode == 0x0C:  # CALL_NATIVE
        vram_addr = cmd.params[0]
        func_name = db.resolve_symbol(vram_addr, "func")
        return f"{indent_str}CALL_NATIVE({func_name})"

    if cmd.opcode in [
        0x02,
        0x04,
        0x1C,
        0x29,
        0x2A,
        0x2C,
        0x37,
    ]:  # Commands with behavior/data pointers
        # These will be resolved in a later pass
        resolved_params = []
        for p in cmd.params:
            if isinstance(p, int) and p > 0x1000000:
                resolved_params.append(db.resolve_symbol(p, "ptr"))
            else:
                resolved_params.append(str(p))
        return f"{indent_str}{name}({', '.join(resolved_params)})"

    # Fallback
    return f"{indent_str}{name}({', '.join(str(p) for p in cmd.params)})"


def serialize_behavior(bhv_name: str, commands: List[CommandIR], db: RomDatabase) -> str:
    """Serialize a full BehaviorRecord into a C file string."""
    lines = [f"const BehaviorScript {bhv_name}[] = {{"]
    for cmd in commands:
        lines.append(serialize_behavior_command(cmd, db) + ",")
    lines.append("};")
    return "\n".join(lines)


def serialize_gfx_command(
    cmd: CommandIR, db: RomDatabase, location: LevelAreaContext, microcode_name: str = "GBI0"
) -> str:
    """Convert a Gfx (Display List) CommandIR back into a C macro string."""
    from microcode import create_microcode

    ucode = create_microcode(microcode_name)
    return ucode.serialize_command(cmd, db, location)


def serialize_gfx_layout(
    dl_name: str,
    commands: List[CommandIR],
    db: RomDatabase,
    location: LevelAreaContext,
    microcode_name: str = "GBI0",
) -> str:
    """Serialize a full DisplayListRecord into a C file string."""
    lines = [f"const Gfx {dl_name}[] = {{"]
    for cmd in commands:
        lines.append(serialize_gfx_command(cmd, db, location, microcode_name) + ",")
    lines.append("};")
    return "\n".join(lines)


G_IM_FMT_INV = {
    0: "G_IM_FMT_RGBA",
    1: "G_IM_FMT_YUV",
    2: "G_IM_FMT_CI",
    3: "G_IM_FMT_IA",
    4: "G_IM_FMT_I",
}
G_IM_SIZ_INV = {0: "G_IM_SIZ_4b", 1: "G_IM_SIZ_8b", 2: "G_IM_SIZ_16b", 3: "G_IM_SIZ_32b"}
