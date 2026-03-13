import hashlib
from typing import Any, Dict, List, Optional, Tuple
from behavior_hashes import KNOWN_BEHAVIOR_HASHES
from utils import (
    debug_print,
    segment_from_addr,
    offset_from_segment_addr,
    get_rom,
    validator,
    TEST_REQUIRED,
    to_signed16,
)
from byteio import CustomBytesIO
from segment import get_segment, where_is_segment_loaded, get_loaded_segment_numbers
from base_processor import BaseProcessor
from rom_database import BehaviorRecord, CommandIR
from context import ctx
from utils import debug_fail

# --- CALL_NATIVE function matching ---
_func_matcher = None
_call_native_cache: Dict[int, Optional[str]] = {}

_CODE_VRAM_START = validator.rom_test(
    0x80246000,
    TEST_REQUIRED,
    b"\x3c\x08\x80\x34",
    rom_offset=0x1000,
    description="Main Code Segment Start",
)
_CODE_ROM_START = 0x1000


def _get_func_matcher():
    global _func_matcher
    if _func_matcher is None:
        from function_matching.matcher import FunctionMatcher

        _func_matcher = FunctionMatcher()
    return _func_matcher


def resolve_call_native(vram_addr: int) -> Optional[str]:
    if vram_addr in _call_native_cache:
        return _call_native_cache[vram_addr]

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
        _call_native_cache[vram_addr] = None
        return None

    rom = get_rom()
    if rom is None or rom_offset >= len(rom):
        _call_native_cache[vram_addr] = None
        return None

    try:
        matcher = _get_func_matcher()
        result = matcher.match(rom, rom_offset=rom_offset, vram_start=vram_base, rom_start=rom_base)
        if result is not None and result.confidence >= 0.90:
            if result.is_ambiguous:
                debug_print(
                    f"  CALL_NATIVE 0x{vram_addr:08X}: ambiguous match "
                    f"{result.best_match} ({result.confidence:.2f}) vs "
                    f"{result.runner_up} ({result.runner_up_confidence:.2f})"
                )
            _call_native_cache[vram_addr] = result.best_match
            return result.best_match
    except Exception as e:
        debug_print(f"  CALL_NATIVE 0x{vram_addr:08X}: match error: {e}")

    _call_native_cache[vram_addr] = None
    return None


BEHAVIOR_ADDR_OVERRIDES = {
    0x13000624: "bhvWFBreakableWallRight",
    0x401700: "RM_Scroll_Texture",
    0x400000: "RM_Scroll_Texture",
    0x402300: "editor_Scroll_Texture",
    0x13003420: "editor_Scroll_Texture2",
}

CUSTOM_BEHAVIOR_HASHES = {
    "383604deda1acda4": "bhvBobombBuddyOpensCannon",
    "31eb59c129ad6852": "bhvHiddenStar",
    "4051cdddcc5b89e0": "bhvExitPodiumWarp",
    "c6ee412250536b1e": "bhvToadMessage",
    "9964b9b7c56cd32e": "bhvBobombBuddy",
    "bd4934039dac8392": "bhvMessagePanel",
    "ed126593eae1c2f3": "bhvWFSolidTowerPlatform",
}

BEHAVIOR_COLLISION_HINTS = {
    "536e016d5d45dbe8": {
        0x0700FC0C: "bhvWFBreakableWallRight",
    },
}

