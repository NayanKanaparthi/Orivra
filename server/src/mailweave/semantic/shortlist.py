"""Stage A's selection rule: top-`k` by cosine, where `k` is a constant nobody tunes.

**Why this is a rule and not a threshold** (§H-5, ADV-109). A score threshold would hand
the implementer the dial that sets `|H|`: pick 0.4 and the shortlist is nine rows, pick 0.2
and it is ninety, and the response's own evidence set would depend on a number chosen after
seeing the data. `k = max_rerank_pairs = 25` is declared before the run, reported in
`retrieval_report.shortlist{rule, k, size}`, and is the same 25 the cross-encoder is bounded
to - so the shortlist is exactly "what stage B can afford to look at", which is a fact about
the machine rather than a judgement about relevance.

**Ordering is total.** Ties on the cosine are broken by message id, ascending, so two runs
over one mailbox produce the same shortlist even where two rows score identically - which
they do, because a thread often carries two near-identical rows. A non-total order here
would make `H` itself non-reproducible, and C-04b asks that ranking be reproducible given
the same inputs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from mailweave.semantic.interface import Vector


def cosine(left: Vector, right: Vector) -> float:
    """Cosine similarity, or `0.0` when either side has no magnitude.

    A zero vector has no direction, so it has no angle to anything. Returning `0.0` rather
    than raising is right here and is not a shrug: `checked_embed` has already refused
    zero-width and non-finite vectors, so the only way to arrive with a zero-magnitude
    vector is a row whose text embedded to the origin, and the honest similarity of a row
    with no content to anything at all is "no evidence of similarity".
    """
    if len(left) != len(right):
        raise ValueError(f"cosine over vectors of different width: {len(left)} and {len(right)}")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(frozen=True)
class Scored:
    """One pool row with its stage-A cosine and the text that produced it."""

    message_id: str
    thread_id: str
    cosine: float
    basis: str


@dataclass(frozen=True)
class ShortlistResult:
    """The selection, and everything the response has to declare about it."""

    #: The declared rule, verbatim, for `retrieval_report.shortlist.rule`.
    rule: str
    k: int
    selected: tuple[Scored, ...]
    #: Every pool row's score, in selection order. The trace's join set; never the response's.
    scored: tuple[Scored, ...]

    @property
    def size(self) -> int:
        return len(self.selected)

    @property
    def selected_ids(self) -> frozenset[str]:
        return frozenset(row.message_id for row in self.selected)

    @property
    def by_id(self) -> dict[str, Scored]:
        return {row.message_id: row for row in self.scored}


#: The rule as the response states it. A constant so the wire and the docstring cannot drift.
SHORTLIST_RULE: str = (
    "top-k by stage-A cosine over the declared pool text, k = max_rerank_pairs "
    "(a pre-registered constant, not a score threshold); ties broken by message id"
)


def shortlist(
    query_vector: Vector,
    rows: Sequence[tuple[str, str, Vector, str]],
    *,
    k: int,
) -> ShortlistResult:
    """Score every pool row against the query and take the top `k`.

    `rows` is `(message_id, thread_id, vector, basis)`. The whole scored set is carried in
    the result as well as the selection, because the trace needs it to be joinable and
    because a reviewer applying a different `k` should not need a re-run - the same reason
    PF-4 records its whole curve rather than the one point its verdict used.
    """
    if k <= 0:
        raise ValueError(f"a shortlist of k={k} selects nothing; k is max_rerank_pairs")
    scored = tuple(
        Scored(
            message_id=message_id,
            thread_id=thread_id,
            cosine=cosine(query_vector, vector),
            basis=basis,
        )
        for message_id, thread_id, vector, basis in rows
    )
    ranked = sorted(scored, key=lambda row: (-row.cosine, row.message_id))
    return ShortlistResult(
        rule=SHORTLIST_RULE, k=k, selected=tuple(ranked[:k]), scored=tuple(ranked)
    )


__all__ = ["SHORTLIST_RULE", "Scored", "ShortlistResult", "cosine", "shortlist"]
