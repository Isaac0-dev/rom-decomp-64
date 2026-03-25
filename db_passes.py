"""
Database-driven analysis passes.

These passes run AFTER parsing and BEFORE serialization, operating on the
populated RomDatabase to cross-reference records and improve naming,
confidence scores, and vanilla detection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set, Tuple

from rom_database import (
    RomDatabase,
    BehaviorRecord,
    GeoRecord,
    LevelRecord,
    ObjectRecord,
)
from behavior_hashes import KNOWN_BEHAVIOR_HASHES
from model_ids import MODEL_ID_BY_VALUE, _MODEL_ID_BY_LEVEL
from data.expected_pairings import BEHAVIOR_TO_MODELS, MODEL_TO_BEHAVIORS
from utils import debug_print

# --- Identification Constants (Migrated from behavior.py) ---

BEHAVIOR_ADDR_OVERRIDES = {
    0x401700: "RM_Scroll_Texture",
    0x400000: "RM_Scroll_Texture",
    0x402300: "editor_Scroll_Texture",
    0x13003420: "editor_Scroll_Texture2",
}

CUSTOM_BEHAVIOR_HASHES = {
    "383604deda1acda4": "bhvBobombBuddyOpensCannon",
    "31eb59c129ad6852": "bhvHiddenStar",
    "4051cdddcc5b89e0": "bhvExitPodiumWarp",
    "c6ee412250536b1e": "bhvToadMessage",
    "9964b9b7c56cd32e": "bhvBobombBuddy",
    "bd4934039dac8392": "bhvMessagePanel",
    "ed126593eae1c2f3": "bhvWFSolidTowerPlatform",
}

BEHAVIOR_COLLISION_HINTS = {
    "536e016d5d45dbe8": {
        0x0700FC0C: "bhvWFBreakableWallRight",
    },
}

# Patch some behaviour names that are different in coop (refresh versions)
BEHAVIOR_NAME_OVERRIDES = {
    "bhvTHIHugeIslandTop": "bhvThiHugeIslandTop",
    "bhvTHITinyIslandTop": "bhvThiTinyIslandTop",
    "bhvWFBreakableWallRight": "bhvWfBreakableWallRight",
    "bhvWFBreakableWallLeft": "bhvWfBreakableWallLeft",
    "bhvWFRotatingWoodenPlatform": "bhvWfRotatingWoodenPlatform",
    "bhvSpawnedBlueCoin": "bhvMrIBlueCoin",
    "bhvThwomp": "bhvThwomp",
    "bhvTumblingBridge": "bhvWfTumblingBridge",
    "bhvBBHTumblingBridge": "bhvBbhTumblingBridge",
    "bhvLLLTumblingBridge": "bhvLllTumblingBridge",
    "bhvRRElevatorPlatform": "bhvRrElevatorPlatform",
    "bhvHMCElevatorPlatform": "bhvHmcElevatorPlatform",
    "bhvBitFSSinkingPlatforms": "bhvBitfsSinkingPlatforms",
    "bhvBitFSSinkingCagePlatform": "bhvBitfsSinkingCagePlatform",
    "bhvDDDMovingPole": "bhvDddMovingPole",
    "bhvBitFSTiltingInvertedPyramid": "bhvBitfsTiltingInvertedPyramid",
    "bhvRRRotatingBridgePlatform": "bhvRrRotatingBridgePlatform",
    "bhvWFSlidingTowerPlatform": "bhvWfSlidingTowerPlatform",
    "bhvWFElevatorTowerPlatform": "bhvWfElevatorTowerPlatform",
    "bhvWFSolidTowerPlatform": "bhvWfSolidTowerPlatform",
    "bhvCCMTouchedStarSpawn": "bhvCcmTouchedStarSpawn",
    "bhvDDDWarp": "bhvDddWarp",
    "bhvLLLRotatingHexagonalPlatform": "bhvLllRotatingHexagonalPlatform",
    "bhvLLLSinkingRockBlock": "bhvLllSinkingRockBlock",
    "bhvLLLMovingOctagonalMeshPlatform": "bhvLllMovingOctagonalMeshPlatform",
    "bhvLLLRotatingBlockWithFireBars": "bhvLllRotatingBlockWithFireBars",
    "bhvLLLRotatingHexFlame": "bhvLllRotatingHexFlame",
    "bhvLLLWoodPiece": "bhvLllWoodPiece",
    "bhvLLLFloatingWoodBridge": "bhvLllFloatingWoodBridge",
    "bhvLLLRotatingHexagonalRing": "bhvLllRotatingHexagonalRing",
    "bhvLLLSinkingRectangularPlatform": "bhvLllSinkingRectangularPlatform",
    "bhvLLLSinkingSquarePlatforms": "bhvLllSinkingSquarePlatforms",
    "bhvLLLTiltingInvertedPyramid": "bhvLllTiltingInvertedPyramid",
    "bhvLLLHexagonalMesh": "bhvLllHexagonalMesh",
    "bhvLLLBowserPuzzlePiece": "bhvLllBowserPuzzlePiece",
    "bhvLLLBowserPuzzle": "bhvLllBowserPuzzle",
    "bhvWDWExpressElevator": "bhvWdwExpressElevator",
    "bhvWDWExpressElevatorPlatform": "bhvWdwExpressElevatorPlatform",
    "bhvJRBSlidingBox": "bhvJrbSlidingBox",
    "bhvBlueCoinNumber": "bhvBlueCoinNumber",
    "bhvBooStaircase": "bhvBooBossSpawnedBridge",
    "bhvBBHTiltingTrapPlatform": "bhvBbhTiltingTrapPlatform",
    "bhvLLLDrawbridgeSpawner": "bhvLllDrawbridgeSpawner",
    "bhvLLLDrawbridge": "bhvLllDrawbridge",
    "bhvWFSlidingPlatform": "bhvWfSlidingPlatform",
    "bhvTTMBowlingBallSpawner": "bhvTtmBowlingBallSpawner",
    "bhvBoBBowlingBallSpawner": "bhvBobBowlingBallSpawner",
    "bhvTHIBowlingBallSpawner": "bhvThiBowlingBallSpawner",
    "bhvRRCruiserWing": "bhvRrCruiserWing",
    "bhvSSLMovingPyramidWall": "bhvSslMovingPyramidWall",
    "bhvStarNumber": "bhvStarNumber",
    "bhvTTMRollingLog": "bhvTtmRollingLog",
    "bhvLLLVolcanoFallingTrap": "bhvLllVolcanoFallingTrap",
    "bhvLLLRollingLog": "bhvLllRollingLog",
    "bhv1UpWalking": "bhv1upWalking",
    "bhv1UpRunningAway": "bhv1upRunningAway",
    "bhv1UpSliding": "bhv1upSliding",
    "bhv1UpJumpOnApproach": "bhv1upJumpOnApproach",
    "bhvHidden1Up": "bhvHidden1up",
    "bhvHidden1UpTrigger": "bhvHidden1upTrigger",
    "bhvHidden1UpInPole": "bhvHidden1upInPole",
    "bhvHidden1UpInPoleTrigger": "bhvHidden1upInPoleTrigger",
    "bhvHidden1UpInPoleSpawner": "bhvHidden1upInPoleSpawner",
    "bhvWDWSquareFloatingPlatform": "bhvWdwSquareFloatingPlatform",
    "bhvWDWRectangularFloatingPlatform": "bhvWdwRectangularFloatingPlatform",
    "bhvJRBFloatingPlatform": "bhvJrbFloatingPlatform",
    "bhvJRBFloatingBox": "bhvJrbFloatingBox",
    "bhvTreasureChestsJRB": "bhvTreasureChestsJrb",
    "bhvTreasureChestsDDD": "bhvTreasureChests",
}


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class DatabaseAnalysisPass(ABC):
    """
    Base class for all analysis passes that run on a fully-populated
    RomDatabase. Subclasses implement ``run(db)``.
    """

    name: str = "unnamed_pass"

    @abstractmethod
    def run(self, db: RomDatabase) -> None:
        """Mutate *db* in-place to refine records."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_model_candidates(obj: ObjectRecord, level: LevelRecord) -> List[str]:
    """
    Return ALL candidate MODEL_* names for an object's model_id slot,
    ordered from most-specific to least-specific.

    Model IDs are per-level slots — the same numeric ID means different things
    in different levels. Level-specific matches come first, then global
    candidates.
    """
    model_id = obj.model_id
    candidates: List[str] = []
    seen: Set[str] = set()

    # 1. Level-specific resolution (highest priority)
    level_short = level.level_name.lower()
    if level_short in _MODEL_ID_BY_LEVEL:
        level_models = _MODEL_ID_BY_LEVEL[level_short]
        if model_id in level_models:
            name = level_models[model_id]
            candidates.append(name)
            seen.add(name)

    # 2. Global lookup (all possible names for this numeric ID)
    if model_id in MODEL_ID_BY_VALUE:
        for name in MODEL_ID_BY_VALUE[model_id]:
            if name not in seen:
                candidates.append(name)
                seen.add(name)

    return candidates


