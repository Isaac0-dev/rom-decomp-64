#!/usr/bin/env python3

import os
import re
import json
import hashlib
from typing import Dict, Any, List

# Path to SM64 decomp root
_env_root = os.environ.get("SM64_DIR") or os.environ.get("SM64_ROOT")
if _env_root:
    SM64_ROOT = _env_root
else:
    SM64_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "sm64")
ACTORS_DIR = os.path.join(SM64_ROOT, "actors")
LEVELS_DIR = os.path.join(SM64_ROOT, "levels")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _freeze(val):
    if isinstance(val, list):
        return tuple(_freeze(v) for v in val)
    if isinstance(val, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in val.items()))
    return val


def _normalize_tex_id(tex_id):
    if tex_id is None:
        return None
    if isinstance(tex_id, int):
        return f"0x{tex_id:08X}"
    # Look for an embedded 8-digit hex chunk
    m = re.search(r"([0-9A-Fa-f]{8})", str(tex_id))
    if m:
        try:
            val = int(m.group(1), 16)
            return f"0x{val:08X}"
        except ValueError:
            pass
    return str(tex_id)


def infer_segment_from_name(name):
    m = re.search(r"_(0[0-9A-Fa-f]{7})", name)
    if not m:
        return None
    try:
        addr = int(m.group(1), 16)
        return (addr >> 24) & 0xFF
    except ValueError:
        return None


def normalize_display_list(commands):
    normalized = []

    for idx, cmd in enumerate(commands):
        cmd_type = cmd["type"]
        norm_cmd = {
            "type": cmd_type,
            "pos": idx,  # Include position in sequence
        }

        # Include exact per-command details
        if cmd_type == "gsSPVertex":
            # Exact vertex count and starting index
            if "count" in cmd:
                norm_cmd["count"] = cmd["count"]
            if "v0" in cmd:
                norm_cmd["v0"] = cmd["v0"]

        elif cmd_type in ["gsSP1Triangle", "gsSP2Triangles"]:
            # Exact triangle count and indices
            norm_cmd["tri_count"] = 2 if "2Triangles" in cmd_type else 1
            if "indices" in cmd:
                norm_cmd["indices"] = cmd["indices"]

        elif cmd_type == "gsSPLight":
            # Each light command separately
            norm_cmd["is_light"] = True

        elif cmd_type in [
            "gsDPSetTextureImage",
            "gsDPLoadTextureBlock",
            "gsDPLoadBlock",
            "gsDPSetTile",
        ]:
            # Include texture info when present in parsed command (addresses ignored)
            norm_cmd["has_tex"] = True
            if "fmt" in cmd:
                norm_cmd["fmt"] = cmd["fmt"]
            if "siz" in cmd:
                norm_cmd["siz"] = cmd["siz"]
            if "width" in cmd:
                norm_cmd["width"] = cmd["width"]
            if "tex_id" in cmd:
                norm_cmd["tex_id"] = _normalize_tex_id(cmd["tex_id"])
            if "tex_id" in cmd:
                norm_cmd["tex_id"] = cmd["tex_id"]

        elif cmd_type == "gsSPDisplayList":
            # Note subdl presence
            norm_cmd["subdl"] = True

        elif cmd_type == "gsSPTexture":
            # Keep decoded texture scaling params
            if "modes" in cmd:
                norm_cmd["modes"] = cmd["modes"]

        elif cmd_type == "gsSPEndDisplayList":
            # Terminal command
            norm_cmd["end"] = True

        normalized.append(norm_cmd)

    # Include overall length to break ties on very short lists
    normalized.append({"type": "__len__", "len": len(commands)})

    return normalized


