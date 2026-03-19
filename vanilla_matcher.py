#!/usr/bin/env python3

import json
import hashlib
import difflib
import re
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, cast

# Path to database files
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DL_DATABASE = os.path.join(DATA_DIR, "vanilla_display_lists.json")
GEO_DATABASE = os.path.join(DATA_DIR, "vanilla_geos.json")


# Global caches
_dl_database: Optional[Dict[str, Any]] = None
_geo_database: Optional[Dict[str, Any]] = None
_dl_name_to_hash: Optional[Dict[str, str]] = None
_fuzzy_match_cache: Dict[
    Tuple[str, str], Any
] = {}  # Cache for fuzzy match results to avoid redundant expensive comparisons
_dl_entries: Optional[List[Dict[str, Any]]] = None
_geo_entries: Optional[List[Dict[str, Any]]] = None


def _freeze(val):
    # Convert lists/dicts into tuples so values stay hashable for matching
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
    m = re.search(r"([0-9A-Fa-f]{8})", str(tex_id))
    if m:
        try:
            val = int(m.group(1), 16)
            return f"0x{val:08X}"
        except ValueError:
            pass
    return str(tex_id)


def _coalesce_texture_loads(commands):
    # Collapse macro-expanded texture load sequences into gsDPLoadTextureBlock
    result = []
    i = 0
    n = len(commands)

    while i < n:
        cmd = commands[i]
        t = cmd.get("type", cmd.get("cmd", ""))

        if t == "gsDPSetTextureImage":
            load_idx = None
            end_idx = None
            j = i + 1
            while j < n and (j - i) <= 8:
                t2 = commands[j].get("type", commands[j].get("cmd", ""))
                if t2 == "gsDPSetTextureImage":
                    break  # start of the next load sequence
                if t2 == "gsDPLoadBlock":
                    load_idx = j
                if t2 == "gsDPSetTileSize":
                    end_idx = j
                j += 1

            if load_idx is not None:
                result.append({"type": "gsDPLoadTextureBlock"})
                i = (end_idx if end_idx is not None else load_idx) + 1
                continue

        result.append(cmd)
        i += 1

    return result


@lru_cache(maxsize=8192)
def _sequence_ratio(a, b):
    """
    Cached SequenceMatcher.ratio for hashable sequences/strings.
    Accepts tuples/strings; callers should convert unhashable sequences to tuples.
    """
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_databases():
    global _dl_database, _geo_database, _dl_name_to_hash, _dl_entries, _geo_entries

    if _dl_database is None:
        try:
            with open(DL_DATABASE, "r") as f:
                _dl_database = json.load(f)

            # Ensure fingerprints are hashable (JSON reload turns tuples into lists)
            def _sanitize_entry(entry):
                fp = entry.get("fingerprint")
                if fp and fp.get("mode_signature"):
                    fp["mode_signature"] = [_freeze(item) for item in fp["mode_signature"]]
                return entry

            for h, entry in list(_dl_database.items()):
                if isinstance(entry, list):
                    _dl_database[h] = [_sanitize_entry(e) for e in entry]
                else:
                    _dl_database[h] = _sanitize_entry(entry)

            print(f"Loaded {len(_dl_database)} display lists from database")

            # Build name to hash map and flattened list for repeated fuzzy searches
            _dl_name_to_hash = {}
            _dl_entries = []
            for h, entry in _dl_database.items():
                if isinstance(entry, list):
                    for e in entry:
                        _dl_name_to_hash[e["name"]] = h
                        _dl_entries.append(e)
                else:
                    _dl_name_to_hash[entry["name"]] = h
                    _dl_entries.append(entry)

        except FileNotFoundError:
            print(f"Warning: Display list database not found at {DL_DATABASE}")
            _dl_database = {}
            _dl_name_to_hash = {}
            _dl_entries = []

    if _geo_database is None:
        try:
            with open(GEO_DATABASE, "r") as f:
                _geo_database = json.load(f)
            print(f"Loaded {len(_geo_database)} geo layouts from database")
            _geo_entries = []
            for entry_list in _geo_database.values():
                if isinstance(entry_list, list):
                    _geo_entries.extend(entry_list)
                else:
                    _geo_entries.append(entry_list)
        except FileNotFoundError:
            print(f"Warning: Geo database not found at {GEO_DATABASE}")
            _geo_database = {}
            _geo_entries = []