# ---------------------------------------------------------------------------
# Reverse index: build once from KNOWN_BEHAVIOR_HASHES
# ---------------------------------------------------------------------------

_BEH_NAME_TO_HASHES: Dict[str, Set[str]] = {}


def _get_vanilla_hashes_for_behavior(beh_name: str) -> Set[str]:
    """Return all known vanilla hashes for a given behavior name."""
    global _BEH_NAME_TO_HASHES
    if not _BEH_NAME_TO_HASHES:
        for h, name_or_list in KNOWN_BEHAVIOR_HASHES.items():
            names = [name_or_list] if isinstance(name_or_list, str) else name_or_list
            for name in names:
                _BEH_NAME_TO_HASHES.setdefault(name, set()).add(h)
    return _BEH_NAME_TO_HASHES.get(beh_name, set())


# ---------------------------------------------------------------------------
# Pass 1: Object Correlation
# ---------------------------------------------------------------------------


class ObjectCorrelationPass(DatabaseAnalysisPass):
    """
    Cross-reference ObjectRecords with EXPECTED_PAIRINGS to:
     1. Score confidence on behaviour + model identification.
     2. Use normalized (fuzzy) hash comparison for vanilla similarity.
     3. Perform bidirectional identification where model candidates and
        behavior candidates mutually influence each other's probabilities.
     4. Set ``is_vanilla`` on behaviours based on fuzzy-hash match.
    """

    name = "object_correlation"

    # Tuning constants
    PAIRING_MATCH_BOOST = 0.25
    PAIRING_MISMATCH_PENALTY = 0.15
    FUZZY_HASH_EXACT_MATCH_SCORE = 0.50
    BASE_KNOWN_SCORE = 0.40

    def run(self, db: RomDatabase) -> None:
        debug_print("[ObjectCorrelationPass] Starting...")

        # Phase 1: Score behaviours standalone (hash matching)
        self._score_behaviors(db)

        # Phase 2: Walk objects — bidirectional correlation
        for level_name, level in db.levels.items():
            for area_id, area in level.areas.items():
                for obj in area.objects:
                    self._correlate_object(obj, level, db)

        # Phase 3: Mark vanilla status on behaviours
        self._mark_vanilla_behaviors(db)

        debug_print("[ObjectCorrelationPass] Done.")

    # ----- Phase 1: Behaviour confidence from hash and map matching -----

    def _score_behaviors(self, db: RomDatabase) -> None:
        """Set base confidence and initial naming on every BehaviorRecord."""
        for key, beh in db.behaviors.items():
            segmented_addr = beh.seg_addr

            # Evidence collection for all candidates
            candidates: Dict[str, float] = {}

            def add_candidate(name, weight):
                if name:
                    candidates[name] = candidates.get(name, 0.0) + weight

            # 1. Address Overrides (Highest priority)
            if segmented_addr in BEHAVIOR_ADDR_OVERRIDES:
                add_candidate(BEHAVIOR_ADDR_OVERRIDES[segmented_addr], 1.2)

            # 2. Hash Matching (Bytecode logic)
            # Check all tiers against both vanilla and custom databases
            for h_val, weight in [(beh.hash, 1.0), (beh.fuzzy_hash, 0.7), (beh.anon_hash, 0.4)]:
                if not h_val:
                    continue
                # Vanilla
                if h_val in KNOWN_BEHAVIOR_HASHES:
                    res = KNOWN_BEHAVIOR_HASHES[h_val]
                    h_names = [res] if isinstance(res, str) else res
                    for n in h_names:
                        add_candidate(n, weight)
                # Custom overrides
                if h_val in CUSTOM_BEHAVIOR_HASHES:
                    res = CUSTOM_BEHAVIOR_HASHES[h_val]
                    h_names = [res] if isinstance(res, str) else res
                    for n in h_names:
                        add_candidate(n, weight)

            # 3. Map File Symbol
            if beh.map_symbol:
                add_candidate(beh.map_symbol, 0.8)

            if not candidates:
                beh.confidence = 0.0
                continue

            # Pick the best candidate based on accumulated weight
            best_name = max(candidates, key=lambda k: candidates[k])
            best_weight = candidates[best_name]

            # Apply final name overrides (Refresh/Coop naming conventions)
            if best_name in BEHAVIOR_NAME_OVERRIDES:
                best_name = BEHAVIOR_NAME_OVERRIDES[best_name]

            # Store results
            beh.beh_name = best_name
            beh.confidence = min(best_weight, 1.0)

            # Sync global symbol table
            db.set_symbol(segmented_addr, best_name, "Behavior", confidence=beh.confidence)

    # ----- Phase 2: Bidirectional object correlation -----

    def _correlate_object(self, obj: ObjectRecord, level: LevelRecord, db: RomDatabase) -> None:
        """
        For one ObjectRecord, get ALL model candidates and let the behaviour
        and model lists mutually influence each other to pick the best pairing.
        """
        beh_name = obj.beh_name
        beh_record = self._find_behavior_record(obj.beh_addr, db)
        model_candidates = _get_model_candidates(obj, level)

        if not model_candidates:
            return

        beh_is_unknown = (
            not beh_name or beh_name.startswith("bhv_unknown") or beh_name.startswith("bhv_fail")
        )

        # --- Case 1: Both sides have candidates → score all combos ---
        if not beh_is_unknown:
            self._score_known_behavior_against_models(
                obj, beh_name, beh_record, model_candidates, db
            )
        else:
            # --- Case 2: Behavior unknown → use model candidates to identify it ---
            self._identify_behavior_from_models(obj, beh_record, model_candidates, db)

    def _score_known_behavior_against_models(
        self,
        obj: ObjectRecord,
        beh_name: str,
        beh_record: Optional[BehaviorRecord],
        model_candidates: List[str],
        db: RomDatabase,
    ) -> None:
        """
        Behavior is known. Score each model candidate against the expected
        pairings table and pick the best model.
        """
        if beh_name not in BEHAVIOR_TO_MODELS:
            # No pairing data for this behavior — just pick the first candidate
            obj.refined_model_name = model_candidates[0]
            return

        valid_models = BEHAVIOR_TO_MODELS[beh_name]

        # Score each model candidate
        best_model: Optional[str] = None
        best_score: float = -1.0

        for model_name in model_candidates:
            score = 0.0
            if model_name in valid_models:
                # This model is an expected partner for this behavior
                score = 1.0
            else:
                # Not in the expected set — could be custom, gets a low score
                score = 0.1

            # Tiebreaker: level-specific candidates rank higher (they're first
            # in the list from _get_model_candidates)
            if score > best_score:
                best_score = score
                best_model = model_name

        if best_model:
            obj.refined_model_name = best_model

            if best_score >= 1.0:
                # Good pairing — boost behavior confidence
                if beh_record:
                    beh_record.confidence = min(
                        beh_record.confidence + self.PAIRING_MATCH_BOOST, 1.0
                    )
                debug_print(
                    f"  [Correlation] ✓ {beh_name} + {best_model} "
                    f"(from {len(model_candidates)} candidates)"
                )
            else:
                # No matching model found — possible custom model
                if beh_record:
                    beh_record.confidence = max(
                        beh_record.confidence - self.PAIRING_MISMATCH_PENALTY, 0.0
                    )
                debug_print(
                    f"  [Correlation] ✗ {beh_name} + {best_model} "
                    f"(none of {len(model_candidates)} candidates matched "
                    f"expected {valid_models})"
                )

    def _identify_behavior_from_models(
        self,
        obj: ObjectRecord,
        beh_record: Optional[BehaviorRecord],
        model_candidates: List[str],
        db: RomDatabase,
    ) -> None:
        """
        Behavior is unknown. For each model candidate, check what behaviors
        are expected for it, then see if the behavior's fuzzy hash matches
        any of those expected behaviors. The model candidate that produces
        the best behavior match wins — both sides get named.
        """
        if not beh_record:
            return

        best_beh_name: Optional[str] = None
        best_model_name: Optional[str] = None
        best_score: float = 0.0

        for model_name in model_candidates:
            candidate_behaviors = MODEL_TO_BEHAVIORS.get(model_name, set())
            if not candidate_behaviors:
                continue

            for candidate_beh in candidate_behaviors:
                vanilla_hashes = _get_vanilla_hashes_for_behavior(candidate_beh)
                if not vanilla_hashes:
                    continue

                # Score: how well does this behavior's hash match the candidate?
                # Try all three tiers
                if beh_record.hash in vanilla_hashes:
                    score = 0.95  # Precise hash match
                elif beh_record.fuzzy_hash in vanilla_hashes:
                    score = 0.85  # Fuzzy hash match (pointer-normalized)
                elif beh_record.anon_hash in vanilla_hashes:
                    score = 0.70  # Anonymous match (structure only, no C funcs)
                else:
                    continue

                if score > best_score:
                    best_score = score
                    best_beh_name = candidate_beh
                    best_model_name = model_name

        if best_beh_name and best_model_name:
            debug_print(
                f"  [Bidirectional ID] {best_model_name} + {best_beh_name} "
                f"(was {beh_record.beh_name} + model_id={obj.model_id}, "
                f"score={best_score:.2f})"
            )
            beh_record.beh_name = best_beh_name
            beh_record.confidence = best_score
            obj.beh_name = best_beh_name
            obj.refined_model_name = best_model_name

    # ----- Phase 3: Vanilla detection -----

    def _mark_vanilla_behaviors(self, db: RomDatabase) -> None:
        """
        For every identified behaviour, determine whether it is structurally
        identical to vanilla using the best available hash tier.
        """
        for key, beh in db.behaviors.items():
            if beh.beh_name.startswith("bhv_unknown") or beh.beh_name.startswith("bhv_fail"):
                beh.is_vanilla = False
                continue

            vanilla_hashes = _get_vanilla_hashes_for_behavior(beh.beh_name)
            if not vanilla_hashes:
                beh.is_vanilla = None
                continue

            # Check all tiers: any match means structurally vanilla
            beh.is_vanilla = (
                beh.hash in vanilla_hashes
                or beh.fuzzy_hash in vanilla_hashes
                or beh.anon_hash in vanilla_hashes
            )

    # ----- Helpers -----

    @staticmethod
    def _find_behavior_record(beh_addr: int, db: RomDatabase) -> Optional[BehaviorRecord]:
        """Find a BehaviorRecord by its segmented address (any segment start)."""
        for (seg_addr, seg_start), rec in db.behaviors.items():
            if seg_addr == beh_addr:
                return rec
        return None


