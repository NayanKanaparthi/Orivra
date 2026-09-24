"""L6 executed: the prohibitions, the gate, the mechanical tier, and the mixed-scale rule.

The four claims this file exists to execute rather than assert.

  * **The three prohibitions hold, and `force_rungs` does not lift them.** RANK-01 forbids a
    ranking rung after an `exact_signal_match`, on a single hit, and on an `rfc822msgid:`
    route. A cross-encoder that ran there would return plausible messages beside the exact
    one and nothing on the wire would look wrong.
  * **The second tier is gated on ambiguity, not on availability.** D.7 names four signals;
    a rerank that ran whenever a model was loaded would spend CPU re-ordering answers the
    lexical ladder had already settled exactly.
  * **The mechanical tier is reproducible and total.** Same inputs, same order, ties broken
    by key - so a response's ordering is never a fact about dictionary iteration (C-04b).
  * **A rerank may order only where its score exists for every candidate** (ADV-110), and a
    row Gmail's `q` selected carries no numeric score at all (D.7).
"""

from __future__ import annotations

from datetime import UTC, datetime

from mailweave.query.analysis import analyse
from mailweave.ranking.gate import (
    AMBIGUITY_HIT_BAND,
    AmbiguitySignal,
    RerankProhibition,
    rerank_gate,
)
from mailweave.ranking.mechanical import (
    MECHANICAL_METHOD,
    MECHANICAL_WEIGHTS,
    Candidate,
    RankComponent,
    mechanical_rank,
)
from mailweave.ranking.rerank import RerankedRow, RerankResult
from mailweave.retrieval.signals import ExactBranch, ExactSignal

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _signal(*, fired: bool = False, branch: ExactBranch | None = None) -> ExactSignal:
    return ExactSignal(
        fired=fired, branch=branch, phrase_tokens=0, hit_count=1, verified_locally=fired
    )


# --- the three prohibitions ------------------------------------------------------------------


def test_an_rfc822msgid_route_is_never_reranked() -> None:
    """RANK-01, read off the parse rather than off the raw string."""
    parsed = analyse("rfc822msgid:<a@b.invalid> cutover", now=NOW)
    gate = rerank_gate(
        parsed,
        exact=_signal(),
        hit_count=9,
        thread_count=4,
        term_coverage=0.5,
    )
    assert gate.fires is False
    assert gate.prohibited_by is RerankProhibition.IDENTIFIER_ROUTE
    assert gate.signals == (), "an ambiguity signal was computed on a prohibited route"


def test_a_quoted_phrase_that_mentions_the_operator_is_not_an_identifier_route() -> None:
    """The reason the prohibition reads the parse: a raw-substring check fires on this."""
    parsed = analyse('"the rfc822msgid: header" cutover', now=NOW)
    gate = rerank_gate(parsed, exact=_signal(), hit_count=9, thread_count=4, term_coverage=0.5)
    assert gate.prohibited_by is None


def test_an_exact_signal_match_is_never_reranked() -> None:
    parsed = analyse('"rollout window slipped"', now=NOW)
    gate = rerank_gate(
        parsed,
        exact=_signal(fired=True, branch=ExactBranch.E_B),
        hit_count=9,
        thread_count=4,
        term_coverage=0.5,
    )
    assert gate.prohibited_by is RerankProhibition.EXACT_SIGNAL_MATCH


def test_a_single_hit_is_never_reranked() -> None:
    """One candidate has no ordering to state, so a rerank over it can only invent one."""
    parsed = analyse("cutover date", now=NOW)
    gate = rerank_gate(parsed, exact=_signal(), hit_count=1, thread_count=1, term_coverage=0.5)
    assert gate.prohibited_by is RerankProhibition.SINGLE_HIT


def test_the_prohibitions_are_evaluated_before_the_signals() -> None:
    """A query that is both prohibited and ambiguous is prohibited, not ambiguous.

    The ordering is what stops a gate from firing on an identity lookup whenever the lookup
    happened to be ambiguous - which is precisely the case RANK-01 names.
    """
    parsed = analyse("rfc822msgid:<a@b.invalid>", now=NOW)
    gate = rerank_gate(
        parsed,
        exact=_signal(fired=True, branch=ExactBranch.E_A),
        hit_count=7,
        thread_count=5,
        term_coverage=0.25,
        top_cosines=(0.71, 0.70),
    )
    assert gate.fires is False
    assert gate.prohibited_by is RerankProhibition.IDENTIFIER_ROUTE
    assert "RANK-01" in gate.why


# --- the four ambiguity signals ---------------------------------------------------------------