OBJECT_FIELDS = {
    1: "oFlags",
    2: "oDialogState",
    3: "oUnk94",
    5: "oIntangibleTimer",
    6: "oPosX",
    7: "oPosY",
    8: "oPosZ",
    9: "oVelX",
    10: "oVelY",
    11: "oVelZ",
    12: "oForwardVelS32",
    13: "oLeftVel",
    14: "oUpVel",
    21: "oGraphYOffset",
    22: "oActiveParticleFlags",
    23: "oGravity",
    24: "oFloorHeight",
    25: "oMoveFlags",
    26: "oAnimState",
    35: "oAngleVelPitch",
    36: "oAngleVelYaw",
    37: "oAngleVelRoll",
    38: "oAnimations",
    39: "oHeldState",
    40: "oWallHitboxRadius",
    41: "oDragStrength",
    42: "oInteractType",
    43: "oInteractStatus",
    44: "oParentRelativePosX",
    45: "oParentRelativePosY",
    46: "oParentRelativePosZ",
    47: "oBhvParams2ndByte",
    49: "oAction",
    50: "oSubAction",
    51: "oTimer",
    52: "oBounciness",
    53: "oDistanceToMario",
    54: "oAngleToMario",
    55: "oHomeX",
    56: "oHomeY",
    57: "oHomeZ",
    58: "oFriction",
    59: "oBuoyancy",
    60: "oSoundStateID",
    61: "oOpacity",
    62: "oDamageOrCoinValue",
    63: "oHealth",
    64: "oBhvParams",
    65: "oPrevAction",
    66: "oInteractionSubtype",
    67: "oCollisionDistance",
    68: "oNumLootCoins",
    69: "oDrawingDistance",
    70: "oRoom",
    72: "oUnusedBhvParams",
    75: "oWallAngle",
    76: "oFloorRoom",
    77: "oAngleToHome",
    78: "oFloor",
    79: "oDeathSound",
    29: "oYoshiChosenHome",
    30: "oYoshiTargetYaw",
    31: "oWoodenPostOffsetY",
    32: "oWigglerTimeUntilRandomTurn",
    33: "oWigglerTargetYaw",
    34: "oWigglerWalkAwayFromWallTimer",
    27: "oYoshiBlinkTimer",
    28: "oWoodenPostPrevAngleToMario",
    0: "oUkikiCageNextAction",
    74: "oUnagiUnk1B2",
    73: "oWigglerTextStatus",
}


def get_field_name(field_offset: int) -> str:
    return OBJECT_FIELDS.get(field_offset, f"0x{field_offset:02X}")


# --- Structural Hashing ---
def _build_structural_repr(
    commands_data: List[Tuple[int, int, List[int]]],
    call_native_mode: str = "resolve",
    script_start: int = 0,
    jump_mode: str = "precise",
) -> str:
    structural_repr = []
    current_seg = (script_start >> 24) & 0xFF

    for opcode, size, words in commands_data:
        parts = [f"{opcode:02X}"]

        if opcode == 0x00:  # BEGIN
            parts.append(f"{(words[0] >> 16) & 0xFF:02X}")
        elif opcode == 0x01:  # DELAY
            parts.append(f"{words[0] & 0xFFFF:04X}")
        elif opcode == 0x02 or opcode == 0x04:  # CALL or GOTO
            target = words[1]
            target_seg = (target >> 24) & 0xFF
            if jump_mode == "normalized":
                if target_seg == current_seg and script_start != 0:
                    parts.append(f"REL:{target - script_start:08X}")
                else:
                    parts.append(f"SEG:{target_seg:02X}")
            else:
                parts.append(f"{target:08X}")
        elif opcode == 0x0C:  # CALL_NATIVE
            vram_addr = words[1] if len(words) >= 2 else 0
            if call_native_mode == "anonymous":
                # Always anonymous — for cross-ROM structural comparison
                parts.append("UNKNOWN")
            else:
                func_name = resolve_call_native(vram_addr)
                if func_name:
                    parts.append(func_name)
                elif call_native_mode == "fuzzy":
                    parts.append("UNKNOWN")
                else:
                    parts.append(f"{vram_addr:08X}")
        elif opcode in [0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12]:  # Fields
            parts.append(f"{(words[0] >> 16) & 0xFF:02X}:{words[0] & 0xFFFF:04X}")
        elif opcode == 0x1B:  # SET_MODEL
            parts.append(f"{words[0] & 0xFFFF:04X}")
        elif opcode == 0x1C:  # SPAWN_CHILD
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x23:  # SET_HITBOX
            if len(words) >= 2:
                parts.append(f"{words[1]:08X}")
        elif opcode == 0x29:  # SPAWN_CHILD_WITH_PARAM
            parts.append(f"{words[0] & 0xFFFF:04X}:{words[1]:08X}")
        elif opcode == 0x2C:  # SPAWN_OBJ
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x2F:  # SET_INTERACT_TYPE
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x31:  # SET_INTERACT_SUBTYPE
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x32:  # SCALE
            parts.append(f"{(words[0] >> 16) & 0xFF:02X}:{words[0] & 0xFFFF:04X}")

        structural_repr.append("-".join(parts))

    return "|".join(structural_repr)


