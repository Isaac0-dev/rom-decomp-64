import os
import hashlib
import struct
from typing import Any, List, Optional, Set, Tuple

import disassemble_sound
from base_processor import BaseProcessor
from context import ctx
from rom_database import AudioRecord, AudioSequenceRecord
from utils import debug_print, find_all_needles_in_haystack, read_int, get_rom


# Translation map for extended sound bank instrument indices
# LunaBank id -> coop ext bank id
# thanks to Fearl for the research on this
INSTRUMENT_MAP = {
    # 0x00: None, # Accordion -> Broken, no obvious replacement
    0x01: 0x5C,  # Slap Bass
    0x02: 0x5E,  # Clavinet or Electric Guitar
    0x03: 0x25,  # Electric Piano
    # 0x04: None, # Piano -> Broken, No obvious replacement
    0x05: 0x03,  # French Horn
    # 0x06: None, # Pan Flute -> Broken, no obvious replacement
    0x07: 0x4B,  # Strings
    0x08: 0x00,  # Nylon Guitar
    0x09: 0x06,  # Jingle Bells or Sleigh Bells
    0x0A: 0x05,  # Hi-hats
    0x0B: 0x11,  # Cymbals
    0x0C: 0x13,  # Triangle and Cabasa
    0x0D: 0x14,  # Celesta
    0x0E: 0x15,  # Banjo
    0x0F: 0x17,  # Fiddle
    0x10: 0x19,  # Whistle
    0x11: 0x1B,  # Acoustic Bass
    0x12: 0x12,  # Military Snare
    0x13: 0x23,  # Pizzicato Strings
    0x14: 0x24,  # Cello or Bassoon
    0x15: 0x28,  # Voice "Ooh"
    0x16: 0x64,  # Sitar Drone
    0x17: 0x29,  # Sitar
    0x18: 0x57,  # Drum Machine K/S Split
    0x19: 0x0D,  # Rhodes Bass
    0x1A: 0x59,  # Percussive Organ
    0x1B: 0x5A,  # Steel Drum
    0x1C: 0x2F,  # Brass
    0x1D: 0x5D,  # Synth Voice
    0x1E: 0x53,  # Low Cowbell
    0x1F: 0x2A,  # Charang (Pungi)
    0x20: 0x65,  # Overdriven Guitar
    0x21: 0x6A,  # Orchestra Hit
    0x22: 0x0E,  # Recorder
    0x23: 0x67,  # Power Drums Kit
    0x24: 0x54,  # High Cowbell
    0x25: 0x7B,  # Melodic Tom
    0x26: 0x1A,  # Steel Guitar or Bright Piano
    0x27: 0x85,  # "Pah" (Maybe Crash)
    0x28: 0x4D,  # Snow Accordion
    0x29: 0x0D,  # Synth Bass broken -> def to Rhodes Bass
    # 0x2A: None, # Lead Square -> Broken, no obvious replacement
    0x2B: 0x12,  # Military Snare
    0x2C: 0x2B,  # Trumpet
    0x2D: 0x31,  # Timpani
    0x2E: 0x27,  # Percussion Loop
    0x2F: 0x20,  # Strings (Low)
    0x30: 0x3D,  # Xylophone (Music Box)
    0x31: 0x43,  # Church Organ
    0x32: 0x51,  # Low Haunting Wind
    0x7F: 0x7F,  # Percussion
    0x80: 0x80,  # Saw Wave
    0x81: 0x81,  # Triangle Wave
    0x82: 0x82,  # Sine Wave
    0x83: 0x83,  # Step Wave
}


# Seems like romhacks such as SM74 have a different place to store bank ids
def check_7f0000_table(rom_bytes: bytes, seq_count: int) -> bool:
    try:
        base = 0x7F0000
        if base + seq_count * 2 >= len(rom_bytes):
            return False

        # Check first few sequences
        check_count = min(5, seq_count)
        valid_entries = 0

        for i in range(check_count):
            off = struct.unpack_from(">H", rom_bytes, base + i * 2)[0]
            if off == 0xFFFF:
                continue  # Empty entry

            bank_addr = base + off + 1
            if bank_addr >= len(rom_bytes):
                continue

            bank = rom_bytes[bank_addr]
            if bank != 0xFF:  # 0xFF is usually uninitialized
                valid_entries += 1

        return valid_entries > 0
    except Exception:
        return False