def get_dl_fingerprint(commands):
    stats: Dict[str, Any] = {
        "vertex_count": 0,
        "tri_count": 0,
        "texture_loads": 0,
        "tex_signature": [],  # List of strings like "RGBA16_32x32"
        "mode_signature": [],
    }

    for cmd in commands:
        t = cmd.get("type", "")

        if "Vertex" in t:
            # Normalize count based on command type logic (extracted in your parser)
            count = cmd.get("count", 0)
            stats["vertex_count"] += count

        elif "Triangle" in t:
            # Count actual triangles (1 or 2)
            n = 2 if "2Triangles" in t else 1
            stats["tri_count"] += n

        elif t in ["gsDPSetTextureImage", "gsDPLoadTextureBlock", "gsDPLoadBlock"]:
            stats["texture_loads"] += 1
            # Add to signature
            fmt = cmd.get("fmt", "?")
            siz = cmd.get("siz", "?")
            width = cmd.get("width", "?")
            tex_id = _normalize_tex_id(cmd.get("tex_id", "?"))
            stats["tex_signature"].append(f"{fmt}_{siz}_{width}_{tex_id}")

        if t in [
            "gsDPSetCombineMode",
            "gsDPSetRenderMode",
            "gsSPSetGeometryMode",
            "gsSPClearGeometryMode",
            "gsSPSetOtherMode_H",
            "gsSPSetOtherMode_L",
            "gsSPTexture",
            "gsDPSetTile",
            "gsDPSetTileSize",
        ]:
            modes = cmd.get("modes")
            if modes:
                stats["mode_signature"].append((t, _freeze(modes)))
            else:
                w0 = cmd.get("w0")
                w1 = cmd.get("w1")
                if w0 is not None or w1 is not None:
                    stats["mode_signature"].append((t, w0, w1))

    return stats


def hash_display_list(normalized_commands):
    # Convert to stable string representation
    cmd_str = json.dumps(normalized_commands, sort_keys=True)
    return hashlib.sha256(cmd_str.encode()).hexdigest()


def parse_display_list_file(file_path, actor_name):
    display_lists: Dict[str, Any] = {}

    try:
        with open(file_path, "r") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return display_lists

    # Find all display list definitions
    # Pattern: const Gfx <name>[] = {
    dl_pattern = re.compile(r"const\s+Gfx\s+(\w+)\[\]\s*=\s*\{([^}]+)\};", re.MULTILINE | re.DOTALL)

    for match in dl_pattern.finditer(content):
        dl_name = match.group(1)
        dl_body = match.group(2)

        # Parse commands from the display list
        commands = parse_display_list_commands(dl_body)

        if not commands:
            continue

        # Normalize and hash
        normalized = normalize_display_list(commands)
        dl_hash = hash_display_list(normalized)

        # Calculate stats
        vert_count = sum(cmd.get("count", 0) for cmd in commands if cmd["type"] == "gsSPVertex")
        tri_count = sum(
            cmd.get("triangle_count", 0) for cmd in commands if "Triangle" in cmd["type"]
        )

        display_lists[dl_name] = {
            "hash": dl_hash,
            "name": dl_name,
            "actor": actor_name,
            "commands": normalized,
            "segment": infer_segment_from_name(dl_name),
            "stats": {
                "vertex_count": vert_count,
                "triangle_count": tri_count,
                "command_count": len(commands),
            },
            "fingerprint": get_dl_fingerprint(commands),
        }

    return display_lists


