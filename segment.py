from compression_util.compression import (
    CompressionType,
    detect_compression_type,
    decompress_by_type,
)
from utils import debug_print, debug_fail, segment_from_addr, offset_from_segment_addr
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple, Deque
from byteio import CustomBytesIO

sRom: Optional[CustomBytesIO] = None

sSegments: Dict[int, Dict[str, Any]] = {}
sSegmentLoadHooks: List[Callable] = []
_segment_cache: Dict[Tuple[str, int, int, int, bool], Dict[str, Any]] = {}

# Segment loading types.
# These only exist for testing purposes. Find the best method for all hacks (maybe switch between them?)
#   - strict:   never append/alias; every load replaces the segment (Quad64-like)
#   - extend:   only extend if the same segment is reloaded with a contiguous/overlapping range
#   - hack:     current behavior that can alias an append chunk to a different contiguous segment
SEG_LOAD_MODE: str = "extend"


def register_segment_load_hook(func: Callable, run_existing: bool = True) -> None:
    global sSegmentLoadHooks
    if func not in sSegmentLoadHooks:
        sSegmentLoadHooks.append(func)
    if run_existing:
        for seg_num, seg in list(sSegments.items()):
            try:
                func(seg_num, seg)
            except Exception as e:
                debug_print(f"DEBUG: segment load hook {func} failed for seg {seg_num:02X}: {e}")


def unregister_segment_load_hook(func: Callable) -> None:
    global sSegmentLoadHooks
    before = len(sSegmentLoadHooks)
    sSegmentLoadHooks = [f for f in sSegmentLoadHooks if f != func]
    after = len(sSegmentLoadHooks)
    if before == after:
        debug_fail(f"ERROR: Attempted to unregister unknown segment load hook {func}")


def wait_for_segment_load(func: Callable, segmented_addr: int, user_data: Tuple[Any, ...]) -> None:
    segment_from_addr(segmented_addr)

    def segment_wait_hook(seg_num: int, segment: Dict[str, Any]) -> None:
        if (
            segment["segmented_address"]
            <= segmented_addr
            < segment["segmented_address"] + segment["size"]
        ):
            # the segment we need is loaded, we can try to load the data now
            func(*user_data)
            unregister_segment_load_hook(segment_wait_hook)

    setattr(segment_wait_hook, "target_addr", segmented_addr)
    register_segment_load_hook(segment_wait_hook)


def seg_hooks_assert() -> None:
    if len(sSegmentLoadHooks) > 0:
        debug_print(f"ERROR: {len(sSegmentLoadHooks)} segment load hooks are still pending:")
        for hook in sSegmentLoadHooks:
            target = getattr(hook, "target_addr", "unknown")
            if isinstance(target, int):
                debug_print(
                    f"  - Hook for address 0x{target:08X} (Seg {segment_from_addr(target)})"
                )
            else:
                debug_print(f"  - Hook for address {target}")
    # Temporarily disabled to see if extraction completes otherwise
    # assert len(sSegmentLoadHooks) == 0, "ERROR: Segment load hooks are not empty."
    if len(sSegmentLoadHooks) > 0:
        debug_print("WARNING: Segment load hooks are not empty. Some textures may be missing.")


# ---------------------------------------------------------
# Pool Allocator (SM64-style stack allocator)
# ---------------------------------------------------------

# Pool management for segments
_segment_pool: Deque[Optional[Any]] = deque()


def push_pool_state() -> None:
    _segment_pool.append(None)
    # debug_print("DEBUG: Pushed segment pool state.")


# Pops everything from the pool
def pop_pool_state() -> None:
    if _segment_pool:
        _segment_pool.pop()  # discard saved snapshot; keep current segments alive
        # debug_print("DEBUG: Popped segment pool state (segments retained).")
    else:
        debug_print("DEBUG: Segment pool is empty. Cannot pop state.")


def segments_load_rom(data: CustomBytesIO) -> None:
    global sRom
    sRom = data
    sSegments.clear()
    _segment_cache.clear()


