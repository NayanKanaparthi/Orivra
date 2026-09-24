"""L6: ranking (AD D.7). Two tiers, both mechanical about provenance (RANK-03).

`mechanical` is the tier that always runs and reads no model. `gate` is D.7's firing
condition for the second tier and the three prohibitions that override it. `rerank` is the
cross-encoder pass, bounded to the shortlist by construction.
"""

from __future__ import annotations

from mailweave.ranking.gate import (
    AMBIGUITY_COSINE_MARGIN,
    AMBIGUITY_HIT_BAND,
    AMBIGUITY_MIN_THREADS,
    AmbiguitySignal,
    RerankGate,
    RerankProhibition,
    rerank_gate,
)
from mailweave.ranking.mechanical import (
    MECHANICAL_METHOD,
    MECHANICAL_WEIGHTS,
    Candidate,
    RankComponent,
    Ranked,
    mechanical_rank,
)
from mailweave.ranking.rerank import RerankedRow, RerankResult, rerank_shortlist

__all__ = [
    "AMBIGUITY_COSINE_MARGIN",
    "AMBIGUITY_HIT_BAND",
    "AMBIGUITY_MIN_THREADS",
    "MECHANICAL_METHOD",
    "MECHANICAL_WEIGHTS",
    "AmbiguitySignal",
    "Candidate",
    "RankComponent",
    "Ranked",
    "RerankGate",
    "RerankProhibition",
    "RerankResult",
    "RerankedRow",
    "mechanical_rank",
    "rerank_gate",
    "rerank_shortlist",
]