def parse_display_list_commands(dl_body):
    commands = []

    # Split by commas (but be careful with nested parentheses)
    lines = dl_body.split("\n")

    fmt_map = {
        "G_IM_FMT_RGBA": 0,
        "G_IM_FMT_YUV": 1,
        "G_IM_FMT_CI": 2,
        "G_IM_FMT_IA": 3,
        "G_IM_FMT_I": 4,
        "G_IM_FMT_RGB": 0,  # alias often used
    }
    siz_map = {
        "G_IM_SIZ_4b": 0,
        "G_IM_SIZ_8b": 1,
        "G_IM_SIZ_16b": 2,
        "G_IM_SIZ_32b": 3,
    }

    def parse_token(tok, mapping=None):
        if mapping and tok in mapping:
            return mapping[tok]
        try:
            return int(tok, 0)
        except ValueError:
            return None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        # Extract command name
        cmd_match = re.match(r"(gs\w+)\s*\(", line)
        if not cmd_match:
            continue

        cmd_name = cmd_match.group(1)
        cmd_info = {"type": cmd_name}

        # Extract specific parameters we care about
        if cmd_name == "gsSPVertex":
            # Args: ptr, count, v0
            args_str = line[line.find("(") + 1 : line.rfind(")")]
            args = [a.strip() for a in args_str.split(",")]
            if len(args) >= 2:
                try:
                    cmd_info["count"] = int(args[1], 0)
                except ValueError:
                    pass
            if len(args) >= 3:
                try:
                    cmd_info["v0"] = int(args[2], 0)
                except ValueError:
                    pass

        elif cmd_name in ["gsSP1Triangle", "gsSP2Triangles"]:
            # Count number of triangles
            cmd_info["triangle_count"] = 2 if "2Triangles" in cmd_name else 1
            args_str = line[line.find("(") + 1 : line.rfind(")")]
            # Grab numeric args only; flags are usually last
            num_tokens = re.findall(r"(0x[0-9A-Fa-f]+|-?\d+)", args_str)
            indices = []
            try:
                max_indices = 6 if cmd_name == "gsSP2Triangles" else 3
                for tok in num_tokens[:max_indices]:
                    indices.append(int(tok, 0))
            except ValueError:
                indices = []
            if indices:
                cmd_info["indices"] = indices

        elif cmd_name in [
            "gsDPSetTextureImage",
            "gsDPSetTile",
            "gsDPLoadTextureBlock",
            "gsDPLoadBlock",
        ]:
            args_str = line[line.find("(") + 1 : line.rfind(")")]
            args = [a.strip() for a in args_str.split(",")]

            if args:
                fmt = parse_token(args[0], fmt_map)
                if fmt is not None:
                    cmd_info["fmt"] = fmt
            if len(args) > 1:
                siz = parse_token(args[1], siz_map)
                if siz is not None:
                    cmd_info["siz"] = siz
            if cmd_name == "gsDPSetTextureImage" and len(args) > 2:
                width = parse_token(args[2])
                if width is not None:
                    cmd_info["width"] = width
                if len(args) > 3:
                    cmd_info["tex_id"] = args[3]

        elif cmd_name in [
            "gsDPSetCombineMode",
            "gsDPSetRenderMode",
            "gsSPSetGeometryMode",
            "gsSPClearGeometryMode",
            "gsSPSetOtherMode_H",
            "gsSPSetOtherMode_L",
            "gsSPTexture",
        ]:
            args_str = line[line.find("(") + 1 : line.rfind(")")]
            num_tokens = re.findall(r"(0x[0-9A-Fa-f]+|-?\d+)", args_str)
            numeric = [parse_token(tok) for tok in num_tokens if parse_token(tok) is not None]
            if numeric:
                cmd_info["modes"] = numeric

        commands.append(cmd_info)

    return commands


def normalize_geo(commands, dl_hash_map):
    normalized = []

    for idx, cmd in enumerate(commands):
        cmd_type = cmd["type"]
        norm_cmd = {"type": cmd_type, "pos": idx}

        # Include structural information
        if cmd_type == "GEO_DISPLAY_LIST":
            # Reference DL by hash if available
            layer = cmd.get("layer")
            dl_name = cmd.get("dl_name")
            if layer:
                norm_cmd["layer"] = layer
            if dl_name and dl_name in dl_hash_map:
                norm_cmd["dl_hash"] = dl_hash_map[dl_name]
        elif cmd_type in ["GEO_SWITCH_CASE", "GEO_ASM"]:
            # Include parameter but not function address
            if "param" in cmd:
                norm_cmd["param"] = cmd["param"]
        elif cmd_type in ["GEO_TRANSLATE_ROTATE", "GEO_ANIMATED_PART"]:
            # Note presence but ignore specific values (they vary)
            norm_cmd["has_transform"] = True
        elif cmd_type == "GEO_BRANCH":
            # Note branch but not target
            norm_cmd["has_branch"] = True
        elif cmd_type == "GEO_CULLING_RADIUS":
            data = cmd.get("data", [])
            if data:
                norm_cmd["data"] = [data[0] & 0xFFFF]
        elif cmd_type in ["GEO_SHADOW", "GEO_SCALE", "GEO_BACKGROUND", "GEO_BACKGROUND_COLOR"]:
            data = cmd.get("data", [])
            if not data:
                pass
            elif cmd_type == "GEO_SHADOW":
                if len(data) >= 3:
                    s_type, solidity, scale = data[0], data[1], data[2]
                elif len(data) >= 2:
                    s_type = data[0] & 0xFFFF
                    solidity = (data[1] >> 16) & 0xFFFF
                    scale = data[1] & 0xFFFF
                else:
                    s_type = 0
                    solidity = data[0] & 0xFFFF
                    scale = data[0] & 0xFFFF
                norm_cmd["data"] = [s_type, solidity, scale]
            elif cmd_type == "GEO_SCALE":
                if len(data) >= 2:
                    norm_cmd["data"] = [data[1]]
            else:  # BACKGROUND / BACKGROUND_COLOR
                norm_cmd["data"] = [data[0] & 0xFFFF]

        normalized.append(norm_cmd)

    # Include overall length to reduce collisions
    normalized.append({"type": "__len__", "len": len(commands)})

    return normalized