# ---------------------------------------------------------------------------
# Pass 2: Texture Context Propagation
# ---------------------------------------------------------------------------


class TextureContextPass(DatabaseAnalysisPass):
    """
    Walk display lists and geo layouts to propagate level context into textures.

    If a texture is used exclusively by DLs belonging to a single level, that
    level name becomes the texture's ``context_prefix``.  Segment 2 textures
    are skipped entirely (they are global/HUD).
    """

    name = "texture_context"

    def run(self, db: RomDatabase) -> None:
        debug_print("[TextureContextPass] Starting...")

        # Build a map: DL address → set of level names that use it
        dl_to_levels: Dict[Tuple[int, int], Set[str]] = {}

        for level_name, level in db.levels.items():
            for model_id, model in level.models.items():
                # Geo → DL link
                if model.geo_addr and model.geo_addr in {k[0] for k in db.geos}:
                    for geo_key, geo_rec in db.geos.items():
                        if geo_key[0] == model.geo_addr:
                            self._collect_dl_addrs_from_geo(geo_rec, level_name, dl_to_levels, db)
                # Direct DL link
                if model.dl_addr:
                    for dl_key in db.display_lists:
                        if dl_key[0] == model.dl_addr:
                            dl_to_levels.setdefault(dl_key, set()).add(level_name)

        # Now map: texture name → set of levels that reference it
        tex_to_levels: Dict[str, Set[str]] = {}
        for dl_key, dl_rec in db.display_lists.items():
            seg_num = (dl_key[0] >> 24) & 0xFF
            if seg_num == 2:
                continue  # Skip Segment 2 (global/HUD)

            levels_for_dl = dl_to_levels.get(dl_key, set())
            if not levels_for_dl:
                continue

            # Scan DL commands for texture references
            for cmd in dl_rec.commands:
                if cmd.name and "TEXTURE" in cmd.name.upper():
                    for param in cmd.params:
                        if isinstance(param, str) and param in db.textures:
                            tex_to_levels.setdefault(param, set()).update(levels_for_dl)

        # Assign context prefix to textures used by a single level
        for tex_name, levels in tex_to_levels.items():
            if len(levels) == 1 and tex_name in db.textures:
                level_name = next(iter(levels))
                tex_rec = db.textures[tex_name]
                if tex_rec.context_prefix is None:
                    tex_rec.context_prefix = level_name
                    debug_print(f"  [TexContext] {tex_name} → {level_name}")

        debug_print("[TextureContextPass] Done.")

    @staticmethod
    def _collect_dl_addrs_from_geo(
        geo_rec: GeoRecord,
        level_name: str,
        dl_to_levels: Dict[Tuple[int, int], Set[str]],
        db: RomDatabase,
    ) -> None:
        """Extract DL addresses from a geo layout's commands."""
        for cmd in geo_rec.commands:
            if cmd.name == "GEO_DISPLAY_LIST":
                # params[1] is typically the DL address
                if len(cmd.params) >= 2:
                    dl_addr = cmd.params[1]
                    if isinstance(dl_addr, int):
                        for dl_key in db.display_lists:
                            if dl_key[0] == dl_addr:
                                dl_to_levels.setdefault(dl_key, set()).add(level_name)


