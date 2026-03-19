from segment import (
    CustomBytesIO,
    debug_print,
    get_segment,
    offset_from_segment_addr,
    segment_from_addr,
    where_is_segment_loaded,
)
from utils import DEBUG, read_int
from typing import Any, Dict, List, Optional, Tuple
from microcode import create_microcode
from base_processor import BaseProcessor
from rom_database import DisplayListRecord
from context import ctx

current_geometry_mode: int = 0x22205
current_microcode: Any = None
sDisplayListHooks: List[Any] = []


def register_display_list_hook(func: Any) -> None:
    if func not in sDisplayListHooks:
        sDisplayListHooks.append(func)


class Disassembler:
    def __init__(self, sTxt: Any, context_prefix: Optional[str]) -> None:
        self.sTxt = sTxt
        self.context_prefix = context_prefix
        self.output = ""
        self.commands: List[Dict[str, Any]] = []
        self.end_dl = False
        self.branch_taken = False
        self.current_pos = 0
        self.current_w0 = 0
        self.current_w1 = 0
        self.current_line: Optional[str] = None

    def start_command(self, pos: int, w0: int, w1: int) -> None:
        self.current_pos = pos
        self.current_w0 = w0
        self.current_w1 = w1
        self.current_line = None

    def text(self, t: str) -> None:
        self.current_line = t

    def set_cmd(self, name: str, params: Dict[str, Any]) -> None:
        cmd = {"type": name, "pos": self.current_pos}
        cmd.update(params)
        self.commands.append(cmd)

    def parse_dl(self, address: int) -> str:
        return parse_display_list(address, self.sTxt, self.context_prefix)

    def finish_command(self) -> None:
        hex_str = (
            f"/* {self.current_pos:06X} {self.current_w0:08X} {self.current_w1:08X} */".ljust(30)
            if DEBUG
            else "   "
        )
        if self.current_line:
            self.output += f"{hex_str} {self.current_line},\n"


def _SHIFTR(val: int, shift: int, size: int) -> int:
    return (val >> shift) & ((1 << size) - 1)


def format_params(params: List[Any]) -> str:
    return ", ".join(map(str, params))


def comment_out(text: str) -> str:
    return text if text.lstrip().startswith("//") else f"// {text}"


def set_microcode(name: str) -> None:
    global current_microcode
    current_microcode = create_microcode(name)
    debug_print(
        f"Switched to microcode: {current_microcode.__class__.__name__} (requested: {name})"
    )


def probe_microcode(segment_data: bytes, offset: int) -> Optional[str]:
    if offset + 4 > len(segment_data):
        return None
    cmd0 = int.from_bytes(segment_data[offset : offset + 4], "big")
    opcode = (cmd0 >> 24) & 0xFF
    if opcode in (0xDE, 0xDF, 0x09, 0x0A):
        return "F3DEX2"
    if opcode in (0x06, 0xB8):
        return "F3D"
    return None


def parse_display_list_from_data(
    stream, start_offset, segmented_addr, sTxt, context_prefix, force_microcode=None
):
    global current_microcode
    old = current_microcode
    if force_microcode:
        current_microcode = create_microcode(force_microcode)
    try:
        dis = Disassembler(sTxt, context_prefix)
        stream.seek(start_offset)
        while True:
            if stream.tell() + 8 > len(stream.getvalue()):
                break
            pos = stream.tell()
            w0 = read_int(stream)
            w1 = read_int(stream)
            if w0 is None or w1 is None:
                break
            if w0 == 0x01010101 and w1 == 0x01010101:
                break
            handler = current_microcode.get_handler(w0)
            dis.start_command(pos, w0, w1)
            handler(w0, w1, dis)
            dis.finish_command()
            if (
                dis.end_dl
                or dis.branch_taken
                or (hasattr(handler, "__name__") and handler.__name__ == "execute_unknown")
            ):
                break
        return dis.output, dis.commands
    finally:
        current_microcode = old


# --- DisplayListProcessor ---


class DisplayListProcessor(BaseProcessor):
    def __init__(self, context):
        super().__init__(context)
        self.parsed_dls: Dict[Tuple[int, int, int], str] = {}
        self.parsed_dl_commands_by_addr: Dict[int, List[Dict[str, Any]]] = {}

    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        sTxt = kwargs.get("txt")
        context_prefix = kwargs.get("context_prefix")
        if not segmented_addr:
            return "NULL"

        for hook in sDisplayListHooks:
            res = hook(segmented_addr, sTxt, context_prefix)
            if res is not None:
                return str(res)

        seg_num = segment_from_addr(segmented_addr)
        segment_info = where_is_segment_loaded(seg_num)
        if segment_info is None:
            return f"dl_fail_0x{segmented_addr:08X}"

        start, end = segment_info

        # Unique database key for level-specific overlaps
        db_key = (segmented_addr, start)

        # Check database for already assigned name for this exact address + segment load
        if self.ctx.db and db_key in self.ctx.db.display_lists:
            return self.ctx.db.display_lists[db_key].name

        if (segmented_addr, start, end) in self.parsed_dls:
            return self.parsed_dls[(segmented_addr, start, end)]

        offset = offset_from_segment_addr(segmented_addr)
        data = get_segment(seg_num)
        if data is None or offset >= len(data):
            return "NULL"

        # Assign name
        dl_name = f"dl_{segmented_addr:08X}"
        if context_prefix:
            dl_name = f"{context_prefix}_{dl_name}"

        # Preventive cache entry to handle simple recursion
        self.parsed_dls[(segmented_addr, start, end)] = dl_name

        forced = probe_microcode(data, offset)
        parsed_content, commands = parse_display_list_from_data(
            CustomBytesIO(data),
            offset,
            segmented_addr,
            sTxt,
            context_prefix,
            force_microcode=forced,
        )

        output_str = f"const Gfx {dl_name}[] = {{\n{parsed_content}}};\n"

        if self.ctx.db:
            self.ctx.db.display_lists[db_key] = DisplayListRecord(
                seg_addr=segmented_addr, name=dl_name, script_text=output_str
            )

        self.parsed_dl_commands_by_addr.setdefault(segmented_addr, []).append(
            {"start": start, "end": end, "commands": commands}
        )
        return dl_name

    def serialize(self, record: DisplayListRecord) -> str:
        if self.ctx.txt and record.script_text:
            self.ctx.txt.write(self.ctx, "dl", record.name, record.script_text)
        return record.script_text


_dl_processor = None


def get_display_list_processor():
    global _dl_processor
    if _dl_processor is None:
        _dl_processor = DisplayListProcessor(ctx)
    return _dl_processor


def parse_display_list(addr, txt, context_prefix=None):
    return get_display_list_processor().parse(addr, txt=txt, context_prefix=context_prefix)


def get_display_list_commands(addr):
    p = get_display_list_processor()
    # Note: this returns the most recent one parsed for this address, which is usually correct in current context
    if addr in p.parsed_dl_commands_by_addr and p.parsed_dl_commands_by_addr[addr]:
        return p.parsed_dl_commands_by_addr[addr][-1]["commands"]
    return None