def generate_geo_skeleton(commands):
    skeleton = ""
    for cmd in commands:
        t = cmd.get("type", "")
        if t == "GEO_OPEN_NODE":
            skeleton += "("
        elif t == "GEO_CLOSE_NODE":
            skeleton += ")"
        elif t == "GEO_ANIMATED_PART":
            skeleton += "A"
        elif t == "GEO_SWITCH_CASE":
            skeleton += "S"
        elif t == "GEO_DISPLAY_LIST":
            skeleton += "D"
        elif t == "GEO_ASM":
            skeleton += "F"  # Function call is a strong structure hint
        elif t == "GEO_BRANCH_AND_LINK":
            skeleton += "B"
        elif t == "GEO_HELD_OBJECT":
            skeleton += "H"
        elif t == "GEO_CULLING_RADIUS":
            skeleton += "R"
        elif t == "GEO_SHADOW":
            skeleton += "W"
        elif t == "GEO_SCALE":
            skeleton += "Z"
        elif t == "GEO_BACKGROUND":
            skeleton += "G"
        # We ignore translations/rotations (T, R) as those are often tweaked in hacks
    return skeleton


def hash_geo(normalized_commands):
    cmd_str = json.dumps(normalized_commands, sort_keys=True)
    return hashlib.sha256(cmd_str.encode()).hexdigest()


def parse_geo_file(file_path, actor_name, dl_hash_map, content):
    geos = {}

    # Find all geo layout definitions
    # Pattern: const GeoLayout <name>[] = {
    geo_pattern = re.compile(
        r"const\s+GeoLayout\s+(\w+)\[\]\s*=\s*\{([^}]+)\};", re.MULTILINE | re.DOTALL
    )

    for match in geo_pattern.finditer(content):
        geo_name = match.group(1)
        geo_body = match.group(2)

        # Parse commands from the geo layout
        commands = parse_geo_commands(geo_body)

        if not commands:
            continue

        # Normalize and hash
        normalized = normalize_geo(commands, dl_hash_map)
        geo_hash = hash_geo(normalized)

        # Collect referenced DL hashes
        child_dl_hashes = [cmd.get("dl_hash") for cmd in normalized if cmd.get("dl_hash")]
        child_dl_names = [
            cmd.get("dl_name")
            for cmd in commands
            if cmd.get("type") == "GEO_DISPLAY_LIST" and cmd.get("dl_name")
        ]

        # Extract parameter values for simple geo matching
        params = {}
        for i, cmd in enumerate(commands):
            t = cmd.get("type", "")
            data = cmd.get("data", [])
            if t == "GEO_CULLING_RADIUS" and data:
                params[f"cull_{i}"] = data[0] & 0xFFFF
            elif t == "GEO_SHADOW" and data:
                if len(data) >= 3:
                    s_type, solidity, scale = data[0], data[1], data[2]
                elif len(data) >= 2:
                    s_type = data[0] & 0xFFFF
                    solidity = (data[1] >> 16) & 0xFFFF
                    scale = data[1] & 0xFFFF
                else:
                    s_type = 0
                    solidity = data[0] & 0xFFFF
                    scale = data[0] & 0xFFFF
                params[f"shadow_{i}"] = f"{s_type}_{solidity}_{scale}"
            elif t == "GEO_SCALE" and len(data) >= 2:
                params[f"scale_{i}"] = data[1]
            elif t == "GEO_BACKGROUND_COLOR" and data:
                params[f"bg_{i}"] = data[0] & 0xFFFF
            elif t == "GEO_BACKGROUND" and data:
                params[f"bg_{i}"] = data[0] & 0xFFFF

        geos[geo_name] = {
            "hash": geo_hash,
            "name": geo_name,
            "actor": actor_name,
            "commands": normalized,
            "child_dl_hashes": child_dl_hashes,
            "child_dl_names": child_dl_names,
            "stats": {"command_count": len(commands), "display_list_count": len(child_dl_hashes)},
            "skeleton": generate_geo_skeleton(commands),
            "asm_funcs": [c.get("param") for c in commands if c.get("type") == "GEO_ASM"],
            "params": params,
        }

    return geos


