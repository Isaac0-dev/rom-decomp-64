import struct
from typing import Any, Dict, List, Optional, Tuple
from segment import (
    segment_from_addr,
    offset_from_segment_addr,
    where_is_segment_loaded,
    get_segment,
)
from byteio import CustomBytesIO
from base_processor import BaseProcessor
from rom_database import CollisionRecord, CommandIR
from context import ctx
from constants import SURFACES

# --- TERRAIN Opcodes ---
TERRAIN_LOAD_VERTICES = 0x40
TERRAIN_LOAD_CONTINUE = 0x41
TERRAIN_LOAD_END = 0x42
TERRAIN_LOAD_OBJECTS = 0x43
TERRAIN_LOAD_ENVIRONMENT = 0x44

SPECIAL_SURFACES = {
    0x0004: "SURFACE_0004",
    0x000E: "SURFACE_FLOWING_WATER",
    0x0024: "SURFACE_DEEP_MOVING_QUICKSAND",
    0x0025: "SURFACE_SHALLOW_MOVING_QUICKSAND",
    0x0027: "SURFACE_MOVING_QUICKSAND",
    0x002C: "SURFACE_HORIZONTAL_WIND",
    0x002D: "SURFACE_INSTANT_MOVING_QUICKSAND",
}

COLLISION_COMMANDS = {
    TERRAIN_LOAD_CONTINUE,
    TERRAIN_LOAD_OBJECTS,
    TERRAIN_LOAD_ENVIRONMENT,
    TERRAIN_LOAD_END,
}

# --- Special Presets ---
preset_id_map: Dict[str, int] = {
    "special_null_start": 0,
    "special_yellow_coin": 1,
    "special_yellow_coin_2": 2,
    "special_unknown_3": 3,
    "special_boo": 4,
    "special_unknown_5": 5,
    "special_lll_moving_octagonal_mesh_platform": 6,
    "special_snow_ball": 7,
    "special_lll_drawbridge_spawner": 8,
    "special_empty_9": 9,
    "special_lll_rotating_block_with_fire_bars": 10,
    "special_lll_floating_wood_bridge": 11,
    "special_tumbling_platform": 12,
    "special_lll_rotating_hexagonal_ring": 13,
    "special_lll_sinking_rectangular_platform": 14,
    "special_lll_sinking_square_platforms": 15,
    "special_lll_tilting_square_platform": 16,
    "special_lll_bowser_puzzle": 17,
    "special_mr_i": 18,
    "special_small_bully": 19,
    "special_big_bully": 20,
    "special_empty_21": 21,
    "special_empty_22": 22,
    "special_empty_23": 23,
    "special_empty_24": 24,
    "special_empty_25": 25,
    "special_moving_blue_coin": 26,
    "special_jrb_chest": 27,
    "special_water_ring": 28,
    "special_mine": 29,
    "special_empty_30": 30,
    "special_empty_31": 31,
    "special_butterfly": 32,
    "special_bowser": 33,
    "special_wf_rotating_wooden_platform": 34,
    "special_small_bomp": 35,
    "special_wf_sliding_platform": 36,
    "special_tower_platform_group": 37,
    "special_rotating_counter_clockwise": 38,
    "special_wf_tumbling_bridge": 39,
    "special_large_bomp": 40,
    "special_level_geo_03": 101,
    "special_level_geo_04": 102,
    "special_level_geo_05": 103,
    "special_level_geo_06": 104,
    "special_level_geo_07": 105,
    "special_level_geo_08": 106,
    "special_level_geo_09": 107,
    "special_level_geo_0A": 108,
    "special_level_geo_0B": 109,
    "special_level_geo_0C": 110,
    "special_level_geo_0D": 111,
    "special_level_geo_0E": 112,
    "special_level_geo_0F": 113,
    "special_level_geo_10": 114,
    "special_level_geo_11": 115,
    "special_level_geo_12": 116,
    "special_level_geo_13": 117,
    "special_level_geo_14": 118,
    "special_level_geo_15": 119,
    "special_level_geo_16": 120,
    "special_bubble_tree": 121,
    "special_spiky_tree": 122,
    "special_snow_tree": 123,
    "special_unknown_tree": 124,
    "special_palm_tree": 125,
    "special_wooden_door": 126,
    "special_haunted_door": 126,
    "special_unknown_door": 127,
    "special_metal_door": 128,
    "special_hmc_door": 129,
    "special_unknown2_door": 130,
    "special_wooden_door_warp": 131,
    "special_unknown1_door_warp": 132,
    "special_metal_door_warp": 133,
    "special_unknown2_door_warp": 134,
    "special_unknown3_door_warp": 135,
    "special_castle_door_warp": 136,
    "special_castle_door": 137,
    "special_0stars_door": 138,
    "special_1star_door": 139,
    "special_3star_door": 140,
    "special_key_door": 141,
}
preset_get_id_map: Dict[int, str] = {v: k for k, v in preset_id_map.items()}