# ---------------------------------------------------------
# Segment Object
# ---------------------------------------------------------


class Segment:
    def __init__(
        self,
        bytes_data: bytes,
        segment_number: int,
        physical_start: int,
        physical_end: int,
        size: int,
    ) -> None:
        self.data: bytes = bytes_data
        self.segment_number: int = segment_number
        self.physical_start: int = physical_start
        self.physical_end: int = physical_end
        self.segmented_address: int = segment_number << 24
        self.size: int = size
        self.valid: bool = True

    def __repr__(self) -> str:
        return (
            f"Segment("
            f"segment_number={self.segment_number}, "
            f"physical_start=0x{self.physical_start:X}, "
            f"physical_end=0x{self.physical_end:X}, "
            f"size={self.size})"
        )

    def __str__(self) -> str:
        return (
            f"Segment {self.segment_number} (0x{self.segmented_address:08X}): "
            f"{self.size} bytes "
            f"(0x{self.physical_start:08X} – 0x{self.physical_end:08X})"
        )


# ---------------------------------------------------------
# Segment Loader (SM64-style)
# ---------------------------------------------------------


def find_contiguous_segment(rom_start: int) -> Optional[int]:
    global sSegments
    # debug_print(f"DEBUG: Checking for segment ending at 0x{rom_start:X}")
    for seg_num, seg_info in sSegments.items():
        # debug_print(f"  Segment 0x{seg_num:X} ends at 0x{seg_info['end']:X}")
        if seg_info["end"] == rom_start:
            debug_print(f"DEBUG: Found contiguous segment 0x{seg_num:X} ending at 0x{rom_start:X}")
            return seg_num
    return None


def append_to_segment(seg_num: int, data: bytes) -> None:
    global sSegments
    if seg_num in sSegments:
        sSegments[seg_num]["data"] += data
        sSegments[seg_num]["end"] += len(data)
        sSegments[seg_num]["size"] += len(data)
        debug_print(
            f"DEBUG: Appended {len(data)} bytes to segment 0x{seg_num:X}. New length {len(sSegments[seg_num]['data'])} bytes."
        )


def alias_segment(new_seg: int, existing_seg: int) -> None:
    global sSegments
    if existing_seg in sSegments:
        sSegments[new_seg] = sSegments[existing_seg]
        debug_print(f"DEBUG: Aliased Segment 0x{new_seg:X} to Segment 0x{existing_seg:X}")


def load_segment(seg_num: int, rom_start: int, rom_end: int, should_decompress: bool) -> None:
    global sSegments
    global sRom  # sRom is the global CustomBytesIO object for the entire ROM

    key = ("load", seg_num, rom_start, rom_end, should_decompress)

    # Cache hit: reuse previously loaded segment to avoid repeated I/O/decompress
    if key in _segment_cache:
        cached = _segment_cache[key]
        sSegments[seg_num] = {
            "start": cached["start"],
            "end": cached["end"],
            "data": cached["data"],
            "compression_type": cached["compression_type"],
            "segmented_address": cached["segmented_address"],
            "size": cached["size"],
        }
        return

    # Ensure sRom is available
    if sRom is None:
        raise Exception("Global ROM object (sRom) not set. Cannot load segment.")

    # Read data from the global ROM object
    prev_pos = sRom.tell()
    sRom.seek(rom_start)
    data = sRom.read(rom_end - rom_start)
    sRom.seek(prev_pos)

    # Auto-detect compression always (it could be different each time)
    compression_type = detect_compression_type(data)

    if should_decompress and compression_type == CompressionType.NONE:
        debug_fail(
            f"Compression format not supported for segment 0x{seg_num:X}. Header: 0x{data[:4]:08X}"
        )

    # Decompress if needed
    if compression_type != CompressionType.NONE:
        if should_decompress:
            try:
                data = decompress_by_type(data, compression_type)
                # debug_print(f"DEBUG: Decompressed segment 0x{seg_num:X} from {rom_end - rom_start} to {len(data)} bytes.")
            except Exception as e:
                debug_fail(f"ERROR: Failed to decompress segment 0x{seg_num:X}: {e}")
        else:
            debug_print("That's weird, we found compressed data when we shouldn't have.")

    sSegments[seg_num] = {
        "start": rom_start,
        "end": rom_end,
        "data": data,
        "compression_type": compression_type,
        "segmented_address": seg_num << 24,
        "size": len(data),
        "ranges": [(rom_start, rom_end)],
    }
    # debug_print(f"DEBUG: Loaded segment 0x{seg_num:X} from 0x{rom_start:X} to 0x{rom_end:X}, length {len(data)} bytes.")

    # Store in cache for reuse
    _segment_cache[key] = sSegments[seg_num]

    for hook in list(sSegmentLoadHooks):
        hook(seg_num, sSegments[seg_num])