def find_gAlBankSets(rom_bytes: bytes, seq_count: int, header_offset: int) -> Optional[int]:
    rom_len = len(rom_bytes)
    candidates = []

    # Start scan from header_offset
    start_addr = header_offset
    if start_addr % 4 != 0:
        start_addr += 4 - (start_addr % 4)

    for base in range(start_addr, rom_len - seq_count * 2, 4):
        try:
            valid_entries = 0
            check_count = min(10, seq_count)

            for i in range(check_count):
                off = struct.unpack_from(">H", rom_bytes, base + i * 2)[0]
                if off < seq_count * 2 or off >= 0x1000:
                    break

                entry_addr = base + off
                if entry_addr >= rom_len:
                    break

                num_banks = rom_bytes[entry_addr]
                if num_banks > 0 and num_banks <= 64:
                    if i == 0:
                        last_bank = rom_bytes[entry_addr + num_banks]
                        if last_bank != 0:
                            break
                    valid_entries += 1
                else:
                    break

            if valid_entries == check_count:
                offsets = [
                    struct.unpack_from(">H", rom_bytes, base + i * 2)[0] for i in range(check_count)
                ]
                if len(set(offsets)) > 1:
                    score = 0
                    # Score to avoid unlikely bank ids
                    for i in range(check_count):
                        off = offsets[i]
                        entry = base + off
                        num = rom_bytes[entry]
                        last_bank = rom_bytes[entry + num]
                        if last_bank < 0x40:
                            score += 1

                    candidates.append((base, score))
        except Exception:
            continue

    if not candidates:
        return None

    # Return candidate with highest score
    # If tie, return the first one (lower address)
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_candidate = candidates[0][0]
    debug_print(f"Found gAlBankSets at 0x{best_candidate:08X} (Score: {candidates[0][1]})")
    return best_candidate


def get_bank_id(rom_bytes: bytes, source: Tuple[Optional[str], int], seq_id: int) -> int:
    strategy, base = source

    try:
        if strategy == "7f0000":
            offset_addr = base + seq_id * 2
            if offset_addr + 2 > len(rom_bytes):
                return 0

            offset = struct.unpack_from(">H", rom_bytes, offset_addr)[0]
            if offset == 0xFFFF:
                return 0

            bank_addr = base + offset + 1
            if bank_addr >= len(rom_bytes):
                return 0

            return rom_bytes[bank_addr]

        elif strategy == "scan":
            offset_addr = base + seq_id * 2
            offset = struct.unpack_from(">H", rom_bytes, offset_addr)[0]
            if offset == 0xFFFF:
                return 0

            entry_addr = base + offset
            if entry_addr >= len(rom_bytes):
                return 0

            num_banks = rom_bytes[entry_addr]
            if num_banks == 0:
                return 0

            return rom_bytes[entry_addr + num_banks]

    except Exception as e:
        debug_print(f"Error getting bank for seq {seq_id}: {e}")
        return 0

    return 0


def detect_bank_source(
    rom_bytes: bytes, seq_count: int, header_offset: int
) -> Tuple[Optional[str], int]:
    # SM74 audio test
    if check_7f0000_table(rom_bytes, seq_count):
        debug_print("Using 0x7F0000 bank table")
        return ("7f0000", 0x7F0000)

    # vanilla test
    scan_result = find_gAlBankSets(rom_bytes, seq_count, header_offset)
    if scan_result:
        debug_print(f"Using gAlBankSets at 0x{scan_result:08X}")
        return ("scan", scan_result)

    debug_print("No bank source found, defaulting to bank 0")
    return (None, 0)


extracted_offsets: List[int] = []
extracted_headers_hash: Set[str] = set()


