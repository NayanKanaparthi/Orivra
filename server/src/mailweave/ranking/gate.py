"""L6's firing condition and its three hard prohibitions (AD D.7, RANK-01, SEM-04).

**The prohibitions are the point of this module.** A cross-encoder that ran after an
`rfc822msgid:` lookup would return *plausible* messages beside the exact one, ordered by
resemblance to the words the user typed, and nothing in the response would look wrong: the
rows would all be real messages, the scores would all be real numbers, and the exact answer
might not be first. That is the failure RANK-01 exists to prevent and it is invisible at
the wire, so it is refused here, in code, before any score is computed.

    never when `exact_signal_match` fired
    never when `hit_count == 1`
    never on an `rfc822msgid:` route

**And the firing condition is an ambiguity signal, not "we have a model".** D.7 gates the
cross-encoder on four signals: a hit-count band, `term_coverage < 1`, thread concentration,
and a scored-retriever margin. A rerank that ran whenever it could would spend CPU on every
query and would re-order answers the lexical ladder had already settled exactly - which is
I-3 (adaptive cost) failing in the direction that is hardest to notice, because the answers
stay correct and only the cost and the provenance get worse.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from mailweave.query.analysis import ParsedQuery
from mailweave.query.operators import OperatorName
from mailweave.retrieval.signals import ExactSignal

#: D.7's hit-count band: a single hit is unambiguous by definition and a very large hit set
#: is a query that needs narrowing rather than re-ordering. [PRE-REG] at G0, recorded here
#: as the published pair so a later calibration is a visible edit rather than a drift.
AMBIGUITY_HIT_BAND: Final[tuple[int, int]] = (2, 50)

#: D.7's thread-concentration signal: hits spread across at least this many threads are an
#: ambiguous answer even when there are few of them. Two threads is the smallest number for
#: which "which thread is the answer in?" is a question at all.
AMBIGUITY_MIN_THREADS: Final[int] = 2

#: D.7's scored-retriever margin: a shortlist whose best and second-best cosines are within
#: this of each other has not separated its candidates, which is the case a cross-encoder is
#: for. [PRE-REG] at G0.
AMBIGUITY_COSINE_MARGIN: Final[float] = 0.05


class AmbiguitySignal(StrEnum):
    """D.7's four signals. A rerank names the ones that fired, never "a model was available"."""

    HIT_COUNT_BAND = "hit_count_band"
    PARTIAL_TERM_COVERAGE = "term_coverage_below_one"
    THREAD_CONCENTRATION = "thread_concentration"
    SCORED_RETRIEVER_MARGIN = "scored_retriever_margin"


class RerankProhibition(StrEnum):
    """The three states in which no ranking rung may run, whatever else is true."""

    EXACT_SIGNAL_MATCH = "exact_signal_match"
    SINGLE_HIT = "hit_count_is_one"
    IDENTIFIER_ROUTE = "rfc822msgid_route"


@dataclass(frozen=True)
class RerankGate:
    """Whether L6 may rerank, and exactly why or why not."""

    fires: bool
    prohibited_by: RerankProhibition | None = None
    signals: tuple[AmbiguitySignal, ...] = ()

    @property
    def why(self) -> str:
        if self.prohibited_by is not None:
            return f"cross-encoder rerank is prohibited here: {self.prohibited_by.value} (RANK-01)"
        if not self.fires:
            return "no D.7 ambiguity signal fired, so the mechanical ranking stands alone"
        return "ambiguity signals fired: " + ", ".join(signal.value for signal in self.signals)


def _is_an_identifier_route(parsed: ParsedQuery) -> bool:
    """Whether this query is an `rfc822msgid:` lookup.

    Read off the parsed operators rather than off the raw string: a raw-substring check
    would fire on a quoted phrase that merely mentions the operator, and would miss a
    spelling the parser normalises. The parse is what the probes were built from, so it is
    what the prohibition is about.
    """
    return any(operator.name is OperatorName.RFC822MSGID for operator in parsed.operators)


def rerank_gate(
    parsed: ParsedQuery,
    *,
    exact: ExactSignal,
    hit_count: int,
    thread_count: int,
    term_coverage: float,
    top_cosines: tuple[float, ...] = (),
) -> RerankGate:
    """D.7's gate: prohibitions first, then the four ambiguity signals.

    **Prohibitions are evaluated before signals and cannot be reached past.** The ordering is
    the same one `semantic_gate` uses and for the same reason: a prohibition is a statement
    that this rung must not run, and a signal is a statement that it would help. Evaluating
    the signals first would produce a gate that fires on an identity lookup whenever the
    lookup happened to be ambiguous, which is precisely the case RANK-01 names.
    """
    if _is_an_identifier_route(parsed):
        route = RerankProhibition.IDENTIFIER_ROUTE
        return RerankGate(fires=False, prohibited_by=route)
    if exact.fired:
        return RerankGate(fires=False, prohibited_by=RerankProhibition.EXACT_SIGNAL_MATCH)
    if hit_count == 1:
        return RerankGate(fires=False, prohibited_by=RerankProhibition.SINGLE_HIT)

    signals: list[AmbiguitySignal] = []
    low, high = AMBIGUITY_HIT_BAND
    if low <= hit_count <= high:
        signals.append(AmbiguitySignal.HIT_COUNT_BAND)
    if term_coverage < 1.0:
        signals.append(AmbiguitySignal.PARTIAL_TERM_COVERAGE)
    if thread_count >= AMBIGUITY_MIN_THREADS:
        signals.append(AmbiguitySignal.THREAD_CONCENTRATION)
    if len(top_cosines) >= 2 and abs(top_cosines[0] - top_cosines[1]) <= AMBIGUITY_COSINE_MARGIN:
        signals.append(AmbiguitySignal.SCORED_RETRIEVER_MARGIN)
    return RerankGate(fires=bool(signals), signals=tuple(signals))


__all__ = [
    "AMBIGUITY_COSINE_MARGIN",
    "AMBIGUITY_HIT_BAND",
    "AMBIGUITY_MIN_THREADS",
    "AmbiguitySignal",
    "RerankGate",
    "RerankProhibition",
    "rerank_gate",
]