def structural_hash_behavior(commands_data, script_start=0):
    structure = _build_structural_repr(
        commands_data,
        call_native_mode="resolve",
        script_start=script_start,
        jump_mode="precise",
    )
    return hashlib.sha256(structure.encode("utf-8")).hexdigest()[:16]


def structural_hash_behavior_fuzzy(commands_data, script_start=0):
    structure = _build_structural_repr(
        commands_data,
        call_native_mode="fuzzy",
        script_start=script_start,
        jump_mode="normalized",
    )
    return hashlib.sha256(structure.encode("utf-8")).hexdigest()[:16]


def structural_hash_behavior_anonymous(commands_data, script_start=0):
    """Hash with ALL CALL_NATIVE entries as UNKNOWN and normalized jumps.

    This produces an identical hash whether or not the function matcher
    can resolve C function pointers — essential for matching behaviours
    in ROMhacks where the code segment has been relocated.
    """
    structure = _build_structural_repr(
        commands_data,
        call_native_mode="anonymous",
        script_start=script_start,
        jump_mode="normalized",
    )
    return hashlib.sha256(structure.encode("utf-8")).hexdigest()[:16]


# --- Behavior Command Handlers ---


def parse_BEGIN(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    obj_list = (cmd[0] >> 16) & 0xFF
    names = {
        0: "OBJ_LIST_PLAYER",
        1: "OBJ_LIST_UNUSED_1",
        2: "OBJ_LIST_DESTRUCTIVE",
        3: "OBJ_LIST_UNUSED_3",
        4: "OBJ_LIST_GENACTOR",
        5: "OBJ_LIST_PUSHABLE",
        6: "OBJ_LIST_LEVEL",
        7: "OBJ_LIST_UNUSED_7",
        8: "OBJ_LIST_DEFAULT",
        9: "OBJ_LIST_SURFACE",
        10: "OBJ_LIST_POLELIKE",
        11: "OBJ_LIST_SPAWNER",
        12: "OBJ_LIST_UNIMPORTANT",
    }
    name = names.get(obj_list, str(obj_list))
    return CommandIR(0x00, [name], name="BEGIN"), False


def parse_DELAY(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x01, [cmd[0] & 0xFFFF], name="DELAY"), False


def parse_CALL(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    bhv_rec = get_behavior_processor().parse(cmd[1], txt=sTxt)
    return CommandIR(0x02, [bhv_rec], name="CALL"), False


def parse_RETURN(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x03, [], name="RETURN"), True


def parse_GOTO(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    bhv_rec = get_behavior_processor().parse(cmd[1], txt=sTxt)
    return CommandIR(0x04, [bhv_rec], name="GOTO"), True


def parse_BEGIN_REPEAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x05, [cmd[0] & 0xFFFF], name="BEGIN_REPEAT"), False


def parse_END_REPEAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x06, [], name="END_REPEAT"), False


def parse_END_REPEAT_CONTINUE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x07, [], name="END_REPEAT_CONTINUE"), False


def parse_BEGIN_LOOP(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x08, [], name="BEGIN_LOOP"), False


def parse_END_LOOP(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x09, [], name="END_LOOP"), True


def parse_BREAK(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x0A, [], name="BREAK"), True


def parse_BREAK_UNUSED(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x0B, [], name="BREAK_UNUSED"), True


def parse_CALL_NATIVE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    func_name = resolve_call_native(cmd[1]) or "NULL"
    return CommandIR(0x0C, [func_name], name="CALL_NATIVE"), False


