from typing import Set, Tuple, Any, Optional
from context import ctx
import hashlib
from segment import (
    segmented_to_virtual,
    where_is_segment_loaded,
    get_segment,
    offset_from_segment_addr,
    segment_from_addr,
)
from utils import (
    debug_mode_prefix,
    level_name_to_int_lookup,
    read_int,
    set_rom,
    debug_print,
    debug_fail,
)
from script_definitions import GLOBAL_SCRIPT_SIGNATURES
from base_processor import BaseProcessor
from rom_database import LevelRecord, CommandIR
from byteio import CustomBytesIO
from address_map import get_physical_symbol, SymbolType

# --- Original Global State ---
parsed_scripts: Set[Tuple[int, str]] = set()
_scripts_in_progress: Set[int] = set()  # Guard against re-entrant parse loops


# --- LevelScriptProcessor ---


class LevelScriptProcessor(BaseProcessor):
    def parse(self, segmented_addr: int, **kwargs: Any) -> Optional[LevelRecord]:
        """Refactored version of process_level_script and parse_level_script."""
        label = kwargs.get("label")
        label_non_recursive = kwargs.get("label_non_recursive")

        seg_phys_start = segmented_to_virtual(segmented_addr)

        if seg_phys_start in self.ctx.db.level_scripts:
            return self.ctx.db.level_scripts[seg_phys_start]

        # Guard: if this exact address is already being parsed higher on the call stack,
        # we have a JUMP that points into itself (circular). Return None instead of looping.
        if seg_phys_start in _scripts_in_progress:
            debug_print(
                f"WARNING: Circular script reference detected at 0x{segmented_addr:08x} – skipping"
            )
            return None

        data = get_segment(segment_num)
        if data is None:
            debug_fail(f"end of the road: failed to load 0x{segmented_addr:08x}")
            return None

        rom = CustomBytesIO(data)
        seg_offset = offset_from_segment_addr(segmented_addr)

        # 2. Setup parsing state
        prev_indent = ctx.indent
        ctx.indent = 0
        ctx.first_command_in_script = True
        ctx.script_cmd_history.append([])

        from deferred_output import DeferredScriptOutput

        prev_deferred = ctx.deferred
        ctx.deferred = DeferredScriptOutput()
        if prev_deferred is not None:
            ctx.deferred.model_table.update(prev_deferred.model_table)
        ctx._pending_record = None

        from segment import get_pool_depth, pop_pool_state

        initial_pool_depth = get_pool_depth()

        _scripts_in_progress.add(seg_phys_start)
        try:
            script_name = ""
            if label:
                script_name = label
                # script_name = f"{label}_script_0x{seg_phys_start:x}"
            elif label_non_recursive:
                script_name = label_non_recursive
            else:
                prefix = None
                for part in reversed(ctx.level_script_tracker):
                    if part == "script_exec_level_table":
                        break
                    is_generated = part.startswith("level_script_") or "_script_0x" in part
                    if not is_generated and not part.startswith("area_"):
                        prefix = part
                        break
                script_name = (
                    f"{prefix}_script_0x{seg_phys_start:x}"
                    if prefix
                    else f"level_script_0x{seg_phys_start:x}"
                )
            ctx.level_script_tracker.append(script_name)

            name = f"{ctx.level_script_tracker[-1]}_entry"
            if (
                len(ctx.level_script_tracker) > 3
                and ctx.level_script_tracker[-3] == "script_exec_level_table"
            ):
                for level in level_name_to_int_lookup:
                    if name.startswith(level + "_script"):
                        name = f"level_{level}_entry"
                        break

            parsed_scripts.add((seg_phys_start, name))

            rom.seek(seg_offset, 0)
            commands_ir = []

            while True:
                continueParsing, ir = parse_line(rom, seg_offset, seg_phys_start)

                if isinstance(ir, CommandIR):
                    commands_ir.append(ir)
                if not continueParsing:
                    break

            if ctx.deferred and ctx.deferred.records:
                ctx.deferred.post_process()

            if prev_deferred is not None and ctx.deferred is not None:
                prev_deferred.model_table.update(ctx.deferred.model_table)

            record = LevelRecord(name=name, script_addr=seg_phys_start, commands=commands_ir)
            record.history = ctx.level_script_tracker[::-1]
            ctx.db.level_scripts[seg_phys_start] = record
            ctx.db.set_symbol(seg_phys_start, name, "LevelScript")
            return record

        finally:
            while get_pool_depth() > initial_pool_depth:
                pop_pool_state()
            _scripts_in_progress.discard(seg_phys_start)
            ctx.script_cmd_history.pop()
            ctx.level_script_tracker.pop()
            ctx.indent = prev_indent
            ctx.deferred = prev_deferred
            ctx._pending_record = None

    def serialize(self, record: LevelRecord) -> str:
        history_comment = ""
        if hasattr(record, "history") and record.history:
            history_comment = "// " + " -> ".join(record.history[::-1]) + "\n"

        def _param_to_str(p):
            return "NULL" if p is None else str(p)

        output = history_comment
        output += f"const LevelScript {record.name}[] = {{\n"
        for ir in record.commands:
            prefix = "    " * (ir.indent + 1)
            comment = ir.comment if hasattr(ir, "comment") else ""

            # Hex dump of the command bytes
            prefix = debug_mode_prefix(
                ir.raw_data,
                prefix,
                ((0x18 // 4) * (8 + 1)) + 2 + 4 + (5 + 8),  # 6 words, 2 spaces and 4 special chars
                metadata=f"0x{ir.address:08X}",
            )

            params_str = ", ".join(_param_to_str(p) for p in ir.params)
            output += f"{prefix}{comment}{ir.name}({params_str}),\n"
        output += "};"
        if self.ctx.txt:
            self.ctx.txt.write(self.ctx, "script", record.name, output)
        return output


_level_processor = None


def get_level_processor():
    global _level_processor
    if _level_processor is None:
        _level_processor = LevelScriptProcessor(ctx)
    return _level_processor


# --- Helpers ---


def is_cmd_terminator(cmd):
    return cmd in {"EXIT", "RETURN", "EXIT_AND_EXECUTE", "JUMP"}


def quick_level_script_parse(rom, max_cmds=5000):
    prev_offset = rom.tell()
    cmds = []
    total_script_size = 0
    cmds_count = 0
    while cmds_count < max_cmds:
        header = read_int(rom)
        if header is None or header == 0:
            break
        from level_commands import parse_command_table, CMD_BBH

        command, size, _ = CMD_BBH([header])
        if command >= len(parse_command_table) or size < 4:
            break
        name = parse_command_table[command]["name"]
        cmds.append(name)
        if is_cmd_terminator(name):
            break
        rom.seek(int(size) - 4, 1)
        total_script_size += int(size)
        cmds_count += 1
    rom.seek(prev_offset, 0)
    return cmds, total_script_size


def level_script_check_match(cmd_list):
    # script_exec_level_table is a jump table to all the levels.
    # So it's essential to identify it so we can know what level we're parsing.
    # It always starts with GET_OR_SET, has a large number of JUMP_IF cmds, and ends with EXIT
    if (
        len(cmd_list) >= 3
        and cmd_list[0] == "GET_OR_SET"
        and cmd_list[-1] == "EXIT"
        and len(cmd_list[1:-1]) > 5
        and all(item == "JUMP_IF" for item in cmd_list[1:-1])
    ):
        return "script_exec_level_table"

    # This isn't very strict, but it seems to work anyway.
    if len(cmd_list) >= 20 and cmd_list[0] == "INIT_LEVEL":
        return "level_main_menu_entry_1"
    return None


def expand_level_script_into(dest: LevelRecord, indent: int, src: LevelRecord, index: int):
    assert len(src.commands) > 0, "Source script must have at least one command"
    command_count = 0
    for command in src.commands:
        command.indent = indent
        if len(command.params) > 0 and isinstance(command.params[0], LevelRecord):
            command_count += expand_level_script_into(dest, indent, command.params[0], index)
        command_count += 1
    dest.commands[index : index + 1] = src.commands[0:-1]  # skip return
    return command_count


def parse_line(rom, seg_offset, seg_phys_start):
    from level_commands import parse_command_table, CMD_BBH

    prev_offset = rom.tell()
    curr_phys = seg_phys_start + (prev_offset - seg_offset)
    header = read_int(rom)
    if header is None:
        return False, ""

    command, size, _ = CMD_BBH([header])
    if ctx.first_command_in_script:
        ctx.first_command_in_script = False
        ctx.first_cmd = command
        if command == 0x3C:  # GET_OR_SET
            rom.seek(prev_offset, 0)
            pre_cmds, _ = quick_level_script_parse(rom)
            if pre_cmds != 1:
                match = level_script_check_match(pre_cmds)
                if match:
                    ctx.level_script_tracker[-1] = match
            rom.seek(prev_offset + 4, 0)

    if command < 0 or command >= len(parse_command_table):
        debug_print(
            f"WARNING: UNRECOGNISED LEVEL CMD OP {command:02X} at phys: 0x{curr_phys:08x}, seg: 0x{seg_phys_start:08x}, offset: 0x{prev_offset - seg_offset:08x}"
        )
        return False, ""

    info = parse_command_table[command]
    name = info["name"]
    length = (int(size) // 4) - 1
    if length > 32:
        length = 3  # Sanity cap

    values = [header]
    for _ in range(length):
        val = read_int(rom)
        if val is not None:
            values.append(val)

    ctx.cmd_bytes = rom[prev_offset : prev_offset + (length + 1) * 4]

    prev_indent = ctx.indent
    ctx.curr_phys = curr_phys

    ctx.script_cmd_history[-1].append(name)
    res = info["function"](values)
    ir = res[0] if isinstance(res, tuple) else res
    continue_parsing = res[1] if isinstance(res, tuple) else not is_cmd_terminator(name)

    ir.address = curr_phys

    # Fix indentation
    indent_for_line = ctx.indent
    if name == "END_AREA" or name == "LOOP_UNTIL":
        indent_for_line = max(indent_for_line - 1, 0)

    # The start of the block should be on the same level as commands before it
    elif name == "AREA" or name == "LOOP_BEGIN":
        indent_for_line = max(indent_for_line - 1, 0)
    elif ctx.indent != prev_indent:
        print(
            f"error, some unsupported command ({name}) just changed the indentation {ctx.indent} != {prev_indent}"
        )

    if indent_for_line < 0:
        print(f"Fail indentation assertion: {name} at 0x{curr_phys:x}")
        indent_for_line = 0
    ir.indent = indent_for_line

    if ctx.deferred:
        from deferred_output import ScriptRecord, RecordType

        pending = getattr(ctx, "_pending_record", None)
        if pending:
            pending.command_ir = ir
            ctx.deferred.add_record(pending)
            ctx._pending_record = None
        else:
            ctx.deferred.add_record(ScriptRecord(RecordType.GENERIC, command_ir=ir))

    return continue_parsing, ir


def pending_parse(start, end=-1, label=None, label_non_recursive=None):
    return get_level_processor().parse(start, label=label, label_non_recursive=label_non_recursive)


def parse_level_script(start_offset, segmented_addr=None, label=None):
    addr = segmented_addr if segmented_addr is not None else (0x10000000 + start_offset)
    return get_level_processor().parse(addr, label=label)


def init_level_script_parsing(rom, txt):
    ctx.rom = rom
    ctx.txt = txt
    set_rom(rom)
    from segment import load_segment

    # Load segment 0 so that physical addresses can be followed;
    # loading it here prevents it from being popped later.
    if where_is_segment_loaded(0) is None:
        load_segment(0x00, 0, len(rom), False)

    # Load the main (entry) segment as segment 16
    # This is similar to setup_game_memory in game_init.c (sm64 decomp)
    load_segment(0x10, 0, len(rom), False)


signature_table = [
    {
        "name_hint": "script_func_global_load_models",
        "pattern": ["LOAD_MODEL_FROM_GEO+", "LOAD_MODEL_FROM_DL*", "RETURN"],
    },
    {
        "name_hint": "script_func_global_mixed",
        "pattern": ["LOAD_MODEL_FROM_DL+", "LOAD_MODEL_FROM_GEO*", "RETURN"],
    },
]


def _match_pattern(tokens, pattern):
    i = 0
    j = 0
    while j < len(pattern):
        pat = pattern[j]
        quant = None
        if pat.endswith("+") or pat.endswith("*"):
            quant = pat[-1]
            pat_core = pat[:-1]
        else:
            pat_core = pat

        alts = pat_core.split("|") if "|" in pat_core else [pat_core]

        if quant is None:
            if i >= len(tokens):
                return False
            if tokens[i] not in alts:
                return False
            i += 1
        else:
            # + means one or more, * means zero or more
            matched = False
            count = 0
            while i < len(tokens) and tokens[i] in alts:
                i += 1
                matched = True
                count += 1
            if quant == "+" and not matched:
                return False
        j += 1

    return True


def probe_parse_candidate(segmented_addr, max_cmds=500):
    from level_commands import parse_command_table, CMD_BBH

    seg = segment_from_addr(segmented_addr)
    data = get_segment(seg)
    if data is None:
        return None

    seg_offset = offset_from_segment_addr(segmented_addr)
    segment = CustomBytesIO(data)
    segment.seek(seg_offset, 0)

    tokens = []
    cmds_read = 0
    while cmds_read < max_cmds:
        header = read_int(segment)
        if header is None:
            break
        command, size, _ = CMD_BBH([header])
        name = (
            parse_command_table[command]["name"]
            if command < len(parse_command_table)
            else "UNKNOWN"
        )

        token = name
        try:
            if name == "LOAD_MODEL_FROM_GEO":
                _, _, model = CMD_BBH([header])
                token = f"{name}:{model}"
            elif name == "LOAD_MODEL_FROM_DL":
                _, _, merged = CMD_BBH([header])
                layer = int(merged) >> 12
                model = int(merged) & 0xFF
                token = f"{name}:{layer}:{model}"
        except Exception:
            token = name

        tokens.append(token)
        cmds_read += 1
        if is_cmd_terminator(name):
            break
        remaining_bytes = int(size) - 4
        if remaining_bytes > 0:
            segment.seek(remaining_bytes, 1)

    return tokens


def match_script_func_global(segmented_addr):
    tokens = probe_parse_candidate(segmented_addr)
    if not tokens:
        return None

    seg_num = segment_from_addr(segmented_addr)
    seg_offset = offset_from_segment_addr(segmented_addr)

    seg_data = get_segment(seg_num)
    if seg_data is None:
        return None

    seg_info = where_is_segment_loaded(seg_num)
    if seg_info is None:
        return None
    start, end = seg_info

    phys_addr = start + seg_offset
    symbol = get_physical_symbol(phys_addr, SymbolType.SYMBOL_TYPE_LVL_SCRIPT)

    # get data
    seg_io = CustomBytesIO(seg_data)
    seg_io.seek(seg_offset, 0)
    result = quick_level_script_parse(seg_io)
    if not isinstance(result, tuple):
        size = 0
    else:
        _, size = result
    data = (
        seg_data[seg_offset : seg_offset + size] if size else seg_data[seg_offset : seg_offset + 4]
    )
    hex_digest = hashlib.sha256(data).hexdigest()

    hash_name = None
    for name, script in GLOBAL_SCRIPT_SIGNATURES.items():
        if script[1] == hex_digest:
            hash_name = name
            break

    if symbol is not None and hash_name is not None and symbol != hash_name:
        raise Exception(f"Symbol {symbol} does not match hash {hash_name}")
    return symbol, hash_name


def process_global_candidates(txt_override=None):
    if txt_override is not None:
        ctx.txt = txt_override
    # Process the recorded JUMP_LINK candidates and attempt to promote them to real scripts
    accepted = []
    for segmented_addr in list(ctx.global_candidates):
        seg_phys = segmented_to_virtual(segmented_addr)
        already = False
        for s, name in parsed_scripts:
            if s == seg_phys:
                already = True
                break
        if already:
            continue

        tokens = probe_parse_candidate(segmented_addr)
        if not tokens:
            continue

        # match against signature table
        matched = False
        for sig in signature_table:
            if _match_pattern(tokens, sig["pattern"]):
                matched = True
                break

        if matched:
            try:
                name = parse_level_script(0, segmented_addr=segmented_addr, label=None)
                accepted.append((segmented_addr, name))
            except Exception as e:
                debug_print(f"Failed to process candidate 0x{segmented_addr:x}: {e}")

    return accepted
