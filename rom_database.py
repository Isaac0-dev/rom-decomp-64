from __future__ import annotations
from context import LevelAreaContext

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Basic Types & IR Structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolRecord:
    """
    A resolved name for a specific memory address (VRAM or Segmented).
    Used by the global symbol table in RomDatabase.
    """

    address: int
    name: str
    type: str = "function"  # "function", "data", "label", "behavior", "geo", "collision"
    confidence: float = 1.0
    source: str = "parsing"  # "parsing", "matcher", "vanilla", "user"


@dataclass
class CommandIR:
    """
    Intermediate representation of a single script command (Level, Geo, Beh, etc).
    Stored in records to allow post-processing of parameters before serialization.
    """

    opcode: int
    params: List[Any] = field(default_factory=list)
    address: int = 0  # ROM address of this command
    raw_data: bytes = b""
    indent: int = 0
    comment: str = ""
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# ROM-level metadata
# ---------------------------------------------------------------------------


@dataclass
class RomMeta:
    """Top-level facts about the ROM file itself."""

    filename: str = ""
    endian: Any = None  # ROM_Endian enum value from utils.py
    compression: str = ""  # e.g. "MIO0", "YAZ0"
    microcode: str = ""  # e.g. "F3D", "F3DEX2"
    is_hack: bool = False
    is_decomp: bool = False
    hack_type: str = ""
    internal_name: str = ""


# ---------------------------------------------------------------------------
# Model / Geometry records
# ---------------------------------------------------------------------------


@dataclass
class ModelRecord:
    """
    One entry in a level's model table (LOAD_MODEL_FROM_GEO / LOAD_MODEL_FROM_DL).
    """

    model_id: int = 0

    # GEO-sourced fields
    geo_addr: Optional[int] = None
    geo_name: str = ""

    # DL-sourced fields
    dl_addr: Optional[int] = None
    dl_name: str = ""
    layer: int = 0

    source: str = ""  # "geo" | "dl"


# ---------------------------------------------------------------------------
# Object records
# ---------------------------------------------------------------------------


@dataclass
class ObjectRecord:
    """
    A single placed object from an OBJECT or OBJECT_WITH_ACTS command.
    """

    model_id: int = 0
    beh_addr: int = 0
    beh_name: str = ""
    pos: Tuple[int, int, int] = (0, 0, 0)
    rot: Tuple[int, int, int] = (0, 0, 0)
    beh_param: int = 0
    acts: int = 0xFF
    refined_model_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Area records
# ---------------------------------------------------------------------------


@dataclass
class AreaRecord:
    """
    One area within a level.
    """

    area_id: int = 0
    objects: List[ObjectRecord] = field(default_factory=list)
    warps: List[Dict[str, Any]] = field(default_factory=list)
    collision_addr: int = 0
    skybox_seg: Optional[int] = None


# ---------------------------------------------------------------------------
# Level records
# ---------------------------------------------------------------------------


@dataclass
class LevelRecord:
    """
    All data discovered for one level.
    """

    level_name: str = ""
    name: str = ""
    script_addr: int = 0
    areas: Dict[int, AreaRecord] = field(default_factory=dict)
    models: Dict[int, ModelRecord] = field(default_factory=dict)
    commands: List[CommandIR] = field(default_factory=list)
    history: List[str] = field(default_factory=list)
    script_text: str = ""

    def __str__(self):
        return self.name or self.level_name


# ---------------------------------------------------------------------------
# Texture records
# ---------------------------------------------------------------------------


@dataclass
class TextureRecord:
    """
    One extracted texture.
    """

    addr: int = 0
    phys: int = 0
    seg_num: int = 0
    offset: int = 0
    fmt: int = 0
    siz: int = 0
    width: int = 0
    height: int = 0
    name: str = ""
    context_prefix: Optional[str] = None
    output_path: str = ""
    # Raw pixel bytes captured at discovery time; serializer converts to PNG
    segment_data: bytes = b""
    # Raw palette bytes (CI textures only)
    palette_data: Optional[bytes] = None

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Behavior records
# ---------------------------------------------------------------------------


@dataclass
class BehaviorRecord:
    """
    One resolved behavior script.
    """

    seg_addr: int = 0
    rom_offset: int = 0
    beh_name: str = ""
    hash: str = ""
    fuzzy_hash: str = ""
    anon_hash: str = ""
    commands: List[CommandIR] = field(default_factory=list)
    script_text: str = ""  # Deprecated: use commands for serialization
    # Analysis pass fields
    confidence: float = 0.0
    is_vanilla: Optional[bool] = None  # None = not yet analysed

    def __str__(self):
        return self.beh_name


