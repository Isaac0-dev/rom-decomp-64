import struct
import sys
import hashlib
from enum import Enum
from typing import List, Dict, Tuple, Optional, Any, Union
import logging
import os


class ParseError(Exception):
    pass


class ExtractionError(Exception):
    pass


logger = logging.getLogger("rom-decomp-64")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)


def is_debugger() -> bool:
    return "debugpy" in sys.modules


vanilla_rom = None
vanilla_rom_path = None


def unscramble_n64(name):
    for i in range(0, 20, 4):
        name[i], name[i + 3] = name[i + 3], name[i]
        name[i + 1], name[i + 2] = name[i + 2], name[i + 1]
    return name


def unscramble_v64(name):
    for i in range(0, 20, 2):
        name[i], name[i + 1] = name[i + 1], name[i]
    return name


def get_internal_name(rom_bytes: bytes):
    first_byte = rom_bytes[0]
    sjs_name = rom_bytes[0x20:0x34]

    if first_byte == 0x40:
        sjs_name = unscramble_n64(sjs_name)
    elif first_byte == 0x37:
        sjs_name = unscramble_v64(sjs_name)

    sjs_name = sjs_name[:20]
    sjs_name = bytes(b if b != 0 else 0x20 for b in sjs_name)

    name = sjs_name.decode("shift_jis", errors="ignore")
    if not name:
        name = sjs_name.decode("utf-8", errors="ignore")

    n = len(name)
    while n > 0 and name[n - 1] == " ":
        n -= 1

    return name[:n]


def get_vanilla_sm64_rom() -> Optional[bytes]:
    global vanilla_rom, vanilla_rom_path
    if vanilla_rom is not None:
        return vanilla_rom

    target_sha1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"

    # Locations to search
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    runtime_base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    search_dirs = [
        os.getcwd(),
        project_root,
        current_dir,
        runtime_base_dir,
        os.path.expanduser("~/.local/share/sm64coopdx"),
        os.path.expanduser("~/.local/share/sm64ex-coop"),
        os.path.expanduser("~/.local/share/mupen64plus/save"),
        os.path.expanduser("~/Downloads"),
    ]

    if sys.platform == "win32":
        if os.getenv("APPDATA"):
            search_dirs.append(os.path.join(os.getenv("APPDATA"), "sm64coopdx"))
            search_dirs.append(os.path.join(os.getenv("APPDATA"), "sm64ex-coop"))

    # Priority file names
    priority_names = ["baserom.us.z64", "Super Mario 64 (USA).z64", "sm64.us.z64"]

    seen_paths = set()

    def check_file(path):
        if not os.path.exists(path) or path in seen_paths:
            return None
        seen_paths.add(path)
        try:
            with open(path, "rb") as f:
                data = f.read()
                if hashlib.sha1(data).hexdigest() == target_sha1:
                    return data
        except Exception:
            pass
        return None

    # Step 1: Check priority names in search dirs
    for d in search_dirs:
        if not d or not os.path.exists(d):
            continue
        for name in priority_names:
            full_path = os.path.join(d, name)
            res = check_file(full_path)
            if res:
                vanilla_rom = res
                vanilla_rom_path = full_path
                logger.info(f"Found vanilla SM64 ROM at: {full_path}")
                return res

    # Step 2: Full walk (only if not found in priority)
    for d in search_dirs:
        if not d or not os.path.exists(d):
            continue
        for root, _, files in os.walk(d):
            for file in files:
                if file.lower().endswith((".z64", ".n64", ".v64")):
                    full_path = os.path.join(root, file)
                    res = check_file(full_path)
                    if res:
                        vanilla_rom = res
                        vanilla_rom_path = full_path
                        logger.info(f"Found vanilla SM64 ROM at: {full_path}")
                        return res

    return None


# Stack to keep track of level scripts for identification
gLevelScriptTracker: List[str] = []

IS_BIG_ENDIAN: bool = True
IS_64_BIT: bool = False
DEBUG: bool = True
ROMHACK: bool = False

