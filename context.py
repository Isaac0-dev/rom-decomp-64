from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Optional


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
    current_context_prefix: Optional[str] = None

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

    reached_end: bool = False

    _pending_record: Any = None

    # Deferred output for the current level script being parsed.
    # Managed by parse_level_script: created at start, post-processed + serialized at end.
    deferred: Any = None

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
