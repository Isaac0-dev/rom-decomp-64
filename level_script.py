from typing import Set, Tuple, Any
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
    level_name_to_int_lookup,
    read_int,
    set_rom,
    debug_print,
    debug_fail,
)
from script_definitions import GLOBAL_SCRIPT_SIGNATURES, GLOBAL_SIGNATURE_HASHES
from base_processor import BaseProcessor
from rom_database import LevelRecord, CommandIR
from byteio import CustomBytesIO

# --- Original Global State ---
parsed_scripts: Set[Tuple[int, str]] = set()

global_signatures = {}
global_signature_hash = {}
for name, toks in GLOBAL_SCRIPT_SIGNATURES.items():
    key = tuple(toks)
    global_signatures[key] = name
global_signature_hash = GLOBAL_SIGNATURE_HASHES

# --- Original Error Handling System ---
PARSE_STATS = {
    "commands": 0,
    "errors": 0,
    "scripts": 0,
    "scripts_with_errors": 0,
}

_current_script_had_error = False


class LevelScriptError(Exception):
    def __init__(self, root_exc, locations=None):
        self.root_exc = root_exc
        self.locations = locations or []
        super().__init__(str(self))

    def add_location(self, loc):
        if not self.locations or self.locations[-1] != loc:
            self.locations.append(loc)

    def __str__(self):
        loc_str = " -> ".join(f"0x{loc:08X}" for loc in reversed(self.locations))
        return f"{self.root_exc}\nChain: {loc_str}"


def _wrap_script_exception(exc, loc):
    if isinstance(exc, LevelScriptError):
        exc.add_location(loc)
        return exc
    return LevelScriptError(exc, [loc])


def _mark_error(count=1):
    global _current_script_had_error
    PARSE_STATS["errors"] += count
    _current_script_had_error = True


def print_parse_summary():
    cmds = PARSE_STATS["commands"]
    errs = PARSE_STATS["errors"]
    scripts = PARSE_STATS["scripts"]
    scripts_err = PARSE_STATS["scripts_with_errors"]

    success_pct = 100.0 * (cmds - errs) / cmds if cmds > 0 else 0.0
    if scripts > 0:
        script_success_pct = 100.0 * (scripts - scripts_err) / scripts
    else:
        script_success_pct = 100.0 if scripts_err == 0 else 0.0

    print("\n=== Level Script Parse summary ===")
    print(f"commands parsed: {cmds}")
    print(f"command errors: {errs}")
    print(f"command success: {success_pct:.2f}%")
    print(f"scripts parsed: {scripts}")
    print(f"scripts with errors: {scripts_err}")
    print(f"script success: {script_success_pct:.2f}%")
    return int((script_success_pct + success_pct) / 2)


# --- LevelScriptProcessor ---


class LevelScriptProcessor(BaseProcessor):
    def parse(self, segmented_addr: int, **kwargs: Any) -> str:
        """Refactored version of process_level_script and parse_level_script."""
        global _current_script_had_error
        label = kwargs.get("label")

        # 1. Load data
        segment_num = segment_from_addr(segmented_addr)
        data = get_segment(segment_num)
        if data is None:
            _mark_error()
            debug_fail(f"end of the road: failed to load 0x{segmented_addr:08x}")
            return label or f"level_script_fail_0x{segmented_addr:08X}"

        rom = CustomBytesIO(data)
        seg_offset = offset_from_segment_addr(segmented_addr)
        seg_phys_start = segmented_to_virtual(segmented_addr)

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

        try:
            if label:
                ctx.level_script_tracker.append(label)
                script_name = f"{label}_script_0x{seg_phys_start:x}"
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

            context_parts = [
                p
                for p in ctx.level_script_tracker
                if p != "script_exec_level_table" and "script_0x" not in p
            ]
            context_prefix = "_".join(context_parts) if context_parts else None
            ctx.current_context_prefix = context_prefix

            _current_script_had_error = False
            rom.seek(seg_offset, 0)
            commands_ir = []

            while True:
                try:
                    continueParsing, ir = parse_line(
                        rom, seg_offset, seg_phys_start, context_prefix
                    )
                except Exception as e:
                    e = _wrap_script_exception(e, seg_phys_start)
                    debug_print(str(e))
                    _mark_error()
                    raise e

                if isinstance(ir, CommandIR):
                    commands_ir.append(ir)
                if not continueParsing:
                    break

            if ctx.deferred and ctx.deferred.records:
                ctx.deferred.post_process()

            if prev_deferred is not None and ctx.deferred is not None:
                prev_deferred.model_table.update(ctx.deferred.model_table)

            if self.ctx.db:
                record = LevelRecord(name=name, script_addr=seg_phys_start, commands=commands_ir)
                record.history = ctx.level_script_tracker[::-1]
                self.ctx.db.level_scripts[seg_phys_start] = record
                self.ctx.db.set_symbol(seg_phys_start, name, "LevelScript")
                return record
            return name

        except Exception as e:
            debug_print(str(e))
            _mark_error()
            raise e

        finally:
            ctx.script_cmd_history.pop()
            ctx.level_script_tracker.pop()
            ctx.indent = prev_indent
            ctx.deferred = prev_deferred
            ctx._pending_record = None

    def serialize(self, record: LevelRecord) -> str:
        history_comment = (
            f"// {record.history}\n" if hasattr(record, "history") and record.history else ""
        )

        output = history_comment
        output += f"const LevelScript {record.name}[] = {{\n"
        for ir in record.commands:
            prefix = "    " * (ir.indent + 1)
            comment = ir.comment if hasattr(ir, "comment") else ""
            params_str = ", ".join(map(str, ir.params))
            output += f"{prefix}{comment}{ir.name}({params_str}),\n"
        output += "};\n"
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


