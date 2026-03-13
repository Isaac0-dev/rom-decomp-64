import struct
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Any

from segment import get_segment
from utils import debug_print

# SM64 text encoding map (US)
TEXT_MAP = {
    0x50: "^",
    0x51: "|",
    0x52: "<",
    0x53: ">",
    0x3E: "'",
    0x3F: ".",
    0x54: "[A]",
    0x55: "[B]",
    0x56: "[C]",
    0x57: "[Z]",
    0x58: "[R]",
    0x6F: ",",
    0x9E: " ",
    0x9F: "-",
    0xD0: "/",
    0xD1: "the",
    0xD2: "you",
    0xDE: "the",
    0xDF: "you",
    0xE0: "^",  # legacy aliases
    0xE1: "|",
    0xE2: "<",
    0xE3: ">",
    0xE4: "[A]",
    0xE5: "[B]",
    0xE6: "[C]",
    0xE7: "[Z]",
    0xE8: "[R]",
    0xE9: "[C-Down]",
    0xEA: "[C-Up]",
    0xEB: "[C-Left]",
    0xEC: "[C-Right]",
    0xF0: "゛",
    0xF1: "゜",
    0xF2: "!",
    0xF3: "%",
    0xF4: "?",
    0xF5: "『",
    0xF6: "』",
    0xF7: "~",
    0xF8: "…",
    0xF9: "$",
    0xFA: "★",
    0xFB: "×",
    0xFC: "・",
    0xFD: "☆",
    0xFE: "\\n\\\\\n",  # Dialog line break
}

# Mapping from course index to macro name used in decomp headers
COURSE_MACRO_NAMES = {
    0: "COURSE_BOB",
    1: "COURSE_WF",
    2: "COURSE_JRB",
    3: "COURSE_CCM",
    4: "COURSE_BBH",
    5: "COURSE_HMC",
    6: "COURSE_LLL",
    7: "COURSE_SSL",
    8: "COURSE_DDD",
    9: "COURSE_SL",
    10: "COURSE_WDW",
    11: "COURSE_TTM",
    12: "COURSE_THI",
    13: "COURSE_TTC",
    14: "COURSE_RR",
    15: "COURSE_BITDW",
    16: "COURSE_BITFS",
    17: "COURSE_BITS",
    18: "COURSE_PSS",
    19: "COURSE_COTMC",
    20: "COURSE_TOTWC",
    21: "COURSE_BOWSER_1",
    22: "COURSE_WMOTR",
    23: "COURSE_BOWSER_2",
    24: "COURSE_BOWSER_3",
    25: "COURSE_SA",
}


DECODE_TABLE: List[Optional[str]] = [None] * 256
for val in range(256):
    if val == 0xFF:
        continue  # handled by caller
    if val < 0x0A:
        DECODE_TABLE[val] = chr(val + 0x30)
    elif val < 0x24:
        DECODE_TABLE[val] = chr(val + 0x37)
    elif val < 0x3E:
        DECODE_TABLE[val] = chr(val + 0x3D)
    else:
        DECODE_TABLE[val] = TEXT_MAP.get(val)


def _decode_string(seg2, offset, max_len=800):
    seg_len = len(seg2)
    if offset < 0 or offset >= seg_len:
        return None

    # Find string terminator within the buffer
    end_limit = offset + max_len
    if end_limit > seg_len:
        end_limit = seg_len
    end_pos = seg2.find(b"\xff", offset, end_limit)
    if end_pos == -1:
        return None

    # Decode the string
    chars: List[str] = []
    table = DECODE_TABLE
    if isinstance(seg2, memoryview):
        raw_source = seg2[offset:end_pos]
    else:
        raw_source = seg2[offset:end_pos]

    for b in raw_source:
        ch = table[b]
        if ch is None:
            return None
        chars.append(ch)
    return "".join(chars)


_text_executor = ThreadPoolExecutor(max_workers=os.cpu_count())


def _parse_dialog_entry(seg2, entry_offset):
    if entry_offset + 16 > len(seg2):
        return None
    entry = seg2[entry_offset : entry_offset + 16]
    unused = struct.unpack(">I", entry[0:4])[0]
    lines_per_box = entry[4]
    left_offset = struct.unpack(">H", entry[6:8])[0]
    width = struct.unpack(">H", entry[8:10])[0]
    text_ptr = struct.unpack(">I", entry[12:16])[0]

    if lines_per_box == 0 or lines_per_box > 10:
        return None
    if left_offset > 400 or width == 0 or width > 400:
        return None
    if (text_ptr >> 24) != 0x02:
        return None
    text_off = text_ptr & 0xFFFFFF
    text = _decode_string(seg2, text_off)
    if text is None or len(text) == 0:
        return None

    return unused, lines_per_box, left_offset, width, text_ptr, text