def normalize_display_list_for_matching(commands):
    # Normalize display list commands for matching
    commands = _coalesce_texture_loads(commands)
    normalized = []

    for idx, cmd in enumerate(commands):
        cmd_type = cmd.get("type", cmd.get("cmd", ""))
        norm_cmd = {
            "type": cmd_type,
            "pos": idx,  # Include position in sequence
        }

        # Include exact per-command details
        w0 = cmd.get("w0")
        w1 = cmd.get("w1")

        if cmd_type == "gsSPVertex":
            # Exact vertex count and starting index
            count = cmd.get("count", cmd.get("vertex_count"))
            v0 = cmd.get("v0")
            if count is None and w0 is not None:
                byte1 = (w0 >> 16) & 0xFF
                count = ((byte1 >> 4) & 0xF) + 1
                v0 = byte1 & 0xF if v0 is None else v0
            if v0 is not None:
                norm_cmd["v0"] = v0
            if count is not None:
                norm_cmd["count"] = count

        elif cmd_type in ["gsSP1Triangle", "gsSP2Triangles"]:
            # Exact triangle indices for this command
            norm_cmd["tri_count"] = 2 if "2Triangles" in cmd_type else 1
            indices = cmd.get("indices")
            if not indices and w0 is not None:
                if cmd_type == "gsSP1Triangle":
                    indices = [
                        (w0 >> 16) & 0xFF,
                        (w0 >> 8) & 0xFF,
                        w0 & 0xFF,
                    ]
                elif cmd_type == "gsSP2Triangles" and w1 is not None:
                    indices = [
                        (w0 >> 16) & 0xFF,
                        (w0 >> 8) & 0xFF,
                        w0 & 0xFF,
                        (w1 >> 16) & 0xFF,
                        (w1 >> 8) & 0xFF,
                        w1 & 0xFF,
                    ]
            if indices:
                norm_cmd["indices"] = indices

        elif cmd_type == "gsSPLight":
            # Each light command separately
            norm_cmd["is_light"] = True

        elif cmd_type in [
            "gsDPSetTextureImage",
            "gsDPLoadTextureBlock",
            "gsDPLoadBlock",
            "gsDPSetTile",
        ]:
            # Include texture-related meta when available in parsed command
            norm_cmd["has_tex"] = True
            fmt = cmd.get("fmt")
            siz = cmd.get("siz")
            width = cmd.get("width")
            tex_id = cmd.get("tex_id")

            if fmt is None and w0 is not None:
                fmt = (w0 >> 21) & 0x7
            if siz is None and w0 is not None:
                siz = (w0 >> 19) & 0x3
            if width is None and w0 is not None and cmd_type == "gsDPSetTextureImage":
                width = (w0 & 0xFFF) + 1
            if tex_id is None and cmd_type == "gsDPSetTextureImage" and w1 is not None:
                tex_id = f"0x{w1:08X}"

            if fmt is not None:
                norm_cmd["fmt"] = fmt
            if siz is not None:
                norm_cmd["siz"] = siz
            if width is not None:
                norm_cmd["width"] = width
            if tex_id is not None:
                norm_cmd["tex_id"] = _normalize_tex_id(tex_id)

        elif cmd_type == "gsSPDisplayList":
            # Note subdl presence (address ignored intentionally)
            norm_cmd["subdl"] = True

        elif cmd_type == "gsSPTexture":
            # Decode texture scale parameters (ignore tile/on to avoid pointer-based matching)
            s_val = (w1 >> 16) & 0xFFFF if w1 is not None else None
            t_val = w1 & 0xFFFF if w1 is not None else None
            level = (w0 >> 11) & 0x7 if w0 is not None else None
            modes = cmd.get("modes")
            # Prefer explicit modes if provided (e.g. from pre-parsed sources)
            if modes:
                norm_cmd["modes"] = modes
            else:
                decoded = [v for v in (s_val, t_val, level) if v is not None]
                if decoded:
                    norm_cmd["modes"] = decoded

        elif cmd_type in [
            "gsDPSetCombineMode",
            "gsDPSetRenderMode",
            "gsSPSetGeometryMode",
            "gsSPClearGeometryMode",
            "gsDPSetEnvColor",
            "gsDPSetPrimColor",
            "gsDPFillRectangle",
            "gsDPSetFillColor",
            "gsDPSetFogColor",
            "gsSPSetOtherMode_H",
            "gsSPSetOtherMode_L",
        ]:
            # Only include modes when they were explicitly parsed; avoid raw word fallback
            modes = cmd.get("modes")
            if modes:
                norm_cmd["modes"] = modes

        elif cmd_type == "gsSPEndDisplayList":
            # Terminal command
            norm_cmd["end"] = True

        normalized.append(norm_cmd)

    # Include overall length to break ties on very short lists
    normalized.append({"type": "__len__", "len": len(commands)})

    return normalized