# ---------------------------------------------------------------------------
# Geo Layout records
# ---------------------------------------------------------------------------


@dataclass
class GeoRecord:
    """
    One geo layout.
    """

    seg_addr: int = 0
    name: str = ""
    hash: str = ""
    fuzzy_hash: str = ""
    commands: List[CommandIR] = field(default_factory=list)
    script_text: str = ""  # Deprecated: use commands for serialization
    # Analysis pass fields
    confidence: float = 0.0
    is_vanilla: Optional[bool] = None

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Collision records
# ---------------------------------------------------------------------------


@dataclass
class CollisionRecord:
    """
    One extracted collision (TERRAIN) layout.
    """

    seg_addr: int = 0
    name: str = ""
    commands: List[CommandIR] = field(default_factory=list)
    script_text: str = ""  # Deprecated: use commands for serialization

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Rooms records
# ---------------------------------------------------------------------------


@dataclass
class RoomsRecord:
    """
    One extracted rooms (ROOMS) layout.
    """

    seg_addr: int = 0
    name: str = ""
    count: int = 0
    values: List[int] = field(default_factory=list)
    script_text: str = ""  # Deprecated: use commands for serialization

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Trajectory records
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryRecord:
    """
    One extracted trajectory (path).
    """

    seg_addr: int = 0
    name: str = ""
    points: List[Tuple[int, int, int, int]] = field(default_factory=list)
    script_text: str = ""

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Display List records
# ---------------------------------------------------------------------------


@dataclass
class DisplayListRecord:
    """
    One extracted display list (Gfx commands).
    """

    seg_addr: int = 0
    name: str = ""
    hash: str = ""
    fuzzy_hash: str = ""
    commands: List[CommandIR] = field(default_factory=list)
    microcode: str = "F3D"
    script_text: str = ""  # Deprecated: use commands for serialization
    # Analysis pass fields
    confidence: float = 0.0
    is_vanilla: Optional[bool] = None

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Movtex records
# ---------------------------------------------------------------------------


@dataclass
class MovtexRecord:
    """
    One extracted moving texture (water/lava/etc). Keyed by name.
    """

    seg_addr: int = 0
    name: str = ""  # e.g. "bob_movtex_001234_collection"
    script_text: str = ""


# ---------------------------------------------------------------------------
# Audio records
# ---------------------------------------------------------------------------


@dataclass
class AudioSequenceRecord:
    """One MIDI sequence extracted from the ALSeqFile."""

    seq_id: int = 0
    bank_id: int = 0
    data: bytes = b""


@dataclass
class AudioRecord:
    """
    Aggregated audio discovery results.
    """

    alseq_candidates: List[int] = field(default_factory=list)
    # Populated by AudioProcessor.parse(); flushed to disk in pass_serialize
    sequences: List[AudioSequenceRecord] = field(default_factory=list)
    lua_lines: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Macro object records
# ---------------------------------------------------------------------------


@dataclass
class MacroRecord:
    """
    One macro-object array discovered during level script parsing.
    Stores raw structured data; C output is generated by MacroObjectProcessor.serialize().
    """

    addr: int = 0
    name: str = ""  # C symbol name, e.g. "bob_area_1_macro_objs"
    context_prefix: str = ""
    # Each entry: (yaw_degrees, preset, posX, posY, posZ, behParam)
    entries: List[Tuple[int, int, int, int, int, int]] = field(default_factory=list)

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Skybox records
# ---------------------------------------------------------------------------


@dataclass
class SkyboxRecord:
    """
    Raw skybox segment data captured at discovery time.
    SkyboxProcessor.serialize() re-assembles tiles and writes PNG + C.
    """

    level_prefix: str = ""
    seg_data: bytes = b""


# ---------------------------------------------------------------------------
# Global segment records
# ---------------------------------------------------------------------------


@dataclass
class GlobalSegRecord:
    """
    One globally-loaded segment.
    """

    seg_num: int = 0
    rom_offset: int = 0
    rom_end: int = 0


