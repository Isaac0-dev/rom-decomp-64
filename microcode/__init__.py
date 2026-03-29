from .base import Microcode

__all__ = ["Microcode"]
from .gbi0 import GBI0, F3DEX_GBI0
from .gbi1 import GBI1
from .gbi2 import GBI2
from .gbi0_dkr import GBI0DKR

# Map from RSP SW Version string (or hash/identifier) to Microcode class
# This logic mirrors n64js/src/hle/microcodes.js inferUcodeFromString


_microcode_cache = {}


def version_str_to_microcode_class(version_str):
    if version_str in _microcode_cache:
        return _microcode_cache[version_str]

    if version_str is None:
        res = GBI0()
    elif version_str == "F3DEX2":
        res = GBI2()
    elif version_str == "F3DEX_GBI0_VTX":
        res = F3DEX_GBI0()
    elif version_str == "F3D":
        res = GBI0()
    elif version_str == "F3DEX":
        res = GBI1()
    elif version_str == "Diddy Kong Racing":
        res = GBI0DKR()
    elif "Diddy Kong Racing" in version_str:
        res = GBI0DKR()
    elif "F3" in version_str or "L3" in version_str:
        if "fifo" in version_str or "xbux" in version_str:
            res = GBI2()
        else:
            res = GBI1()
    else:
        res = GBI0()

    _microcode_cache[version_str] = res
    return res


def create_microcode(version_str=None):
    return version_str_to_microcode_class(version_str)
