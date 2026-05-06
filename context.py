from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Optional
from utils import level_const_name_to_int, level_num_to_const_name


class TweakValue(int):
    def __new__(cls, value: int, default: int):
        obj = super().__new__(cls, value)
        obj._default = default
        return obj

    def is_modified(self) -> bool:
        return self != self._default


class TweakableValues:
    # Subclasses define TWEAKS and LUA_TABLE_NAME
    TWEAKS: Dict[str, tuple] = {}
    LUA_TABLE_NAME: str = ""

    def __init__(self):
        for py_name, tweak_info in self.TWEAKS.items():
            default = tweak_info[0]
            self.__dict__[py_name] = TweakValue(default, default)

    def __setattr__(self, name, value):
        if name in self.TWEAKS:
            default = self.TWEAKS[name][0]
            self.__dict__[name] = TweakValue(value, default)
        else:
            super().__setattr__(name, value)

    def is_modified(self, field_name: str) -> bool:
        val = getattr(self, field_name, None)
        if val is not None and hasattr(val, "is_modified"):
            return val.is_modified()
        return False

    def get_tweaks_lua(self) -> List[str]:
        lines = []
        for py_name, tweak_info in self.TWEAKS.items():
            lua_name = tweak_info[1]
            converter = tweak_info[2] if len(tweak_info) > 2 else None

            current_val = getattr(self, py_name)
            if current_val.is_modified():
                if converter:
                    out_val = converter(int(current_val))
                else:
                    out_val = current_val
                lines.append(f"{self.LUA_TABLE_NAME}.{lua_name} = {out_val}\n")
        return lines


class LevelValues(TweakableValues):
    # This makes it easy to add level-based tweaks that automatically
    # appear in tweaks.lua if their values differ from the default.
    LUA_TABLE_NAME = "gLevelValues"
    TWEAKS = {
        "lowest_vtx_height": (-11000, "floorLowerLimit"),
        "highest_vtx_height": (20000, "cellHeightLimit"),
        "entry_level": (
            level_const_name_to_int["LEVEL_CASTLE_GROUNDS"],
            "entryLevel",
            lambda v: level_num_to_const_name.get(v, f"LEVEL_UNKNOWN_{v}"),
        ),
    }


class BehaviorValues(TweakableValues):
    LUA_TABLE_NAME = "gBehaviorValues"
    TWEAKS = {
        "toad_star_1_requirement": (12, "ToadStar1Requirement"),
        "toad_star_2_requirement": (25, "ToadStar2Requirement"),
        "toad_star_3_requirement": (35, "ToadStar3Requirement"),
        "mips_star_1_requirement": (15, "MipsStar1Requirement"),
        "mips_star_2_requirement": (50, "MipsStar2Requirement"),
    }


@dataclass
class LevelAreaContext:
    curr_level: int = -1
    curr_area: int = -1


@dataclass
class ExtractionContext:
    rom: Any = None
    data: Any = None
    txt: Any = None
    db: Any = None

    level_values: LevelValues = field(default_factory=LevelValues)
    behavior_values: BehaviorValues = field(default_factory=BehaviorValues)

    first_command_in_script: bool = True
    first_cmd: Optional[int] = None

    level_area: LevelAreaContext = field(default_factory=LevelAreaContext)

    indent: int = 0
    last_collision_surface_count: int = 0

    level_script_tracker: List[str] = field(default_factory=list)
    script_cmd_history: List[List[str]] = field(default_factory=list)

    callers_map: Dict[int, Set[str]] = field(default_factory=dict)
    global_candidates: Set[int] = field(default_factory=set)
    candidate_placeholders: Dict[int, str] = field(default_factory=dict)
    pending_locs: Set[int] = field(default_factory=set)
    pending_areas: List[tuple] = field(default_factory=list)

    found_mops: Set[str] = field(default_factory=set)

    reached_end: bool = False

    _pending_record: Any = None

    curr_phys: int = 0

    # Deferred output for the current level script being parsed.
    # Managed by parse_level_script: created at start, post-processed + serialized at end.
    deferred: Any = None

    cmd_bytes: bytes = b""

    @property
    def current_context_prefix(self) -> Optional[str]:
        context_parts = [
            p
            for p in self.level_script_tracker
            if p != "script_exec_level_table" and "script_0x" not in p
        ]
        return "_".join(context_parts) if context_parts else None

    @property
    def curr_level(self) -> int:
        return self.level_area.curr_level

    @curr_level.setter
    def curr_level(self, value: int):
        self.level_area.curr_level = value

    @property
    def curr_area(self) -> int:
        return self.level_area.curr_area

    @curr_area.setter
    def curr_area(self, value: int):
        self.level_area.curr_area = value

    def get_cur_level(self) -> Optional[str]:
        from utils import level_num_to_str

        return level_num_to_str.get(self.curr_level)

    def ensure_deferred(self) -> Any:
        """Get or create the deferred output for the current script."""
        if self.deferred is None:
            from deferred_output import DeferredScriptOutput

            self.deferred = DeferredScriptOutput()
        return self.deferred


# Global context for the current extraction run.
ctx = ExtractionContext()
