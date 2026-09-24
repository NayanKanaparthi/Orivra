"""L6 executed: the mechanical tier, the gate, and the cross-encoder over the shortlist.

This module is the seam between `mailweave.ranking` - which owns D.7's policy and knows
nothing about Gmail, ledgers or envelopes - and `assemble`, which owns the response. It
turns a mapped-thread set plus an L5 run into an ordering and a set of scores, and it is the
only place that decides whether a given row carries a number at all.

**What carries a score and what does not** (D.7). A row Gmail's `q` selected says exactly
that and carries **no** numeric score: its provenance is an exact statement about what Gmail
matched, and a similarity number beside it would invite a reader to compare the two on one
scale. A row the scored retriever admitted carries a score, its `basis` is the text that was
actually encoded for it, and `ordering_effect` is true only where the score exists for every
candidate in the comparison it appears in.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import BudgetCapName, NotTriedWhy
from mailweave.envelope.wire import Affordance, NotTriedEntry, Score
from mailweave.policy.account import force_rungs
from mailweave.policy.budget import BudgetAccountant
from mailweave.ranking.gate import RerankGate, rerank_gate
from mailweave.ranking.mechanical import (
    MECHANICAL_METHOD,
    Candidate,
    Ranked,
    mechanical_rank,
)
from mailweave.ranking.rerank import RerankResult, rerank_shortlist
from mailweave.retrieval.ladder import LadderRun
from mailweave.retrieval.semantic import SemanticRun, SemanticState
from mailweave.semantic.interface import BackendRegistry, SemanticError


class RankingState(StrEnum):
    """What L6 did. `MECHANICAL_ONLY` is a run, not a decline: the first tier always runs."""

    RERANKED = "reranked"
    MECHANICAL_ONLY = "mechanical_only"
    #: Fewer than two candidates were disclosed, so there is no ordering to state. D.7 scopes
    #: mechanical ranking to "whenever more than one candidate is disclosed", and a response
    #: that named L6 over a single row - or over none - would be claiming it ranked something.
    NO_CANDIDATES = "no_candidates"
    #: A D.7 prohibition applied. The rung could not have helped and carries no affordance.
    NOT_APPLICABLE = "not_applicable"
    #: The gate fired and the model would not load or would not score.
    UNAVAILABLE = "unavailable"


#: The model string a mechanical score carries. D.7 requires `model` on every `Score`, and
#: the honest value for a score no model produced is a statement that no model produced it -
#: not the name of a model that happened to be loaded for something else.
NO_MODEL = "none (mechanical)"


@dataclass
class RankingRun:
    """L6's account of itself for one query."""

    state: RankingState
    gate: RerankGate
    mechanical: tuple[Ranked, ...] = ()
    rerank: RerankResult | None = None
    ms: int = 0
    #: The cap this rung hit, when it hit one. Read into `budget_caps_hit` by `assemble`.
    cap: BudgetCapName | None = None
    #: Whether the rerank was allowed to order the candidates - which is a fact about the
    #: **candidate set**, not about any one source's rows. See `score_for`.
    ordering_applied: bool = False
    errors: tuple[str, ...] = ()

    @property
    def ordering_method(self) -> str:
        """Which of D.7's two tiers ordered this response, in the method's own spelling."""
        if self.state is RankingState.RERANKED and self.ordering_applied:
            return f"{MECHANICAL_METHOD}+cross-encoder"
        return MECHANICAL_METHOD

    @property
    def order(self) -> tuple[str, ...]:
        """The candidate keys, best first, under whichever tier is allowed to order them."""
        return tuple(row.key for row in self.mechanical)

    @property
    def by_key(self) -> Mapping[str, Ranked]:
        return {row.key: row for row in self.mechanical}

    @property
    def not_tried_why(self) -> NotTriedWhy | None:
        return {
            RankingState.RERANKED: None,
            RankingState.MECHANICAL_ONLY: None,
            # Nothing to order is a rung that could not have helped, which is the one
            # `not_tried` reason compatible with `outcome: not_found` - and it is the honest
            # one: no ranking policy produces an ordering over zero or one candidate.
            RankingState.NO_CANDIDATES: NotTriedWhy.NOT_APPLICABLE,
            RankingState.NOT_APPLICABLE: NotTriedWhy.NOT_APPLICABLE,
            RankingState.UNAVAILABLE: NotTriedWhy.ERROR,
        }[self.state]

    def entry(self, *, query: str) -> NotTriedEntry | None:
        """L6's `not_tried[]` entry, or `None` when a tier ran.

        **`mechanical_only` produces no entry, and that is the substantive choice here.**
        The first tier of D.7 *is* L6, and it ran: the response's ordering is
        `mailweave/mechanical-v1` and every score says so. Recording the rung as not tried
        because its second tier declined would be a response claiming it did no ranking
        while shipping a ranked list.
        """
        why = self.not_tried_why
        if why is None:
            return None
        # A rung that could not have helped carries no call, and `RungAccount` refuses one:
        # an affordance here offers the caller a budget that changes nothing.
        affordance: Affordance | None = (
            None
            if self.state in {RankingState.NOT_APPLICABLE, RankingState.NO_CANDIDATES}
            else force_rungs(RungId.L6, query=query)
        )
        return NotTriedEntry(rung=RungId.L6.value, why=why, affordance=affordance)

    def score_for(self, message_id: str) -> Score | None:
        """The `Score` this row carries, or `None` when it must carry none.

        **`ordering_effect` is a fact about the comparison the rerank actually ordered**, and
        the first version asked the wrong one. It passed the rows of the row's own *source*,
        while `_reordered` orders the *candidate thread list* and orders it only when it
        scored every candidate - so a lone scored row in a source of one reported
        `ordering_effect: true` in the very field ADV-110 created to say otherwise, on a
        response whose order the rerank had declined to touch. The two answers are computed
        once, together, in `rank`, so they cannot come apart again.
        """
        if self.rerank is None:
            return None
        row = self.rerank.by_id.get(message_id)
        if row is None:
            return None
        return Score(
            value=row.value,
            method=f"{MECHANICAL_METHOD}+cross-encoder",
            model=f"{self.rerank.model_id}@{self.rerank.model_revision}",
            basis=row.basis,
            ordering_effect=self.ordering_applied,
        )

    def mechanical_score(self, key: str) -> Score | None:
        """The first tier's number for one candidate, for a caller that wants it on the wire.

        Not attached by `assemble` today: D.7 puts mechanical ranking's output in the
        *ordering* and its provenance in `score.method`, and the rows that would carry it
        are the `q`-selected rows D.7 says carry no numeric score. It exists because the
        number is real and a caller building a different surface over this engine should not
        have to recompute it.
        """
        row = self.by_key.get(key)
        if row is None:
            return None
        return Score(
            value=float(row.value),
            method=MECHANICAL_METHOD,
            model=NO_MODEL,
            basis=row.basis,
            ordering_effect=True,
        )


