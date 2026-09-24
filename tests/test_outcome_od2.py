"""OD-2 as a structural property of the response, not a comment.

OD-2 (binding, 2026-08-30):

    NOT_FOUND means every retrieval path applicable to this query was actually executed
    and exhausted, and no evidence was found. If an applicable path was not executed
    because of budget exhaustion, error, timeout or cap, the result is INCONCLUSIVE.

The vocabulary literals below are quoted from OD-2 and AD D.2, not imported from the
implementation, so that a change to the implementation's own constants cannot silently
redefine what the test is checking.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from mailweave.envelope import (
    Affordance,
    BudgetCapName,
    DispositionLedger,
    EnvelopeBuilder,
    NotTriedEntry,
    NotTriedWhy,
    Outcome,
    RungId,
    Sufficiency,
    ToolName,
    WithheldCap,
)
from mailweave.envelope.vocab import EmptyDiagnosisStatus
from mailweave.envelope.wire import (
    Counters,
    EmptyDiagnosis,
    RetrievalReport,
    ScanScopeEntry,
)
from tests.fixtures import envelope_kit as kit

#: AD D.2 field note, quoted.
DOCUMENTED_NOT_TRIED_VOCABULARY = {"not_applicable", "budget", "cap", "timeout", "error"}
#: Round 22's addition to it, argued in `NotTriedWhy`'s own docstring and recorded in
#: `docs/reviews/ROUND_22/IMPLEMENTER.md`. Written here as a separate set rather than folded
#: into the quotation above, so the published list stays quotable and an addition stays
#: visible as an addition. `tests/test_ws10_escalation.py` carries the same partition.
ROUND_22_ADDITION = {"stopped_on_evidence"}
#: "...not executed because of budget exhaustion, error, timeout or cap" (OD-2), plus round
#: 22's addition, which forbids `not_found` for a second and independent reason: a D.3 stop
#: rule fires only on non-zero evidence, so `not_found`'s own "and no evidence was found"
#: conjunct is already false wherever `stopped_on_evidence` can appear.
DOCUMENTED_BLOCKING_REASONS = {"budget", "cap", "timeout", "error"} | ROUND_22_ADDITION
DOCUMENTED_OUTCOMES = {"answered", "not_found", "inconclusive"}


def widen() -> Affordance:
    return Affordance(tool=ToolName.SEARCH, args={"pool": {"max_threads": 50}})


def report(
    *,
    outcome: Outcome,
    not_tried: tuple[NotTriedEntry, ...] = (),
    caps: tuple[BudgetCapName, ...] = (),
    scan: tuple[ScanScopeEntry, ...] = (),
) -> RetrievalReport:
    return RetrievalReport(
        outcome=outcome,
        rungs=(RungId.L0, RungId.L1),
        # Built directly rather than through `EnvelopeBuilder`, which is the only place
        # that derives these from the ledger; this report is about the OD-2 outcome rule.
        hit_count_per_rung=(0, 0),
        scan_scope=scan,
        not_tried=not_tried,
        budget_caps_hit=caps,
        sufficiency=Sufficiency.INSUFFICIENT,
        counters=Counters(http_requests=2, api_calls=2, quota_units=10),
        empty_diagnosis=EmptyDiagnosis(
            status=EmptyDiagnosisStatus.COMPLETE, tried=("from",), untried_drops=(), restores=None
        ),
    )


def test_the_closed_vocabularies_match_the_governing_documents() -> None:
    assert {member.value for member in NotTriedWhy} == (
        DOCUMENTED_NOT_TRIED_VOCABULARY | ROUND_22_ADDITION
    )
    assert {member.value for member in Outcome} == DOCUMENTED_OUTCOMES


def test_not_found_is_accepted_when_nothing_applicable_was_left_untried() -> None:
    accepted = report(
        outcome=Outcome.NOT_FOUND,
        not_tried=(NotTriedEntry(rung="L5", why=NotTriedWhy.NOT_APPLICABLE),),
    )
    assert accepted.outcome is Outcome.NOT_FOUND


@pytest.mark.parametrize("why", sorted(DOCUMENTED_BLOCKING_REASONS))
def test_not_found_is_refused_when_a_rung_was_skipped_for_a_blocking_reason(why: str) -> None:
    with pytest.raises(ValidationError) as failure:
        report(
            outcome=Outcome.NOT_FOUND,
            not_tried=(NotTriedEntry(rung="L5", why=NotTriedWhy(why), affordance=widen()),),
        )
    assert "inconclusive" in str(failure.value)


def test_not_found_is_refused_when_any_budget_cap_fired() -> None:
    with pytest.raises(ValidationError) as failure:
        report(outcome=Outcome.NOT_FOUND, caps=(BudgetCapName.MAX_QUOTA_UNITS,))
    assert "inconclusive" in str(failure.value)


def test_the_same_evidence_is_representable_as_inconclusive() -> None:
    """The rule must not make the honest response unconstructible - only the dishonest one."""
    honest = report(
        outcome=Outcome.INCONCLUSIVE,
        not_tried=(NotTriedEntry(rung="L5", why=NotTriedWhy.BUDGET, affordance=widen()),),
        caps=(BudgetCapName.MAX_QUOTA_UNITS,),
    )
    assert honest.outcome is Outcome.INCONCLUSIVE


def test_a_blocking_not_tried_entry_must_carry_the_call_that_would_reach_it() -> None:
    with pytest.raises(ValidationError):
        NotTriedEntry(rung="L5", why=NotTriedWhy.CAP)


@given(
    whys=st.lists(st.sampled_from(sorted(DOCUMENTED_NOT_TRIED_VOCABULARY)), max_size=4),
    cap_count=st.integers(min_value=0, max_value=3),
)
def test_not_found_is_constructible_exactly_when_od2_permits_it(
    whys: list[str], cap_count: int
) -> None:
    caps = tuple(sorted(BudgetCapName)[:cap_count])
    entries = tuple(
        NotTriedEntry(
            rung=f"r{index}",
            why=NotTriedWhy(why),
            affordance=widen() if why in DOCUMENTED_BLOCKING_REASONS else None,
        )
        for index, why in enumerate(whys)
    )
    permitted = not (set(whys) & DOCUMENTED_BLOCKING_REASONS) and cap_count == 0

    if permitted:
        assert report(outcome=Outcome.NOT_FOUND, not_tried=entries, caps=caps)
    else:
        with pytest.raises(ValidationError):
            report(outcome=Outcome.NOT_FOUND, not_tried=entries, caps=caps)
    # The inconclusive form is always available, whatever happened.
    assert report(outcome=Outcome.INCONCLUSIVE, not_tried=entries, caps=caps)


def test_not_found_is_refused_while_a_message_is_withheld() -> None:
    """A withheld record is retrieved evidence; claiming nothing was found contradicts it."""
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched(["m1"], thread="t1"), rung=RungId.L1, query="from:amy")
    ledger.note_withheld(
        message_id="m1",
        cap=WithheldCap.MAX_HIT_THREADS,
        why="beyond the map cap",
        affordance=kit.thread_affordance("t1"),
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())

    with pytest.raises(ValidationError) as failure:
        builder.build(
            outcome=Outcome.NOT_FOUND,
            rungs=(RungId.L1,),
            sufficiency=Sufficiency.INSUFFICIENT,
            counters=kit.counters(),
            empty_diagnosis=kit.empty_diagnosis_complete(),
        )
    assert "withheld" in str(failure.value)


def test_not_found_is_refused_while_result_pages_remain_unfetched() -> None:
    """OD-2's "exhausted": ids on unfetched pages were never examined."""
    ledger = DispositionLedger()
    ledger.record_list_page(
        kit.fetched([], more_pages=True),
        rung=RungId.L1,
        query="from:amy launch",
        affordance=Affordance(tool=ToolName.SEARCH, args={"scan": {"max_pages": 3}}),
    )
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())

    with pytest.raises(ValidationError) as failure:
        builder.build(
            outcome=Outcome.NOT_FOUND,
            rungs=(RungId.L1,),
            sufficiency=Sufficiency.INSUFFICIENT,
            counters=kit.counters(),
            empty_diagnosis=kit.empty_diagnosis_complete(),
        )
    assert "unfetched" in str(failure.value)


def test_answered_requires_something_to_have_been_disclosed() -> None:
    ledger = DispositionLedger()
    ledger.record_list_page(kit.fetched([]), rung=RungId.L1, query="q")
    builder = EnvelopeBuilder(ledger, asked_for=kit.asked_for())
    with pytest.raises(ValidationError):
        builder.build(
            outcome=Outcome.ANSWERED,
            rungs=(RungId.L1,),
            sufficiency=Sufficiency.SUFFICIENT,
            counters=kit.counters(),
            empty_diagnosis=kit.empty_diagnosis_complete(),
        )
