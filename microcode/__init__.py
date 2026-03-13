from .base import Microcode

__all__ = ["Microcode"]
from .gbi0 import GBI0, F3DEX_GBI0
from .gbi1 import GBI1
from .gbi2 import GBI2
from .gbi0_dkr import GBI0DKR

# Map from RSP SW Version string (or hash/identifier) to Microcode class
# This logic mirrors n64js/src/hle/microcodes.js inferUcodeFromString


def version_str_to_microcode_class(version_str):
    if version_str is None:
        return GBI0()

    # Handle explicit names from extract.py
    if version_str == "F3DEX2":
        return GBI2()
    if version_str == "F3DEX_GBI0_VTX":
        return F3DEX_GBI0()
    if version_str == "F3D":
        return GBI0()
    if version_str == "F3DEX":
        return GBI1()
    if version_str == "Diddy Kong Racing":
        return GBI0DKR()

    # Heuristic detection based on n64js logic
    if "Diddy Kong Racing" in version_str:
        return GBI0DKR()

    if "F3" in version_str or "L3" in version_str:
        if "fifo" in version_str or "xbux" in version_str:
            return GBI2()
        return GBI1()

    return GBI0()


def create_microcode(version_str=None):
    return version_str_to_microcode_class(version_str)