def rank(
    run: LadderRun,
    *,
    candidates: Sequence[Candidate],
    semantic: SemanticRun | None,
    registry: BackendRegistry,
    clock_ms: Callable[[], float],
    thread_count: int,
    forced: bool = False,
    accountant: BudgetAccountant | None = None,
    cross_encoder: bool = True,
) -> RankingRun:
    """Run D.7's two tiers over `candidates`, in the order D.7 puts them.

    The mechanical tier runs first and unconditionally, so a response always has an ordering
    that exists for every candidate. The gate is then consulted, and the cross-encoder runs
    only if it fires and only over the shortlist L5 already selected.

    **`forced` can add the second tier and can never reach past a prohibition** (WS-15, AD
    D.1: `force_rungs` "can only add rungs"). A caller who does not trust the ambiguity gate
    may have the rerank run; a caller who asks for it after an identity resolution is told
    why instead, because RANK-01 is not a policy a caller may overrule. Honouring it is what
    keeps `force_rungs: ["rerank"]` from being the silent no-op D.2's vocabulary exists to
    break.
    """
    mechanical = mechanical_rank(candidates)
    if len(candidates) < 2:
        # D.7: "Mechanical ranking runs whenever **more than one candidate is disclosed**."
        # With one or none there is no ordering to state, and a response that named L6 anyway
        # would be claiming it ranked something - which a query the parser produced no probe
        # from did, for one draft, on a report whose `rungs` was otherwise empty.
        return RankingRun(
            state=RankingState.NO_CANDIDATES,
            gate=RerankGate(fires=False),
            mechanical=mechanical,
        )
    cosines = (
        tuple(row.cosine for row in semantic.result.selected[:2])
        if semantic is not None and semantic.result is not None
        else ()
    )
    gate = rerank_gate(
        run.parsed,
        exact=run.exact_signal,
        hit_count=run.hit_count,
        thread_count=thread_count,
        term_coverage=run.parsed.term_coverage(run.parsed.constraints),
        top_cosines=cosines,
    )
    if gate.prohibited_by is not None:
        return RankingRun(state=RankingState.NOT_APPLICABLE, gate=gate, mechanical=mechanical)
    if not cross_encoder:
        # **D.7's second tier is absent from this configuration** - the H2 bypass arm. The
        # first tier has already run and its ordering stands, which is what `MECHANICAL_ONLY`
        # says and is the registered non-cross-encoder ordering, unchanged: `mechanical_rank`
        # above produced it and nothing here touches it.
        #
        # **Placed after the prohibition and before anything that scores.** After, so RANK-01,
        # the single-hit rule and the `rfc822msgid:` route report `not_applicable` identically
        # on both arms and the comparison is not contaminated by a tier one arm skipped for a
        # different reason. Before, so no backend is acquired and no pair is scored: the bypass
        # is the absence of the work, not a substitute for it. **No score is fabricated** -
        # `rerank` stays `None`, so `score_for` returns `None` and every row carries the
        # mechanical provenance it would carry on any response the gate did not fire for.
        #
        # It outranks `forced` deliberately. `force_rungs` adds a rung this build *has*; an
        # arm configured without the cross-encoder does not have it, and letting a request
        # re-enable it would mean the arm under measurement was not the arm configured. Like
        # `Selector`/Baseline F, this is an evaluation configuration and is never shipped: the
        # default is `True` and `MailweaveService` leaves it that way.
        return RankingRun(state=RankingState.MECHANICAL_ONLY, gate=gate, mechanical=mechanical)
    if not gate.fires and not forced:
        return RankingRun(state=RankingState.MECHANICAL_ONLY, gate=gate, mechanical=mechanical)
    if (
        semantic is None
        or semantic.result is None
        or semantic.state is not SemanticState.RAN
        or semantic.build is None
    ):
        # The gate fired and there is no shortlist to rerank. That is not a failure and not
        # a prohibition: D.7's second tier is defined over the scored retriever's output, so
        # with no scored retriever the first tier is the whole of the ranking.
        return RankingRun(state=RankingState.MECHANICAL_ONLY, gate=gate, mechanical=mechanical)
    try:
        backend = registry.acquire()
    except SemanticError as failure:
        return RankingRun(
            state=RankingState.UNAVAILABLE,
            gate=gate,
            mechanical=mechanical,
            errors=(f"{type(failure).__name__}: {failure}",),
        )
    # **The cross-encoder runs under `max_semantic_ms`, like L5's embed.** It did not, for one
    # draft: L5 entered and left the semantic clock before `assemble` was called, and the
    # rerank ran inside the assembly with no deadline over it at all - neither cap. A backend
    # that took ten minutes produced a normal response with an empty `budget_caps_hit`. The
    # accountant's own `enter_semantic` docstring names L5 *and L6* as what this cap is for.
    #
    # The budget accumulates across entries, so L5's embed and L6's rerank spend one
    # `max_semantic_ms` between them rather than one each.
    if accountant is not None:
        accountant.enter_semantic()
    try:
        spent = 0.0 if accountant is None else accountant.elapsed_ms
        limit = None if accountant is None else accountant.budget.max_semantic_ms
        if limit is not None and spent >= limit:
            # L5's own work has already spent the semantic budget. The mechanical tier stands
            # and the cap is named, which is the honest report: this is a rerank that did not
            # run, not a rerank that ran and returned nothing.
            return RankingRun(
                state=RankingState.MECHANICAL_ONLY,
                gate=gate,
                mechanical=mechanical,
                cap=BudgetCapName.MAX_SEMANTIC_MS,
            )
        texts = {row.message_id: row.text for row in semantic.build.rows}
        result = rerank_shortlist(
            backend,
            query=run.parsed.raw,
            selected=semantic.result.selected,
            texts=texts,
            clock_ms=clock_ms,
        )
        overran = (
            None
            if accountant is None or accountant.elapsed_ms < accountant.budget.max_semantic_ms
            else BudgetCapName.MAX_SEMANTIC_MS
        )
    finally:
        if accountant is not None:
            accountant.leave_semantic()
    if result.failed is not None:
        return RankingRun(
            state=RankingState.UNAVAILABLE,
            gate=gate,
            mechanical=mechanical,
            rerank=result,
            ms=result.ms,
            cap=overran,
            errors=(result.failed,),
        )
    ordered = _may_order(mechanical, result)
    return RankingRun(
        state=RankingState.RERANKED,
        gate=gate,
        mechanical=_reordered(mechanical, result),
        rerank=result,
        ms=result.ms,
        cap=overran,
        ordering_applied=ordered,
    )


