from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from utils import debug_fail, debug_print

_BLOCK_SHIFT = 16


@dataclass
class RegionClaim:
    start: int
    end: int
    kind: str  # examples: "Level Script", "Geo Layout", "Collision"
    owners: List[str] = field(default_factory=list)
    conflicted: bool = False

    def describe(self) -> str:
        span = f"[0x{self.start:06X}-0x{self.end:06X})"
        who = "; ".join(o for o in self.owners if o) or "<unknown>"
        flag = " (CONFLICTED)" if self.conflicted else ""
        return f"{self.kind} {span} claimed by {who}{flag}"


class RomRegionMap:
    def __init__(self) -> None:
        self.reset()

    def __len__(self) -> int:
        return len(self.claims)

    def reset(self) -> None:
        self.claims: List[RegionClaim] = []
        self._blocks: Dict[int, List[int]] = {}
        self.conflict_count: int = 0

    def _overlapping(self, start: int, end: int) -> List[RegionClaim]:
        out: List[RegionClaim] = []
        seen: set = set()
        for b in range(start >> _BLOCK_SHIFT, ((end - 1) >> _BLOCK_SHIFT) + 1):
            for i in self._blocks.get(b, ()):
                if i in seen:
                    continue
                seen.add(i)
                c = self.claims[i]

                # Does it overlap?
                # AABB intersection test
                if c.start < end and start < c.end:
                    out.append(c)
        return out

    def _insert(self, start: int, end: int, kind: str, owner: str, conflicted: bool) -> None:
        claim = RegionClaim(start=start, end=end, kind=kind, owners=[owner] if owner else [])
        claim.conflicted = conflicted
        index = len(self.claims)
        self.claims.append(claim)
        for b in range(start >> _BLOCK_SHIFT, ((end - 1) >> _BLOCK_SHIFT) + 1):
            self._blocks.setdefault(b, []).append(index)

    def claim(self, start: int, end: int, kind: str, owner: str = "") -> None:

        # Size is 0
        if start == end:
            return

        # End should always be larger than the start
        assert start < end, f"Start {start:08X} needs to be smaller than end {end:08X}"

        # Get all the claims that already overlap.
        # If there are none, just insert the new claim.
        candidates = self._overlapping(start, end)
        if not candidates:
            self._insert(start, end, kind, owner, conflicted=False)
            return

        # Exact range match
        exact = [c for c in candidates if c.start == start and c.end == end]
        if exact:
            match = next((c for c in exact if c.kind == kind), None)
            if match is not None:
                if owner and owner not in match.owners:
                    match.owners.append(owner)
                return
            self.conflict_count += 1
            debug_fail(
                f"new {kind} claim as {owner} covers "
                f"(0x{start:06X}-0x{end:06X}) which is already claimed as "
                f"{exact[0].kind} by {'; '.join(exact[0].owners)}"
            )
            self._insert(start, end, kind, owner, conflicted=True)
            return

        partial: List[RegionClaim] = []
        nested: List[Tuple[str, RegionClaim]] = []
        for c in candidates:
            if c.start <= start and end <= c.end:
                nested.append(("inside", c))
            elif start <= c.start and c.end <= end:
                nested.append(("contains", c))
            else:
                partial.append(c)

        # Partial overlaps
        # This usually means a bad pointer
        if partial:
            self.conflict_count += 1
            p = partial[0]
            debug_fail(
                f"new {kind} claim (0x{start:06X}-0x{end:06X}) partial overlap: {p.describe()}."
            )
            self._insert(start, end, kind, owner, conflicted=True)

        # Nested overlaps
        if nested:
            debug_print(
                f"{kind} claim {owner} "
                f"(0x{start:06X}-0x{end:06X}) nests with {len(nested)} existing "
                f"claim(s), e.g. {nested[0][1].describe()}"
            )

        # Overlap accepted
        self._insert(start, end, kind, owner, conflicted=False)