# --- COMPLEXITY HELPERS ---


def get_geo_complexity(commands):
    # Returns a score representing how 'unique' this geo layout is likely to be
    score: float = 0.0
    for cmd in commands:
        t = cmd.get("type", "")
        if t == "GEO_ASM":
            score += 5  # ASMs are very unique
        elif t == "GEO_DISPLAY_LIST":
            score += 3  # DL refs are good anchors
        elif t == "GEO_ANIMATED_PART":
            score += 2
        elif t == "GEO_SWITCH_CASE":
            score += 2
        elif t == "GEO_BRANCH_AND_LINK":
            score += 2
        elif t in ["GEO_OPEN_NODE", "GEO_CLOSE_NODE", "GEO_END"]:
            score += 0.1
        else:
            score += 1
    return score


def get_dl_complexity(stats):
    # Returns a score representing how 'unique' this display list is
    score: float = 0.0
    # Textures are the best fingerprint
    score += len(stats.get("tex_signature", [])) * 5
    score += len(stats.get("mode_signature", [])) * 1.5

    # Vertices add weight, but diminish after a point
    vtx = stats.get("vertex_count", 0)
    score += min(vtx, 50) * 0.1

    # Triangles
    tri = stats.get("tri_count", 0)
    score += min(tri, 50) * 0.1

    return score


def hash_display_list(normalized_commands):
    cmd_str = json.dumps(normalized_commands, sort_keys=True)
    return hashlib.sha256(cmd_str.encode()).hexdigest()


def match_display_list(commands, segment_id=None, addr_hint=None):
    # Match a display list against the vanilla database
    # Ensure database is loaded
    if _dl_database is None:
        load_databases()

    # Normalize and hash
    normalized = normalize_display_list_for_matching(commands)
    dl_hash = hash_display_list(normalized)

    # Look up in database
    if _dl_database is None:
        return None
    entry = _dl_database.get(dl_hash)
    if isinstance(entry, list):
        # Try to disambiguate using segment and basic stats
        candidates = entry
        if segment_id is not None:
            candidates = [e for e in candidates if e.get("segment") == segment_id]
        if len(candidates) == 1:
            entry = candidates[0]
        else:
            # As an extra filter, match by command count
            cmd_count = len(normalized)
            filtered = [
                e for e in candidates if e.get("stats", {}).get("command_count") == cmd_count
            ]
            candidates = filtered if filtered else candidates

            # Try address hint matching (useful when names embed the segmented address)
            if addr_hint is not None:
                addr_hex = f"{addr_hint:08X}"
                addr_filtered = [e for e in candidates if addr_hex in e.get("name", "")]
                if len(addr_filtered) == 1:
                    entry = addr_filtered[0]
                elif len(addr_filtered) > 1:
                    entry = None  # still ambiguous
                else:
                    entry = candidates[0] if len(candidates) == 1 else None
            else:
                entry = candidates[0] if len(candidates) == 1 else None

    # If we have a segment constraint, ensure it matches the expected one
    if entry and segment_id is not None:
        expected_seg = entry.get("segment")
        if expected_seg is not None and expected_seg != segment_id:
            return None
    return entry