def analyze_alseq_file_header(rom: Any, offset: int) -> Optional[Tuple[int, int, str]]:
    try:
        rom.seek(offset)
        header_start_bytes = rom.read(4)
        if len(header_start_bytes) < 4:
            return None

        revision = struct.unpack(">H", header_start_bytes[0:2])[0]
        seq_count = struct.unpack(">H", header_start_bytes[2:4])[0]

        if seq_count > 256:
            return None

        header_entries_bytes = rom.read(seq_count * 8)
        header_content = header_start_bytes + header_entries_bytes
        header_hash = hashlib.md5(header_content).hexdigest()

        return (revision, seq_count, header_hash)
    except Exception:
        return None


def extract_alseq_file_data(rom: Any, txt: Any, candidates: List[int], output_dir: str) -> None:
    if ctx.db is not None:
        ctx.db.audio = AudioRecord(alseq_candidates=candidates)

    if not candidates:
        return

    best_candidate = None
    best_count = -1

    unique_candidates = sorted(list(set(candidates)))

    print(f"Analyzing {len(unique_candidates)} sequence header candidates...")

    ctl_offset = -1
    tbl_offset = -1
    for offset in unique_candidates:
        info = analyze_alseq_file_header(rom, offset)
        if info:
            revision, count, _ = info
            print(f"  Candidate 0x{offset:08X}: Rev {revision}, {count} sequences")

            if revision == 1:
                ctl_offset = offset
            elif revision == 2:
                tbl_offset = offset
            elif revision == 3:
                # Prioritize higher sequence count for the actual sequence data
                if count > best_count:
                    best_count = count
                    best_candidate = offset

    ap = get_audio_processor()
    extract_sound(rom, txt, output_dir, ctl_offset, tbl_offset)

    if best_candidate is not None:
        print(
            f"Selected best sequence header at 0x{best_candidate:08X} with {best_count} sequences."
        )

        # Extract sequences
        ap.parse(rom, header_offset=best_candidate, output_dir=output_dir)
    else:
        print("No valid sequence headers found among candidates.")


class AudioProcessor(BaseProcessor):
    """
    Discovers sequences from an ALSeqFile and serializes them to disk.

    parse()     — reads sequence data, stores AudioSequenceRecord entries in
                  db.audio.sequences and lua_lines. No file I/O.
    serialize() — writes .m64 files and music.lua from the stored records.
    """

    def parse(self, segmented_addr: int, **kwargs: Any) -> None:
        header_offset: int = kwargs["header_offset"]

        rom = get_rom()

        if header_offset in extracted_offsets:
            return
        extracted_offsets.append(header_offset)

        info = analyze_alseq_file_header(rom, header_offset)
        if not info:
            return

        revision, seq_count, header_hash = info

        if header_hash in extracted_headers_hash:
            debug_print(
                f"Skipping duplicate sequence header at 0x{header_offset:08X} (already extracted)"
            )
            return
        extracted_headers_hash.add(header_hash)

        debug_print(f"Extracting sequences from 0x{header_offset:08X}...")
        debug_print(f"Sequence Header: Revision {revision}, Count {seq_count}")

        rom_bytes = rom.getvalue()
        bank_source = detect_bank_source(rom_bytes, seq_count, header_offset)

        lua_lines: List[str] = []
        count = 0

        for i in range(seq_count):
            # Disable extracting sound effects
            if i == 0:
                continue

            entry_offset = header_offset + 4 + i * 8
            rom.seek(entry_offset)
            offset = read_int(rom)
            length = read_int(rom)

            if offset == 0 and length == 0:
                continue

            if offset is None or length is None:
                continue
            abs_offset = header_offset + offset

            if abs_offset + length > len(rom.getvalue()):
                debug_print(
                    f"Warning: Sequence {i} out of bounds (0x{abs_offset:08X} + 0x{length:X})"
                )
                continue

            rom.seek(abs_offset)
            data = rom.read(length)

            bank_id = get_bank_id(rom_bytes, bank_source, i)
            volume = 75
            seq_name = f"seq_{i:02X}"

            # Translate ext instruments
            if bank_id == 0x0C:
                mut_data = bytearray(data)
                j = 0
                while j < len(mut_data) - 1:
                    # 0xC1 = CMD_INSTRUMENT in Seq64 (used for Program Change)
                    if mut_data[j] == 0xC1:
                        inst = mut_data[j + 1]
                        if inst in INSTRUMENT_MAP:
                            mut_data[j + 1] = INSTRUMENT_MAP[inst]
                            # Assume standard 2-byte usage of 0xC1, skip the payload
                            j += 1
                    j += 1
                data = mut_data
                bank_id = 0x2A

            lua_lines.append(
                f"smlua_audio_utils_replace_sequence("
                f"0x{i:02X}, 0x{bank_id:02X}, {volume}, '{seq_name}')\n"
            )

            if self.db is not None:
                self.db.audio.sequences.append(
                    AudioSequenceRecord(seq_id=i, bank_id=bank_id, data=bytes(data))
                )
            count += 1

        if self.db is not None:
            self.db.audio.lua_lines = lua_lines

        print(f"Stored {count} sequences for deferred write.")

    def serialize(self, record: AudioRecord) -> str:
        """Write all stored sequences and music.lua to disk."""
        if not record.sequences and not record.lua_lines:
            return ""

        # Determine output dir from txt base path
        base_path = self.txt.base_path if self.txt else "out"
        seq_dir = os.path.join(base_path, "sound")
        os.makedirs(seq_dir, exist_ok=True)

        for seq_rec in record.sequences:
            out_path = os.path.join(seq_dir, f"seq_{seq_rec.seq_id:02X}.m64")
            with open(out_path, "wb") as f:
                f.write(seq_rec.data)

        if record.lua_lines and self.txt:
            self.txt.write_lua(record.lua_lines, "music.lua")

        print(f"Wrote {len(record.sequences)} sequences and music.lua.")
        return ""


