#!/usr/bin/env python3
import ast
import hashlib
import re
import sys
from pathlib import Path
from typing import Optional

FIELD_NAME_TO_INDEX: dict[str, int] = {}

CMD_INFO = {
    0x00: ("BEGIN", 1),
    0x01: ("DELAY", 1),
    0x02: ("CALL", 2),
    0x03: ("RETURN", 1),
    0x04: ("GOTO", 2),
    0x05: ("BEGIN_REPEAT", 1),
    0x06: ("END_REPEAT", 1),
    0x07: ("END_REPEAT_CONTINUE", 1),
    0x08: ("BEGIN_LOOP", 1),
    0x09: ("END_LOOP", 1),
    0x0A: ("BREAK", 1),
    0x0B: ("BREAK_UNUSED", 1),
    0x0C: ("CALL_NATIVE", 2),
    0x0D: ("ADD_FLOAT", 1),
    0x0E: ("SET_FLOAT", 1),
    0x0F: ("ADD_INT", 1),
    0x10: ("SET_INT", 1),
    0x11: ("OR_INT", 1),
    0x12: ("BIT_CLEAR", 1),
    0x13: ("SET_INT_RAND_RSHIFT", 2),
    0x14: ("SET_RANDOM_FLOAT", 2),
    0x15: ("SET_RANDOM_INT", 2),
    0x16: ("ADD_RANDOM_FLOAT", 2),
    0x17: ("ADD_INT_RAND_RSHIFT", 2),
    0x18: ("CMD_NOP_1", 1),
    0x19: ("CMD_NOP_2", 1),
    0x1A: ("CMD_NOP_3", 1),
    0x1B: ("SET_MODEL", 1),
    0x1C: ("SPAWN_CHILD", 3),
    0x1D: ("DEACTIVATE", 1),
    0x1E: ("DROP_TO_FLOOR", 1),
    0x1F: ("SUM_FLOAT", 1),
    0x20: ("SUM_INT", 1),
    0x21: ("BILLBOARD", 1),
    0x22: ("HIDE", 1),
    0x23: ("SET_HITBOX", 2),
    0x24: ("CMD_NOP_4", 1),
    0x25: ("DELAY_VAR", 1),
    0x26: ("BEGIN_REPEAT_UNUSED", 1),
    0x27: ("LOAD_ANIMATIONS", 2),
    0x28: ("ANIMATE", 1),
    0x29: ("SPAWN_CHILD_WITH_PARAM", 3),
    0x2A: ("LOAD_COLLISION_DATA", 2),
    0x2B: ("SET_HITBOX_WITH_OFFSET", 3),
    0x2C: ("SPAWN_OBJ", 3),
    0x2D: ("SET_HOME", 1),
    0x2E: ("SET_HURTBOX", 2),
    0x2F: ("SET_INTERACT_TYPE", 2),
    0x30: ("SET_OBJ_PHYSICS", 5),
    0x31: ("SET_INTERACT_SUBTYPE", 2),
    0x32: ("SCALE", 1),
    0x33: ("PARENT_BIT_CLEAR", 2),
    0x34: ("ANIMATE_TEXTURE", 1),
    0x35: ("DISABLE_RENDERING", 1),
    0x36: ("SET_INT_UNUSED", 2),
    0x37: ("SPAWN_WATER_DROPLET", 2),
}

CMD_NAME_TO_OPCODE = {name: opcode for opcode, (name, _) in CMD_INFO.items()}