def get_vanilla_name(commands, default_name, segment_id=None, addr_hint=None):
    # Get vanilla name for a display list, or return default if no match
    match = match_display_list(commands, segment_id=segment_id, addr_hint=addr_hint)
    if match:
        # Just return the name - it already includes actor prefix
        name = match.get("name", "")
        if name:
            return name  # Early return - exact match found, skip fuzzy matching

    # Try Fuzzy Match only if exact match failed
    fuzzy_name, confidence = find_best_match(commands, type="dl", addr_hint=addr_hint)
    if fuzzy_name:
        # Check segment constraint if provided
        # (This is tricky because fuzzy match might find the same DL in a different segment if it was moved)
        # For now, we trust the fuzzy match if confidence is high enough
        return fuzzy_name

    return default_name


def normalize_geo_for_matching(commands, dl_names):
    # Normalize geo commands for matching
    normalized = []

    for idx, cmd in enumerate(commands):
        cmd_type = cmd.get("type", cmd.get("cmd", ""))
        norm_cmd = {"type": cmd_type, "pos": idx}

        # Include structural information
        if cmd_type == "GEO_DISPLAY_LIST":
            # Reference DL by its name (which might be vanilla matched)
            layer = cmd.get("layer")
            dl_name = cmd.get("dl_name")
            if layer:
                norm_cmd["layer"] = layer
            if dl_name:
                # Use the cleaned display list name for matching
                dl_ref = dl_names.get(dl_name, dl_name)
                if _dl_name_to_hash is None:
                    load_databases()
                assert _dl_name_to_hash is not None
                dl_hash = _dl_name_to_hash.get(dl_ref)
                if dl_hash:
                    norm_cmd["dl_hash"] = dl_hash
                else:
                    norm_cmd["dl_ref"] = dl_ref
        elif cmd_type == "GEO_CULLING_RADIUS":
            data = cmd.get("data", [])
            if data:
                radius = data[0] & 0xFFFF
                norm_cmd["data"] = [radius]
        elif cmd_type in ["GEO_SHADOW", "GEO_SCALE", "GEO_BACKGROUND", "GEO_BACKGROUND_COLOR"]:
            data = cmd.get("data", [])
            if not data:
                pass
            elif cmd_type == "GEO_SHADOW":
                if len(data) >= 2:
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
        elif cmd_type in ["GEO_SWITCH_CASE", "GEO_ASM"]:
            # Include parameter but not function address
            if "param" in cmd:
                norm_cmd["param"] = cmd["param"]
        elif cmd_type in [
            "GEO_TRANSLATE_ROTATE",
            "GEO_ANIMATED_PART",
            "GEO_ROTATION_NODE",
            "GEO_TRANSLATE_NODE",
        ]:
            # Note presence but ignore specific values
            norm_cmd["has_transform"] = True
        elif cmd_type == "GEO_BRANCH":
            norm_cmd["has_branch"] = True

        normalized.append(norm_cmd)

    # Include overall length to reduce collisions
    normalized.append({"type": "__len__", "len": len(commands)})

    return normalized


def hash_geo(normalized_commands):
    cmd_str = json.dumps(normalized_commands, sort_keys=True)
    return hashlib.sha256(cmd_str.encode()).hexdigest()


def match_geo(commands, dl_names):
    # Match a geo layout against the vanilla database
    # Ensure database is loaded
    if _geo_database is None:
        load_databases()

    # Normalize and hash
    normalized = normalize_geo_for_matching(commands, dl_names)
    geo_hash = hash_geo(normalized)

    # Look up in database
    if _geo_database is None:
        return None
    entry = _geo_database.get(geo_hash)
    if isinstance(entry, list):
        if len(entry) == 1:
            return entry[0]
        # Disambiguate collisions by rescoring with child DL info
        best = None
        best_score = -1
        for candidate in entry:
            score = score_geo_similarity(
                commands, candidate, dl_names, complexity=get_geo_complexity(commands)
            )
            if score > best_score:
                best_score = score
                best = candidate
        return best if best_score >= 0.99 else None
    return entry


def is_in_coop(name, is_level):
    import dynos_builtins

    if is_level:
        return name in dynos_builtins.gDynosBuiltinLvlGeos
    else:
        return name in dynos_builtins.gDynosBuiltinActors