SPTYPE_NO_YROT_OR_PARAMS = 0
SPTYPE_YROT_NO_PARAMS = 1
SPTYPE_PARAMS_AND_YROT = 2
SPTYPE_UNKNOWN = 3
SPTYPE_DEF_PARAM_AND_YROT = 4

SPECIAL_PRESET_TYPES: Dict[int, int] = {
    0: SPTYPE_YROT_NO_PARAMS,
    1: SPTYPE_NO_YROT_OR_PARAMS,
    2: SPTYPE_NO_YROT_OR_PARAMS,
    3: SPTYPE_NO_YROT_OR_PARAMS,
    4: SPTYPE_NO_YROT_OR_PARAMS,
    5: SPTYPE_NO_YROT_OR_PARAMS,
    6: SPTYPE_NO_YROT_OR_PARAMS,
    7: SPTYPE_NO_YROT_OR_PARAMS,
    8: SPTYPE_YROT_NO_PARAMS,
    10: SPTYPE_NO_YROT_OR_PARAMS,
    13: SPTYPE_NO_YROT_OR_PARAMS,
    14: SPTYPE_YROT_NO_PARAMS,
    15: SPTYPE_NO_YROT_OR_PARAMS,
    16: SPTYPE_NO_YROT_OR_PARAMS,
    18: SPTYPE_NO_YROT_OR_PARAMS,
    19: SPTYPE_NO_YROT_OR_PARAMS,
    20: SPTYPE_NO_YROT_OR_PARAMS,
    21: SPTYPE_NO_YROT_OR_PARAMS,
    22: SPTYPE_NO_YROT_OR_PARAMS,
    23: SPTYPE_NO_YROT_OR_PARAMS,
    24: SPTYPE_NO_YROT_OR_PARAMS,
    25: SPTYPE_NO_YROT_OR_PARAMS,
    26: SPTYPE_NO_YROT_OR_PARAMS,
    27: SPTYPE_NO_YROT_OR_PARAMS,
    28: SPTYPE_NO_YROT_OR_PARAMS,
    29: SPTYPE_NO_YROT_OR_PARAMS,
    30: SPTYPE_UNKNOWN,
    31: SPTYPE_NO_YROT_OR_PARAMS,
    32: SPTYPE_NO_YROT_OR_PARAMS,
    33: SPTYPE_NO_YROT_OR_PARAMS,
    34: SPTYPE_NO_YROT_OR_PARAMS,
    35: SPTYPE_YROT_NO_PARAMS,
    36: SPTYPE_YROT_NO_PARAMS,
    37: SPTYPE_NO_YROT_OR_PARAMS,
    38: SPTYPE_NO_YROT_OR_PARAMS,
    39: SPTYPE_NO_YROT_OR_PARAMS,
    40: SPTYPE_NO_YROT_OR_PARAMS,
    101: SPTYPE_YROT_NO_PARAMS,
    102: SPTYPE_YROT_NO_PARAMS,
    103: SPTYPE_YROT_NO_PARAMS,
    104: SPTYPE_YROT_NO_PARAMS,
    105: SPTYPE_YROT_NO_PARAMS,
    106: SPTYPE_YROT_NO_PARAMS,
    107: SPTYPE_YROT_NO_PARAMS,
    108: SPTYPE_YROT_NO_PARAMS,
    109: SPTYPE_YROT_NO_PARAMS,
    110: SPTYPE_YROT_NO_PARAMS,
    111: SPTYPE_YROT_NO_PARAMS,
    112: SPTYPE_YROT_NO_PARAMS,
    113: SPTYPE_YROT_NO_PARAMS,
    114: SPTYPE_YROT_NO_PARAMS,
    115: SPTYPE_YROT_NO_PARAMS,
    116: SPTYPE_YROT_NO_PARAMS,
    117: SPTYPE_YROT_NO_PARAMS,
    118: SPTYPE_YROT_NO_PARAMS,
    119: SPTYPE_YROT_NO_PARAMS,
    120: SPTYPE_YROT_NO_PARAMS,
    121: SPTYPE_NO_YROT_OR_PARAMS,
    122: SPTYPE_NO_YROT_OR_PARAMS,
    123: SPTYPE_NO_YROT_OR_PARAMS,
    124: SPTYPE_NO_YROT_OR_PARAMS,
    125: SPTYPE_NO_YROT_OR_PARAMS,
    126: SPTYPE_YROT_NO_PARAMS,
    127: SPTYPE_YROT_NO_PARAMS,
    128: SPTYPE_YROT_NO_PARAMS,
    129: SPTYPE_YROT_NO_PARAMS,
    130: SPTYPE_YROT_NO_PARAMS,
    131: SPTYPE_PARAMS_AND_YROT,
    132: SPTYPE_PARAMS_AND_YROT,
    133: SPTYPE_PARAMS_AND_YROT,
    134: SPTYPE_PARAMS_AND_YROT,
    135: SPTYPE_PARAMS_AND_YROT,
    136: SPTYPE_PARAMS_AND_YROT,
    137: SPTYPE_YROT_NO_PARAMS,
    138: SPTYPE_DEF_PARAM_AND_YROT,
    139: SPTYPE_DEF_PARAM_AND_YROT,
    140: SPTYPE_DEF_PARAM_AND_YROT,
    141: SPTYPE_DEF_PARAM_AND_YROT,
}


