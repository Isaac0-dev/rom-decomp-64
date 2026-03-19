import struct
from typing import Any, List, Optional, Tuple

from base_processor import BaseProcessor
from context import ctx
from rom_database import MacroRecord
from segment import (
    get_segment,
    offset_from_segment_addr,
    segment_from_addr,
    segmented_to_virtual,
    where_is_segment_loaded,
)
from utils import debug_fail, debug_print
from constants import macro_presets


def _parse_single_macro(data_bytes: bytes) -> Optional[Tuple[int, int, int, int, int, int, int]]:
    if len(data_bytes) < 10:
        return None
    vals = struct.unpack(">5H", data_bytes[:10])

    # Extract bitfields from first short
    yaw_and_preset = vals[0]
    yaw_raw = (yaw_and_preset >> 9) & 0x7F
    preset = (yaw_and_preset & 0x1FF) - 0x1F

    # Position values (convert unsigned to signed)
    posX = struct.unpack(">h", struct.pack(">H", vals[1]))[0]
    posY = struct.unpack(">h", struct.pack(">H", vals[2]))[0]
    posZ = struct.unpack(">h", struct.pack(">H", vals[3]))[0]

    behParam = vals[4]
    yaw_degrees = (yaw_raw * 45) // 16
    return (yaw_and_preset, yaw_degrees, preset, posX, posY, posZ, behParam)


def _generate_macro_c_code(
    entries: List[Tuple[int, int, int, int, int, int]], context_prefix: str
) -> str:
    macro_list_name = f"{context_prefix}_macro_objs" if context_prefix else "macro_objs"

    output = ""
    if not entries:
        output += f"// {context_prefix}\n"
        output += f"const MacroObject {macro_list_name}[] = {{\n"
        output += "    MACRO_OBJECT_END(),\n"
        output += "};\n"
        return output

    output += f"// {context_prefix}\n"
    output += f"const MacroObject {macro_list_name}[] = {{\n"

    for yaw, preset, posX, posY, posZ, behParam in entries:
        preset_name = macro_presets.get(preset, f"{preset:#x}")
        if behParam == 0:
            output += f"    MACRO_OBJECT({preset_name}, {yaw}, {posX}, {posY}, {posZ}),\n"
        else:
            output += f"    MACRO_OBJECT_WITH_BEH_PARAM({preset_name}, {yaw}, {posX}, {posY}, {posZ}, {behParam:#x}),\n"

    output += "    MACRO_OBJECT_END(),\n"
    output += "};\n"

    return output


class MacroObjectProcessor(BaseProcessor):
    """
    Discovers macro-object arrays during level-script parsing and serializes
    them to C in the final pass.

    parse()     — parses the binary array, stores a MacroRecord (no I/O).
    serialize() — generates C text from the stored entries, writes via txt.
    """

    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[MacroRecord]:
        context_prefix: str = kwargs.get("context_prefix") or ""

        try:
            segmented_to_virtual(segmented_addr)
        except Exception as e:
            debug_fail(f"Failed to convert macro object address 0x{segmented_addr:08x}: {e}")
            return None

        seg_num = segment_from_addr(segmented_addr)
        data = get_segment(seg_num)

        if data is None:
            debug_fail(
                f"Failed to load segment {seg_num} for macro objects at 0x{segmented_addr:08x}"
            )
            return None

        offset = offset_from_segment_addr(segmented_addr)

        if offset >= len(data):
            debug_fail(
                f"Macro object offset 0x{offset:x} is beyond segment data (size 0x{len(data):x})"
            )
            return None

        entries: List[Tuple[int, int, int, int, int, int]] = []
        pos = offset

        while pos + 10 <= len(data):
            entry_data = data[pos : pos + 10]

            result = _parse_single_macro(entry_data)
            if result is None:
                debug_print(f"WARNING: Failed to parse macro object at offset 0x{pos:x}")
                break

            yaw_and_preset, yaw, preset, posX, posY, posZ, behParam = result

            # Check for end marker
            if yaw_and_preset == 0x001E:
                break

            entries.append((yaw, preset, posX, posY, posZ, behParam))
            pos += 10

        macro_list_name = f"{context_prefix}_macro_objs" if context_prefix else "macro_objs"

        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            debug_fail(
                f"Failed to find segment {seg_num} for macro objects at 0x{segmented_addr:08x}"
            )
            return None

        start, _ = segment_info
        record = MacroRecord(
            addr=segmented_addr,
            name=macro_list_name,
            context_prefix=context_prefix,
            entries=entries,
            location=self.ctx.level_area,
        )
        self.db.macros[(segmented_addr, start)] = record
        return record

    def serialize(self, record: MacroRecord) -> str:
        """Generate C text from the stored entries and write to output."""
        c_text = _generate_macro_c_code(record.entries, record.context_prefix)
        macro_context = f"{record.context_prefix}_macro" if record.context_prefix else "macro"
        if self.txt:
            self.txt.write(ctx, "macro", macro_context, c_text)
        return c_text


_macro_processor: Optional[MacroObjectProcessor] = None


def get_macro_processor() -> MacroObjectProcessor:
    global _macro_processor
    if _macro_processor is None:
        _macro_processor = MacroObjectProcessor(ctx)
    return _macro_processor


def parse_macro_object_list(
    segmented_addr: int, txt: Any, context_prefix: Optional[str] = None
) -> Optional[MacroRecord]:
    """Thin shim: delegates to MacroObjectProcessor.parse()."""
    mp = get_macro_processor()
    old_txt = mp.ctx.txt
    if txt is not None:
        mp.ctx.txt = txt
    result = mp.parse(segmented_addr, context_prefix=context_prefix or "")
    mp.ctx.txt = old_txt
    return result
