from typing import Any, Optional
from abc import ABC, abstractmethod
from context import ExtractionContext
from rom_database import RomDatabase
from segment import (
    segment_from_addr,
    offset_from_segment_addr,
    where_is_segment_loaded,
    get_segment,
)
from byteio import CustomBytesIO
from utils import debug_print


class BaseProcessor(ABC):
    """
    Base class for all ROM data processors (Geo, Collision, Behavior, Level, etc).
    Manages shared state like segment loading, symbol resolution, and indentation.
    """

    def __init__(self, ctx: ExtractionContext):
        self.ctx = ctx
        self.db: RomDatabase = ctx.db
        self.indent_level: int = 0
        self.current_segmented_addr: int = 0
        self.current_context_prefix: Optional[str] = None

    @property
    def txt(self):
        """Helper to access the output manager."""
        return self.ctx.txt

    def get_segment_stream(self, segmented_addr: int) -> Optional[CustomBytesIO]:
        """
        Helper to get a seeked CustomBytesIO stream for a segmented address.
        Handles segment validation and loading checks.
        """
        seg_num = segment_from_addr(segmented_addr)
        offset = offset_from_segment_addr(segmented_addr)

        output = where_is_segment_loaded(seg_num)
        if output is None:
            debug_print(f"WARNING: Segment {seg_num} for 0x{segmented_addr:08X} not loaded")
            return None

        data = get_segment(seg_num)
        if data is None:
            return None

        if offset >= len(data):
            debug_print(f"WARNING: Offset 0x{offset:X} out of bounds for segment {seg_num}")
            return None

        stream = CustomBytesIO(data)
        stream.seek(offset)
        return stream

    def indent(self) -> str:
        """Returns the current indentation string."""
        return "    " * (self.indent_level + 1)

    @abstractmethod
    def parse(self, segmented_addr: int, **kwargs: Any) -> Any:
        """Read bytes and populate a record in the database."""
        pass

    @abstractmethod
    def serialize(self, record: Any) -> str:
        """Convert a database record back into a C/Lua string."""
        pass