def _find_dialog_table(seg2, min_entries=10, max_entries=500):
    best_offset = None
    best_entries: List[Any] = []
    for offset in range(0, len(seg2) - 16 * min_entries, 4):
        entries: List[Any] = []
        pos = offset
        while pos + 16 <= len(seg2) and len(entries) < max_entries:
            parsed = _parse_dialog_entry(seg2, pos)
            if not parsed:
                break
            entries.append(parsed)
            pos += 16
        if len(entries) > len(best_entries):
            best_entries = entries
            best_offset = offset
    if best_offset is None or len(best_entries) < min_entries:
        debug_print(f"WARNING: Not enough entries in dialog table {len(best_entries)}")
        return None
    return best_offset, best_entries


def _score_course_strings(strings):
    score = 0
    for s in strings:
        if any(c in s for c in (" ", "-", "'")):
            score += 2
        if len(s) > 8:
            score += 1
        if s.lstrip().startswith(tuple(str(i) for i in range(1, 10))):
            score += 3
    return score


def _looks_like_courses(strings, act_strings=None):
    if not strings or len(strings) != 26:
        return False
    uniq = len(set(strings))
    digit_starts = sum(1 for s in strings if s.lstrip()[:1].isdigit())
    course_word = sum(1 for s in strings if s.strip().upper().startswith("COURSE"))
    spaced = sum(" " in s for s in strings)
    if act_strings:
        if len(set(strings).intersection(act_strings)) >= 8:
            return False
    return uniq >= 20 and (
        digit_starts >= 3 or course_word >= 3 or (digit_starts >= 1 and spaced >= 20)
    )


def _find_pointer_table(seg2, count, max_len, start=0, scorer=None, min_len=1):
    end = len(seg2) - count * 4
    best = None
    best_score = -1
    for offset in range(start, end + 1, 4):
        strings = []
        ok = True
        for i in range(count):
            ptr = struct.unpack(">I", seg2[offset + 4 * i : offset + 4 * (i + 1)])[0]
            if (ptr >> 24) != 0x02:
                ok = False
                break
            str_off = ptr & 0xFFFFFF
            s = _decode_string(seg2, str_off, max_len=max_len)
            if s is None or len(s) < min_len:
                ok = False
                break
            strings.append(s)
        if ok:
            score = scorer(strings) if scorer else 0
            if score > best_score:
                best_score = score
                best = (offset, strings)
    return best


def _read_pointer_table(seg2, start, count, max_len):
    if start < 0 or start + count * 4 > len(seg2):
        return None
    strings = []
    for i in range(count):
        ptr = struct.unpack(">I", seg2[start + 4 * i : start + 4 * (i + 1)])[0]
        if (ptr >> 24) != 0x02:
            return None
        str_off = ptr & 0xFFFFFF
        s = _decode_string(seg2, str_off, max_len=max_len)
        if s is None or len(s) == 0:
            return None
        strings.append(s)
    return strings


def _find_extras_pointer(seg2, acts, courses):
    import re

    def _clean(s):
        s = s.lstrip(" 0")
        return re.sub(r"^[^A-Za-z]+", "", s)

    act_set = set(_clean(s) for s in (acts or []))
    course_set = set(_clean(s) for s in (courses or []))
    best = None
    best_score = -1
    end = len(seg2) - 7 * 4
    for off in range(0, end, 4):
        strings = _read_pointer_table(seg2, off, 7, max_len=80)
        if not strings:
            continue
        if len(set(strings)) < 7:
            continue
        if act_set and len(act_set.intersection(strings)) > 1:
            continue
        if course_set and len(course_set.intersection(strings)) > 1:
            continue
        score = sum(len(s) for s in strings) + 5 * sum(" " in s for s in strings)
        if score > best_score:
            best_score = score
            best = strings
    return best


def _find_sequential_strings(seg2, anchor_text, count, cleaner):
    for off in range(len(seg2)):
        raw = _decode_string(seg2, off)
        if raw is None:
            continue
        if cleaner(raw) != anchor_text:
            continue

        strings = []
        cur = off
        for _ in range(count):
            s = _decode_string(seg2, cur)
            if s is None:
                break
            strings.append(cleaner(s))
            terminator = seg2.find(b"\xff", cur)
            if terminator == -1:
                break
            cur = terminator + 1
        if len(strings) == count:
            return cur, strings
    return None


def _find_sequential_block(seg2, start, count, max_len, min_len=1):
    best = None
    best_score = -1
    for off in range(start, len(seg2)):
        strings = []
        cur = off
        score = 0
        for _ in range(count):
            s = _decode_string(seg2, cur, max_len=max_len)
            if s is None or len(s) < min_len:
                break
            strings.append(s)
            score += len(s)
            term = seg2.find(b"\xff", cur)
            if term == -1:
                break
            cur = term + 1
        if len(strings) == count and score > best_score:
            best_score = score
            best = (off, strings)
    return best