_audio_processor: Optional[AudioProcessor] = None


def get_audio_processor() -> AudioProcessor:
    global _audio_processor
    if _audio_processor is None:
        _audio_processor = AudioProcessor(ctx)
    return _audio_processor


def extract_sound(rom: Any, txt: Any, output_dir: str, ctl_offset: int, tbl_offset: int) -> None:
    sampledir = os.path.join(output_dir, "sound")
    os.makedirs(sampledir, exist_ok=True)

    # If offsets weren't found via ALSeqFile detection, try to find them via signature or vanilla fallback
    if ctl_offset == -1:
        ctl_header_bytes = b"\x00\x01\x00\x26\x00\x00\x01\x40\x00\x00\x04\x20\x00\x00\x05\x60"
        ctl_header_matches = find_all_needles_in_haystack(rom, ctl_header_bytes)
        if len(ctl_header_matches) > 0:
            ctl_offset = ctl_header_matches[0]

    if tbl_offset == -1:
        tbl_header_bytes = b"\x00\x02\x00\x26\x00\x00\x01\x40\x00"
        tbl_header_matches = find_all_needles_in_haystack(rom, tbl_header_bytes)
        if len(tbl_header_matches) > 0:
            tbl_offset = tbl_header_matches[0]

    # Final vanilla fallbacks if all else fails
    if ctl_offset == -1 or tbl_offset == -1:
        # Check region
        rom.seek(0x3B)
        region = rom.read(1)
        if region == b"E":  # US
            if ctl_offset == -1:
                ctl_offset = 0x57B720
            if tbl_offset == -1:
                tbl_offset = 0x593560
        elif region == b"J":  # JP
            if ctl_offset == -1:
                ctl_offset = 0x5491D0
            if tbl_offset == -1:
                tbl_offset = 0x55F9B0
        elif region == b"P":  # EU
            if ctl_offset == -1:
                ctl_offset = 0x539920
            if tbl_offset == -1:
                tbl_offset = 0x54F210
        else:
            debug_print(
                f"Couldn't find offsets for sound extraction! (ctl=0x{ctl_offset:X}, tbl=0x{tbl_offset:X}) {region}"
            )
            return

    print(f"Extracting sounds (ctl=0x{ctl_offset:08X}, tbl=0x{tbl_offset:08X})")

    try:
        disassemble_sound.main(
            rom,
            ctl_offset,
            len(rom) - ctl_offset,
            tbl_offset,
            len(rom) - tbl_offset,
            sampledir,
            sampledir,
            txt,
        )
        pass
    except Exception:
        import traceback

        traceback.print_exc()
        debug_print("Failed to extract sound, continuing...")