level_num_to_str: Dict[int, str] = {
    0: "none",
    1: "unknown_1",
    2: "unknown_2",
    3: "unknown_3",
    4: "bbh",
    5: "ccm",
    6: "castle_inside",
    7: "hmc",
    8: "ssl",
    9: "bob",
    10: "sl",
    11: "wdw",
    12: "jrb",
    13: "thi",
    14: "ttc",
    15: "rr",
    16: "castle_grounds",
    17: "bitdw",
    18: "vcutm",
    19: "bitfs",
    20: "sa",
    21: "bits",
    22: "lll",
    23: "ddd",
    24: "wf",
    25: "ending",
    26: "castle_courtyard",
    27: "pss",
    28: "cotmc",
    29: "totwc",
    30: "bowser_1",
    31: "wmotr",
    32: "unknown_32",
    33: "bowser_2",
    34: "bowser_3",
    35: "unknown_35",
    36: "ttm",
    37: "unknown_37",
    38: "unknown_38",
    39: "count",
}

level_name_to_int: Dict[str, int] = {v: k for k, v in level_num_to_str.items()}
level_name_to_int_lookup: List[str] = sorted(level_name_to_int.keys(), key=len, reverse=True)

level_num_to_const_name: Dict[int, str] = {
    i: name
    for i, name in enumerate(
        [
            "LEVEL_NONE",
            "LEVEL_UNKNOWN_1",
            "LEVEL_UNKNOWN_2",
            "LEVEL_UNKNOWN_3",
            "LEVEL_BBH",
            "LEVEL_CCM",
            "LEVEL_CASTLE",
            "LEVEL_HMC",
            "LEVEL_SSL",
            "LEVEL_BOB",
            "LEVEL_SL",
            "LEVEL_WDW",
            "LEVEL_JRB",
            "LEVEL_THI",
            "LEVEL_TTC",
            "LEVEL_RR",
            "LEVEL_CASTLE_GROUNDS",
            "LEVEL_BITDW",
            "LEVEL_VCUTM",
            "LEVEL_BITFS",
            "LEVEL_SA",
            "LEVEL_BITS",
            "LEVEL_LLL",
            "LEVEL_DDD",
            "LEVEL_WF",
            "LEVEL_ENDING",
            "LEVEL_CASTLE_COURTYARD",
            "LEVEL_PSS",
            "LEVEL_COTMC",
            "LEVEL_TOTWC",
            "LEVEL_BOWSER_1",
            "LEVEL_WMOTR",
            "LEVEL_UNKNOWN_32",
            "LEVEL_BOWSER_2",
            "LEVEL_BOWSER_3",
            "LEVEL_UNKNOWN_35",
            "LEVEL_TTM",
            "LEVEL_UNKNOWN_37",
            "LEVEL_UNKNOWN_38",
        ]
    )
}

VANILLA_SHA1: str = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"


def is_romhack(rom: Any) -> bool:
    global ROMHACK
    ROMHACK = hashlib.sha1(rom.read()).hexdigest() != VANILLA_SHA1
    return ROMHACK


class ROM_Endian(Enum):
    BIG = 1
    MIXED = 2
    LITTLE = 3


# --- ROM Validation Toolset ---
TEST_REQUIRED = 0  # Fail = Mark as DECOMP
TEST_OPTIONAL = 1  # Fail = Just log
TEST_PROBE = 2  # Returns True/False only