def parse_ADD_FLOAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x0D, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF], name="ADD_FLOAT"),
        False,
    )


def parse_SET_FLOAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x0E, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF], name="SET_FLOAT"),
        False,
    )


def parse_ADD_INT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    val = to_signed16(cmd[0] & 0xFFFF)
    return (
        CommandIR(0x0F, [get_field_name((cmd[0] >> 16) & 0xFF), val], name="ADD_INT"),
        False,
    )


def parse_SET_INT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    val = to_signed16(cmd[0] & 0xFFFF)
    return (
        CommandIR(0x10, [get_field_name((cmd[0] >> 16) & 0xFF), val], name="SET_INT"),
        False,
    )


def parse_OR_INT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x11,
            [get_field_name((cmd[0] >> 16) & 0xFF), f"0x{cmd[0] & 0xFFFF:04X}"],
            name="OR_INT",
        ),
        False,
    )


def parse_BIT_CLEAR(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x12,
            [get_field_name((cmd[0] >> 16) & 0xFF), f"0x{cmd[0] & 0xFFFF:04X}"],
            name="BIT_CLEAR",
        ),
        False,
    )


def parse_SET_INT_RAND_RSHIFT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x13,
            [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF, (cmd[1] >> 16) & 0xFFFF],
            name="SET_INT_RAND_RSHIFT",
        ),
        False,
    )


def parse_SET_RANDOM_FLOAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x14,
            [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF, (cmd[1] >> 16) & 0xFFFF],
            name="SET_RANDOM_FLOAT",
        ),
        False,
    )


def parse_SET_RANDOM_INT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x15,
            [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF, (cmd[1] >> 16) & 0xFFFF],
            name="SET_RANDOM_INT",
        ),
        False,
    )


def parse_ADD_RANDOM_FLOAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x16,
            [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF, (cmd[1] >> 16) & 0xFFFF],
            name="ADD_RANDOM_FLOAT",
        ),
        False,
    )


def parse_ADD_INT_RAND_RSHIFT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x17,
            [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF, (cmd[1] >> 16) & 0xFFFF],
            name="ADD_INT_RAND_RSHIFT",
        ),
        False,
    )


def parse_CMD_NOP_1(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x18, [get_field_name((cmd[0] >> 16) & 0xFF)], name="CMD_NOP_1"), False


def parse_CMD_NOP_2(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x19, [get_field_name((cmd[0] >> 16) & 0xFF)], name="CMD_NOP_2"), False


def parse_CMD_NOP_3(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x1A, [get_field_name((cmd[0] >> 16) & 0xFF)], name="CMD_NOP_3"), False


def parse_SET_MODEL(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x1B, [f"0x{cmd[0] & 0xFFFF:02X}"], name="SET_MODEL"), False


def parse_SPAWN_CHILD(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    bhv_rec = get_behavior_processor().parse(cmd[2], txt=sTxt)
    return CommandIR(0x1C, [f"0x{cmd[1]:02X}", bhv_rec], name="SPAWN_CHILD"), False


def parse_DEACTIVATE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x1D, [], name="DEACTIVATE"), True


def parse_DROP_TO_FLOOR(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x1E, [], name="DROP_TO_FLOOR"), False


def parse_SUM_FLOAT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x1F,
            [
                get_field_name((cmd[0] >> 16) & 0xFF),
                get_field_name((cmd[0] >> 8) & 0xFF),
                get_field_name(cmd[0] & 0xFF),
            ],
            name="SUM_FLOAT",
        ),
        False,
    )


def parse_SUM_INT(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x20,
            [
                get_field_name((cmd[0] >> 16) & 0xFF),
                get_field_name((cmd[0] >> 8) & 0xFF),
                get_field_name(cmd[0] & 0xFF),
            ],
            name="SUM_INT",
        ),
        False,
    )


def parse_BILLBOARD(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x21, [], name="BILLBOARD"), False


def parse_HIDE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x22, [], name="HIDE"), False


def parse_SET_HITBOX(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x23, [(cmd[1] >> 16) & 0xFFFF, cmd[1] & 0xFFFF], name="SET_HITBOX"),
        False,
    )


