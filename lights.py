from utils import debug_fail, debug_print, offset_from_segment_addr, segment_from_addr
from segment import CustomBytesIO, get_segment, where_is_segment_loaded
import struct
from typing import Dict, Tuple, Any, List, Optional
from dataclasses import dataclass
from context import ctx
from base_processor import BaseProcessor
from rom_database import LightRecord


@dataclass
class ParsedLight:
    name: str
    type_name: str


def vb_type_name_to_extension(type_name: str, light_idx: int) -> str:
    if type_name == "Lights1":
        return ".l" if light_idx == 0 else ".a"
    elif type_name == "Lights2":
        return ".l" if light_idx == 0 else ".a"
    elif type_name == "Light_t":
        return ".col"
    elif type_name == "Ambient_t":
        return ".col"
    else:
        return ""


class LightProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)
        self.parsed_lights: Dict[Tuple[int, int, int, int], ParsedLight] = {}

    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[LightRecord]:
        size = kwargs.get("size", 0)
        context_prefix = kwargs.get("context_prefix")

        if not segmented_addr:
            debug_fail("No segmented address provided for light")
            return None

        seg_num = segment_from_addr(segmented_addr)
        offset = offset_from_segment_addr(segmented_addr)
        output = where_is_segment_loaded(seg_num)
        if output is None:
            debug_fail(
                f"Segment {seg_num} for light 0x{segmented_addr:08X} not loaded (size: {size})"
            )
            return None
        start, end = output

        key = (segmented_addr, size, start, end)

        # DB key for lights
        db_key = (segmented_addr, size, start)
        if self.ctx.db and db_key in self.ctx.db.lights:
            return self.ctx.db.lights[db_key]

        # Determine type based on size
        is_ambient = size == 8
        is_lights1 = size == 24
        is_lights2 = size == 40

        if is_ambient:
            type_name = "Ambient_t"
        elif is_lights1:
            type_name = "Lights1"
        elif is_lights2:
            type_name = "Lights2"
        else:
            type_name = "Light_t"

        name = f"light_{segmented_addr:08X}"
        if context_prefix:
            name = f"{context_prefix}_{name}"

        self.parsed_lights[key] = ParsedLight(name, type_name)

        data = get_segment(seg_num)
        if data is None:
            debug_print(f"WARNING: Segment {seg_num} for light 0x{segmented_addr:08X} not loaded")
            return None

        segment_data = CustomBytesIO(data)
        segment_data.seek(offset)

        output_lines: List[str] = []

        try:
            if is_ambient:
                output_lines = [f"{type_name} {name} = {{"]
                # 8 bytes
                block = segment_data.read(8)
                if len(block) < 8:
                    output_lines.append("    /* TRUNCATED DATA */")
                else:
                    col = block[0:3]
                    colc = block[4:7]
                    output_lines.append(
                        f"    {{ {col[0]}, {col[1]}, {col[2]} }}, 0, {{ {colc[0]}, {colc[1]}, {colc[2]} }}, 0"
                    )
                output_lines.append("};")
            elif is_lights1 or is_lights2:
                func_name = "gdSPDefLights1" if is_lights1 else "gdSPDefLights2"
                output_lines = [f"{type_name} {name} = {func_name}("]

                # Lights1 (24 bytes) or Lights2 (40 bytes)
                # Both start with Ambient (8 bytes)
                read_len = 24 if is_lights1 else 40
                block = segment_data.read(read_len)

                if len(block) < read_len:
                    output_lines.append("    /* TRUNCATED DATA */")
                else:
                    ambient_color = block[0:3]
                    l1_col = block[8:11]
                    l1_dir = block[16:19]

                    if is_lights1:
                        output_lines.append(
                            f"    0x{ambient_color[0]:x}, 0x{ambient_color[1]:x}, 0x{ambient_color[2]:x}, "
                            f"0x{l1_col[0]:x}, 0x{l1_col[1]:x}, 0x{l1_col[2]:x}, "
                            f"0x{l1_dir[0]:x}, 0x{l1_dir[1]:x}, 0x{l1_dir[2]:x}"
                        )
                    else:
                        l2_col = block[24:27]
                        l2_dir = block[32:35]
                        output_lines.append(
                            f"    0x{ambient_color[0]:x}, 0x{ambient_color[1]:x}, 0x{ambient_color[2]:x}, "
                            f"0x{l1_col[0]:x}, 0x{l1_col[1]:x}, 0x{l1_col[2]:x}, "
                            f"0x{l1_dir[0]:x}, 0x{l1_dir[1]:x}, 0x{l1_dir[2]:x}, "
                            f"0x{l2_col[0]:x}, 0x{l2_col[1]:x}, 0x{l2_col[2]:x}, "
                            f"0x{l2_dir[0]:x}, 0x{l2_dir[1]:x}, 0x{l2_dir[2]:x}"
                        )

                output_lines.append(");")

            else:
                output_lines = [f"{type_name} {name} = {{"]
                # 16 bytes (Light)
                block = segment_data.read(16)
                if len(block) < 16:
                    output_lines.append("    /* TRUNCATED DATA */")
                else:
                    col = block[0:3]
                    # pad1 = block[3]
                    colc = block[4:7]
                    # pad2 = block[7]
                    # dir is signed char
                    dir_ = struct.unpack(">3b", block[8:11])
                    # pad3 = block[11]

                    output_lines.append(
                        f"    {{ {col[0]}, {col[1]}, {col[2]} }}, 0, {{ {colc[0]}, {colc[1]}, {colc[2]} }}, 0, {{ {dir_[0]}, {dir_[1]}, {dir_[2]} }}, 0"
                    )
                output_lines.append("};")
        except Exception as e:
            debug_fail(f"Could not unpack light data at 0x{segmented_addr:08X}: {e}")
            output_lines.append("    /* ERROR: Could not unpack light data */")

        output_str = "\n".join(output_lines) + "\n"

        self.ctx.db.lights[db_key] = LightRecord(
            seg_addr=segmented_addr,
            name=name,
            type_name=type_name,
            script_text=output_str,
            location=self.ctx.level_area,
        )
        self.ctx.db.set_symbol(segmented_addr, name, "Light")

        return self.ctx.db.lights[db_key]

    def serialize(self, record: LightRecord) -> str:
        if self.ctx.txt and record.script_text:
            self.ctx.txt.write(self.ctx, "light", record.name, record.script_text)
        return record.script_text


_light_processor = None


def get_light_processor():
    global _light_processor
    if _light_processor is None:
        _light_processor = LightProcessor(ctx)
    return _light_processor


def parse_light(segmented_addr, size, sTxt, context_prefix=None):
    return get_light_processor().parse(
        segmented_addr, size=size, txt=sTxt, context_prefix=context_prefix
    )