def get_vanilla_geo_name(commands, dl_names, default_name, addr_hint=None, is_level=False):
    # Get vanilla name for a geo layout, or return default if no match
    match = match_geo(commands, dl_names)
    if match:
        # Just return the name - it already includes actor prefix
        name = match.get("name", "")
        if name and is_in_coop(name, is_level):
            return name  # Early return - exact match found, skip fuzzy matching

    # Try Fuzzy Match only if exact match failed
    fuzzy_name, confidence = find_best_match(
        commands, type="geo", dl_names=dl_names, addr_hint=addr_hint
    )
    if fuzzy_name and is_in_coop(fuzzy_name, is_level):
        # print(f"Fuzzy matched {fuzzy_name} with {confidence*100:.1f}% confidence")
        return fuzzy_name

    return default_name


# --- 1. GEO MATCHING ---


def generate_geo_skeleton(commands):
    # Creates a structural string representing the Geo Layout
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


def get_geo_params(commands):
    # Extract parameter values from geo commands for simple structure matching
    params = {}

    for i, cmd in enumerate(commands):
        t = cmd.get("type", "")

        data = cmd.get("data", [])
        if t == "GEO_CULLING_RADIUS" and data:
            radius = data[0] & 0xFFFF
            params[f"cull_{i}"] = radius

        elif t == "GEO_SHADOW" and len(data) >= 2:
            s_type = data[0] & 0xFFFF
            solidity = (data[1] >> 16) & 0xFFFF
            scale = data[1] & 0xFFFF
            params[f"shadow_{i}"] = f"{s_type}_{solidity}_{scale}"
        elif t == "GEO_SHADOW" and data:
            # Fallback when only solidity/scale were captured
            solidity = data[0] & 0xFFFF
            scale = data[-1] & 0xFFFF
            params[f"shadow_{i}"] = f"0_{solidity}_{scale}"

        elif t == "GEO_SCALE" and len(data) >= 2:
            params[f"scale_{i}"] = data[1]

        elif t == "GEO_BACKGROUND_COLOR" and data:
            params[f"bg_{i}"] = data[0] & 0xFFFF
        elif t == "GEO_BACKGROUND" and len(data) >= 1:
            params[f"bg_{i}"] = data[0] & 0xFFFF

        # Can add more parameter types here if needed

    return params


