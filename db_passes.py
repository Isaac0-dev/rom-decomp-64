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
        for h, name in KNOWN_BEHAVIOR_HASHES.items():
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

    # ----- Phase 1: Behaviour confidence from hash matching -----

    def _score_behaviors(self, db: RomDatabase) -> None:
        """Set base confidence on every BehaviorRecord."""
        for key, beh in db.behaviors.items():
            if beh.beh_name.startswith("bhv_unknown") or beh.beh_name.startswith("bhv_fail"):
                beh.confidence = 0.0
                continue

            score = self.BASE_KNOWN_SCORE

            # Bonus: check hash tiers against known vanilla hashes for that name
            vanilla_hashes = _get_vanilla_hashes_for_behavior(beh.beh_name)
            if vanilla_hashes:
                if beh.hash in vanilla_hashes:
                    score += self.FUZZY_HASH_EXACT_MATCH_SCORE
                elif beh.fuzzy_hash in vanilla_hashes:
                    score += self.FUZZY_HASH_EXACT_MATCH_SCORE
                elif beh.anon_hash in vanilla_hashes:
                    # Anonymous tier: weaker signal (structure matches but
                    # we can't verify the C function pointers)
                    score += self.FUZZY_HASH_EXACT_MATCH_SCORE * 0.7

            beh.confidence = min(score, 1.0)

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
# Registry
# ---------------------------------------------------------------------------

ALL_ANALYSIS_PASSES: List[DatabaseAnalysisPass] = [
    ObjectCorrelationPass(),
    TextureContextPass(),
]


def run_all_analysis_passes(db: RomDatabase) -> None:
    """Execute every registered analysis pass in order."""
    for p in ALL_ANALYSIS_PASSES:
        debug_print(f"[Pipeline] Running analysis pass: {p.name}")
        p.run(db)
