import struct
from typing import Any, Optional
from base_processor import BaseProcessor
from rom_database import RoomsRecord
from segment import segment_from_addr, where_is_segment_loaded, get_segment
from context import ctx
from utils import debug_fail


class RoomsProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)

    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[RoomsRecord]:
        num_surfaces = self.ctx.last_collision_surface_count

        if num_surfaces <= 0 or not segmented_addr:
            return None

        seg_num = segment_from_addr(segmented_addr)
        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            return None

        start = segment_info[0]

        offset = segmented_addr & 0x00FFFFFF
        seg_data = get_segment(seg_num)
        if seg_data is None or offset + num_surfaces > len(seg_data):
            return None

        name = f"rooms_{segmented_addr:08X}"
        if self.ctx.current_context_prefix:
            name = f"{self.ctx.current_context_prefix}_{name}"

        room_bytes = seg_data[offset : offset + num_surfaces]
        room_values = list(struct.unpack(f">{num_surfaces}b", room_bytes))

        db_key = (segmented_addr, start)
        if self.ctx.db is None:
            debug_fail(f"Failed to find database for rooms at 0x{segmented_addr:08x}")
            return None

        record = RoomsRecord(
            seg_addr=segmented_addr,
            name=name,
            count=num_surfaces,
            values=room_values,
            script_text="",
            location=self.ctx.level_area,
        )
        self.ctx.db.rooms[db_key] = record
        self.ctx.db.set_symbol(segmented_addr, name, "Rooms")
        return record

    def serialize(self, record: RoomsRecord) -> str:
        output_str = f"const u8 {record.name}[] = {{\n"
        for i in range(0, len(record.values), 8):
            chunk = record.values[i : i + 8]
            vals = ", ".join(f"{v:2d}" for v in chunk)
            output_str += f"    {vals}, // {i}-{i + len(chunk) - 1}\n"
        output_str += "};\n"
        self.ctx.txt.write(self.ctx, "room", record.name, output_str)
        return output_str


_rooms_processor = None


def get_rooms_processor():
    global _rooms_processor
    if _rooms_processor is None:
        _rooms_processor = RoomsProcessor(ctx)
    return _rooms_processor