def parse_CMD_NOP_4(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x24, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF], name="CMD_NOP_4"),
        False,
    )


def parse_DELAY_VAR(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x25, [get_field_name((cmd[0] >> 16) & 0xFF)], name="DELAY_VAR"), False


def parse_BEGIN_REPEAT_UNUSED(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x26, [(cmd[0] >> 16) & 0xFF], name="BEGIN_REPEAT_UNUSED"), False


def parse_LOAD_ANIMATIONS(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x27, [get_field_name((cmd[0] >> 16) & 0xFF), f"0x{cmd[1]:08X}"], name="LOAD_ANIMATIONS"
        ),
        False,
    )


def parse_ANIMATE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x28, [(cmd[0] >> 16) & 0xFF], name="ANIMATE"), False


def parse_SPAWN_CHILD_WITH_PARAM(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    bhv_rec = get_behavior_processor().parse(cmd[2], txt=sTxt)
    return (
        CommandIR(
            0x29, [cmd[0] & 0xFFFF, f"0x{cmd[1]:02X}", bhv_rec], name="SPAWN_CHILD_WITH_PARAM"
        ),
        False,
    )


def parse_LOAD_COLLISION_DATA(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x2A, [f"0x{cmd[1]:08X}"], name="LOAD_COLLISION_DATA"), False


def parse_SET_HITBOX_WITH_OFFSET(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x2B,
            [(cmd[1] >> 16) & 0xFFFF, cmd[1] & 0xFFFF, to_signed16((cmd[2] >> 16) & 0xFFFF)],
            name="SET_HITBOX_WITH_OFFSET",
        ),
        False,
    )


def parse_SPAWN_OBJ(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    bhv_rec = get_behavior_processor().parse(cmd[2], txt=sTxt)
    return CommandIR(0x2C, [f"0x{cmd[1]:02X}", bhv_rec], name="SPAWN_OBJ"), False


def parse_SET_HOME(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x2D, [], name="SET_HOME"), False


def parse_SET_HURTBOX(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x2E, [(cmd[1] >> 16) & 0xFFFF, cmd[1] & 0xFFFF], name="SET_HURTBOX"),
        False,
    )


def parse_SET_INTERACT_TYPE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x2F, [f"0x{cmd[1]:08X}"], name="SET_INTERACT_TYPE"), False


def parse_SET_OBJ_PHYSICS(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    p = [
        (cmd[1] >> 16) & 0xFFFF,
        to_signed16(cmd[1] & 0xFFFF),
        to_signed16((cmd[2] >> 16) & 0xFFFF),
        to_signed16(cmd[2] & 0xFFFF),
        to_signed16((cmd[3] >> 16) & 0xFFFF),
        to_signed16(cmd[3] & 0xFFFF),
        (cmd[4] >> 16) & 0xFFFF,
        cmd[4] & 0xFFFF,
    ]
    return CommandIR(0x30, p, name="SET_OBJ_PHYSICS"), False


def parse_SET_INTERACT_SUBTYPE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x31, [f"0x{cmd[1]:08X}"], name="SET_INTERACT_SUBTYPE"), False


def parse_SCALE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(0x32, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF], name="SCALE"),
        False,
    )


def parse_PARENT_BIT_CLEAR(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x33,
            [get_field_name((cmd[0] >> 16) & 0xFF), f"0x{cmd[1]:08X}"],
            name="PARENT_BIT_CLEAR",
        ),
        False,
    )


def parse_ANIMATE_TEXTURE(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x34, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[0] & 0xFFFF], name="ANIMATE_TEXTURE"
        ),
        False,
    )


def parse_DISABLE_RENDERING(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x35, [], name="DISABLE_RENDERING"), False