def test_each_of_the_four_signals_can_fire_on_its_own() -> None:
    """D.7 names four; a gate that only ever fired on one would be three dead clauses."""
    wide = analyse("cutover date rollout window", now=NOW)
    low, high = AMBIGUITY_HIT_BAND
    band = rerank_gate(wide, exact=_signal(), hit_count=low, thread_count=1, term_coverage=1.0)
    assert band.signals == (AmbiguitySignal.HIT_COUNT_BAND,)

    coverage = rerank_gate(
        wide, exact=_signal(), hit_count=high + 1, thread_count=1, term_coverage=0.75
    )
    assert coverage.signals == (AmbiguitySignal.PARTIAL_TERM_COVERAGE,)

    threads = rerank_gate(
        wide, exact=_signal(), hit_count=high + 1, thread_count=3, term_coverage=1.0
    )
    assert threads.signals == (AmbiguitySignal.THREAD_CONCENTRATION,)

    margin = rerank_gate(
        wide,
        exact=_signal(),
        hit_count=high + 1,
        thread_count=1,
        term_coverage=1.0,
        top_cosines=(0.62, 0.60),
    )
    assert margin.signals == (AmbiguitySignal.SCORED_RETRIEVER_MARGIN,)


def test_no_signal_means_the_mechanical_ranking_stands_alone() -> None:
    """Availability is not a reason to rerank (I-3: adaptive cost)."""
    parsed = analyse("cutover date", now=NOW)
    _low, high = AMBIGUITY_HIT_BAND
    gate = rerank_gate(
        parsed,
        exact=_signal(),
        hit_count=high + 1,
        thread_count=1,
        term_coverage=1.0,
        top_cosines=(0.9, 0.1),
    )
    assert gate.fires is False
    assert gate.prohibited_by is None
    assert "mechanical ranking stands alone" in gate.why


# --- the mechanical tier ------------------------------------------------------------------


def test_the_mechanical_ranking_is_total_and_reproducible() -> None:
    """C-04b: same inputs, same order - including where two candidates tie exactly."""
    candidates = [
        Candidate(key="t-b", hit_messages=1),
        Candidate(key="t-a", hit_messages=1),
        Candidate(key="t-c", hit_messages=2, unrelaxed_route=True),
    ]
    first = mechanical_rank(candidates)
    second = mechanical_rank(list(reversed(candidates)))
    assert [row.key for row in first] == [row.key for row in second]
    assert first[0].key == "t-c"
    assert [row.key for row in first[1:]] == ["t-a", "t-b"], "the tie-break is not by key"


def test_every_mechanical_score_names_the_components_that_fired() -> None:
    """RANK-03: `score.method = mailweave/mechanical-v1` with the firing components listed."""
    ranked = mechanical_rank(
        [Candidate(key="t", hit_messages=2, participant_match=True, unrelaxed_route=True)]
    )[0]
    assert ranked.components == (
        RankComponent.QUERY_HIT,
        RankComponent.UNRELAXED_ROUTE,
        RankComponent.PARTICIPANT_MATCH,
        RankComponent.HIT_CONCENTRATION,
    )
    assert ranked.value == (
        MECHANICAL_WEIGHTS[RankComponent.QUERY_HIT]
        + MECHANICAL_WEIGHTS[RankComponent.UNRELAXED_ROUTE]
        + MECHANICAL_WEIGHTS[RankComponent.PARTICIPANT_MATCH]
        + MECHANICAL_WEIGHTS[RankComponent.HIT_CONCENTRATION]
    )
    for component in ranked.components:
        assert component.value in ranked.basis
    assert MECHANICAL_METHOD == "mailweave/mechanical-v1"


def test_a_candidate_on_which_nothing_fired_scores_zero_and_says_so() -> None:
    """A zero with no components is not the same statement as a zero with some."""
    ranked = mechanical_rank([Candidate(key="t")])[0]
    assert ranked.value == 0
    assert ranked.components == ()
    assert ranked.basis == "no mechanical component fired"


def test_the_weights_are_total_over_the_components() -> None:
    """A component added later has to be given a weight in the same edit."""
    assert set(MECHANICAL_WEIGHTS) == set(RankComponent)


def test_no_query_independent_component_can_outrank_a_query_derived_one() -> None:
    """DISC-01's guard, one layer out from the E4 fill: concentration cannot beat a hit.

    `HIT_CONCENTRATION` is the one component that says nothing about the *query* - a thread
    with two hits has two hits whatever was asked - so it must never by itself order a
    candidate ahead of one the query reached through an unrelaxed route.
    """
    assert MECHANICAL_WEIGHTS[RankComponent.HIT_CONCENTRATION] < min(
        MECHANICAL_WEIGHTS[component]
        for component in RankComponent
        if component is not RankComponent.HIT_CONCENTRATION
    )


# --- the mixed-scale rule ------------------------------------------------------------------


def _result(*rows: tuple[str, str, float]) -> RerankResult:
    return RerankResult(
        model_id="test/cross",
        model_revision="0" * 40,
        rows=tuple(
            RerankedRow(message_id=mid, thread_id=tid, value=value, basis="subject\naddr")
            for mid, tid, value in rows
        ),
        pairs=len(rows),
        ms=1,
    )


def test_a_rerank_orders_only_a_comparison_it_scored_every_member_of() -> None:
    """ADV-110: mixing a rerank score with a mechanical one inside one sort is forbidden."""
    result = _result(("m-1", "t", 0.9), ("m-2", "t", 0.1))
    assert result.orders(["m-1", "m-2"]) is True
    assert result.orders(["m-1", "m-2", "m-3"]) is False