@dataclass
class VertexRecord:
    """
    One extracted vertex array (Vtx).
    """

    seg_addr: int = 0
    name: str = ""
    count: int = 0
    pos_data: List[Tuple[int, int, int]] = field(default_factory=list)
    script_text: str = ""

    location: LevelAreaContext = field(default_factory=LevelAreaContext)


@dataclass
class LightRecord:
    """
    One extracted light (Lights1, Light_t, etc).
    """

    seg_addr: int = 0
    name: str = ""
    type_name: str = ""
    script_text: str = ""

    location: LevelAreaContext = field(default_factory=LevelAreaContext)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Top-level database
# ---------------------------------------------------------------------------


@dataclass
class RomDatabase:
    """
    The central Intermediate Representation produced by ExtractionPipeline.
    """

    meta: RomMeta = field(default_factory=RomMeta)
    symbols: Dict[int, SymbolRecord] = field(default_factory=dict)
    levels: Dict[str, LevelRecord] = field(default_factory=dict)

    # Keyed by name (unique) or address-phys tuple for level-specific overlaps
    textures: Dict[str, TextureRecord] = field(default_factory=dict)
    behaviors: Dict[Tuple[int, int], BehaviorRecord] = field(default_factory=dict)
    geos: Dict[Tuple[int, int], GeoRecord] = field(default_factory=dict)
    level_scripts: Dict[int, LevelRecord] = field(default_factory=dict)

    trajectories: Dict[Tuple[int, int], TrajectoryRecord] = field(default_factory=dict)
    display_lists: Dict[Tuple[int, int], DisplayListRecord] = field(default_factory=dict)
    collisions: Dict[Tuple[int, int], CollisionRecord] = field(default_factory=dict)
    rooms: Dict[Tuple[int, int], RoomsRecord] = field(default_factory=dict)

    vertices: Dict[Tuple[int, int, int], VertexRecord] = field(default_factory=dict)
    lights: Dict[Tuple[int, int, int], LightRecord] = field(default_factory=dict)

    movtexs: Dict[str, MovtexRecord] = field(default_factory=dict)
    audio: AudioRecord = field(default_factory=AudioRecord)
    global_segs: Dict[int, GlobalSegRecord] = field(default_factory=dict)
    macros: Dict[Tuple[int, int], MacroRecord] = field(default_factory=dict)
    skyboxes: Dict[str, SkyboxRecord] = field(default_factory=dict)

    def get_or_create_level(self, level_name: str, script_addr: int = 0) -> LevelRecord:
        if level_name not in self.levels:
            self.levels[level_name] = LevelRecord(level_name=level_name, script_addr=script_addr)
        return self.levels[level_name]

    def get_or_create_area(self, level_name: str, area_id: int) -> AreaRecord:
        level = self.get_or_create_level(level_name)
        if area_id not in level.areas:
            level.areas[area_id] = AreaRecord(area_id=area_id)
        return level.areas[area_id]

    def set_symbol(
        self, address: int, name: str, symbol_type: str = "function", confidence: float = 1.0
    ) -> None:
        """Register or update a symbol in the global table."""
        if address in self.symbols:
            # if name != self.symbols[address].name:
            #     raise ValueError(
            #         f"Symbol at address 0x{address:08X} {name} ({symbol_type}) already exists with name {self.symbols[address].name}"
            #     )
            # Only update if the new symbol has higher confidence
            if confidence >= self.symbols[address].confidence:
                self.symbols[address].name = name
                self.symbols[address].confidence = confidence
                self.symbols[address].type = symbol_type
        else:
            self.symbols[address] = SymbolRecord(
                address=address, name=name, type=symbol_type, confidence=confidence
            )

    def resolve_symbol(self, address: int, location: LevelAreaContext, type: str) -> str:
        """Look up a symbol name by address. Returns default or hex string if not found."""
        if address in self.symbols:
            return self.symbols[address].name

        from segment import segmented_to_virtual, segment_from_addr

        # We'll build a router here that constructs the names for symbols
        name = ""
        if location is not None and location.curr_level != -1:
            from utils import level_num_to_str

            name += f"{level_num_to_str[location.curr_level]}_"
            if location.curr_area != -1:
                name += f"area_{location.curr_area}_"

        phys = segmented_to_virtual(address)
        seg_num = segment_from_addr(address)

        name += f"{type}_{address:08X}_{phys:08X}_seg{seg_num}"

        return name

        # raise ValueError(f"Unknown symbol at address 0x{address:08X} (type: {type})")