def _read_sequential_at(seg2, start, count, max_len, min_len=1):
    strings = []
    cur = start
    for _ in range(count):
        s = _decode_string(seg2, cur, max_len=max_len)
        if s is None or len(s) < min_len:
            return None
        strings.append(s)
        term = seg2.find(b"\xff", cur)
        if term == -1:
            return None
        cur = term + 1
    return strings


def export_text(rom, output_manager=None, output_dir: Optional[str] = None):
    rom_bytes = getattr(rom, "_data", rom)
    if not isinstance(rom_bytes, (bytes, bytearray, memoryview)):
        try:
            rom_bytes = bytes(rom)
        except Exception:
            debug_print("export_text: Unable to read ROM bytes; skipping text export.")
            return

    seg2 = get_segment(2)
    if seg2 is None:
        debug_print("export_text: Segment 2 not loaded; skipping text export.")
        return

    dialog_info = _find_dialog_table(seg2)
    if not dialog_info:
        debug_print("export_text: Failed to locate dialog table in segment 2.")
        return
    dialog_offset, dialogs = dialog_info
    search_start = dialog_offset + len(dialogs) * 16

    # Locate course names, act names, and extra text strings (sequential in segment 2)
    # Check several different layouts, as hacks can put strings nearly anywhere
    course_table = _find_pointer_table(
        seg2, 26, max_len=80, min_len=3, scorer=_score_course_strings
    )
    course_seq = None
    course_strings = None
    if course_table and _looks_like_courses(course_table[1]):
        course_seq = (course_table[0], course_table[1])
        course_strings = course_table[1]

    anchor_seq = _find_sequential_strings(
        seg2, " 1 BOB-OMB BATTLEFIELD", 26, cleaner=lambda s: s.lstrip("0")
    )
    if anchor_seq and _looks_like_courses(anchor_seq[1]):
        course_seq = anchor_seq
        course_strings = anchor_seq[1]

    if not course_strings:
        block = _find_sequential_block(seg2, search_start, 26, max_len=80, min_len=1)
        if block and _looks_like_courses(block[1]):
            course_seq = block
            course_strings = block[1]
    if not course_strings:
        # Fallback to vanilla-relative offsets from dialog table
        fallback_start = dialog_offset + 0xD4F
        if fallback_start < len(seg2):
            seq = _read_sequential_at(seg2, fallback_start, 26, max_len=80, min_len=1)
            if seq and _looks_like_courses(seq):
                course_seq = (fallback_start, seq)
                course_strings = seq
    if not course_strings:
        # Try pointer table heuristic (non-anchored)
        table = _find_pointer_table(seg2, 26, max_len=80, min_len=1)
        if table and _looks_like_courses(table[1]):
            course_seq = (table[0], table[1])
            course_strings = table[1]

    act_seq = _find_sequential_strings(
        seg2, "BIG BOB-OMB ON THE SUMMIT", 15 * 6, cleaner=lambda s: s.lstrip(" 0")
    )
    act_strings = act_seq[1] if act_seq else None
    if not act_strings:
        start_for_act = min(course_seq[0], search_start) if course_seq else search_start
        block = _find_sequential_block(seg2, start_for_act, 15 * 6, max_len=80, min_len=1)
        if block:
            act_seq = block
            act_strings = block[1]
    if not act_strings:
        # Fallback relative to dialog/course offsets (vanilla spacing)
        fallback_act_start = (course_seq[0] if course_seq else dialog_offset) + 0x24F
        if fallback_act_start < len(seg2):
            seq = _read_sequential_at(seg2, fallback_act_start, 15 * 6, max_len=80, min_len=1)
            if seq:
                act_seq = (fallback_act_start, seq)
                act_strings = seq
    if not act_strings:
        # Try pointer table heuristic (non-anchored)
        table = _find_pointer_table(seg2, 15 * 6, max_len=80, min_len=1)
        if table:
            act_seq = (table[0], table[1])
            act_strings = table[1]

    # fallback for if we can't find the course names
    # or the "course names" are actually just clones of act names
    if course_strings is None and act_strings:
        course_strings = [f"Course {i + 1}" for i in range(26)]
    if course_strings and act_strings:
        overlap = len(set(course_strings).intersection(act_strings))
        if overlap >= 20 or (overlap >= 6 and not _looks_like_courses(course_strings, act_strings)):
            course_strings = [f"Course {i + 1}" for i in range(26)]

    extra_strings = None

    def _extras_ok(cand):
        import re

        def _clean(s):
            s = s.lstrip(" 0")
            return re.sub(r"^[^A-Za-z]+", "", s)

        cand_set = set(_clean(s) for s in cand)
        if cand is None:
            return False
        if act_strings:
            act_set = set(_clean(s) for s in act_strings)
            if len(cand_set.intersection(act_set)) > 0:
                return False
        return True

    if act_seq:
        extras: List[str] = []
        cur = act_seq[0]
        while len(extras) < 7 and cur < len(seg2):
            s = _decode_string(seg2, cur, max_len=128)
            if s is None:
                break
            extras.append(s.lstrip(" 0"))
            term = seg2.find(b"\xff", cur)
            if term == -1:
                break
            cur = term + 1
        if extras:
            extra_strings = extras
    if extra_strings is None:
        start_for_extra = act_seq[0] if act_seq else (course_seq[0] if course_seq else search_start)
        block = _find_sequential_block(seg2, start_for_extra, 7, max_len=80, min_len=1)
        if block and _extras_ok(block[1]):
            extra_strings = [s.lstrip(" 0") for s in block[1]]
    if extra_strings is None:
        table = _find_extras_pointer(seg2, act_strings, course_strings)
        if table and _extras_ok(table):
            extra_strings = [s.lstrip(" 0") for s in table]
    if extra_strings is None:
        fallback_extra_start = (act_seq[0] if act_seq else dialog_offset) + 0xD77
        if fallback_extra_start < len(seg2):
            seq = _read_sequential_at(seg2, fallback_extra_start, 7, max_len=80, min_len=1)
            if seq and _extras_ok(seq):
                extra_strings = [s.lstrip(" 0") for s in seq]
    # Drop extras if they look identical to act names
    if extra_strings and act_strings:
        import re

        act_clean = set(re.sub(r"^[^A-Za-z]+", "", s.lstrip(" 0")) for s in act_strings)
        extra_clean = set(re.sub(r"^[^A-Za-z]+", "", s.lstrip(" 0")) for s in extra_strings)
        if len(extra_clean.intersection(act_clean)) >= 3:
            extra_strings = None

    def sanitize_dialog_or_act(s):
        import re

        zero_runs = list(re.finditer(r"0{3,}", s))
        if zero_runs:
            s = s[zero_runs[-1].end() :]
        s = s.lstrip(" 0")
        s = re.sub(r"^[^A-Za-z]+", "", s)
        return s

    def sanitize_course(s):
        import re

        zero_runs = list(re.finditer(r"0{3,}", s))
        if zero_runs:
            s = s[zero_runs[-1].end() :]
        s = s.strip()
        if s and s[0].isdigit():
            s = f" {s}"
        s = re.sub(r"^[^A-Za-z0-9 ]+", "", s)
        return s

    def lua_escape(s):
        s = sanitize_dialog_or_act(s)
        s = s.replace("\\n", "").replace("\\\\", "\\")
        if "]]" not in s:
            return f'("{s}")'
        return s

    if output_manager:
        lua_dialog_lines: list[str] = []
        lua_course_lines: list[str] = []
        for idx, (unused, lines_per_box, left_offset, width, _ptr, text) in enumerate(dialogs):
            lua_dialog_lines.append(
                f"smlua_text_utils_dialog_replace(DIALOG_{idx:03d}, {unused}, {lines_per_box}, {left_offset}, {width}, {lua_escape(text)})\n"
            )
        if course_strings:
            for course_idx, name in enumerate(course_strings):
                macro = COURSE_MACRO_NAMES.get(course_idx, str(course_idx))
                if course_idx < 15 and act_strings:
                    acts = act_strings[course_idx * 6 : (course_idx + 1) * 6]
                    acts_fmt = ", ".join([lua_escape(act) for act in acts])
                    lua_course_lines.append(
                        f'smlua_text_utils_course_acts_replace({macro}, "{sanitize_course(name)}", {acts_fmt})\n'
                    )
                elif course_idx < 25:
                    lua_course_lines.append(
                        f'smlua_text_utils_secret_star_replace({course_idx}, "{sanitize_course(name)}")\n'
                    )
                else:
                    lua_course_lines.append(
                        f'smlua_text_utils_castle_secret_stars_replace("{sanitize_course(name)}")\n'
                    )
        if extra_strings:
            for i, extra in enumerate(extra_strings[:7]):
                lua_course_lines.append(
                    f"smlua_text_utils_extra_text_replace({i}, {lua_escape(extra)})\n"
                )

        output_manager.write_lua(lua_dialog_lines, "dialogs.lua")
        output_manager.write_lua(lua_course_lines, "courses.lua")


def export_text_async(rom, output_manager=None, output_dir: Optional[str] = None):
    future = _text_executor.submit(export_text, rom, output_manager, output_dir)
    if output_manager and hasattr(output_manager, "register_future"):
        try:
            output_manager.register_future(future)
        except Exception:
            pass
    return future
