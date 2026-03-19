"""
Deferred output system for level script parsing.

Instead of immediately serializing each command to a string, command handlers
can register structured records into a DeferredScriptOutput. After all commands
in a script are parsed, a post-processing pass runs that can refine the
interpretation of data using cross-references between records.

Primary use case: model ID resolution.
  - LOAD_MODEL_FROM_GEO records: "model ID X uses geo layout Y"
  - LOAD_MODEL_FROM_DL records:  "model ID X uses display list Y"
  - OBJECT_WITH_ACTS can then look up which geo/dl was loaded for a given
    model ID, enabling perfect disambiguation of actor group bins (0x54-0x69)
    where the same numeric ID maps to different constants depending on the
    loaded actor group.

Architecture:
  - Each command handler can optionally attach a ScriptRecord to the deferred
    output via `ctx.deferred.add_record(record)`.
  - Records hold both the raw parsed data AND the formatted output string.
  - Post-processors iterate through all records and can mutate the formatted
    output based on cross-referenced data.
  - The final serialized output is produced by joining all record outputs.

This is designed to be incrementally adopted. Commands that don't benefit from
deferred output simply return their formatted string as before — those strings
are wrapped in a basic record automatically by the parsing loop.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum, auto


class RecordType(Enum):
    """Types of records that can be deferred."""

    GENERIC = auto()  # Any command, no special handling
    LOAD_MODEL_FROM_GEO = auto()
    LOAD_MODEL_FROM_DL = auto()
    OBJECT_WITH_ACTS = auto()
    OBJECT = auto()
    MARIO = auto()


@dataclass
class ScriptRecord:
    """
    A single parsed command's structured output, held for deferred processing.

    Fields:
        record_type: What kind of command this is (for filtering during post-processing)
        output: The formatted output string (may be mutated by post-processors)
        data: Arbitrary structured data from the command handler. The schema
              depends on record_type. This is what post-processors use to
              refine the output.

    Data schemas by record_type:
        LOAD_MODEL_FROM_GEO:
            {"model": int, "geo_name": str, "geo_addr": int}
        LOAD_MODEL_FROM_DL:
            {"model": int, "layer": int, "dl_name": str, "dl_addr": int}
        OBJECT_WITH_ACTS / OBJECT:
            {"model": int, "beh_name": str, "pos": (x,y,z), "angle": (x,y,z),
             "behParam": int, "acts": int, "level": str|None}
        MARIO:
            {"model": int, "beh_name": str, "behParam": int}
    """

    record_type: RecordType = RecordType.GENERIC
    output: str = ""
    command_ir: Optional[Any] = None
    data: Dict[str, Any] = field(default_factory=dict)


# Type alias for post-processor functions
PostProcessor = Callable[["DeferredScriptOutput"], None]


class DeferredScriptOutput:
    """
    Accumulates ScriptRecords for a single level script, then runs
    post-processing before serialization.

    Usage:
        deferred = DeferredScriptOutput()

        # During parsing:
        deferred.add_record(ScriptRecord(...))

        # After parsing completes:
        deferred.post_process()
        final_output = deferred.serialize()
    """

    def __init__(self) -> None:
        self.records: List[ScriptRecord] = []

        # Model table: populated by LOAD_MODEL_FROM_GEO and LOAD_MODEL_FROM_DL
        # Maps model_id (int) -> {"geo_name": str, "geo_addr": int} or similar
        self.model_table: Dict[int, Dict[str, Any]] = {}

    def add_record(self, record: ScriptRecord) -> None:
        """Add a record to the deferred output."""
        self.records.append(record)

        # Eagerly index model loads so they're available for same-script lookups
        if record.record_type == RecordType.LOAD_MODEL_FROM_GEO:
            model_id = record.data.get("model")
            if model_id is not None:
                self.model_table[model_id] = {
                    "geo_name": record.data.get("geo_name", ""),
                    "geo_addr": record.data.get("geo_addr", 0),
                    "source": "geo",
                }
        elif record.record_type == RecordType.LOAD_MODEL_FROM_DL:
            model_id = record.data.get("model")
            if model_id is not None:
                # Don't overwrite a geo entry with a DL entry
                if model_id not in self.model_table:
                    self.model_table[model_id] = {
                        "dl_name": record.data.get("dl_name", ""),
                        "dl_addr": record.data.get("dl_addr", 0),
                        "layer": record.data.get("layer", 0),
                        "source": "dl",
                    }

    def get_model_info(self, model_id: int) -> Optional[Dict[str, Any]]:
        """
        Look up what geo/dl was loaded for a given model ID.
        Returns None if the model wasn't loaded in this script.
        """
        return self.model_table.get(model_id)

    def post_process(self) -> None:
        """
        Run all post-processing passes over the accumulated records.

        Currently runs:
          1. Model ID refinement pass (uses model_table to improve OBJECT outputs)

        Future passes could include:
          - Behavior name cross-referencing
          - Geo layout type inference
          - Vanilla pattern matching improvements
        """
        self._refine_model_ids()

    def _refine_model_ids(self) -> None:
        """
        Post-processing pass: refine model ID resolution for OBJECT records.

        For OBJECT/OBJECT_WITH_ACTS records, checks if the model_table contains
        geo/dl information that can help disambiguate the model ID constant.
        This is particularly useful for actor group bins where the same numeric
        ID (e.g. 0x54) maps to different constants depending on which actor
        group was loaded.
        """
        from model_ids import MODEL_ID_BY_VALUE

        for record in self.records:
            if record.record_type not in (RecordType.OBJECT_WITH_ACTS, RecordType.OBJECT):
                continue

            model_id = record.data.get("model")
            if model_id is None:
                continue

            candidates = MODEL_ID_BY_VALUE.get(model_id, [])
            if len(candidates) <= 1:
                # Already unique or unknown — no refinement needed
                continue

            # Check if we have geo/dl info for this model from the model table
            model_info = self.model_table.get(model_id)
            if model_info is None:
                continue

            # Try to match the geo or DL name against the candidates
            geo_name = model_info.get("geo_name", "")
            dl_name = model_info.get("dl_name", "")
            target_name = geo_name or dl_name

            if target_name:
                refined = self._match_geo_to_model_constant(target_name, candidates)
                if refined:
                    if record.command_ir is not None:
                        # In CommandIR, params[0] is the model_param string
                        # Use the refined name directly to ensure validity
                        record.command_ir.params[0] = refined
                        record.data["refined_model_name"] = refined
                    else:
                        # Update the output string
                        old_output = record.output
                        import re

                        # Match either a commented model ID or a raw hex model ID
                        pattern = r"(?:/\* model: .+? \*/ )?0x([0-9a-f]{2})"
                        replacement = f"{refined}"
                        new_output = re.sub(pattern, replacement, old_output, count=1)
                        if new_output != old_output:
                            record.output = new_output
                            record.data["refined_model_name"] = refined

        # Final pass: remove any leftover model comments from all LOAD_MODEL records
        for record in self.records:
            if record.record_type in (
                RecordType.LOAD_MODEL_FROM_GEO,
                RecordType.LOAD_MODEL_FROM_DL,
            ):
                if record.command_ir is not None and len(record.command_ir.params) > 0:
                    p0 = str(record.command_ir.params[0])
                    if "/*" in p0:
                        import re

                        match = re.search(r"0x([0-9a-f]{2})", p0)
                        if match:
                            record.command_ir.params[0] = f"0x{match.group(1)}"

    def _match_geo_to_model_constant(self, geo_name: str, candidates: List[str]) -> Optional[str]:
        """
        Try to match a geo layout name to one of the candidate model constants.

        model_ids.h has comments like:
            #define MODEL_GOOMBA  0xC0  // goomba_geo

        The geo name from LOAD_MODEL_FROM_GEO should match the comment.
        We use heuristic matching: if a candidate's name (after removing MODEL_)
        appears as a substring of the geo_name (or vice versa), that's a match.

        Future: could parse the comments from model_ids.h for exact matching.
        """
        geo_lower = geo_name.lower().replace("_geo", "").replace("geo_", "")

        for candidate in candidates:
            # Strip MODEL_ prefix and convert to lowercase for comparison
            short = candidate[6:].lower() if candidate.startswith("MODEL_") else candidate.lower()

            # Direct substring match
            if short in geo_lower or geo_lower in short:
                return candidate

            # Try matching key words (e.g. "goomba" in "goomba_geo")
            words = short.split("_")
            if len(words) >= 2 and all(w in geo_lower for w in words if len(w) > 2):
                return candidate

        return None

    def serialize(self) -> str:
        """
        Serialize all records into the final output string.
        Should be called after post_process().
        """
        return "\n".join(r.output for r in self.records if r.output)

    def clear(self) -> None:
        """Reset for reuse."""
        self.records.clear()
        self.model_table.clear()
