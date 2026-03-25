import re
import os
from typing import Dict, List, Optional


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

        if map_path and os.path.exists(map_path):
            self._parse_map()
            self._initialized = True
        else:
            print(f"Warning: AddressMap could not find map file at {map_path}")

    def _parse_map(self):
        # Pattern for symbols: 0x0000000080246074                thread3_main
        symbol_re = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)$")

        # Also need to handle cases where the symbol is on the next line
        #                0x00000000803328E0                bhvStarDoor

        with open(self.map_path, "r") as f:
            for line in f:
                # Basic cleanup
                line = line.expandtabs(8).rstrip()

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

    def get_address(self, symbol: str) -> Optional[int]:
        """Returns the address for the given symbol."""
        return self.symbol_to_addr.get(symbol)


def get_address_map() -> AddressMap:
    return AddressMap()