def test_a_partly_scored_candidate_set_keeps_the_mechanical_order_whole() -> None:
    """`_reordered` consults `orders` - which the first version did not, and it showed.

    It permuted the *positions* the rerank scored, which moves a scored candidate relative to
    an unscored one sitting between them: with mechanical order [a(5), b(4), c(0)] and rerank
    scores for a and c only, a landed behind b - and b carries no rerank score, so no
    comparison between a and b was ever made on one scale. That is ADV-110's mixed scale
    produced by the function whose docstring said it could not happen.
    """
    from mailweave.retrieval.ranking import _reordered

    mechanical = mechanical_rank(
        [
            Candidate(key="t-a", hit_messages=1, unrelaxed_route=True),
            Candidate(key="t-b", hit_messages=1),
            Candidate(key="t-c"),
        ]
    )
    assert [row.key for row in mechanical] == ["t-a", "t-b", "t-c"]
    partial = _result(("m-a", "t-a", 0.1), ("m-c", "t-c", 0.9))
    assert [row.key for row in _reordered(mechanical, partial)] == ["t-a", "t-b", "t-c"], (
        "the rerank reordered a comparison containing a candidate it never scored"
    )
    whole = _result(("m-a", "t-a", 0.1), ("m-b", "t-b", 0.5), ("m-c", "t-c", 0.9))
    assert [row.key for row in _reordered(mechanical, whole)] == ["t-c", "t-b", "t-a"], (
        "a rerank that scored every candidate may order them, and did not"
    )


def test_an_empty_comparison_orders_nothing_rather_than_vacuously_ordering() -> None:
    """`ordering_effect: true` on a response that ordered nothing is a claim about no work."""
    assert _result(("m-1", "t", 0.9)).orders([]) is False


def test_a_failed_rerank_orders_nothing_even_where_it_has_rows() -> None:
    """The `failed` guard, exercised - which the first version of this test did not do.

    It built `rows=()`, so `all(candidate in scored ...)` was already False and the guard
    clause could be deleted with the test still green. A rerank can fail *after* producing
    rows - a contract error on the last of twenty-five pairs, a clock that ran out - and a
    partially-scored result ordering a comparison it half measured is the case the guard is
    for. So the fixture carries rows and asserts both directions.
    """
    rows = (
        RerankedRow(message_id="m-1", thread_id="t", value=0.9, basis="x"),
        RerankedRow(message_id="m-2", thread_id="t", value=0.1, basis="x"),
    )
    ok = RerankResult(model_id="test/cross", model_revision="0" * 40, rows=rows, pairs=2, ms=3)
    assert ok.orders(["m-1", "m-2"]) is True, "the same rows, without the failure, do order"

    failed = RerankResult(
        model_id="test/cross",
        model_revision="0" * 40,
        rows=rows,
        pairs=2,
        ms=3,
        failed="boom",
    )
    assert failed.orders(["m-1", "m-2"]) is False


# --- the two facts a response has to state about its own ordering ---------------------------


def test_ordering_effect_is_about_the_set_the_rerank_ordered_not_one_source() -> None:
    """ADV-110, in the field built to say it.

    `_score_for` used to ask `RerankResult.orders` about the rows of the row's *own source*,
    while `_reordered` decides over the candidate thread list. The two disagree in the
    reachable direction: a lone scored row in a source of one reported `ordering_effect:
    true` on a response whose order the rerank had declined to touch. One predicate now
    answers both, computed once in `rank`.
    """
    from mailweave.ranking.rerank import RerankResult
    from mailweave.retrieval.ranking import RankingRun, RankingState, _may_order, _reordered

    mechanical = mechanical_rank(
        [Candidate(key="t-a", hit_messages=1), Candidate(key="t-b", hit_messages=1)]
    )
    partial = _result(("m-a", "t-a", 0.9))
    assert _may_order(mechanical, partial) is False
    assert [row.key for row in _reordered(mechanical, partial)] == [row.key for row in mechanical]
    run = RankingRun(
        state=RankingState.RERANKED,
        gate=rerank_gate(
            analyse("cutover rollout", now=NOW),
            exact=_signal(),
            hit_count=4,
            thread_count=2,
            term_coverage=1.0,
        ),
        mechanical=mechanical,
        rerank=partial,
        ordering_applied=_may_order(mechanical, partial),
    )
    score = run.score_for("m-a")
    assert score is not None
    assert score.ordering_effect is False, (
        "a score reported an ordering effect on a response the rerank did not reorder"
    )

    whole = _result(("m-a", "t-a", 0.9), ("m-b", "t-b", 0.1))
    assert _may_order(mechanical, whole) is True
    ordered = RankingRun(
        state=RankingState.RERANKED,
        gate=run.gate,
        mechanical=_reordered(mechanical, whole),
        rerank=whole,
        ordering_applied=True,
    )
    assert isinstance(ordered.rerank, RerankResult)
    scored = ordered.score_for("m-a")
    assert scored is not None and scored.ordering_effect is True