class Validator:
    def __init__(self):
        self.is_decomp: bool = False
        self.failed_tests: List[str] = []
        self._pending_tests: List[Dict[str, Any]] = []

    def set_decomp(self, reason: str):
        """Explicitly flag the ROM as decomp and record why."""
        if not self.is_decomp:
            self.is_decomp = True
            logger.info(f"Validator: ROM marked as DECOMP. Reason: {reason}")
        self.failed_tests.append(reason)

    def check_rom_data(self, offset: int, expected: bytes) -> bool:
        """Helper to read and compare bytes from the current ROM."""
        rom_obj = get_rom()
        if not rom_obj:
            return False

        # Save position, read, and restore
        old_pos = rom_obj.tell()
        rom_obj.seek(offset)
        actual = rom_obj.read(len(expected))
        rom_obj.seek(old_pos)

        return actual == expected

    def rom_test(
        self,
        value: int,
        mode: int,
        expected_data: bytes,
        rom_offset: Optional[int] = None,
        description: str = "",
    ) -> int:
        """
        Validates ROM data. If ROM isn't loaded yet, queues the test.
        Always returns 'value'.
        """
        target_offset = rom_offset if rom_offset is not None else value

        if get_rom() is None:
            # Queue for later
            self._pending_tests.append(
                {
                    "value": value,
                    "mode": mode,
                    "expected": expected_data,
                    "offset": target_offset,
                    "description": description,
                }
            )
            return value

        # Run immediately if ROM is ready
        self._run_test(value, mode, expected_data, target_offset, description)
        return value

    def _run_test(self, value, mode, expected, offset, description):
        match = self.check_rom_data(offset, expected)
        if not match:
            if mode == TEST_REQUIRED:
                self.is_decomp = True
            self.failed_tests.append(description or f"0x{offset:X}")
            logger.debug(f"Validator: Test failed at 0x{offset:X} (expected {expected.hex()})")
        else:
            logger.debug(f"Validator: Test passed at 0x{offset:X}")

    def run_pending_tests(self):
        """Execute all tests that were queued before ROM loading."""
        if get_rom() is None:
            return

        for t in self._pending_tests:
            self._run_test(t["value"], t["mode"], t["expected"], t["offset"], t["description"])

        self._pending_tests.clear()
        if self.failed_tests:
            logger.info(
                f"Validator: Completed pending tests. {len(self.failed_tests)} failures found."
            )


# Global validator instance
validator = Validator()


def to_signed16(val: int) -> int:
    return val if val < 0x8000 else val - 0x10000


def swap_mixed_big(rom_data: Union[bytearray, List[int]]) -> None:
    for i in range(0, len(rom_data), 2):
        if i + 1 < len(rom_data):
            temp = rom_data[i]
            rom_data[i] = rom_data[i + 1]
            rom_data[i + 1] = temp


def swap_little_big(rom_data: Union[bytearray, List[int]]) -> None:
    for i in range(0, len(rom_data), 4):
        if i + 3 < len(rom_data):
            temp0 = rom_data[i + 0]
            temp1 = rom_data[i + 1]
            temp2 = rom_data[i + 2]
            temp3 = rom_data[i + 3]
            rom_data[i + 0] = temp3
            rom_data[i + 1] = temp2
            rom_data[i + 2] = temp1
            rom_data[i + 3] = temp0


def _SHIFTL(v: int, s: int, w: int) -> int:
    return (int(v) & ((1 << w) - 1)) << s


def _SHIFTR(v: int, s: int, w: int) -> int:
    return (int(v) >> s) & ((1 << w) - 1)


def _apply_64bit(value: int) -> int:
    return (value << 32) if (IS_BIG_ENDIAN and IS_64_BIT) else value


def CMD_BBBB_unpack(value: int) -> Tuple[int, int, int, int]:
    return (
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 0) & 0xFF,
    )


def CMD_BBBB_pack(a: int, b: int, c: int, d: int) -> int:
    if IS_BIG_ENDIAN:
        val = _SHIFTL(a, 24, 8) | _SHIFTL(b, 16, 8) | _SHIFTL(c, 8, 8) | _SHIFTL(d, 0, 8)
    else:
        val = _SHIFTL(a, 0, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(c, 16, 8) | _SHIFTL(d, 24, 8)

    return _apply_64bit(val)


def CMD_BBH_unpack(value: int) -> Tuple[int, int, int]:
    return (
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 0) & 0xFFFF,
    )


