from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import queue
import threading
from typing import List, Optional, Any, TYPE_CHECKING
from context import ctx

from rom_database import (
    GlobalSegRecord,
    RomDatabase,
)

if TYPE_CHECKING:
    from segment import CustomBytesIO
    from output_manager import OutputManager


# ---------------------------------------------------------------------------
# Status prefix (matches extract.py so GUI still works)
# ---------------------------------------------------------------------------

STATUS_PREFIX = "STATUS|"


class ExtractionPipeline:
    """
    Orchestrates the multi-pass extraction of a Super Mario 64 ROM.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        rom_path: str,
        output_status: bool = False,
        host: str = "auto",
        called_by_main: bool = False,
    ) -> None:
        self.rom_path = rom_path
        self.output_status = output_status
        self.host = host
        self.called_by_main = called_by_main

        self.db = RomDatabase()
        self.rom: Optional[CustomBytesIO] = None  # set in pass_init
        self.txt: Optional[OutputManager] = None  # set in pass_init
        self.output_dir: str = ""

        # Internals reused across passes
        self._prev_offset: int = 0
        self._compression_type: Optional[str] = None
        self._alseq_candidates: List[int] = []
        self._text_future: Optional[Any] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> int:
        """
        Run all passes in order and return an exit code.
        Returns 0 on success, non-zero on error (same as old main()).
        """
        self.pass_init()
        self.pass_emulate()  # n64js: detect seg2, microcode, alseq
        self.pass_audio()  # extract ALSeqFile data
        self.pass_text()  # text/dialog export (async-capable)
        self.pass_level_scripts()  # parse entry scripts
        # self.pass_trajectory_scan()  # Disabled for debug purposes
        self.pass_global_candidates()  # resolve JUMP_LINK targets

        # Refinement passes — operate on the fully-populated db
        # self.pass_refine_behaviors()
        # self.pass_refine_models()
        # self.pass_refine_warps()

        # Analysis passes — cross-reference and score records
        self.pass_analysis()

        self.pass_optimization()

        self.pass_serialize()

        return self.pass_finalize()

    # ------------------------------------------------------------------
    # Pass 7: Serialization
    # ------------------------------------------------------------------

    def _get_target_path(self, context: str) -> str:
        """
        Determines the relative output path for a given context name.
        Replicates the logic from the old OutputManager.write.
        """
        from utils import level_name_to_int_lookup

        # 1. Determine the filename based on context clues
        if context is None:
            filename = "misc.c.txt"
        elif "dl" in context or "vertex" in context or "light" in context:
            filename = "model.inc.c"
        elif "geo" in context:
            filename = "geo.inc.c"
        elif "trajectory" in context:
            filename = "trajectory.inc.c"
        elif "collision" in context:
            filename = "collision.inc.c"
        elif "macro" in context:
            filename = "macro.inc.c"
        elif "script" in context or ("level_" in context and "_entry" in context):
            filename = "script.c"
        elif "room" in context:
            filename = "room.inc.c"
        elif "texture" in context or "segment2" in context or "font_graphics" in context:
            filename = f"{context}.png"
        elif "tiles_c" in context:
            filename = "texture.inc.c"
        else:
            filename = "misc.c.txt"

        # 2. Determine the directory
        target_dir = "misc"

        # Special cases for textures
        if "skybox" in context:
            target_dir = os.path.join("textures", "skybox_tiles")
        elif any(
            k in context
            for k in [
                "segment2",
                "font_graphics",
                "texture_hud_char",
                "texture_font_char",
                "texture_transition",
                "texture_waterbox",
            ]
        ):
            target_dir = os.path.join("textures", "segment2")
        else:
            # Level-based routing
            for level in level_name_to_int_lookup:
                if context.startswith(level + "_") or context == level or f"_{level}_" in context:
                    level_dir = os.path.join("levels", level)

                    # Area detection
                    area_index = -1
                    parts = context.split("_")
                    for i, part in enumerate(parts):
                        if part == "area" and i + 1 < len(parts):
                            try:
                                area_index = int(parts[i + 1])
                                break
                            except ValueError:
                                pass

                    if area_index != -1:
                        target_dir = os.path.join(level_dir, "areas", str(area_index))
                    else:
                        target_dir = level_dir
                    break

        return os.path.join(target_dir, filename)

    def pass_serialize(self) -> None:
        """
        Final pass: Regenerate all script text from the structured CommandIRs
        using the processor classes, organized into the original file structure.
        """
        # Reset context state so that path deduction is string-based during serialization
        ctx.curr_level = -1
        ctx.curr_area = -1
        ctx.current_context_prefix = None

        from geo_layout import get_geo_processor
        from collision import get_collision_processor
        from behavior import get_behavior_processor
        from display_list import get_display_list_processor
        from level_script import get_level_processor
        from macro_objects import get_macro_processor
        from collections import defaultdict
        import sys

        print("Writing files to output directory...")

        sys.stdout.flush()

        all_symbols = []
        filepath_to_content = defaultdict(list)

        # 1. Collect Geo Layouts
        gp = get_geo_processor()
        for geo_rec in self.db.geos.values():
            text = gp.serialize(geo_rec)
            all_symbols.append(("GeoLayout", geo_rec.name))
            path = self._get_target_path(geo_rec.name)
            filepath_to_content[path].append(text)

        # 2. Collect Collisions
        cp = get_collision_processor()
        for col_rec in self.db.collisions.values():
            text = cp.serialize(col_rec)
            all_symbols.append(("Collision", col_rec.name))
            path = self._get_target_path(col_rec.name)
            filepath_to_content[path].append(text)

        # 2.1 Collect Rooms
        from rooms import get_rooms_processor

        rp = get_rooms_processor()
        for room_rec in self.db.rooms.values():
            text = rp.serialize(room_rec)
            all_symbols.append(("Room", room_rec.name))
            path = self._get_target_path(room_rec.name)
            filepath_to_content[path].append(text)

        # 2.2 Collect Vertices
        from vertices import get_vertex_processor

        vp = get_vertex_processor()
        for vtx_rec in self.db.vertices.values():
            text = vp.serialize(vtx_rec)
            all_symbols.append(("Vtx", vtx_rec.name))
            path = self._get_target_path(vtx_rec.name)
            filepath_to_content[path].append(text)

        # 2.3 Collect Lights
        from lights import get_light_processor

        lp_light = get_light_processor()
        for light_rec in self.db.lights.values():
            text = lp_light.serialize(light_rec)
            all_symbols.append(("Lights", light_rec.name))
            path = self._get_target_path(light_rec.name)
            filepath_to_content[path].append(text)

        # 3. Collect Display Lists
        dp = get_display_list_processor()
        for dl_rec in self.db.display_lists.values():
            text = dp.serialize(dl_rec)
            all_symbols.append(("Gfx", dl_rec.name))
            path = self._get_target_path(dl_rec.name)
            filepath_to_content[path].append(text)

        # 4. Collect Behaviors
        bp = get_behavior_processor()
        for beh_rec in self.db.behaviors.values():
            text = bp.serialize(beh_rec)
            all_symbols.append(("BehaviorScript", beh_rec.beh_name))
            # Behaviors traditionally go to misc/behaviors.c
            filepath_to_content[os.path.join("misc", "behaviors.c")].append(text)

        # 5. Collect Macro Objects
        mp = get_macro_processor()
        for macro_rec in self.db.macros.values():
            text = mp.serialize(macro_rec)
            all_symbols.append(("MacroObject", macro_rec.name))
            path = self._get_target_path(macro_rec.name)
            filepath_to_content[path].append(text)

        # 6. Collect Level Scripts
        lp = get_level_processor()
        for script_rec in self.db.level_scripts.values():
            text = lp.serialize(script_rec)
            all_symbols.append(("LevelScript", script_rec.name))
            path = self._get_target_path(script_rec.name)
            filepath_to_content[path].append(text)

        # 7. Textures (segment-2 global + level textures)
        from texture import get_texture_processor, get_skybox_processor

        tp = get_texture_processor()
        for tex_rec in self.db.textures.values():
            text = tp.serialize(tex_rec)
            if text:
                all_symbols.append(("Texture", tex_rec.name))
                # The C struct belongs in model.inc.c (or similar)
                # We use a suffix to force _get_target_path to return the .c file
                c_path = self._get_target_path(f"{tex_rec.name}_dl")
                filepath_to_content[c_path].append(text)

        # 8. Skyboxes
        sp = get_skybox_processor()
        for sky_rec in self.db.skyboxes.values():
            text = sp.serialize(sky_rec)
            if text:
                all_symbols.append(("Skybox", sky_rec.level_prefix))
                # Skybox C code traditionally goes to texture.inc.c
                path = self._get_target_path(f"{sky_rec.level_prefix}_tiles_c")
                filepath_to_content[path].append(text)

        # 9. Audio sequences + music.lua
        from audio import get_audio_processor

        ap = get_audio_processor()
        ap.serialize(self.db.audio)

        # 10. Write all accumulated content to disk
        if self.txt:
            for path, contents in filepath_to_content.items():
                # Join all chunks of code for this specific file
                full_text = "\n\n".join(contents)
                self.txt.create_file(path, full_text)

    # ------------------------------------------------------------------
    # Pass 1: Initialisation
    # ------------------------------------------------------------------

    def pass_init(self) -> None:
        """
        Load the ROM, detect endianness, set up the segment system and
        OutputManager.
        """
        import os
        import shutil

        from segment import CustomBytesIO, segments_load_rom
        from output_manager import OutputManager
        from compression_util.compression import get_compression_types
        from utils import (
            ROM_Endian,
            swap_little_big,
            swap_mixed_big,
            is_romhack,
            find_all_needles_in_haystack,
            set_rom,
            validator,
            get_internal_name,
        )

        filename = self.rom_path
        base_filename = os.path.basename(filename)

        # Read ROM
        with open(filename, "rb") as f:
            rom_data = bytearray(f.read())

        # Detect and normalise endianness
        first_two = rom_data[:2]

        if first_two[0] == 0x80 and first_two[1] == 0x37:
            endian = ROM_Endian.BIG
        elif first_two[0] == 0x37 and first_two[1] == 0x80:
            endian = ROM_Endian.MIXED
            swap_mixed_big(rom_data)
        elif first_two[0] == 0x40 and first_two[1] == 0x12:
            endian = ROM_Endian.LITTLE
            swap_little_big(rom_data)
        else:
            from utils import debug_fail

            debug_fail(f"Unknown ROM endianness: {hex(first_two[0])} {hex(first_two[1])}")
            endian = ROM_Endian.BIG  # unreachable, debug_fail raises

        self.rom = CustomBytesIO(bytes(rom_data))
        set_rom(self.rom)

        internal_name = get_internal_name(rom_data)
        is_hack = is_romhack(self.rom)

        # Attempt to identify what type of ROM it is
        rom_types = [
            # rom has been extended. It just means no data here.
            # (bytes([0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01]), "M64 ROM extender or Rom Manager"),
            # editor hacks
            (bytes([0x80, 0x08, 0x00, 0x00, 0x19, 0x00, 0x00, 0x1C]), "SM64 Editor"),
            (bytes([0x80, 0x08, 0x00, 0x00, 0x0E, 0x00, 0x00, 0xC4]), "SM64 Editor"),
            (bytes([0x08, 0x00, 0x00, 0x0A, 0x00, 0xA0, 0x00, 0x78]), "SM64 Editor"),
        ]
        hack_type = ""
        if is_hack:
            for compare, name in rom_types:
                if rom_data[0x1200000:0x1200008] == compare:
                    hack_type = name
                    break

        # Update db.meta
        self.db.meta.filename = filename
        self.db.meta.endian = endian
        self.db.meta.is_hack = is_hack
        self.db.meta.hack_type = hack_type
        self.db.meta.internal_name = internal_name

        print(
            f"Opened ROM {filename} ({internal_name})\nROM is {'a romhack' if self.db.meta.is_hack else 'vanilla'}"
        )

        if hack_type != "":
            print(f"ROM was likely built with {hack_type}.")

        self._prev_offset = self.rom.tell()

        # Detect compression
        compression_types = get_compression_types()
        for ctype in compression_types:
            results = find_all_needles_in_haystack(self.rom.getvalue(), ctype)
            if len(results) > 0:
                self._compression_type = ctype.decode()
                self.db.meta.compression = self._compression_type
                print(f"ROM uses {self._compression_type} compression.")
                break

        if self._compression_type is None:
            print("No specific compression header found. Assuming 'NONE' for global ROM.")
            self._compression_type = "NONE"
            self.db.meta.compression = "NONE"

        self.rom.seek(0)
        segments_load_rom(self.rom)

        # Run any deferred validator tests registered by module imports
        validator.run_pending_tests()

        if validator.is_decomp:
            self.db.meta.is_decomp = True
            print("NOTICE: ROM is likely a DECOMP-based hack.")
        else:
            print("NOTICE: ROM matches traditional layout.")

        # Set up output directory
        runtime_base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(runtime_base_dir, "out", base_filename)
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir)

        self.txt = OutputManager(self.output_dir, internal_name)

        # Wire db into the global extraction context so extractors can use it
        ctx.db = self.db
        ctx.txt = self.txt

    # ------------------------------------------------------------------
    # Pass 2: Dynamic emulation (n64js / python fallback)
    # ------------------------------------------------------------------

    def pass_emulate(self) -> None:
        """
        Launch the n64js headless emulator (or Python fallback), parse its
        stdout to detect:
          - Segment 2 (MIO0/etc compressed block via PI DMA)
          - Microcode version
          - ALSeqFile header locations
        """
        from display_list import set_microcode
        from segment import load_segment
        from utils import validator, debug_print

        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Build emulator command
        host = self.host
        if host == "auto":
            if shutil.which("bun"):
                host = "bun"
            elif shutil.which("node"):
                host = "node"
            else:
                host = "python"

        debug_print(
            f"Using {host} to emulate {self.rom_path} to find segment 2 "
            f"({self._compression_type}) while it's loaded..."
        )

        filename = self.rom_path
        ct = self._compression_type or "MIO0"

        if host == "bun":
            cmd: List[str] = [
                "bun",
                os.path.join(current_dir, "n64js_headless.mjs"),
                filename,
                "--compression-type",
                ct,
            ]
        elif host == "node":
            cmd = [
                "node",
                os.path.join(current_dir, "n64js_headless_node.mjs"),
                filename,
                "--compression-type",
                ct,
            ]
        else:
            cmd = [
                str(sys.executable),
                os.path.join(current_dir, "n64_host.py"),
                filename,
                "--compression-type",
                ct,
            ]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        pi_dma_pattern = re.compile(
            rf"\[PI DMA\] found {ct} header at ROM 0x([0-9a-fA-F]+) cart=0x([0-9a-fA-F]+)"
        )

        TIMEOUT_SECONDS = 10.0
        start_time = time.time()
        stdout = process.stdout
        if stdout is None:
            return
        required_microcode_detected = False

        # Create a queue and a thread to read the stdout without blocking
        io_q: queue.Queue = queue.Queue()

        def stream_reader(pipe, q):
            for line in iter(pipe.readline, b""):
                q.put(line)
            pipe.close()

        thread = threading.Thread(target=stream_reader, args=(stdout, io_q))
        thread.daemon = True
        thread.start()
        try:
            while True:
                remaining = TIMEOUT_SECONDS - (time.time() - start_time)
                if remaining <= 0:
                    print(f"Timeout ({TIMEOUT_SECONDS}s) waiting for n64js; killing.")
                    process.kill()
                    break

                if not io_q.empty():
                    line = io_q.get()
                else:
                    # No data yet, check if process is still alive
                    if process.poll() is not None:
                        break
                    continue

                if not line:
                    break

                # Segment 2 detection (PI DMA)
                match = pi_dma_pattern.search(line)
                if match:
                    rom_offset = int(match.group(1), 16)
                    debug_print(f"{ct} header found at ROM 0x{rom_offset:08X}, loading seg2")

                    # Precise sizing
                    block_size = self._get_compressed_block_size(rom_offset, ct)
                    from typing import cast

                    rom_end = (
                        rom_offset + block_size if block_size > 0 else len(cast(Any, self.rom))
                    )
                    debug_print(f"Segment 2 size: 0x{(rom_end - rom_offset):X} bytes")

                    load_segment(2, rom_offset, rom_end, True)

                    # Record in db
                    self.db.global_segs[2] = GlobalSegRecord(
                        seg_num=2, rom_offset=rom_offset, rom_end=rom_end
                    )

                    # Extract global textures from segment 2
                    from segment2_extractor import get_segment2_processor

                    s2p = get_segment2_processor()
                    s2p.ctx.txt = self.txt
                    s2p.parse(0)

                # Microcode detection
                mc_match = re.search(
                    r"\[N64JS MICROCODE\]\s+ucode=(\d+)\s+mapped=([A-Za-z0-9_]+)"
                    r"\s+version=\"(.*)\"",
                    line,
                )
                if mc_match:
                    mapped = mc_match.group(2)
                    version = mc_match.group(3)
                    print(f"Microcode detected by n64js: {version} -> {mapped}")
                    if mapped and mapped.lower() != "unknown":
                        set_microcode(mapped)
                        self.db.meta.microcode = mapped
                        required_microcode_detected = True
                        if mapped != "F3D":
                            validator.set_decomp(
                                f"Non-standard microcode (therefore decomp): {mapped}"
                            )
                    else:
                        validator.set_decomp(f"Unknown microcode (therefore decomp): {version}")

                # ALSeqFile detection
                seq_match = re.search(r"ALSeqFile at ROM 0x([0-9a-fA-F]+)", line)
                if seq_match:
                    offset = int(seq_match.group(1), 16)
                    debug_print(f"Found ALSeqFile header at ROM 0x{offset:08X}")
                    self._alseq_candidates.append(offset)
                    self.db.audio.alseq_candidates.append(offset)

                if line.strip() == "--- n64js completed tasks, exiting ---":
                    process.kill()
                    break
        except Exception as e:
            print(f"Error: {e}")
            process.kill()

        finally:
            try:
                process.wait(timeout=2)
            except Exception:
                print("Cleanup timeout hit, forcefully killing n64js process...")
                try:
                    process.kill()
                    debug_print("n64js process killed")
                except Exception:
                    debug_print("Failed to kill n64js process")

        # Fallback: scan ROM for microcode signatures
        if not required_microcode_detected:
            debug_print("Microcode not detected by n64js. Attempting ROM scan fallback...")
            mc_name = self._detect_microcode_from_rom()
            if mc_name:
                set_microcode(mc_name)
                self.db.meta.microcode = mc_name
                required_microcode_detected = True

        assert required_microcode_detected, "ERROR: Microcode detection failed even with fallbacks."

    # ------------------------------------------------------------------
    # Pass 3: Audio
    # ------------------------------------------------------------------

    def pass_audio(self) -> None:
        """Extract ALSeqFile data if any candidates were found in pass_emulate."""
        from audio import extract_alseq_file_data

        assert self.rom is not None
        assert self.txt is not None

        self._status("sequences", "start")
        if self._alseq_candidates:
            saved_pos = self.rom.tell()
            extract_alseq_file_data(self.rom, self.txt, self._alseq_candidates, self.output_dir)
            self.rom.seek(saved_pos)
            self._status("sequences", "done")
        else:
            self._status("sequences", "skipped")

    # ------------------------------------------------------------------
    # Pass 4: Text / Dialog export
    # ------------------------------------------------------------------

    def pass_text(self) -> None:
        """
        Export in-ROM text/dialog.  Supports async export if available.
        """
        import text_export

        assert self.rom is not None
        assert self.txt is not None

        self._status("text", "start")
        text_export_async_fn = getattr(text_export, "export_text_async", None)
        if callable(text_export_async_fn):
            self._text_future = text_export_async_fn(self.rom, self.txt, self.output_dir)
            if self._text_future:

                def _done(fut) -> None:
                    try:
                        fut.result()
                        self._status("text", "done")
                    except Exception:
                        self._status("text", "error")

                try:
                    self._text_future.add_done_callback(_done)
                except Exception:
                    pass
        else:
            try:
                text_export.export_text(self.rom, self.txt, self.output_dir)
                self._status("text", "done")
            except Exception:
                self._status("text", "error")

    # ------------------------------------------------------------------
    # Pass 5: Level scripts
    # ------------------------------------------------------------------

    def pass_level_scripts(self) -> None:
        """
        Search the ROM for the entry-script signature and parse all found
        level scripts, populating db.levels.
        """
        from utils import find_all_needles_in_haystack, debug_fail, debug_print
        from level_script import parse_entry_script

        assert self.rom is not None
        assert self.txt is not None

        # Import local byte-pattern helpers from extract.py
        # (kept there to avoid duplication)
        from extract import INIT_LEVEL, SLEEP, BLACKOUT, JUMP

        candidates = find_all_needles_in_haystack(self.rom.getvalue(), INIT_LEVEL())
        results = []
        for i in range(len(candidates)):
            cand = candidates[i]
            # Check for SLEEP(2) nearby (within 32 bytes)
            nearby = self.rom.getvalue()[cand : cand + 32]
            if SLEEP(2) in nearby and BLACKOUT(False) in nearby:
                results.append(cand)

        if len(results) < 1:
            # Fallback for some hacks: just SLEEP + BLACKOUT
            results = find_all_needles_in_haystack(self.rom.getvalue(), SLEEP(2) + BLACKOUT(False))

        if len(results) < 1:
            debug_print(
                "Could not find standard entry script pattern. Searching for INIT_LEVEL only..."
            )
            results = candidates[:1]  # Blindly try the first one if all else fails

        if not results:
            debug_fail("Cannot find any entry script instance.")
            self._status("level_scripts", "not_found")
            return

        self._status("level_scripts", "start")
        jump_cmd_start, _ = JUMP(0)

        for start in results:
            end = -1
            index = start
            while index < len(self.rom):
                cmd = self.rom[index : index + 4]
                if cmd == jump_cmd_start:
                    end = index + 8
                    break
                index += 4

            if end != -1:
                debug_print(f"Found entry level script at 0x{start:08x}")
                self.rom.seek(self._prev_offset, 0)
                parse_entry_script(self.rom, self.txt, start, end)

        self._status("level_scripts", "done")

    # ------------------------------------------------------------------
    # Pass 6: Global candidates (JUMP_LINK targets)
    # ------------------------------------------------------------------

    def pass_global_candidates(self) -> None:
        """Process any JUMP_LINK targets recorded during level script parsing."""
        from utils import debug_print

        assert self.txt is not None

        try:
            from level_script import process_global_candidates

            process_global_candidates(self.txt)
        except Exception:
            debug_print("process_global_candidates failed or not present")
        else:
            self._status("level_scripts", "globals_done")

    # ------------------------------------------------------------------
    # Pass 5b: Trajectory Scan (Optional/Disabled)
    # ------------------------------------------------------------------

    def pass_trajectory_scan(self) -> None:
        """
        Scan for trajectories in specific segments.
        This is slow and typically only used during deep research.
        """
        from trajectory import scan_for_trajectories
        from utils import debug_print
        from segment import get_loaded_segment_numbers

        assert self.txt is not None

        debug_print("Scanning for trajectories...")
        loaded_segs = get_loaded_segment_numbers()
        for seg_num in loaded_segs:
            # Scan all loaded segments EXCEPT Segment 7 (which is level-specific and handled during script parsing)
            # and excluding Segment 1 (often small/junk in hacks)
            if seg_num not in (1, 7):
                debug_print(f"Scanning segment 0x{seg_num:02X} for trajectories...")
                scan_for_trajectories(seg_num, self.txt)

    # ------------------------------------------------------------------
    # Analysis passes (db_passes)
    # ------------------------------------------------------------------

    def pass_analysis(self) -> None:
        """
        Run database-driven analysis passes that cross-reference records
        to improve confidence, naming, and vanilla detection.
        """
        from db_passes import run_all_analysis_passes
        from utils import debug_print

        if not self.db:
            return
        debug_print("=== Analysis Passes ===")
        run_all_analysis_passes(self.db)

    # ------------------------------------------------------------------
    # Optimization passes
    # ------------------------------------------------------------------

    def pass_optimization(self) -> None:
        """
        Run optimization passes on the database.
        """
        from optimization_passes import run_model_optimization_passes
        from utils import debug_print

        if not self.db:
            return
        debug_print("=== Optimization Passes ===")

        # Optimize models
        run_model_optimization_passes(self.db)

        # Optimize level scripts

        # Identify all scripts that are actually referenced by a command
        referenced_scripts = set()
        for s in self.db.level_scripts.values():
            for cmd in s.commands:
                for param in cmd.params:
                    # Check if the parameter is a reference to another LevelRecord
                    if hasattr(param, "script_addr"):
                        referenced_scripts.add(param.script_addr)
        for addr, script in list(self.db.level_scripts.items()):
            # Skip over non-master scripts, and prune unreferenced ones
            if not (script.name.startswith("level_") and script.name.endswith("_entry")):
                if addr not in referenced_scripts:
                    self.db.level_scripts.pop(addr)
                continue

            # skip if this script was already inlined into another script in this pass
            if addr not in self.db.level_scripts:
                continue

            in_area_block = False
            i = 0
            while i < len(script.commands):
                cmd = script.commands[i]

                # Remove NOPs
                if cmd.name == "SKIP_NOP" or cmd.name == "NOP":
                    cmd.comment = "// "

                if cmd.name == "AREA":
                    in_area_block = True
                if cmd.name == "END_AREA":
                    in_area_block = False

                # Expand jump links only inside AREA blocks
                if cmd.name == "JUMP_LINK" and in_area_block:
                    level_script = cmd.params[0]

                    # Ensure we have a valid record with commands to expand
                    if hasattr(level_script, "commands"):
                        level_script_cmds = level_script.commands[0:-1]  # skip return

                        # copy indentation across
                        for command in level_script_cmds:
                            command.indent = cmd.indent
                        script.commands[i : i + 1] = level_script_cmds

                        # remove the original level script from the database
                        self.db.level_scripts.pop(level_script.script_addr, None)

                        # Do not increment i; re-process the new commands at this position
                        continue

                i += 1

    # ------------------------------------------------------------------
    # Refinement Pass A: Behavior resolution
    # ------------------------------------------------------------------

    def pass_refine_behaviors(self) -> None:
        """
        Ensure all objects have a beh_name that matches the recorded BehaviorRecord
        if they share the same address. This handles cases where a behavior was
        identified in one script but used (unidentified) in another.
        """
        for level in self.db.levels.values():
            for area in level.areas.values():
                for obj in area.objects:
                    if not obj.beh_addr:
                        continue

                    # Fallback logic: check all possible behavior records for this address
                    for key, beh_rec in self.db.behaviors.items():
                        if key[0] == obj.beh_addr:
                            if beh_rec.beh_name and not obj.beh_name:
                                obj.beh_name = beh_rec.beh_name
                            elif (
                                beh_rec.beh_name
                                and obj.beh_name
                                and ("0x" in obj.beh_name or "bhv_unknown" in obj.beh_name)
                            ):
                                obj.beh_name = beh_rec.beh_name
                            break

    # ------------------------------------------------------------------
    # Refinement Pass B: Model ID cross-referencing
    # ------------------------------------------------------------------

    def pass_refine_models(self) -> None:
        """
        For every ObjectRecord in every area of every level, attempt to
        improve model_id resolution using the level's model table and
        global assets.
        """
        from model_ids import MODEL_ID_BY_VALUE

        for level in self.db.levels.values():
            # First, try to fill in missing names in the level's model table
            # using global records discovered during parsing.
            for model_rec in level.models.values():
                if model_rec.geo_addr and not model_rec.geo_name:
                    for key, geo_rec in self.db.geos.items():
                        if key[0] == model_rec.geo_addr:
                            model_rec.geo_name = geo_rec.name
                            break

                if model_rec.dl_addr and not model_rec.dl_name:
                    for key, dl_rec in self.db.display_lists.items():
                        if key[0] == model_rec.dl_addr:
                            model_rec.dl_name = dl_rec.name
                            break

            # Now refine individual object model names
            for area in level.areas.values():
                for obj in area.objects:
                    if obj.refined_model_name:
                        continue  # already refined by a per-script pass

                    candidates = MODEL_ID_BY_VALUE.get(obj.model_id, [])
                    if not candidates:
                        continue

                    # If only one candidate exists, it's trivial
                    if len(candidates) == 1:
                        obj.refined_model_name = candidates[0]
                        continue

                    # Look up the model record in this level's model table
                    obj_model_rec = level.models.get(obj.model_id)
                    if obj_model_rec is None or not obj_model_rec.geo_name:
                        continue

                    geo_lower = (
                        obj_model_rec.geo_name.lower().replace("_geo", "").replace("geo_", "")
                    )
                    for c in candidates:
                        short = c[6:].lower() if c.startswith("MODEL_") else c.lower()
                        if short in geo_lower or geo_lower in short:
                            obj.refined_model_name = c
                            break

    # ------------------------------------------------------------------
    # Refinement Pass C: Warp target resolution
    # ------------------------------------------------------------------

    def pass_refine_warps(self) -> None:
        """
        Replace raw numeric warp-target level IDs with known level name
        strings now that all levels have been parsed.

        Warp dicts stored in AreaRecord.warps use key "dest_level_id" (int).
        After this pass, a "dest_level_name" key is added where a match exists.
        """
        from utils import level_name_to_int

        # Build a reverse map: level_id (int) -> level_name (str)
        id_to_name: dict[int, str] = {}
        for name, level_id in level_name_to_int.items():
            if isinstance(level_id, int):
                id_to_name[level_id] = name

        for level in self.db.levels.values():
            for area in level.areas.values():
                for warp in area.warps:
                    dest_id = warp.get("dest_level_id")
                    if dest_id is not None and dest_id in id_to_name:
                        warp["dest_level_name"] = id_to_name[dest_id]

    # ------------------------------------------------------------------
    # Final pass: summarise + close
    # ------------------------------------------------------------------

    def pass_finalize(self) -> int:
        """Print parse summary, assert segment hooks, close OutputManager."""
        from level_script import print_parse_summary
        from segment import seg_hooks_assert

        assert self.txt is not None

        ret = print_parse_summary()
        seg_hooks_assert()
        self.txt.close()
        ctx.reached_end = True

        return ret

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _status(self, component: str, state: str) -> None:
        """Emit a machine-readable status line for the GUI if enabled."""
        if not self.output_status:
            return
        try:
            print(f"{STATUS_PREFIX}{component}|{state}")
        except Exception:
            pass

    def _get_compressed_block_size(self, offset: int, compression_type: str) -> int:
        """Attempt to find the actual end of a compressed block via its header."""
        assert self.rom is not None
        self.rom.seek(offset)
        if compression_type == "MIO0":
            header = self.rom.read(4)
            if header == b"MIO0":
                from compression_util.compression import decompress_mio0, Endianness

                self.rom.seek(offset)
                data = self.rom.read(min(len(self.rom) - offset, 0x100000))
                try:
                    _, end_pos = decompress_mio0(data, Endianness.BIG)
                    return end_pos
                except Exception:
                    pass
        return 0

    def _detect_microcode_from_rom(self) -> Optional[str]:
        """Scan the ROM for RSP microcode string signatures."""
        assert self.rom is not None
        self.rom.seek(0)
        data = self.rom.read()
        signatures = [
            (b"F3DEX2.NoN", "F3DEX2"),
            (b"F3DEX.NoN", "F3DEX"),
            (b"F3DEX2.fifo", "F3DEX2"),
            (b"F3DEX2", "F3DEX2"),
            (b"F3DEX", "F3DEX"),
            (b"F3D", "F3D"),
            (b"Diddy Kong Racing", "Diddy Kong Racing"),
        ]
        for sig_bytes, mc_name in signatures:
            if sig_bytes in data:
                print(f"INFO: Detected microcode '{sig_bytes.decode()}' via ROM scan -> {mc_name}")
                return mc_name
        return None