# ---------------------------------------------------------------------------
# Pass 3: Scrolling Texture Conversion
# ---------------------------------------------------------------------------


class ScrollingTexturePass(DatabaseAnalysisPass):
    name = "scrolling_textures"

    def run(self, db: RomDatabase) -> None:
        from context import ctx
        from scroll_targets import register_scroll_target

        for level_key, level in db.level_scripts.items():
            for ir in level.commands:
                if ir.name not in ("OBJECT", "OBJECT_WITH_ACTS"):
                    continue

                # ir.params: [model, posX, posY, posZ, angX, angY, angZ, behParam, beh_rec]
                if len(ir.params) < 9:
                    continue

                bhv_rec = ir.params[8]
                if not bhv_rec or not hasattr(bhv_rec, "seg_addr"):
                    continue

                beh_addr = bhv_rec.seg_addr

                # Resolve the refined name from the global symbol table
                beh_name = db.resolve_symbol(beh_addr, None, "Behavior")

                if beh_name == "editor_Scroll_Texture2":
                    beh_name = "editor_Scroll_Texture"

                # Check if it's a known scrolling behavior
                if not ("editor_Scroll_Texture" in beh_name or "RM_Scroll_Texture" in beh_name):
                    continue

                # ir.params[1-7] are now Parameter objects.
                posX = ir.params[1].value
                posY = ir.params[2].value
                posZ = ir.params[3].value
                angX = ir.params[4].value
                angY = ir.params[5].value
                angZ = ir.params[6].value
                behParam = ir.params[7].value

                # Restore the segment state to ensure we find the data we need
                if ir.snapshot is not None:
                    ir.snapshot.restore()

                converted = register_scroll_target(
                    db.txt if hasattr(db, "txt") else ctx.txt,
                    level.name,
                    beh_name,
                    posX,
                    posY,
                    posZ,
                    angX,
                    angY,
                    angZ,
                    behParam,
                )

                if not converted:
                    continue

                ir.params[1].value = converted["posX"]
                ir.params[2].value = converted["posY"]
                ir.params[3].value = converted["posZ"]
                ir.params[4].value = converted["angleX"]
                ir.params[5].value = converted["angleY"]
                ir.params[6].value = converted["angleZ"]
                ir.params[7].value = converted["behParam"]
                ir.params[7].fmt = "hex"  # Ensure target ID is hex

                # Update the behavior name string in the C output
                ir.params[8] = beh_name


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_ANALYSIS_PASSES: List[DatabaseAnalysisPass] = [
    ObjectCorrelationPass(),
    TextureContextPass(),
    ScrollingTexturePass(),
]


def run_all_analysis_passes(db: RomDatabase) -> None:
    """Execute every registered analysis pass in order."""
    for p in ALL_ANALYSIS_PASSES:
        debug_print(f"[Pipeline] Running analysis pass: {p.name}")
        p.run(db)