def load_object_field_indices(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    # Capture the expression inside OBJECT_FIELD_*() even when it references
    # earlier macros (e.g. O_MOVE_ANGLE_YAW_INDEX).
    field_re = re.compile(
        r"#define\s+/\*0x[0-9A-Fa-f]+\*/\s+(o[A-Za-z0-9_]+)\s+OBJECT_FIELD_[A-Za-z0-9_]+\(([^)]+)\)"
    )
    constants = load_constant_defines([path])
    mapping: dict[str, int] = {}
    for line in path.read_text().splitlines():
        m = field_re.search(line)
        if not m:
            continue
        name = m.group(1)
        idx_str = m.group(2)
        idx = parse_number(idx_str, constants)
        if idx is None:
            continue
        mapping[name] = idx
    return mapping


def safe_eval_expr(expr: str, constants: dict) -> Optional[int]:
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None

    def _eval(n):
        if isinstance(n, ast.Constant):
            return int(n.value) if isinstance(n.value, (int, float, str)) else None
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub, ast.Invert)):
            val = _eval(n.operand)
            if val is None:
                return None
            if isinstance(n.op, ast.UAdd):
                return +val
            if isinstance(n.op, ast.USub):
                return -val
            return ~val
        if isinstance(n, ast.BinOp) and isinstance(
            n.op,
            (ast.Add, ast.Sub, ast.Mult, ast.BitOr, ast.BitAnd, ast.BitXor, ast.LShift, ast.RShift),
        ):
            left_val = _eval(n.left)
            right_val = _eval(n.right)
            if left_val is None or right_val is None:
                return None
            if isinstance(n.op, ast.Add):
                return left_val + right_val
            if isinstance(n.op, ast.Sub):
                return left_val - right_val
            if isinstance(n.op, ast.Mult):
                return left_val * right_val
            if isinstance(n.op, ast.BitOr):
                return left_val | right_val
            if isinstance(n.op, ast.BitAnd):
                return left_val & right_val
            if isinstance(n.op, ast.BitXor):
                return left_val ^ right_val
            if isinstance(n.op, ast.LShift):
                return left_val << right_val
            return left_val >> right_val
        if isinstance(n, ast.Name):
            return constants.get(n.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            func_name = n.func.id
            if func_name.startswith("BPARAM") and len(n.args) == 1:
                arg_val = _eval(n.args[0])
                if arg_val is None:
                    return None
                byte = arg_val & 0xFF
                shift = {"BPARAM1": 24, "BPARAM2": 16, "BPARAM3": 8, "BPARAM4": 0}.get(func_name)
                if shift is None:
                    return None
                return byte << shift
        return None

    return _eval(node)


def load_constant_defines(paths: list[Path]) -> dict[str, int]:
    constants: dict[str, int] = {}
    define_re = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$")

    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            # Strip inline block and line comments so expressions can be evaluated.
            line = re.sub(r"/\*.*?\*/", "", line)
            line = line.split("//")[0]
            m = define_re.match(line)
            if not m:
                continue
            name, value_str = m.group(1), m.group(2).strip()
            # Skip macros with parameters
            if "(" in name:
                continue
            # Skip empty/complex macro bodies
            if value_str.startswith("(") and ")" in value_str and "," in value_str:
                continue
            val = safe_eval_expr(value_str, constants)
            if val is None:
                value_no_suffix = value_str.rstrip("uUlLfF")
                if value_no_suffix != value_str:
                    val = safe_eval_expr(value_no_suffix, constants)
            if val is not None:
                constants[name] = val
    return constants


def parse_number(token: str, constants: dict[str, int]) -> Optional[int]:
    token = token.strip()
    # Trim braces/extra characters
    if token.startswith("(") and token.endswith(")"):
        token = token[1:-1].strip()

    if token in FIELD_NAME_TO_INDEX:
        return FIELD_NAME_TO_INDEX[token]
    if token in constants:
        return constants[token]
    try:
        return int(token, 0)
    except ValueError:
        # Strip trailing type suffixes (u/U/l/L/f/F) after a failed parse
        token_no_suffix = token.rstrip("fFuUlL")
        if token_no_suffix != token:
            try:
                return int(token_no_suffix, 0)
            except ValueError:
                pass
    return safe_eval_expr(token, constants)


def structural_hash_behavior(commands_data, func_names=None):
    """Hash behavior structure including CALL_NATIVE function names.

    Args:
        commands_data: List of (opcode, size, words) tuples.
        func_names: Optional parallel list of function name strings for
                    CALL_NATIVE commands (None entries for non-CALL_NATIVE).
                    When running from C source, these come from the macro args.
                    When running from ROM, they come from FunctionMatcher.
    """
    structural_repr = []

    for idx, (opcode, size, words) in enumerate(commands_data):
        parts = [f"{opcode:02X}"]

        if opcode == 0x00:  # BEGIN
            parts.append(f"{(words[0] >> 16) & 0xFF:02X}")
        elif opcode == 0x01:  # DELAY
            parts.append(f"{words[0] & 0xFFFF:04X}")
        elif opcode == 0x0C:  # CALL_NATIVE - include function name
            fn = None
            if func_names and idx < len(func_names):
                fn = func_names[idx]
            if fn:
                parts.append(fn)
            else:
                # Fallback: raw address (or 0 if unavailable)
                vram = words[1] if size >= 2 else 0
                parts.append(f"{vram:08X}")
        elif opcode in [0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12]:
            field = (words[0] >> 16) & 0xFF
            value = words[0] & 0xFFFF
            parts.append(f"{field:02X}:{value:04X}")
        elif opcode in [0x13, 0x17]:  # SET_INT_RAND_RSHIFT, ADD_INT_RAND_RSHIFT
            field = (words[0] >> 16) & 0xFF
            min_val = words[0] & 0xFFFF
            rshift = (words[1] >> 16) & 0xFFFF
            parts.append(f"{field:02X}:{min_val:04X}:{rshift:04X}")
        elif opcode in [0x14, 0x15, 0x16]:  # SET_RANDOM_FLOAT/INT, ADD_RANDOM_FLOAT
            field = (words[0] >> 16) & 0xFF
            min_val = words[0] & 0xFFFF
            range_val = (words[1] >> 16) & 0xFFFF
            parts.append(f"{field:02X}:{min_val:04X}:{range_val:04X}")
        elif opcode == 0x1B:  # SET_MODEL
            parts.append(f"{words[0] & 0xFFFF:04X}")
        elif opcode == 0x1C:  # SPAWN_CHILD
            modelID = words[1]
            parts.append(f"{modelID:08X}")
        elif opcode == 0x23:  # SET_HITBOX
            if size >= 2:
                parts.append(f"{words[1]:08X}")
        elif opcode == 0x27:  # LOAD_ANIMATIONS
            field = (words[0] >> 16) & 0xFF
            parts.append(f"{field:02X}")
        elif opcode == 0x28:  # ANIMATE
            animIndex = (words[0] >> 16) & 0xFF
            parts.append(f"{animIndex:02X}")
        elif opcode == 0x29:  # SPAWN_CHILD_WITH_PARAM
            bhvParam = words[0] & 0xFFFF
            modelID = words[1]
            parts.append(f"{bhvParam:04X}:{modelID:08X}")
        elif opcode == 0x2A:  # LOAD_COLLISION_DATA
            # Address is not cross-ROM stable, just include opcode
            pass
        elif opcode == 0x2B:  # SET_HITBOX_WITH_OFFSET
            if size >= 3:
                parts.append(f"{words[1]:08X}:{words[2]:08X}")
        elif opcode == 0x2C:  # SPAWN_OBJ
            modelID = words[1]
            parts.append(f"{modelID:08X}")
        elif opcode == 0x2E:  # SET_HURTBOX
            if size >= 2:
                parts.append(f"{words[1]:08X}")
        elif opcode == 0x2F:  # SET_INTERACT_TYPE
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x31:  # SET_INTERACT_SUBTYPE
            parts.append(f"{words[1]:08X}")
        elif opcode == 0x32:  # SCALE
            parts.append(f"{(words[0] >> 16) & 0xFF:02X}:{words[0] & 0xFFFF:04X}")

        structural_repr.append("-".join(parts))

    structure = "|".join(structural_repr)
    h = hashlib.sha256(structure.encode("utf-8")).hexdigest()[:16]
    return h, structure


def structural_hash_from_c_source(block_text, constants: dict[str, int]):
    commands = []
    func_names = []  # Parallel list: function name for CALL_NATIVE, None otherwise
    i = 0
    text = block_text
    while i < len(text):
        m = re.search(r"[A-Z_][A-Z0-9_]*\s*\(", text[i:])
        if not m:
            break

        start = i + m.start()
        name_match = re.match(r"([A-Z_][A-Z0-9_]*)", text[start:])
        if not name_match:
            i = start + 1
            continue
        cmd_name = name_match.group(1)
        if cmd_name not in CMD_NAME_TO_OPCODE:
            i = start + len(cmd_name)
            continue

        # Find matching closing parenthesis to support nested parentheses in args.
        open_paren = text.find("(", start + len(cmd_name))
        depth = 1
        j = open_paren + 1
        while j < len(text) and depth > 0:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
            j += 1
        args_str = text[open_paren + 1 : j - 1].strip()

        opcode = CMD_NAME_TO_OPCODE[cmd_name]
        size = CMD_INFO[opcode][1]
        args = [a.strip() for a in args_str.split(",")] if args_str else []

        # Build synthetic words array just for hashing
        words = [0 for _ in range(size)]
        call_native_name = None

        if cmd_name == "BEGIN" and args:
            obj_list_map = {
                "OBJ_LIST_PLAYER": 0,
                "OBJ_LIST_UNUSED_1": 1,
                "OBJ_LIST_DESTRUCTIVE": 2,
                "OBJ_LIST_UNUSED_3": 3,
                "OBJ_LIST_GENACTOR": 4,
                "OBJ_LIST_PUSHABLE": 5,
                "OBJ_LIST_LEVEL": 6,
                "OBJ_LIST_UNUSED_7": 7,
                "OBJ_LIST_DEFAULT": 8,
                "OBJ_LIST_SURFACE": 9,
                "OBJ_LIST_POLELIKE": 10,
                "OBJ_LIST_SPAWNER": 11,
                "OBJ_LIST_UNIMPORTANT": 12,
            }
            obj = obj_list_map.get(args[0], 0)
            words[0] = obj << 16
        elif cmd_name == "CALL_NATIVE" and args:
            # Extract the function name directly from the C source
            call_native_name = args[0].strip()
        elif cmd_name == "DELAY" and args:
            val = parse_number(args[0], constants)
            if val is not None:
                words[0] = val & 0xFFFF
        elif (
            cmd_name in ["ADD_FLOAT", "SET_FLOAT", "ADD_INT", "SET_INT", "OR_INT", "BIT_CLEAR"]
            and len(args) >= 2
        ):
            field = parse_number(args[0], constants)
            value = parse_number(args[1], constants)
            if field is None:
                field = 0
            if value is None:
                value = 0
            words[0] = ((field & 0xFF) << 16) | (value & 0xFFFF)
        elif cmd_name == "SET_MODEL" and args:
            val = parse_number(args[0], constants)
            if val is not None:
                words[0] = val & 0xFFFF
        elif cmd_name == "SET_HITBOX" and len(args) >= 2:
            radius = parse_number(args[0], constants) or 0
            height = parse_number(args[1], constants) or 0
            words[1] = ((radius & 0xFFFF) << 16) | (height & 0xFFFF)
        elif cmd_name == "SET_HURTBOX" and len(args) >= 2:
            radius = parse_number(args[0], constants) or 0
            height = parse_number(args[1], constants) or 0
            words[1] = ((radius & 0xFFFF) << 16) | (height & 0xFFFF)
        elif cmd_name == "LOAD_ANIMATIONS" and args:
            field = parse_number(args[0], constants) or 0
            words[0] = (field & 0xFF) << 16
        elif cmd_name == "ANIMATE" and args:
            animIndex = parse_number(args[0], constants) or 0
            words[0] = (animIndex & 0xFF) << 16
        elif cmd_name == "SET_HITBOX_WITH_OFFSET" and len(args) >= 3:
            radius = parse_number(args[0], constants) or 0
            height = parse_number(args[1], constants) or 0
            downOffset = parse_number(args[2], constants) or 0
            words[1] = ((radius & 0xFFFF) << 16) | (height & 0xFFFF)
            words[2] = downOffset & 0xFFFFFFFF
        elif cmd_name == "SCALE" and len(args) >= 2:
            field = parse_number(args[0], constants) or 0
            percent = parse_number(args[1], constants) or 0
            words[0] = ((field & 0xFF) << 16) | (percent & 0xFFFF)

        commands.append((opcode, size, words))
        func_names.append(call_native_name)
        i = j

    return structural_hash_behavior(commands, func_names=func_names), commands, func_names


def generate_hashes(src_path: Path):
    if not src_path.exists():
        print(f"Source file not found: {src_path}", file=sys.stderr)
        return

    repo_root = Path(__file__).resolve().parents[2]
    import os

    env_root = os.environ.get("SM64_DIR") or os.environ.get("SM64_ROOT")
    if env_root:
        sm64_root = Path(env_root)
    else:
        sm64_root = repo_root / "sm64"
    include_dir = sm64_root / "include"

    global FIELD_NAME_TO_INDEX
    FIELD_NAME_TO_INDEX = load_object_field_indices(include_dir / "object_fields.h")

    constants = load_constant_defines(
        [
            include_dir / "object_constants.h",
            include_dir / "sm64.h",
            include_dir / "model_ids.h",
            sm64_root / "src/game/object_list_processor.h",
            sm64_root / "src/game/interaction.h",
        ]
    )

    txt = src_path.read_text(encoding="utf-8")

    # remove C comments
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    txt = re.sub(r"//.*?$", "", txt, flags=re.M)

    pattern = re.compile(r"\bconst\s+BehaviorScript\s+([A-Za-z0-9_]+)\s*\[\s*\]\s*=\s*\{", re.M)
    matches = list(pattern.finditer(txt))

    hashes: dict[str, str] = {}

    print(f"Found {len(matches)} scripts in {src_path}", file=sys.stderr)

    for m in matches:
        name = m.group(1)
        # find the block using brace counting
        i = m.end()
        depth = 1
        start = i
        while i < len(txt) and depth > 0:
            c = txt[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        block = txt[start : i - 1]

        (h, structure), commands_list, func_names_list = structural_hash_from_c_source(
            block.strip(), constants
        )

        if h in hashes:
            print(f"WARNING: Duplicate hash for {name} and {hashes[h]}", file=sys.stderr)

        hashes[h] = name
        print(f"{name}: {h} (struct: {structure[:80]}...)", file=sys.stderr)

        # Also generate fuzzy hashes for romhack tolerance.
        # For each CALL_NATIVE position, replace that function name with "UNKNOWN"
        # to allow matching when a romhack modifies one native function.
        if func_names_list and any(fn is not None for fn in func_names_list):
            # Generate one fuzzy variant per CALL_NATIVE position
            for ci in range(len(func_names_list)):
                if func_names_list[ci] is None:
                    continue
                fuzzy_names = list(func_names_list)
                fuzzy_names[ci] = "UNKNOWN"
                h_fuzzy, _ = structural_hash_behavior(commands_list, func_names=fuzzy_names)
                if h_fuzzy != h and h_fuzzy not in hashes:
                    hashes[h_fuzzy] = name
                elif h_fuzzy in hashes and hashes[h_fuzzy] != name:
                    print(
                        f"WARNING: Fuzzy hash collision for {name} and {hashes[h_fuzzy]} "
                        f"(fn[{ci}]={func_names_list[ci]}->UNKNOWN)",
                        file=sys.stderr,
                    )

            # Generate one fully fuzzy variant where ALL CALL_NATIVE positions are "UNKNOWN"
            fully_fuzzy_names = ["UNKNOWN" if fn is not None else None for fn in func_names_list]
            h_fully_fuzzy, _ = structural_hash_behavior(commands_list, func_names=fully_fuzzy_names)
            if h_fully_fuzzy != h and h_fully_fuzzy not in hashes:
                hashes[h_fully_fuzzy] = name

    print("# This file is auto-generated by tools/generate_behavior_hashes.py")
    print("# Do not edit manually.")
    print("")
    print("from typing import Dict")
    print("")
    print("KNOWN_BEHAVIOR_HASHES: Dict[str, str] = {")
    for h, name in sorted(hashes.items(), key=lambda x: x[1]):
        print(f'    "{h}": "{name}",')
    print("}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./generate_behavior_hashes.py <path_to_behavior_data.c>")
        sys.exit(1)

    generate_hashes(Path(sys.argv[1]))
