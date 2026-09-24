"""L6's cross-encoder pass, bounded to the shortlist and honest about its scale (AD D.7).

**Bounded by construction, not by intent.** A cross-encoder scores query x candidate pairs
with no reusable per-document work, so its cost is linear in the number of pairs ([VERIFIED]
RO §5.2). That is a design constraint rather than a preference: `max_rerank_pairs` is the
shortlist size and this module cannot be handed more than `k` pairs, because the only thing
it is given is the shortlist.

**The mixed-scale rule, which is the part that is easy to get wrong** (A.9, ADV-110). A
rerank score exists for the shortlisted candidates and for nothing else. Where a comparison
contains a candidate the rerank did not score, the rerank may not order it: the two numbers
are on different scales and putting them in one sort is the fabricated comparability RANK-03
exists to prevent. So `ordering_effect` is `True` only where the score exists for **every**
candidate in that comparison, and `False` otherwise - with the ordering falling back to
`mailweave/mechanical-v1` alone, which exists for everybody.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mailweave.semantic.interface import SemanticBackend, SemanticError, checked_rerank
from mailweave.semantic.shortlist import Scored


@dataclass(frozen=True)
class RerankedRow:
    """One message's cross-encoder score, and the name of the text it was computed over."""

    message_id: str
    thread_id: str
    value: float
    #: **The name of** the text that was encoded for this row - the pool's declared text mode,
    #: carried through from `PoolRow.basis` - not the text itself. See `rerank_shortlist`.
    basis: str


@dataclass(frozen=True)
class RerankResult:
    """What the cross-encoder produced, and what it is allowed to order."""

    model_id: str
    model_revision: str
    rows: tuple[RerankedRow, ...]
    pairs: int
    ms: int
    failed: str | None = None

    @property
    def by_id(self) -> Mapping[str, RerankedRow]:
        return {row.message_id: row for row in self.rows}

    def orders(self, candidates: Sequence[str]) -> bool:
        """Whether this rerank may order **this** comparison (ADV-110).

        `True` only when every candidate in the comparison carries a rerank score. An empty
        comparison orders nothing and returns `False`, which is the honest answer rather
        than a vacuous truth: `ordering_effect: true` on a response that ordered nothing
        would be a claim about work that did not happen.
        """
        if not candidates or self.failed is not None:
            return False
        scored = self.by_id
        return all(candidate in scored for candidate in candidates)


def rerank_shortlist(
    backend: SemanticBackend,
    *,
    query: str,
    selected: Sequence[Scored],
    texts: Mapping[str, str],
    clock_ms: Callable[[], float],
) -> RerankResult:
    """Score the shortlist's pairs, or report the failure without raising.

    **A backend failure here is a degraded ranking, not a failed query.** The shortlist is
    already `H` and the mechanical ranking already exists for every candidate, so a
    cross-encoder that will not run costs the response its second tier and nothing else.
    Raising would turn a ranking problem into an unanswerable call, which is exactly the
    partition D.11 draws: anything that still permits a truthful partial answer is in band.

    `texts` maps message id to the text the pool embedded for that row. It decides *which*
    rows can be scored - a shortlisted id with no text is skipped rather than scored against
    the empty string, because a score over text nobody has is a number with no basis, the one
    thing D.7 says a score may never be - and it is **not** what `basis` carries.

    **`basis` names the text, and does not quote it** (round 31, R-M2-018). An earlier reading
    of D.7's "the text that was actually embedded" put the candidate's own pool text in this
    field: a message's subject, its participants and its snippet, verbatim and unfenced, in a
    string this server writes. AD D.2's worked example renders the field as
    `"subject+participants+snippet"` and ADV-110 asks it to *name* what was embedded, which is
    also the only reading INJ-02 permits - `Score` is a connector-voiced model and a reader
    cannot tell which half of one of its strings a message wrote. `Scored.basis` already
    carries the pool's declared text mode, computed once in `PoolRow`, so the name travels
    from the pool to the score rather than being restated here.
    """
    pairs = [row for row in selected if texts.get(row.message_id)]
    if not pairs:
        return RerankResult(
            model_id=backend.model_id,
            model_revision=backend.model_revision,
            rows=(),
            pairs=0,
            ms=0,
            failed="no shortlisted row carried the pool text its score would be computed over",
        )
    started = clock_ms()
    try:
        scores = checked_rerank(backend, query, [texts[row.message_id] for row in pairs])
    except SemanticError as failure:
        return RerankResult(
            model_id=backend.model_id,
            model_revision=backend.model_revision,
            rows=(),
            pairs=len(pairs),
            ms=int(clock_ms() - started),
            failed=f"{type(failure).__name__}: {failure}",
        )
    elapsed = int(clock_ms() - started)
    rows = tuple(
        RerankedRow(
            message_id=row.message_id,
            thread_id=row.thread_id,
            value=float(score),
            basis=row.basis,
        )
        for row, score in zip(pairs, scores, strict=True)
    )
    return RerankResult(
        model_id=backend.model_id,
        model_revision=backend.model_revision,
        rows=rows,
        pairs=len(pairs),
        ms=elapsed,
    )


__all__ = ["RerankResult", "RerankedRow", "rerank_shortlist"]
