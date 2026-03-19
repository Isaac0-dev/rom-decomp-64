from utils import debug_fail
import json
import gzip
from pathlib import Path
from .extractor import MipsFunctionExtractor


class MatchResult:
    def __init__(
        self,
        best_match=None,
        confidence=0.0,
        is_ambiguous=False,
        runner_up=None,
        runner_up_confidence=0.0,
    ):
        self.best_match = best_match
        self.confidence = confidence
        self.is_ambiguous = is_ambiguous
        self.runner_up = runner_up
        self.runner_up_confidence = runner_up_confidence

    def __repr__(self):
        return f"MatchResult(match={self.best_match}, conf={self.confidence:.2f}, ambig={self.is_ambiguous})"


class FunctionMatcher:
    def __init__(self):
        self.db_path = Path(__file__).parent / "vanilla_functions_db.json.gz"
        self.db = self._load_db()

    def _load_db(self):
        with gzip.open(self.db_path, "rt", encoding="utf-8") as f:
            return json.load(f)

    # Returns a dictionary containing the information about the
    # functions listed in `context`, with information from the database
    def get_candidates_for_context(self, context=None):
        # Default to all functions
        if context is None or context == "Global":
            return self.db

        # Handle explicit list of names
        if isinstance(context, (list, tuple, set, dict)):
            filtered = {}
            for name in context:
                if name in self.db:
                    filtered[name] = self.db[name]
            return filtered

        print(f"Warning: Unknown context type: {type(context)}")
        return {}

    def match(
        self,
        rom_bytes,
        rom_offset=0,
        vram=0,
        context="Global",
        vram_start=0x80246000,
        rom_start=0x1000,
    ):
        if rom_offset >= len(rom_bytes):
            debug_fail(
                f"rom_offset=0x{rom_offset:X} outside ROM bounds. "
                "Did you pass a VRAM address instead of a ROM offset?"
            )
            return None

        candidates = self.get_candidates_for_context(context)
        if not candidates:
            if not self.db:
                debug_fail("Error: Database is empty.")
                return None
            return None

        # Candidate extraction

        # Use the full ROM + the offset the caller specified
        # rom_bytes is assumed to be the full ROM buffer if rom_offset is provided
        # If rom_offset is 0, it might be a slice or start of ROM.

        extractor = MipsFunctionExtractor(
            rom_bytes, rom_offset, vram_start=vram_start, rom_start=rom_start
        )
        cand = extractor.extract()

        if cand is None:
            return None

        # Check for 100% binary match
        for name, entry in candidates.items():
            if cand.exact_hash == entry["exact_hash"]:
                return MatchResult(best_match=name, confidence=1.0)

        # Check for relocated match
        for name, entry in candidates.items():
            if cand.masked_signature == entry["masked_signature"]:
                return MatchResult(best_match=name, confidence=0.99)

        # Match based on structure
        cand_features = cand.features

        scores = []
        for name, entry in candidates.items():
            db_feats = entry["features"]
            score = self.compute_score(cand_features, db_feats)
            scores.append((name, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores:
            return None

        best_name, best_score = scores[0]

        # Make sure we're still in sane territory
        ACCEPTANCE_THRESHOLD = 0.5
        if best_score < ACCEPTANCE_THRESHOLD:
            return None

        # Ambiguity handling
        if len(scores) > 1:
            runner_up_name, runner_up_score = scores[1]
            gap = best_score - runner_up_score
            is_ambiguous = gap < 0.05  # Threshold
            return MatchResult(best_name, best_score, is_ambiguous, runner_up_name, runner_up_score)
        else:
            return MatchResult(best_name, best_score, False)

    def compute_score(self, cand_feats, db_feats):
        # Inst count
        c_cnt = cand_feats["inst_count"]
        d_cnt = db_feats["inst_count"]
        if max(c_cnt, d_cnt) == 0:
            match_cnt = 1.0
        else:
            match_cnt = 1.0 - abs(c_cnt - d_cnt) / max(c_cnt, d_cnt)

        # Block count
        c_blk = cand_feats["block_count"]
        d_blk = db_feats["block_count"]
        if max(c_blk, d_blk) == 0:
            match_blk = 1.0
        else:
            match_blk = 1.0 - abs(c_blk - d_blk) / max(c_blk, d_blk)

        # N-Grams (Set Jaccard) - reduced weight
        c_grams = set(cand_feats.get("opcode_ngrams", []))
        d_grams = set(db_feats.get("opcode_ngrams", []))
        if not c_grams and not d_grams:
            match_gram = 1.0
        elif not c_grams or not d_grams:
            match_gram = 0.0
        else:
            match_gram = len(c_grams & d_grams) / len(c_grams | d_grams)

        # Constants (Set Jaccard) - only high-halves (LUI values)
        c_const = set(cand_feats.get("constants", []))
        d_const = set(db_feats.get("constants", []))
        if not c_const and not d_const:
            match_const = 1.0
        elif not c_const or not d_const:
            match_const = 0.0
        else:
            match_const = len(c_const & d_const) / len(c_const | d_const)

        # Opcode Histogram (order-invariant, resilient to recompilation)
        c_hist = cand_feats.get("opcode_histogram", {})
        d_hist = db_feats.get("opcode_histogram", {})
        all_opcodes = set(c_hist.keys()) | set(d_hist.keys())
        if not all_opcodes:
            match_hist = 1.0
        else:
            # Intersection-over-union for histogram values
            intersection = sum(min(c_hist.get(op, 0), d_hist.get(op, 0)) for op in all_opcodes)
            union = max(sum(c_hist.values()), sum(d_hist.values()), 1)
            match_hist = intersection / union

        # Weights (adjusted for recompilation resilience)
        # Histogram: 0.40 (most stable)
        # Constants: 0.25 (LUI high-halves only)
        # Blocks: 0.15 (CFG structure)
        # N-grams: 0.10 (sequence-dependent, less stable)
        # Count: 0.10 (basic size)
        score = (
            (match_cnt * 0.10)
            + (match_blk * 0.15)
            + (match_gram * 0.10)
            + (match_const * 0.25)
            + (match_hist * 0.40)
        )
        return score


if __name__ == "__main__":
    pass