def score_geo_similarity(
    found_cmds, vanilla_entry, dl_names=None, found_skel=None, found_asms=None, complexity=0
):
    # Returns a score (0.0 - 1.0) indicating likelihood of match
    # 1. Structural Comparison (High Weight)
    if found_skel is None:
        found_skel = generate_geo_skeleton(found_cmds)
    vanilla_skel = vanilla_entry.get("skeleton", "")

    # Use cached SequenceMatcher to handle slight insertions/deletions of nodes
    struct_score = _sequence_ratio(found_skel, vanilla_skel)

    # Immediate reject for very low complexity if structure differs
    if complexity < 5 and struct_score < 1.0:
        return 0.0

    # 2. ASM Function Check (Very High Weight if present)
    # If the geo uses GEO_ASM, the function index/pointer is usually a dead giveaway
    # even if the model is changed.
    if found_asms is None:
        found_asms = [
            c.get("param") for c in found_cmds if c.get("type") == "GEO_ASM" and "param" in c
        ]
    vanilla_asms = vanilla_entry.get("asm_funcs", [])

    asm_penalty = 0
    if found_asms and vanilla_asms:
        # If ASMs don't match, this is likely a different actor with same structure
        # (e.g. Goomba vs Bob-omb often share simple structures but different logic)
        # Note: params are strings in found_cmds but might be ints/strings in DB depending on parsing
        # Normalize to string for comparison
        found_asms_str = [str(x) for x in found_asms]
        vanilla_asms_str = [str(x) for x in vanilla_asms]

        if found_asms_str != vanilla_asms_str:
            return 0.0

    # 3. Parameter Check (For Simple Structures)
    # If the skeleton is very short, check parameter values
    param_penalty = 0.0
    found_params = get_geo_params(found_cmds)
    vanilla_params = vanilla_entry.get("params", {})
    if found_params and vanilla_params:
        total = 0
        matches = 0
        # Compare by key first for strict matches
        for key, value in found_params.items():
            if key in vanilla_params:
                total += 1
                if vanilla_params[key] == value:
                    matches += 1
        # Fall back to value-multiset comparison for low complexity cases
        if complexity < 10 and total == 0:
            total = len(found_params)
            valset = list(vanilla_params.values())
            for v in found_params.values():
                if v in valset:
                    matches += 1
                    valset.remove(v)
        if total > 0 and matches != total:
            param_penalty = 0.5 if complexity < 10 else 0.1

    # 4. Child Display List Check (Tie-Breaker)
    dl_bonus = 0.0
    if dl_names and "child_dl_hashes" in vanilla_entry:
        vanilla_child_hashes = set(vanilla_entry["child_dl_hashes"])
        if vanilla_child_hashes:
            # Count how many GEO_DISPLAY_LIST commands we found
            found_dl_count = sum(1 for c in found_cmds if c.get("type") == "GEO_DISPLAY_LIST")

            # Resolve found DL names to vanilla hashes
            found_child_hashes = []
            for c in found_cmds:
                if c.get("type") == "GEO_DISPLAY_LIST" and "dl_name" in c:
                    name = c["dl_name"]
                    vanilla_name = dl_names.get(name, name)
                    if _dl_name_to_hash is None:
                        load_databases()
                    assert _dl_name_to_hash is not None
                    v_hash = _dl_name_to_hash.get(vanilla_name)
                    if v_hash:
                        found_child_hashes.append(v_hash)

            overlap = vanilla_child_hashes.intersection(found_child_hashes)
            if not overlap and found_child_hashes:
                # If we know child DLs and none match, reject low/medium complexity outright
                if complexity < 25:
                    return 0.0
            elif not overlap and not found_child_hashes and found_dl_count > 0:
                # Found geo has DL commands, but none could be resolved to vanilla hashes.
                # This strongly suggests custom/hack DLs, not a vanilla geo.
                # Reject for level area geos (high complexity but with DLs).
                if complexity < 50:
                    return 0.0
            elif overlap:
                # Boost confidence based on overlap count
                dl_bonus = min(0.25, 0.1 + 0.05 * len(overlap))

    # Child DL name check to disambiguate collisions (e.g., tree variants)
    if dl_names and vanilla_entry.get("child_dl_names"):
        vanilla_child_names = set(vanilla_entry["child_dl_names"])
        found_child_names = set()
        for c in found_cmds:
            if c.get("type") == "GEO_DISPLAY_LIST" and "dl_name" in c:
                found_child_names.add(dl_names.get(c["dl_name"], c["dl_name"]))
        name_overlap = vanilla_child_names.intersection(found_child_names)
        if not name_overlap and found_child_names and complexity < 25:
            return 0.0
        if name_overlap:
            dl_bonus += min(0.1, 0.05 * len(name_overlap))

    return max(0, struct_score - asm_penalty - param_penalty + dl_bonus)


# --- 2. DISPLAY LIST MATCHING ---


def get_dl_fingerprint(commands):
    # Generates a statistical dictionary for the display list
    commands = _coalesce_texture_loads(commands)
    stats: Dict[str, Any] = {
        "vertex_count": 0,
        "tri_count": 0,
        "texture_loads": 0,
        "tex_signature": [],  # List of strings like "RGBA16_32x32"
        "mode_signature": [],  # Sequence of mode changes to disambiguate generic setups
    }

    for cmd in commands:
        t = cmd.get("type", "")

        if "Vertex" in t:
            # Normalize count based on command type logic (extracted in your parser)
            count = cmd.get("count")
            if count is None:
                w0 = cmd.get("w0")
                if w0 is not None:
                    count = ((w0 >> 12) & 0xFF) or (((w0 >> 20) & 0xF) + 1)
            if count is None:
                count = 0
            stats["vertex_count"] += count

        elif "Triangle" in t:
            # Count actual triangles (1 or 2)
            n = 2 if "2Triangles" in t else 1
            stats["tri_count"] += n

        elif t in ["gsDPSetTextureImage", "gsDPLoadTextureBlock", "gsDPLoadBlock"]:
            stats["texture_loads"] += 1
            # Add to signature
            w0 = cmd.get("w0")
            fmt = cmd.get("fmt")
            siz = cmd.get("siz")
            width = cmd.get("width")
            tex_id = cmd.get("tex_id")
            if fmt is None and w0 is not None:
                fmt = (w0 >> 21) & 0x7
            if siz is None and w0 is not None:
                siz = (w0 >> 19) & 0x3
            if width is None and w0 is not None and t == "gsDPSetTextureImage":
                width = (w0 & 0xFFF) + 1
            if tex_id is None:
                w1 = cmd.get("w1")
                if w1 is not None:
                    tex_id = f"0x{w1:08X}"
            fmt = "?" if fmt is None else fmt
            siz = "?" if siz is None else siz
            width = "?" if width is None else width
            tex_id = _normalize_tex_id(tex_id) if tex_id is not None else "?"
            stats["tex_signature"].append(f"{fmt}_{siz}_{width}_{tex_id}")

        # Capture rendering state changes to differentiate generic lists
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
            if modes is None and t == "gsSPTexture":
                w0 = cmd.get("w0")
                w1 = cmd.get("w1")
                if w0 is not None and w1 is not None:
                    s_val = (w1 >> 16) & 0xFFFF
                    t_val = w1 & 0xFFFF
                    level = (w0 >> 11) & 0x7
                    modes = [s_val, t_val, level]
            if modes:
                stats["mode_signature"].append((t, _freeze(modes)))

    return stats