def _reordered(mechanical: Sequence[Ranked], result: RerankResult) -> tuple[Ranked, ...]:
    """Reorder only where the rerank scored **every** candidate (ADV-110).

    **The first version permuted positions and that was the mixed scale wearing a
    permutation's clothes.** It moved the scored candidates among the slots they occupied,
    which changes the order of a scored candidate relative to an *unscored* one sitting
    between them: with mechanical order [a(5), b(4), c(0)] and rerank scores for a and c
    only, a landed behind b because c's rerank score outranked a's. b has no rerank score at
    all, so no comparison between b and a was ever made on one scale - which is exactly the
    fabricated comparability RANK-03 exists to prevent, produced by the function whose
    docstring said it could not happen.

    `RerankResult.orders` is the guard written for this, and it is now actually consulted:
    the rerank reorders the candidate list only when every candidate in it carries a rerank
    score. Otherwise the mechanical order stands whole, and `ordering_effect` on every score
    reports `false` - which is the response saying, in the field built to say it, that the
    numbers it is showing did not decide the order.
    """
    if not _may_order(mechanical, result):
        return tuple(mechanical)
    best = _best_by_thread(result)
    return tuple(sorted(mechanical, key=lambda row: (-best[row.key], row.key)))


def _best_by_thread(result: RerankResult) -> dict[str, float]:
    """Each candidate's best rerank score. A thread takes the score of its best row."""
    best: dict[str, float] = {}
    for row in result.rows:
        best[row.thread_id] = max(best.get(row.thread_id, row.value), row.value)
    return best