# --- Parsing Helpers ---


def _parse_vertices(rom: CustomBytesIO) -> Tuple[List[CommandIR], List[Tuple[int, int, int]]]:
    vcount = rom.read_u16()
    ir_list = [CommandIR(TERRAIN_LOAD_VERTICES, [vcount], name="COL_VERTEX_INIT")]
    verts = []
    for _ in range(vcount):
        x, y, z = struct.unpack(">3h", rom.read(6))
        verts.append((x, y, z))
        ir_list.append(CommandIR(TERRAIN_LOAD_VERTICES, [x, y, z], name="COL_VERTEX"))
    return ir_list, verts


def looks_like_next_cmd(val: int) -> bool:
    return val in COLLISION_COMMANDS or val < 0x40 or val >= 0x65


def _parse_triangles(rom: CustomBytesIO) -> Tuple[List[CommandIR], int]:
    ir_list = []
    total = 0
    while True:
        try:
            if rom.peek_u16() == TERRAIN_LOAD_CONTINUE:
                break
            stype = rom.read_u16()
            tcount = rom.read_u16()
        except EOFError:
            break

        ir_list.append(
            CommandIR(TERRAIN_LOAD_CONTINUE, [SURFACES(stype), tcount], name="COL_TRI_INIT")
        )
        total += tcount
        is_spec = stype in SPECIAL_SURFACES
        for _ in range(tcount):
            v1, v2, v3 = struct.unpack(">3h", rom.read(6))
            if is_spec:
                param = struct.unpack(">H", rom.read(2))[0]
                ir_list.append(
                    CommandIR(
                        TERRAIN_LOAD_CONTINUE,
                        [v1, v2, v3, f"0x{param:04X}"],
                        name="COL_TRI_SPECIAL",
                    )
                )
            else:
                ir_list.append(CommandIR(TERRAIN_LOAD_CONTINUE, [v1, v2, v3], name="COL_TRI"))

    try:
        rom.read_u16()  # 0x41
    except EOFError:
        pass
    ir_list.append(CommandIR(TERRAIN_LOAD_CONTINUE, [], name="COL_TRI_STOP"))
    return ir_list, total


