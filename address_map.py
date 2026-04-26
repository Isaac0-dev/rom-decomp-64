import re
import os
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum


class SymbolType(Enum):
    SYMBOL_TYPE_LEVEL_FUNC = 0
    SYMBOL_TYPE_BHV_FUNC = 1
    SYMBOL_TYPE_GEO_FUNC = 2
    SYMBOL_TYPE_ANIM = 3
    SYMBOL_TYPE_COLLISION = 4
    SYMBOL_TYPE_GEO = 5
    SYMBOL_TYPE_MACRO_OBJ = 6
    SYMBOL_TYPE_LVL_SCRIPT = 7
    SYMBOL_TYPE_BHV = 8


def get_physical_symbol(phys_addr: int, symbol_type: SymbolType) -> Optional[str]:
    from address_map_typed import address_map

    result = address_map.get(phys_addr)
    if result and result[1] == symbol_type:
        return result[0]
    return None


class AddressMap:
    _instance: Optional["AddressMap"] = None

    def __new__(cls, map_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super(AddressMap, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, map_path: Optional[str] = None):
        if self._initialized:
            return

        if map_path is None:
            # Get map from path in this directory
            map_path = "sm64.us.map"
            if not os.path.exists(map_path):
                # Try sibling directory as suggested by user in memory
                # But here it's in the root according to file tree.
                pass

        self.map_path = map_path
        self.addr_to_symbol: Dict[int, List[str]] = {}
        self.symbol_to_addr: Dict[str, int] = {}
        self.symbol_to_rom: Dict[str, int] = {}
        self.rom_to_symbol: Dict[int, List[str]] = {}
        self.segments: List[Tuple[int, int, int]] = []  # List of (vma_start, vma_end, lma_start)

        if map_path and os.path.exists(map_path):
            self._parse_map()
            self._initialized = True
        else:
            print(f"Warning: AddressMap could not find map file at {map_path}")

    def _parse_map(self):
        # Pattern for symbols: 0x0000000080246074                thread3_main
        # Note: We need to handle 64-bit addresses (padded with zeros) and 32-bit addresses
        symbol_re = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)$")

        # Pattern for segment name on its own line: .castle_grounds
        seg_name_re = re.compile(r"^\.([a-zA-Z0-9_\.]+)$")

        # Pattern for segment info (VMA, size, LMA): 0x0e000000      0x820 load address 0x004545e0
        seg_info_re = re.compile(
            r"^\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+load address\s+(0x[0-9a-fA-F]+)"
        )

        # Pattern for segment header on one line: .boot           0x04000000     0x1000 load address 0x00000000
        segment_re = re.compile(
            r"^\.([a-zA-Z0-9_\.]+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+load address\s+(0x[0-9a-fA-F]+)"
        )

        curr_vma = 0
        curr_lma = 0
        curr_segment = None
        pending_segment = None

        with open(self.map_path, "r") as f:
            for line in f:
                # Basic cleanup
                line = line.expandtabs(8).rstrip()
                if not line:
                    continue

                # Check for segment header on one line
                seg_m = segment_re.match(line)
                if seg_m:
                    curr_segment = seg_m.group(1)
                    curr_vma = int(seg_m.group(2), 16) & 0xFFFFFFFF
                    curr_lma = int(seg_m.group(4), 16) & 0xFFFFFFFF
                    size = int(seg_m.group(3), 16)
                    self.segments.append((curr_vma, curr_vma + size, curr_lma))
                    pending_segment = None
                    continue

                # Check for segment name on its own line
                name_m = seg_name_re.match(line)
                if name_m:
                    pending_segment = name_m.group(1)
                    continue

                # Check for segment info on its own line (usually after a name line)
                info_m = seg_info_re.match(line)
                if info_m and pending_segment:
                    curr_segment = pending_segment
                    curr_vma = int(info_m.group(1), 16) & 0xFFFFFFFF
                    curr_lma = int(info_m.group(3), 16) & 0xFFFFFFFF
                    size = int(info_m.group(2), 16)
                    self.segments.append((curr_vma, curr_vma + size, curr_lma))
                    pending_segment = None
                    continue

                # Check for address + symbol
                m = symbol_re.match(line)
                if m:
                    addr_str = m.group(1)
                    symbol = m.group(2)
                    try:
                        addr = int(addr_str, 16)
                        # We only care about 32-bit addresses for SM64
                        addr &= 0xFFFFFFFF

                        if addr not in self.addr_to_symbol:
                            self.addr_to_symbol[addr] = []
                        if symbol not in self.addr_to_symbol[addr]:
                            self.addr_to_symbol[addr].append(symbol)

                        self.symbol_to_addr[symbol] = addr

                        # Calculate ROM address if we are in a segment
                        if curr_segment is not None:
                            rom_addr = curr_lma + (addr - curr_vma)
                            self.symbol_to_rom[symbol] = rom_addr
                            if rom_addr not in self.rom_to_symbol:
                                self.rom_to_symbol[rom_addr] = []
                            if symbol not in self.rom_to_symbol[rom_addr]:
                                self.rom_to_symbol[rom_addr].append(symbol)
                    except ValueError:
                        pass

    def get_symbol(self, addr: int) -> Optional[str]:
        """Returns the first symbol found at the given address."""
        # Standardize address
        addr &= 0xFFFFFFFF
        symbols = self.addr_to_symbol.get(addr)
        return symbols[0] if symbols else None

    def get_symbols(self, addr: int) -> List[str]:
        """Returns all symbols found at the given address."""
        addr &= 0xFFFFFFFF
        return self.addr_to_symbol.get(addr, [])

    def get_rom_address(self, symbol_or_addr: Union[str, int]) -> Optional[int]:
        """Returns the ROM address (load address) for a given symbol or VRAM address."""
        if isinstance(symbol_or_addr, str):
            return self.symbol_to_rom.get(symbol_or_addr)

        # Handle VRAM address lookup
        addr = symbol_or_addr & 0xFFFFFFFF
        for v_start, v_end, l_start in self.segments:
            if v_start <= addr < v_end:
                return l_start + (addr - v_start)
        return None

    def get_symbols_at_rom(self, rom_addr: int) -> List[str]:
        """Returns symbols found at the given ROM address."""
        return self.rom_to_symbol.get(rom_addr, [])


def get_address_map() -> AddressMap:
    return AddressMap()