def parse_geo_commands(geo_body):
    commands = []
    lines = geo_body.split("\n")

    shadow_type_map = {
        "SHADOW_CIRCLE_9_VERTS": 0,
        "SHADOW_CIRCLE_4_VERTS": 1,
        "SHADOW_CIRCLE_4_VERTS_FLAT_UNUSED": 2,
        "SHADOW_SQUARE_PERMANENT": 10,
        "SHADOW_SQUARE_SCALABLE": 11,
        "SHADOW_SQUARE_TOGGLABLE": 12,
        "SHADOW_RECTANGLE_HARDCODED_OFFSET": 50,
        "SHADOW_CIRCLE_PLAYER": 99,
    }

    def parse_token(tok):
        try:
            return int(tok, 0)
        except ValueError:
            return None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        # Extract command name
        cmd_match = re.match(r"(GEO_\w+)\s*\(", line)
        if not cmd_match:
            continue

        cmd_name = cmd_match.group(1)
        cmd_info = {"type": cmd_name}

        # Extract specific parameters we care about
        if cmd_name == "GEO_DISPLAY_LIST":
            # Extract layer and DL name
            # Pattern: GEO_DISPLAY_LIST(LAYER_X, dl_name)
            dl_match = re.search(r"GEO_DISPLAY_LIST\s*\(\s*(LAYER_\w+)\s*,\s*(\w+)\s*\)", line)
            if dl_match:
                cmd_info["layer"] = dl_match.group(1)
                cmd_info["dl_name"] = dl_match.group(2)

        elif cmd_name == "GEO_SHADOW":
            arg_str = line[line.find("(") + 1 : line.rfind(")")]
            args = [a.strip() for a in arg_str.split(",")]

            s_type = None
            solidity = None
            scale = None
            if args:
                s_type = shadow_type_map.get(args[0], parse_token(args[0]))
            if len(args) > 1:
                solidity = parse_token(args[1])
            if len(args) > 2:
                scale = parse_token(args[2])

            data = []
            if s_type is not None:
                data.append(s_type)
            if solidity is not None:
                if scale is not None:
                    data.append((solidity << 16) | (scale & 0xFFFF))
                else:
                    data.append(solidity)
            if scale is not None and solidity is None:
                data.append(scale)
            if data:
                cmd_info["data"] = data

        elif cmd_name in ["GEO_SWITCH_CASE", "GEO_ASM"]:
            # Extract first parameter
            param_match = re.search(r"\(\s*(\d+|0x[0-9A-Fa-f]+)", line)
            if param_match:
                cmd_info["param"] = param_match.group(1)

        # Capture numeric data for parameter-sensitive commands
        num_tokens = re.findall(r"(0x[0-9A-Fa-f]+|-?\d+)", line)
        if num_tokens and "data" not in cmd_info:
            try:
                cmd_info["data"] = [int(tok, 0) for tok in num_tokens]
            except ValueError:
                pass

        commands.append(cmd_info)

    return commands