def _parse_special_objects(rom: CustomBytesIO) -> List[CommandIR]:
    cmd = rom.read_u16()
    if cmd != TERRAIN_LOAD_OBJECTS:
        raise ValueError("Not a special object block")
    count = rom.read_u16()
    ir_list = [CommandIR(TERRAIN_LOAD_OBJECTS, [count], name="COL_SPECIAL_INIT")]
    for _ in range(count):
        preset_id = rom.read_u16()
        x, y, z = struct.unpack(">3h", rom.read(6))
        sp_type = SPECIAL_PRESET_TYPES.get(preset_id, SPTYPE_NO_YROT_OR_PARAMS)
        name = preset_get_id_map.get(preset_id, str(preset_id))
        if sp_type == SPTYPE_NO_YROT_OR_PARAMS:
            ir_list.append(CommandIR(TERRAIN_LOAD_OBJECTS, [name, x, y, z], name="SPECIAL_OBJECT"))
        elif sp_type == SPTYPE_YROT_NO_PARAMS:
            yaw = rom.read_u16()
            ir_list.append(
                CommandIR(
                    TERRAIN_LOAD_OBJECTS, [name, x, y, z, yaw], name="SPECIAL_OBJECT_WITH_YAW"
                )
            )
        elif sp_type == SPTYPE_PARAMS_AND_YROT:
            yaw = rom.read_u16()
            param = rom.read_u16()
            ir_list.append(
                CommandIR(
                    TERRAIN_LOAD_OBJECTS,
                    [name, x, y, z, yaw, f"0x{param:04X}"],
                    name="SPECIAL_OBJECT_WITH_YAW_AND_PARAM",
                )
            )
        elif sp_type == SPTYPE_DEF_PARAM_AND_YROT:
            yaw = rom.read_u16()
            ir_list.append(
                CommandIR(
                    TERRAIN_LOAD_OBJECTS,
                    [name, x, y, z, yaw, 0],
                    name="SPECIAL_OBJECT_WITH_YAW_AND_PARAM",
                )
            )
        else:
            # SPTYPE_UNKNOWN: assume 3 more shorts
            unk_a, unk_b, unk_c = struct.unpack(">3h", rom.read(6))
            ir_list.append(
                CommandIR(
                    TERRAIN_LOAD_OBJECTS,
                    [name, x, y, z, unk_a, unk_b, unk_c],
                    name="SPECIAL_OBJECT_SPECIAL",
                )
            )
    return ir_list


def _parse_water_boxes(rom: CustomBytesIO) -> List[CommandIR]:
    cmd = rom.read_u16()
    if cmd != TERRAIN_LOAD_ENVIRONMENT:
        raise ValueError("Not a water box block")
    count = rom.read_u16()
    ir_list = [CommandIR(TERRAIN_LOAD_ENVIRONMENT, [count], name="COL_WATER_BOX_INIT")]
    for _ in range(count):
        id_val, x1, z1, x2, z2, y = struct.unpack(">6h", rom.read(12))
        ir_list.append(
            CommandIR(TERRAIN_LOAD_ENVIRONMENT, [id_val, x1, z1, x2, z2, y], name="COL_WATER_BOX")
        )
    return ir_list