def _may_order(mechanical: Sequence[Ranked], result: RerankResult) -> bool:
    """Whether this rerank may order **this** candidate set (ADV-110).

    One predicate, read by `_reordered` and reported by `RankingRun.ordering_applied`, so the
    ordering and the response's account of the ordering cannot disagree - which they did:
    `score_for` used to ask `RerankResult.orders` about the rows of one source while
    `_reordered` was deciding over the candidate list.
    """
    if result.failed is not None:
        return False
    best = _best_by_thread(result)
    keys = [row.key for row in mechanical]
    return bool(best) and bool(keys) and all(key in best for key in keys)


@dataclass(frozen=True)
class CandidateFacts:
    """The per-thread facts `Candidate` needs, gathered once by `assemble`."""

    thread_id: str
    hit_messages: int = 0
    participant_match: bool = False
    inside_query_window: bool = False
    unrelaxed_route: bool = False
    extras: Mapping[str, object] = field(default_factory=dict)

    def as_candidate(self) -> Candidate:
        return Candidate(
            key=self.thread_id,
            hit_messages=self.hit_messages,
            participant_match=self.participant_match,
            inside_query_window=self.inside_query_window,
            unrelaxed_route=self.unrelaxed_route,
        )


#: `mechanical_rank` is re-exported because this module is the seam a caller reaches the
#: ranking through, and because a test that substitutes it has to name it somewhere the
#: type checker agrees exists.
__all__ = [
    "NO_MODEL",
    "CandidateFacts",
    "RankingRun",
    "RankingState",
    "mechanical_rank",
    "rank",
]
