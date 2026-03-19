from utils import debug_fail, debug_print, offset_from_segment_addr, segment_from_addr
from segment import CustomBytesIO, get_segment, where_is_segment_loaded
import struct
from typing import Dict, Tuple, Any, Optional
from base_processor import BaseProcessor
from rom_database import VertexRecord
from context import ctx


class VertexProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)
        self.parsed_vertices: Dict[tuple, Tuple[str, int]] = {}

    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[VertexRecord]:
        count = kwargs.get("count", 0)
        context_prefix = kwargs.get("context_prefix")
        parent_dl = kwargs.get("parent_dl")

        if not segmented_addr:
            debug_print("No segmented address provided")
            return None

        seg_num = segment_from_addr(segmented_addr)
        offset = offset_from_segment_addr(segmented_addr)
        output = where_is_segment_loaded(seg_num)
        if output is None:
            debug_print(
                f"Segment {seg_num} for vertices 0x{segmented_addr:08X} not loaded (count: {count})"
            )
            return None
        start, end = output

        # Use count in the symbol to avoid reusing an under-sized buffer if a DL
        # references the same address with a larger count later.
        name = f"vertex_{segmented_addr:08X}"
        if context_prefix:
            name = f"{context_prefix}_{name}"
        name = f"{name}_n{count}"

        # DB key for vertices
        db_key = (segmented_addr, count, start)
        if self.ctx.db and db_key in self.ctx.db.vertices:
            return self.ctx.db.vertices[db_key]

        data = get_segment(seg_num)
        if data is None:
            debug_print(
                f"WARNING: Segment {seg_num} for vertices 0x{segmented_addr:08X} not loaded"
            )
            return None

        segment_data = CustomBytesIO(data)
        segment_data.seek(offset)

        output_lines = [f"const Vtx {name}[] = {{"]

        total_bytes = count * 16
        vtx_data_block = segment_data.read(total_bytes)

        actual_count = len(vtx_data_block) // 16

        pos_data = []
        if actual_count > 0:
            valid_block = vtx_data_block[: actual_count * 16]

            try:
                for x, y, z, flag, u, v, r, g, b, a in struct.iter_unpack(">3hH2h4B", valid_block):
                    pos_data.append((x, y, z))
                    output_lines.append(
                        "    {{{ %5d, %6d, %6d}, 0, { %5d, %6d}, {%2d, %2d, %2d, %2d}}},"
                        % (x, y, z, u, v, r, g, b, a)
                    )
            except Exception as e:
                debug_fail(f"Could not unpack vertex data at 0x{segmented_addr:08X}: {e}")
                output_lines.append("    /* ERROR: Could not unpack vertex data */")

        if len(vtx_data_block) < total_bytes:
            output_lines.append("    /* TRUNCATED DATA */")

        output_lines.append("};")
        output_str = "\n".join(output_lines) + "\n\n"

        key = (segmented_addr, count, start, end, parent_dl)
        self.parsed_vertices[key] = (name, actual_count)

        self.ctx.db.vertices[db_key] = VertexRecord(
            seg_addr=segmented_addr,
            name=name,
            count=actual_count,
            pos_data=pos_data,
            script_text=output_str,
            location=self.ctx.level_area,
        )

        return self.ctx.db.vertices[db_key]

    def serialize(self, record: VertexRecord) -> str:
        if self.ctx.txt and record.script_text:
            self.ctx.txt.write(self.ctx, "vertex", record.name, record.script_text)
        return record.script_text


_vertex_processor = None


def get_vertex_processor():
    global _vertex_processor
    if _vertex_processor is None:
        _vertex_processor = VertexProcessor(ctx)
    return _vertex_processor


def parse_vertices(segmented_addr, count, sTxt, context_prefix=None, parent_dl=None):
    return get_vertex_processor().parse(
        segmented_addr, count=count, txt=sTxt, context_prefix=context_prefix, parent_dl=parent_dl
    )