def extract_all_display_lists():
    all_display_lists: Dict[str, Any] = {}
    hash_to_metadata: Dict[str, List[Any]] = {}
    name_to_hash: Dict[str, str] = {}

    # Find all model.inc.c files (actors + levels)
    model_files = []
    for root, dirs, files in os.walk(ACTORS_DIR):
        for file in files:
            if file == "model.inc.c":
                model_files.append(os.path.join(root, file))
    for root, dirs, files in os.walk(LEVELS_DIR):
        for file in files:
            if file == "model.inc.c":
                model_files.append(os.path.join(root, file))

    print(f"Found {len(model_files)} model.inc.c files")

    for model_file in model_files:
        # Use directory name as namespace to reduce collisions
        actor_name = os.path.basename(os.path.dirname(model_file))
        print(f"Processing {actor_name}...")

        display_lists = parse_display_list_file(model_file, actor_name)

        for dl_name, dl_data in display_lists.items():
            dl_hash = dl_data["hash"]

            # Store by hash for lookup (allow collisions; keep all)
            hash_to_metadata.setdefault(dl_hash, []).append(dl_data)

            # Also keep full mapping
            all_display_lists[f"{actor_name}_{dl_name}"] = dl_data
            name_to_hash[dl_name] = dl_hash

        print(f"  Extracted {len(display_lists)} display lists")

    return hash_to_metadata, name_to_hash


def extract_all_geos(dl_name_to_hash):
    hash_to_metadata: Dict[str, List[Any]] = {}

    # Find all geo.inc.c files (actors + levels)
    geo_files = []
    for root, dirs, files in os.walk(ACTORS_DIR):
        for file in files:
            if file == "geo.inc.c":
                geo_files.append(os.path.join(root, file))
    for root, dirs, files in os.walk(LEVELS_DIR):
        for file in files:
            if file == "geo.inc.c":
                geo_files.append(os.path.join(root, file))

    print(f"\nFound {len(geo_files)} geo.inc.c files")

    for geo_file in geo_files:
        actor_name = os.path.basename(os.path.dirname(geo_file))
        print(f"Processing {actor_name}...")

        try:
            with open(geo_file, "r") as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {geo_file}: {e}")
            continue

        geos = parse_geo_file(geo_file, actor_name, dl_name_to_hash, content)

        for geo_name, geo_data in geos.items():
            if len(re.findall(r"\b" + re.escape(geo_name) + r"\b", content)) != 1:
                continue

            geo_hash = geo_data["hash"]

            # Store by hash for lookup (allow collisions)
            hash_to_metadata.setdefault(geo_hash, []).append(geo_data)

        print(f"  Extracted {len(geos)} geo layouts")

    return hash_to_metadata


def main():
    print("=== Vanilla SM64 Database Generator ===\n")

    # Check SM64 decomp path
    if not os.path.exists(ACTORS_DIR):
        print(f"Error: Actors directory not found at {ACTORS_DIR}")
        print(
            "Please ensure SM64_DIR or SM64_ROOT environment variable points to the SM64 decomp root."
        )
        return 1

    # Extract display lists
    print("Extracting display lists...")
    display_lists_db, dl_name_to_hash = extract_all_display_lists()

    # Save display lists to JSON
    dl_output = os.path.join(OUTPUT_DIR, "vanilla_display_lists.json")
    with open(dl_output, "w") as f:
        json.dump(display_lists_db, f, indent=2, sort_keys=True)

    print(f"\nGenerated database with {len(display_lists_db)} unique display list hashes")
    print(f"Saved to {dl_output}")

    # Extract geo layouts
    print("\nExtracting geo layouts...")
    geos_db = extract_all_geos(dl_name_to_hash)

    # Save geos to JSON
    geo_output = os.path.join(OUTPUT_DIR, "vanilla_geos.json")
    with open(geo_output, "w") as f:
        json.dump(geos_db, f, indent=2, sort_keys=True)

    print(f"\nGenerated database with {len(geos_db)} unique geo layout hashes")
    print(f"Saved to {geo_output}")

    return 0


if __name__ == "__main__":
    exit(main())
