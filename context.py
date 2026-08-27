import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set, Optional, TypeVar
from tweaks import LevelValues, BehaviorValues


@dataclass
class LevelAreaContext:
    curr_level: int = -1
    curr_area: int = -1


@dataclass
class ParseFrame:  # For provenance error stack
    kind: str
    addr: int
    source: Optional[str] = None

    def describe(self) -> str:
        desc = f"{self.kind} @ 0x{self.addr:08X}"
        if self.source:
            desc += f"  <- {self.source}"
        return desc


F = TypeVar("F", bound=Callable[..., Any])


# Decorator factory for BaseProcessor.parse implementations;
# specifically in order to improve debugging by maintaining a paper trail of the current internal stack.
def provenance(kind: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)  # make sure to keep the same function name from the original
        def wrapper(self, segmented_addr: int, *args: Any, **kwargs: Any):
            outermost = not ctx.parse_stack
            if outermost:
                ctx.last_failure_chain = (
                    None  # New top level parse (new level script), so new chain
                )
            source = None

            # Try to find a descriptor of this frame
            parent = ctx.parse_stack[-1] if ctx.parse_stack else None
            if parent is not None and parent.kind == "Level Script":
                cmd_name = None
                if ctx.script_cmd_history and ctx.script_cmd_history[-1]:
                    cmd_name = ctx.script_cmd_history[-1][-1]
                phys = ctx.curr_phys
                if cmd_name or phys:
                    source = f"{cmd_name or 'command'} @ rom 0x{phys:08X}"

            # Build the frame info, append it to the stack
            frame = ParseFrame(kind=kind, addr=segmented_addr, source=source)
            ctx.parse_stack.append(frame)

            # Call the function and handle errors
            try:
                return fn(self, segmented_addr, *args, **kwargs)
            except BaseException:
                # An exception occured, make sure our chain has been printed
                if ctx.last_failure_chain is None:
                    ctx.last_failure_chain = ctx.format_parse_chain()
                raise  # Re-raise the error
            finally:
                ctx.parse_stack.pop()

        return wrapper  # type: ignore[return-value]

    return decorator


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

    parse_stack: List[ParseFrame] = field(default_factory=list)
    last_failure_chain: Optional[str] = None

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

    def format_parse_chain(self) -> str:
        if not self.parse_stack:
            return ""
        lines = ["Parse provenance chain (outermost first):"]
        lines.extend(f"  {frame.describe()}" for frame in self.parse_stack)
        return "\n".join(lines)

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