def parse_SET_INT_UNUSED(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return (
        CommandIR(
            0x36, [get_field_name((cmd[0] >> 16) & 0xFF), cmd[1] & 0xFFFF], name="SET_INT_UNUSED"
        ),
        False,
    )


def parse_SPAWN_WATER_DROPLET(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x37, [f"0x{cmd[1]:08X}"], name="SPAWN_WATER_DROPLET"), False


def parse_CMD_3B(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x3B, [f"0x{cmd[0] & 0x00FFFFFF:06X}"], name="CMD_3B"), True


def parse_CMD_57(cmd: List[int], sTxt: Any) -> Tuple[CommandIR, bool]:
    return CommandIR(0x57, [f"0x{cmd[0] & 0x00FFFFFF:06X}"], name="CMD_57"), True


BEHAVIOR_COMMANDS: Dict[int, Dict[str, Any]] = {
    0x00: {"name": "BEGIN", "func": parse_BEGIN, "size": 1},
    0x01: {"name": "DELAY", "func": parse_DELAY, "size": 1},
    0x02: {"name": "CALL", "func": parse_CALL, "size": 2},
    0x03: {"name": "RETURN", "func": parse_RETURN, "size": 1},
    0x04: {"name": "GOTO", "func": parse_GOTO, "size": 2},
    0x05: {"name": "BEGIN_REPEAT", "func": parse_BEGIN_REPEAT, "size": 1},
    0x06: {"name": "END_REPEAT", "func": parse_END_REPEAT, "size": 1},
    0x07: {"name": "END_REPEAT_CONTINUE", "func": parse_END_REPEAT_CONTINUE, "size": 1},
    0x08: {"name": "BEGIN_LOOP", "func": parse_BEGIN_LOOP, "size": 1},
    0x09: {"name": "END_LOOP", "func": parse_END_LOOP, "size": 1},
    0x0A: {"name": "BREAK", "func": parse_BREAK, "size": 1},
    0x0B: {"name": "BREAK_UNUSED", "func": parse_BREAK_UNUSED, "size": 1},
    0x0C: {"name": "CALL_NATIVE", "func": parse_CALL_NATIVE, "size": 2},
    0x0D: {"name": "ADD_FLOAT", "func": parse_ADD_FLOAT, "size": 1},
    0x0E: {"name": "SET_FLOAT", "func": parse_SET_FLOAT, "size": 1},
    0x0F: {"name": "ADD_INT", "func": parse_ADD_INT, "size": 1},
    0x10: {"name": "SET_INT", "func": parse_SET_INT, "size": 1},
    0x11: {"name": "OR_INT", "func": parse_OR_INT, "size": 1},
    0x12: {"name": "BIT_CLEAR", "func": parse_BIT_CLEAR, "size": 1},
    0x13: {"name": "SET_INT_RAND_RSHIFT", "func": parse_SET_INT_RAND_RSHIFT, "size": 2},
    0x14: {"name": "SET_RANDOM_FLOAT", "func": parse_SET_RANDOM_FLOAT, "size": 2},
    0x15: {"name": "SET_RANDOM_INT", "func": parse_SET_RANDOM_INT, "size": 2},
    0x16: {"name": "ADD_RANDOM_FLOAT", "func": parse_ADD_RANDOM_FLOAT, "size": 2},
    0x17: {"name": "ADD_INT_RAND_RSHIFT", "func": parse_ADD_INT_RAND_RSHIFT, "size": 2},
    0x18: {"name": "CMD_NOP_1", "func": parse_CMD_NOP_1, "size": 1},
    0x19: {"name": "CMD_NOP_2", "func": parse_CMD_NOP_2, "size": 1},
    0x1A: {"name": "CMD_NOP_3", "func": parse_CMD_NOP_3, "size": 1},
    0x1B: {"name": "SET_MODEL", "func": parse_SET_MODEL, "size": 1},
    0x1C: {"name": "SPAWN_CHILD", "func": parse_SPAWN_CHILD, "size": 3},
    0x1D: {"name": "DEACTIVATE", "func": parse_DEACTIVATE, "size": 1},
    0x1E: {"name": "DROP_TO_FLOOR", "func": parse_DROP_TO_FLOOR, "size": 1},
    0x1F: {"name": "SUM_FLOAT", "func": parse_SUM_FLOAT, "size": 1},
    0x20: {"name": "SUM_INT", "func": parse_SUM_INT, "size": 1},
    0x21: {"name": "BILLBOARD", "func": parse_BILLBOARD, "size": 1},
    0x22: {"name": "HIDE", "func": parse_HIDE, "size": 1},
    0x23: {"name": "SET_HITBOX", "func": parse_SET_HITBOX, "size": 2},
    0x24: {"name": "CMD_NOP_4", "func": parse_CMD_NOP_4, "size": 1},
    0x25: {"name": "DELAY_VAR", "func": parse_DELAY_VAR, "size": 1},
    0x26: {"name": "BEGIN_REPEAT_UNUSED", "func": parse_BEGIN_REPEAT_UNUSED, "size": 1},
    0x27: {"name": "LOAD_ANIMATIONS", "func": parse_LOAD_ANIMATIONS, "size": 2},
    0x28: {"name": "ANIMATE", "func": parse_ANIMATE, "size": 1},
    0x29: {"name": "SPAWN_CHILD_WITH_PARAM", "func": parse_SPAWN_CHILD_WITH_PARAM, "size": 3},
    0x2A: {"name": "LOAD_COLLISION_DATA", "func": parse_LOAD_COLLISION_DATA, "size": 2},
    0x2B: {"name": "SET_HITBOX_WITH_OFFSET", "func": parse_SET_HITBOX_WITH_OFFSET, "size": 3},
    0x2C: {"name": "SPAWN_OBJ", "func": parse_SPAWN_OBJ, "size": 3},
    0x2D: {"name": "SET_HOME", "func": parse_SET_HOME, "size": 1},
    0x2E: {"name": "SET_HURTBOX", "func": parse_SET_HURTBOX, "size": 2},
    0x2F: {"name": "SET_INTERACT_TYPE", "func": parse_SET_INTERACT_TYPE, "size": 2},
    0x30: {"name": "SET_OBJ_PHYSICS", "func": parse_SET_OBJ_PHYSICS, "size": 5},
    0x31: {"name": "SET_INTERACT_SUBTYPE", "func": parse_SET_INTERACT_SUBTYPE, "size": 2},
    0x32: {"name": "SCALE", "func": parse_SCALE, "size": 1},
    0x33: {"name": "PARENT_BIT_CLEAR", "func": parse_PARENT_BIT_CLEAR, "size": 2},
    0x34: {"name": "ANIMATE_TEXTURE", "func": parse_ANIMATE_TEXTURE, "size": 1},
    0x35: {"name": "DISABLE_RENDERING", "func": parse_DISABLE_RENDERING, "size": 1},
    0x36: {"name": "SET_INT_UNUSED", "func": parse_SET_INT_UNUSED, "size": 2},
    0x37: {"name": "SPAWN_WATER_DROPLET", "func": parse_SPAWN_WATER_DROPLET, "size": 2},
    0x3B: {"name": "CMD_3B", "func": parse_CMD_3B, "size": 1},
    0x57: {"name": "CMD_57", "func": parse_CMD_57, "size": 1},
}


# --- BehaviorProcessor ---


class BehaviorProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)

    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[BehaviorRecord]:
        sTxt = kwargs.get("txt")
        if not segmented_addr:
            return None

        seg_num = segment_from_addr(segmented_addr)
        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            debug_fail(f"Failed to find segment {seg_num} for behavior at 0x{segmented_addr:08x}")
            return None

        start, end = segment_info
        db_key = (segmented_addr, start)

        # Check database for already assigned name
        if self.ctx.db and db_key in self.ctx.db.behaviors:
            return self.ctx.db.behaviors[db_key]

        data = get_segment(seg_num)
        if data is None:
            debug_fail(f"Failed to load segment {seg_num} for behavior at 0x{segmented_addr:08x}")
            return None

        rom = CustomBytesIO(data)
        rom.seek(offset_from_segment_addr(segmented_addr))

        commands_ir = []
        commands_data = []
        found_end = False
        while not found_end:
            try:
                pos = rom.tell()
                w0 = rom.read_u32()
                opcode = (w0 >> 24) & 0xFF
                if opcode not in BEHAVIOR_COMMANDS:
                    break

                info = BEHAVIOR_COMMANDS[opcode]
                size_words = info["size"]
                words = [w0]
                for _ in range(size_words - 1):
                    words.append(rom.read_u32())

                commands_data.append((opcode, size_words * 4, words))
                ir, is_end = info["func"](words, sTxt)
                ir.address = segmented_addr + pos - offset_from_segment_addr(segmented_addr)
                commands_ir.append(ir)
                if is_end:
                    found_end = True
            except Exception:
                break

        prec_hash = structural_hash_behavior(commands_data, script_start=segmented_addr)
        fuzzy_hash = structural_hash_behavior_fuzzy(commands_data, script_start=segmented_addr)
        anon_hash = structural_hash_behavior_anonymous(commands_data, script_start=segmented_addr)

        name = f"bhv_unknown_{segmented_addr:08X}"
        known_name = None
        if segmented_addr in BEHAVIOR_ADDR_OVERRIDES:
            known_name = BEHAVIOR_ADDR_OVERRIDES[segmented_addr]
        elif prec_hash in CUSTOM_BEHAVIOR_HASHES:
            known_name = CUSTOM_BEHAVIOR_HASHES[prec_hash]
        elif prec_hash in KNOWN_BEHAVIOR_HASHES:
            known_name = KNOWN_BEHAVIOR_HASHES[prec_hash]
        elif fuzzy_hash in CUSTOM_BEHAVIOR_HASHES:
            known_name = CUSTOM_BEHAVIOR_HASHES[fuzzy_hash]
        elif fuzzy_hash in KNOWN_BEHAVIOR_HASHES:
            known_name = KNOWN_BEHAVIOR_HASHES[fuzzy_hash]
        elif anon_hash in CUSTOM_BEHAVIOR_HASHES:
            known_name = CUSTOM_BEHAVIOR_HASHES[anon_hash]
        elif anon_hash in KNOWN_BEHAVIOR_HASHES:
            known_name = KNOWN_BEHAVIOR_HASHES[anon_hash]

        if known_name and not (
            known_name.startswith("bhv_unknown") or "_bhv_unknown_" in known_name
        ):
            name = known_name

        if self.ctx.db is None:
            debug_fail(f"Failed to find database for behavior at 0x{segmented_addr:08x}")
            return None

        record = BehaviorRecord(
            seg_addr=segmented_addr,
            beh_name=name,
            hash=prec_hash,
            fuzzy_hash=fuzzy_hash,
            anon_hash=anon_hash,
            commands=commands_ir,
        )
        self.ctx.db.behaviors[db_key] = record
        self.ctx.db.set_symbol(segmented_addr, name, "Behavior")

        return record

    def serialize(self, record: BehaviorRecord) -> str:
        output = f"const BehaviorScript {record.beh_name}[] = " + "{\n"
        for ir in record.commands:
            params_str = ", ".join(map(str, ir.params))
            output += f"    {ir.name}({params_str}),\n"
        output += "};\n"
        if self.ctx.txt:
            self.ctx.txt.write(self.ctx, "behavior", record.beh_name, output)
        return output


_beh_processor = None


def get_behavior_processor():
    global _beh_processor
    if _beh_processor is None:
        _beh_processor = BehaviorProcessor(ctx)
    return _beh_processor


# --- shims ---
def parse_behavior_script(addr, txt, context_prefix=None):
    p = get_behavior_processor()
    res = p.parse(addr, txt=txt, context_prefix=context_prefix)

    beh_name = str(res)
    beh_hash = ""
    if hasattr(res, "hash"):
        beh_hash = res.hash
    return beh_name, beh_hash


def parse_behavior(rom_or_addr, sTxt, segmented_addr=None):
    addr = segmented_addr if segmented_addr is not None else rom_or_addr
    name, _ = parse_behavior_script(addr, sTxt)
    return name
