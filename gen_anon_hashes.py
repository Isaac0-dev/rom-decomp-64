#!/usr/bin/env python3
"""
Generate anonymous behavior hashes from a vanilla ROM and append them
to behavior_hashes.py.

Usage:
    python3 gen_anon_hashes.py baserom.us.z64

This runs the behavior parser against the vanilla ROM's behavior segment
and computes the anonymous hash (CALL_NATIVE = always UNKNOWN) for every
known behavior. The output is a dict that can be merged into
KNOWN_BEHAVIOR_HASHES.
"""

import sys
import os

# Add the py/ directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from behavior_hashes import KNOWN_BEHAVIOR_HASHES


def collect_existing_anon_hashes():
    """Find all (precise_hash, behavior_name) pairs and compute what the
    anonymous hash would be IF we could re-parse the original data.

    Since we can't re-parse without the ROM loaded, we need a different strategy:
    Run the full extractor against the vanilla ROM and intercept the hashes.
    """
    # We need to actually run extraction to get the commands_data.
    # This script hooks into the extraction pipeline.
    pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 gen_anon_hashes.py <vanilla_rom.z64>")
        sys.exit(1)

    rom_path = sys.argv[1]

    # Import and run extraction to populate the behavior database
    from context import ctx
    from rom_database import RomDatabase

    ctx.db = RomDatabase()

    # Minimal pipeline run to discover behaviors
    from pipeline import ExtractionPipeline

    # Redirect output
    pipeline = ExtractionPipeline(rom_path)
    pipeline.output_dir = "/tmp/anon_hash_gen"
    pipeline.pass_init()
    pipeline.pass_emulate()
    pipeline.pass_level_scripts()

    # Now collect all anonymous hashes
    new_entries = {}
    for key, beh in ctx.db.behaviors.items():
        if beh.beh_name.startswith("bhv_unknown") or beh.beh_name.startswith("bhv_fail"):
            continue
        if beh.anon_hash:
            new_entries[beh.anon_hash] = beh.beh_name

    # Check which ones are truly new (not already in KNOWN_BEHAVIOR_HASHES)
    added = 0
    for h, name in sorted(new_entries.items(), key=lambda x: x[1]):
        if h not in KNOWN_BEHAVIOR_HASHES:
            print(f'    "{h}": "{name}",')
            added += 1

    print(f"\n# {added} new anonymous hashes to add to KNOWN_BEHAVIOR_HASHES", file=sys.stderr)


if __name__ == "__main__":
    main()