def parse_collision_data_to_ir(rom: CustomBytesIO) -> Tuple[List[CommandIR], int]:
    ir_list = []
    total_surfaces = 0
    try:
        cmd = rom.read_u16()
    except EOFError:
        return [], 0
    if cmd != TERRAIN_LOAD_VERTICES:
        return [], 0

    ir_list.append(CommandIR(0, [], name="COL_INIT"))

    # Pass 1: Vertices
    v_ir, _ = _parse_vertices(rom)
    ir_list.extend(v_ir)

    # Pass 2: Triangles
    t_ir, total_surfaces = _parse_triangles(rom)
    ir_list.extend(t_ir)

    # Pass 3: Special Objects
    if rom.tell() + 2 <= len(rom.getvalue()):
        if rom.peek_u16() == TERRAIN_LOAD_OBJECTS:
            ir_list.extend(_parse_special_objects(rom))

    # Pass 4: Water Boxes
    if rom.tell() + 2 <= len(rom.getvalue()):
        if rom.peek_u16() == TERRAIN_LOAD_ENVIRONMENT:
            ir_list.extend(_parse_water_boxes(rom))

    # End
    while rom.tell() + 2 <= len(rom.getvalue()):
        c = rom.peek_u16()
        if c == TERRAIN_LOAD_END:
            rom.read_u16()
            ir_list.append(CommandIR(TERRAIN_LOAD_END, [], name="COL_END"))
            break
        if looks_like_next_cmd(c):
            # Sometimes there are multiple triangle blocks
            t_ir, extra = _parse_triangles(rom)
            ir_list.extend(t_ir)
            total_surfaces += extra
            continue
        break

    return ir_list, total_surfaces


# --- CollisionProcessor ---


class CollisionProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)
        self.parsed_collisions: Dict[Tuple[int, int], Any] = {}

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        context_prefix = kwargs.get("context_prefix")
        if not segmented_addr:
            return "NULL"
        seg_num = segment_from_addr(segmented_addr)
        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            return f"collision_fail_0x{segmented_addr:08X}"

        start = segment_info[0]
        db_key = (segmented_addr, start)

        # Check database for already assigned name
        if self.ctx.db and db_key in self.ctx.db.collisions:
            return self.ctx.db.collisions[db_key]

        offset = offset_from_segment_addr(segmented_addr)
        key = (offset, start)
        if key in self.parsed_collisions:
            return self.parsed_collisions[key]

        data = get_segment(seg_num)
        if data is None:
            return "NULL"

        rom = CustomBytesIO(data)
        rom.seek(offset)
        commands_ir, surface_count = parse_collision_data_to_ir(rom)

        name = f"collision_0x{segmented_addr:08X}"
        if context_prefix is not None:
            name = f"{context_prefix}_collision_0x{segmented_addr:08X}"

        if self.ctx.db:
            record = CollisionRecord(
                seg_addr=segmented_addr,
                name=name,
                commands=commands_ir,
                location=self.ctx.level_area,
            )
            self.ctx.db.collisions[db_key] = record
            self.ctx.db.set_symbol(segmented_addr, name, "Collision")

        self.parsed_collisions[key] = record if self.ctx.db else name
        ctx.last_collision_surface_count = surface_count
        return self.parsed_collisions[key]

    def serialize(self, record: CollisionRecord) -> str:
        output = f"const Collision {record.name}[] = " + "{\n"
        for ir in record.commands:
            params_str = ", ".join(map(str, ir.params))
            output += f"    {ir.name}({params_str}),\n"
        output += "};\n"
        if self.ctx.txt:
            self.ctx.txt.write(self.ctx, "collision", record.name, output)
        return output


_col_processor = None


def get_collision_processor():
    global _col_processor
    if _col_processor is None:
        _col_processor = CollisionProcessor(ctx)
    return _col_processor


def parse_collision_data_global(segmented_addr, sTxt):
    return get_collision_processor().parse(segmented_addr, txt=sTxt)


def parse_collision(segmented_addr: int, sTxt: Any, context_prefix: Optional[str] = None) -> str:
    return get_collision_processor().parse(segmented_addr, txt=sTxt, context_prefix=context_prefix)