def score_dl_similarity(found_cmds, vanilla_entry, found_fp=None, complexity=0):
    if found_fp is None:
        found_fp = get_dl_fingerprint(found_cmds)
    vanilla_fp = vanilla_entry.get("fingerprint", {})

    if not vanilla_fp:
        return 0.0

    # 1. Texture Signature Match (Highest Confidence)
    # If they load the same sequence of texture types, it's almost certainly the same DL
    # even if vertices moved.
    sig_score = 0.0
    has_textures = len(found_fp["tex_signature"]) > 0
    van_tex = vanilla_fp.get("tex_signature")
    if has_textures and van_tex:
        sig_score = _sequence_ratio(tuple(found_fp["tex_signature"]), tuple(van_tex))
    elif not has_textures and not van_tex:
        sig_score = 1.0
    else:
        return 0.0  # One has textures, the other doesn't.

    # 1b. Mode signature (combine/tile/render) alignment helps disambiguate generic tex loads
    mode_score = 0.0
    if found_fp.get("mode_signature") and vanilla_fp.get("mode_signature"):
        mode_score = _sequence_ratio(
            tuple(found_fp["mode_signature"]), tuple(vanilla_fp["mode_signature"])
        )
    elif not found_fp.get("mode_signature") and not vanilla_fp.get("mode_signature"):
        mode_score = 1.0
    else:
        mode_score = 0.0

    # 2. Geometric Density Match
    # Compare vertex/tri ratios. Allow for ~20% modification.
    def get_ratio_score(val1, val2):
        if val1 == 0 and val2 == 0:
            return 1.0
        if val1 == 0 or val2 == 0:
            return 0.0
        diff = abs(val1 - val2)
        avg = (val1 + val2) / 2
        return max(0, 1 - (diff / avg))

    v_found = found_fp["vertex_count"]
    v_vanilla = vanilla_fp.get("vertex_count", 0)

    # STRICT CHECK for Low Complexity DLs
    if complexity < 10:
        if abs(v_found - v_vanilla) > 1:
            return 0.0
        if not has_textures and v_found == 0:
            if abs(len(found_cmds) - vanilla_entry.get("stats", {}).get("command_count", 0)) > 1:
                return 0.0

    # Penalize extremely generic, texture-less tiny lists unless they match counts exactly
    if not has_textures and v_found <= 4 and found_fp["tri_count"] <= 4:
        if v_found != v_vanilla or found_fp["tri_count"] != vanilla_fp.get("tri_count", 0):
            return 0.0

    vtx_score = get_ratio_score(v_found, v_vanilla)
    tri_score = get_ratio_score(found_fp["tri_count"], vanilla_fp.get("tri_count", 0))

    # Weighted final score
    return (sig_score * 0.55) + (mode_score * 0.15) + (vtx_score * 0.15) + (tri_score * 0.15)


# --- MASTER FINDER ---