def quick_level_script_parse(rom):
    prev_offset = rom.tell()
    cmds = []
    while True:
        header = read_int(rom)
        if not header:
            break
        from level_commands import parse_command_table, CMD_BBH

        command, size, _ = CMD_BBH([header])
        if command >= len(parse_command_table):
            return 1
        name = parse_command_table[command]["name"]
        cmds.append(name)
        if is_cmd_terminator(name):
            break
        rom.seek(int(size) - 4, 1)
    rom.seek(prev_offset, 0)
    return cmds


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


def parse_line(rom, seg_offset, seg_phys_start, context_prefix=None):
    from level_commands import parse_command_table, CMD_BBH

    prev_offset = rom.tell()
    curr_phys = seg_phys_start + (prev_offset - seg_offset)
    header = read_int(rom)
    if header is None:
        _mark_error()
        return False, ""

    command, size, _ = CMD_BBH([header])
    if ctx.first_command_in_script:
        ctx.first_command_in_script = False
        ctx.first_cmd = command
        if command == 0x3C:
            rom.seek(prev_offset, 0)
            pre_cmds = quick_level_script_parse(rom)
            if pre_cmds != 1:
                match = level_script_check_match(pre_cmds)
                if match:
                    ctx.level_script_tracker[-1] = match
            rom.seek(prev_offset + 4, 0)

    PARSE_STATS["commands"] += 1
    if command >= len(parse_command_table):
        _mark_error()
        debug_print(f"WARNING: UNRECOGNISED LEVEL CMD OP {command} at 0x{curr_phys:08x}")
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

    try:
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
    except Exception as e:
        _mark_error()
        debug_fail(f"Exception at 0x{curr_phys:x}: {e}")
        raise _wrap_script_exception(e, curr_phys)


def pending_parse(start, end=-1, label=None):
    seg_phys = segmented_to_virtual(start)
    for s, name in parsed_scripts:
        if seg_phys == s:
            return name
    try:
        return get_level_processor().parse(start, label=label)
    except Exception:
        return label or f"level_script_fail_0x{start:08X}"


def parse_level_script(rom, start_offset, segmented_addr=None, label=None):
    addr = segmented_addr if segmented_addr is not None else (0x10000000 + start_offset)
    return get_level_processor().parse(addr, label=label)


def parse_entry_script(rom, txt, start_offset, end_offset):
    ctx.rom = rom
    ctx.txt = txt
    set_rom(rom)
    from segment import load_segment

    # Load segment 0 so that physical addresses can be followed;
    # loading it here prevents it from being popped later.
    # todo in original game, segment 0 is loaded with an offset of 0x80000000
    # That might be the correct logic here
    # set_segment_base_addr(0, (void *) 0x80000000);
    if where_is_segment_loaded(0) is None:
        load_segment(0x00, 0, len(rom), False)
        load_segment(0x80, 0, len(rom), False)

    # Load the main (entry) segment as segment 16
    # This is consistent with setup_game_memory in game_init.c (sm64 decomp)
    load_segment(0x10, start_offset, len(rom), False)
    parse_level_script(rom, start_offset, 0x10000000)


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

    key = tuple(tokens)
    if key in global_signatures:
        return global_signatures[key]

    h = hashlib.sha1((",".join(tokens)).encode("utf-8")).hexdigest()
    return global_signature_hash.get(h)


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
                hint = sig["name_hint"]
                break

        if matched:
            try:
                name = parse_level_script(None, 0, segmented_addr=segmented_addr, label=None)
                accepted.append((segmented_addr, name))
                if ctx.txt:
                    ctx.txt.write(
                        ctx,
                        "script_func",
                        f"script_func_global_0x{seg_phys:x}",
                        f"// detected as {hint}\n",
                    )
            except Exception as e:
                debug_print(f"Failed to process candidate 0x{segmented_addr:x}: {e}")

    return accepted