def CMD_BBH_pack(a: int, b: int, c: int) -> int:
    if IS_BIG_ENDIAN:
        val = _SHIFTL(a, 24, 8) | _SHIFTL(b, 16, 8) | _SHIFTL(c, 0, 16)
    else:
        val = _SHIFTL(a, 0, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(c, 16, 16)

    return _apply_64bit(val)


def CMD_HH_unpack(value: int) -> Tuple[int, int]:
    return (
        (value >> 16) & 0xFFFF,
        (value >> 0) & 0xFFFF,
    )


def CMD_HH_pack(a: int, b: int) -> int:
    if IS_BIG_ENDIAN:
        val = _SHIFTL(a, 16, 16) | _SHIFTL(b, 0, 16)
    else:
        val = _SHIFTL(a, 0, 16) | _SHIFTL(b, 16, 16)
    return _apply_64bit(val)


def CMD_HHHHHH_unpack(values: List[int]) -> Tuple[int, int, int, int, int, int]:
    v1 = values.pop(0)
    v2 = values.pop(0)
    v3 = values.pop(0)
    a1, b1 = CMD_HH_unpack(v1)
    a2, b2 = CMD_HH_unpack(v2)
    a3, b3 = CMD_HH_unpack(v3)
    return a1, b1, a2, b2, a3, b3


def CMD_HHHHHH_pack(a: int, b: int, c: int, d: int, e: int, f: int) -> Tuple[int, int, int]:
    return (
        CMD_HH_pack(a, b),
        CMD_HH_pack(c, d),
        CMD_HH_pack(e, f),
    )


def CMD_W_unpack(value: int) -> int:
    return value


def CMD_W_pack(a: int) -> int:
    return _apply_64bit(a)


def CMD_PTR_unpack(value: int) -> int:
    return value


def CMD_PTR_pack(a: int) -> int:
    return int(a)


def to_bytes_32(value: int) -> bytes:
    return value.to_bytes(4, "big")


def to_bytes_64(value: int) -> bytes:
    return value.to_bytes(8, "big")


def pack_to_bytes(pack_result: int) -> bytes:
    if IS_BIG_ENDIAN and IS_64_BIT:
        return pack_result.to_bytes(8, "big")
    return pack_result.to_bytes(4, "big")


def format_int(value: int) -> str:
    return "{:08x} ".format(value)


def read_int(rom: Any) -> Optional[int]:
    data = rom.read(4)
    if not data:
        return None
    return struct.unpack(">I", data)[0]


def swap_bytes(value: int) -> int:
    v1 = struct.pack(">I", value)
    return struct.unpack("<I", v1)[0]


def segment_from_addr(addr: int) -> int:
    return addr >> 24


def offset_from_segment_addr(addr: int) -> int:
    if addr == -1:
        return -1
    return addr & 0x00FFFFFF


def find_all_needles_in_haystack(haystack: bytes, needle: bytes) -> List[int]:
    positions = []
    start = 0

    while True:
        index = haystack.find(needle, start)
        if index == -1:
            break
        positions.append(index)
        start = index + 1
    return positions


rom: Optional[Any] = None


def set_rom(r: Any) -> None:
    global rom
    rom = r


def get_rom() -> Optional[Any]:
    return rom


def get_cur_level() -> Optional[str]:
    for i in reversed(range(len(gLevelScriptTracker))):
        name = gLevelScriptTracker[i]
        for level in level_name_to_int_lookup:
            if level in name:
                return level
    return None


def debug_print(msg: str) -> None:
    logger.debug(msg)


def exception(msg: str) -> None:
    if is_debugger():
        raise ExtractionError(msg)

    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is not None:
        logger.error(msg, exc_info=sys.exc_info())
    else:
        # Note: traceback format_stack gets stack inside exception/debug_fail itself,
        # so logging handles this cleanly with logger.error
        logger.error(msg, stack_info=True)

    raise ExtractionError(msg)


def debug_fail(msg: str) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        exception(msg)
    else:
        logger.warning(msg)


def debug_error(msg: str) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        exception(msg)
    else:
        logger.error(msg)
        raise ExtractionError(msg)
