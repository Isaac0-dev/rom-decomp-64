import re
import json
import gzip
from pathlib import Path
from extractor import MipsFunctionExtractor


class VanillaSignatureGenerator:
    def __init__(self, map_path, rom_path, output_path):
        self.map_path = Path(map_path)
        self.rom_path = Path(rom_path)
        self.output_path = Path(output_path)
        self.symbols = []

        # TODO update this to be dynamic later
        # VRAM Start: 0x80246000
        # ROM Start:  0x1000
        self.CODE_VRAM_START = 0x80246000
        self.CODE_ROM_START = 0x1000

    def parse_map(self):
        print(f"Parsing map file: {self.map_path}")
        symbol_re = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+(\w+)$")
        current_section = None
        current_obj = None

        candidates = []

        with open(self.map_path, "r") as f:
            for line in f:
                # Track sections
                if (
                    line.strip().startswith(".text")
                    or line.strip().startswith(".data")
                    or line.strip().startswith(".rodata")
                    or line.strip().startswith(".bss")
                ):
                    parts = line.split()
                    if len(parts) >= 1:
                        current_section = parts[0]
                        if len(parts) >= 4 and parts[-1].endswith(".o"):
                            current_obj = parts[-1]
                    else:
                        current_section = None
                        current_obj = None
                    continue

                if ".text" in line or "build/" in line or "=" in line:
                    continue

                if current_section != ".text":
                    continue

                # Filter rsp.o and data objects (not useful)
                if current_obj and ("rsp.o" in current_obj or "data" in current_obj):
                    continue

                m = symbol_re.match(line)
                if m:
                    addr_str = m.group(1)
                    name = m.group(2)
                    addr = int(addr_str, 16)

                    # Filter for main code segment
                    # TODO update this to be dynamic later
                    if 0x80240000 <= addr < 0x80400000:
                        candidates.append({"name": name, "vram": addr})

        # Sort by address
        candidates.sort(key=lambda x: x["vram"])
        self.symbols = candidates
        print(f"Found {len(self.symbols)} candidate symbols.")

    def extract_and_process(self):
        if not self.rom_path.exists():
            print(f"Error: ROM not found at {self.rom_path}")
            return {}

        print(f"Reading ROM: {self.rom_path}")
        with open(self.rom_path, "rb") as f:
            rom_data = f.read()

        database = {}
        processed_count = 0
        skipped_count = 0

        for sym in self.symbols:
            vram = sym["vram"]
            name = sym["name"]

            # Calculate ROM offset
            if vram < self.CODE_VRAM_START:
                continue
            rom_offset = vram - self.CODE_VRAM_START + self.CODE_ROM_START

            if rom_offset >= len(rom_data):
                continue

            # Use Extractor
            # Note: We must restrict Extractor to NOT scan beyond end of ROM.
            extractor = MipsFunctionExtractor(
                rom_data, rom_offset, vram_start=self.CODE_VRAM_START, rom_start=self.CODE_ROM_START
            )

            result = extractor.extract()

            if result is None:
                # Extractor failed to find valid path (e.g. infinite loop protection or no code)
                # This often happens for symbols that are actually data labels in .text
                skipped_count += 1
                continue

            # Store in DB
            database[name] = {
                "vram": vram,
                "rom_offset": rom_offset,
                "size": result.size,
                "exact_hash": result.exact_hash,
                "masked_signature": result.masked_signature,
                "features": result.features,
            }
            processed_count += 1

        print(f"Processed {processed_count} functions (Skipped {skipped_count}).")
        return database

    def run(self):
        self.parse_map()
        db = self.extract_and_process()

        print(f"Saving database to {self.output_path}")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(self.output_path, "wt", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
        print("Done.")


if __name__ == "__main__":
    # Default paths
    ROOT = Path(__file__).resolve().parents[2]
    MAP_FILE = ROOT / "sm64.us.map"
    ROM_FILE = ROOT / "baserom.us.z64"
    OUTPUT_FILE = ROOT / "py" / "function_matching" / "vanilla_functions_db.json.gz"

    gen = VanillaSignatureGenerator(MAP_FILE, ROM_FILE, OUTPUT_FILE)
    gen.run()