def load_segment_append(
    seg_num: int, rom_start: int, rom_end: int, should_decompress: bool
) -> None:
    global sSegments
    global sRom

    if sRom is None:
        raise Exception("Global ROM object (sRom) not set. Cannot load segment.")

    # Read data
    prev_pos = sRom.tell()
    sRom.seek(rom_start)
    data = sRom.read(rom_end - rom_start)
    sRom.seek(prev_pos)

    # Decompress if needed (though usually False for LOAD_RAW)
    compression_type = detect_compression_type(data)
    if should_decompress and compression_type != CompressionType.NONE:
        try:
            data = decompress_by_type(data, compression_type)
        except Exception as e:
            debug_fail(f"ERROR: Failed to decompress segment 0x{seg_num:X}: {e}")

    # Mode: strict – never append; treat as a fresh load.
    if SEG_LOAD_MODE == "strict":
        sSegments[seg_num] = {
            "start": rom_start,
            "end": rom_end,
            "data": data,
            "compression_type": compression_type,
            "segmented_address": seg_num << 24,
            "size": len(data),
            "ranges": [(rom_start, rom_end)],
        }
        # debug_print(f"DEBUG: [strict] Loaded segment 0x{seg_num:X} from 0x{rom_start:X} to 0x{rom_end:X}, length {len(data)} bytes.")
        for hook in list(sSegmentLoadHooks):
            hook(seg_num, sSegments[seg_num])
        return

    # Mode: extend – only extend the same segment if contiguous/overlapping and compression flags match.
    if SEG_LOAD_MODE == "extend":
        if seg_num in sSegments:
            seg_info = sSegments[seg_num]
            contiguous = rom_start == seg_info["end"] or (
                rom_start >= seg_info["start"] and rom_start <= seg_info["end"]
            )
            compression_match = (
                seg_info["compression_type"] == compression_type
            ) or not should_decompress
            if contiguous and compression_match:
                buf = bytearray(seg_info["data"])
                # If overlapping, trim already-present prefix
                overlap = max(0, seg_info["end"] - rom_start)
                if overlap > 0:
                    data_to_add = data[overlap:]
                else:
                    data_to_add = data
                buf.extend(data_to_add)
                seg_info["data"] = bytes(buf)
                seg_info["size"] = len(seg_info["data"])
                seg_info["end"] = seg_info["start"] + seg_info["size"]
                seg_info["ranges"].append((rom_start, rom_end))
                # debug_print(f"DEBUG: [extend] Appended {len(data_to_add)} bytes to segment 0x{seg_num:X}. New size: 0x{seg_info['size']:X}")
                for hook in list(sSegmentLoadHooks):
                    hook(seg_num, seg_info)
                return

        # Fallback: fresh load (overwrite)
        sSegments[seg_num] = {
            "start": rom_start,
            "end": rom_end,
            "data": data,
            "compression_type": compression_type,
            "segmented_address": seg_num << 24,
            "size": len(data),
            "ranges": [(rom_start, rom_end)],
        }
        # debug_print(f"DEBUG: [extend] Loaded segment 0x{seg_num:X} from 0x{rom_start:X} to 0x{rom_end:X}, length {len(data)} bytes.")
        for hook in list(sSegmentLoadHooks):
            hook(seg_num, sSegments[seg_num])
        return

    # Mode: hack – previous alias/append behavior (can merge into another contiguous segment).
    if SEG_LOAD_MODE == "hack":
        contiguous_seg = find_contiguous_segment(rom_start)

        if contiguous_seg is not None:
            base_seg = sSegments[contiguous_seg]
            buf = bytearray(base_seg["data"])
            buf.extend(data)
            base_seg["data"] = bytes(buf)
            base_seg["size"] = len(base_seg["data"])
            base_seg["end"] = base_seg["start"] + base_seg["size"]
            base_seg.setdefault("ranges", []).append((rom_start, rom_end))
            sSegments[contiguous_seg] = base_seg
            sSegments[seg_num] = base_seg  # alias appended segment to the base
            # debug_print(
            #     f"DEBUG: [hack] Appended {len(data)} bytes to contiguous segment 0x{contiguous_seg:X} "
            #     f"for segment 0x{seg_num:X}. New size: 0x{base_seg['size']:X}")

            for hook in list(sSegmentLoadHooks):
                hook(contiguous_seg, base_seg)
                if seg_num != contiguous_seg:
                    hook(seg_num, base_seg)
            return

        if seg_num in sSegments:
            buf = bytearray(sSegments[seg_num]["data"])
            buf.extend(data)
            sSegments[seg_num]["data"] = bytes(buf)
            sSegments[seg_num]["size"] = len(sSegments[seg_num]["data"])
            # keep start as original, end becomes start+size
            sSegments[seg_num]["end"] = sSegments[seg_num]["start"] + sSegments[seg_num]["size"]
            sSegments[seg_num].setdefault("ranges", []).append((rom_start, rom_end))
            # debug_print(f"DEBUG: [hack] Appended {len(data)} bytes to segment 0x{seg_num:X}. New size: 0x{sSegments[seg_num]['size']:X}")
        else:
            # New load
            sSegments[seg_num] = {
                "start": rom_start,
                "end": rom_end,
                "data": data,
                "compression_type": compression_type,
                "segmented_address": seg_num << 24,
                "size": len(data),
                "ranges": [(rom_start, rom_end)],
            }
            # debug_print(f"DEBUG: [hack] Loaded (append-mode) segment 0x{seg_num:X} from 0x{rom_start:X} to 0x{rom_end:X}, length {len(data)} bytes.")

        for hook in list(sSegmentLoadHooks):
            hook(seg_num, sSegments[seg_num])
        return