def find_best_match(commands, type="geo", dl_names=None, addr_hint=None):
    # Iterates database and finds best fuzzy match with dynamic thresholds and complexity penalties
    if _dl_database is None or _geo_database is None:
        load_databases()

    # 1. Calculate content hash for cache key (exclude addr_hint)
    if type == "dl":
        normalized = normalize_display_list_for_matching(commands)
        content_hash = ("dl", hash_display_list(normalized))
    else:
        normalized = normalize_geo_for_matching(commands, dl_names or {})
        content_hash = ("geo", hash_geo(normalized))

    # 2. Retrieve or compute base candidates (without addr_hint bonus)
    if content_hash in _fuzzy_match_cache:
        base_candidates = _fuzzy_match_cache[content_hash]
    else:
        entries_list = _geo_entries if type == "geo" else _dl_entries

        # Calculate complexity/entropy
        if type == "geo":
            complexity = get_geo_complexity(commands)
            fp = None
        else:
            fp = get_dl_fingerprint(commands)
            complexity = get_dl_complexity(fp)

        # Dynamic thresholds based on complexity
        if complexity < 5:
            threshold = 0.99
        elif complexity < 15:
            threshold = 0.95
        else:
            threshold = 0.85

        # Prepare artifacts once
        found_fp = None
        found_skel = None
        found_asms = None
        if type == "dl":
            found_fp = fp
        else:
            found_skel = generate_geo_skeleton(commands)
            found_asms = [
                c.get("param") for c in commands if c.get("type") == "GEO_ASM" and "param" in c
            ]

        # Flatten DB into unique entries (precomputed)
        assert entries_list is not None
        unique_entries = {e["name"]: e for e in entries_list}.values()

        cmd_len = len(commands)
        base_candidates = []

        for entry in unique_entries:
            v_len = entry.get("stats", {}).get("command_count", 0)

            # Length filters tuned by complexity
            if complexity < 10:
                if abs(v_len - cmd_len) > 2:
                    continue
            else:
                if v_len < cmd_len * 0.5 or v_len > cmd_len * 1.5:
                    continue

            if type == "geo":
                score = score_geo_similarity(
                    commands, entry, dl_names, found_skel, found_asms, complexity
                )
            else:
                score = score_dl_similarity(commands, entry, found_fp, complexity)

            if score >= threshold:
                base_candidates.append((score, entry))

        # Cache the base results
        _fuzzy_match_cache[content_hash] = base_candidates

    # 3. Apply address hint bonus and select best match
    if not base_candidates:
        return None, 0.0

    final_candidates = []
    addr_hex = f"{addr_hint:08X}" if addr_hint is not None else None

    for score, entry in base_candidates:
        final_score = score
        if addr_hex and addr_hex in entry.get("name", ""):
            final_score += 0.02
        final_candidates.append((final_score, entry))

    final_candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_candidate = final_candidates[0]

    # Get complexity again for ambiguity check (could be cached too, but it's fast)
    if type == "geo":
        complexity = get_geo_complexity(commands)
    else:
        # We don't have fp here if it was cached, so recompute or simplify
        # Recomputing complexity is cheap compared to scoring
        if type == "dl":
            fp = get_dl_fingerprint(commands)
            complexity = get_dl_complexity(fp)

    # Ambiguity handling: for low/medium complexity, require clear winner
    if len(final_candidates) > 1:
        second_score, second_candidate = final_candidates[1]
        if (best_score - second_score) < 0.02 and complexity < 15:
            if (
                not addr_hex
                or addr_hex not in best_candidate["name"]
                or addr_hex in second_candidate.get("name", "")
            ):
                return None, 0.0

    return best_candidate["name"], best_score


def match_geo_precisely(h: str) -> Optional[str]:
    if _geo_database is None:
        load_databases()
    assert _geo_database is not None
    entry = _geo_database.get(h)
    if entry:
        if isinstance(entry, list) and len(entry) > 0:
            return entry[0].get("name")
        return cast(Dict[str, Any], entry).get("name")
    return None


def match_geo_fuzzily(h: str) -> Optional[str]:
    # This is a bit of a placeholder since find_best_match
    # usually takes the command list, not just a hash.
    # But for now, we'll just return None if precision failed,
    # or implement a real fuzzy lookup if we had the commands.
    return None


# Load databases on module import
load_databases()