def get_segment(seg_num: int) -> Optional[bytes]:
    global sSegments
    if seg_num not in sSegments:
        return None
    return sSegments[seg_num]["data"]


# Create a copy of segment data that takes minimal amount of memory
def get_segment_no_alloc(seg_num: int) -> Optional[Tuple[int, int, int]]:
    if seg_num not in sSegments:
        debug_fail(f"DEBUG: Attempted to get no alloc unloaded segment 0x{seg_num:02X}")
        return None
    segment = sSegments[seg_num]
    return (segment["segmented_address"], segment["start"], segment["end"])


def where_is_segment_loaded(seg_num: int) -> Optional[Tuple[int, int]]:
    global sSegments
    if seg_num in sSegments:
        return sSegments[seg_num]["start"], sSegments[seg_num]["end"]
    return None


def get_loaded_segment_numbers() -> List[int]:
    global sSegments
    return list(sSegments.keys())


def segmented_to_virtual(segmented_addr: int) -> int:
    seg_phys_start = segmented_addr
    seg_num = segment_from_addr(segmented_addr)
    if seg_num != 0:
        offset = offset_from_segment_addr(segmented_addr)
        location = where_is_segment_loaded(seg_num)
        if location is not None:
            seg_phys_start, _ = location
            seg_phys_start += offset
    return seg_phys_start
