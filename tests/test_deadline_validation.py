"""The deadline validation's judgement, driven offline (round 28, item 5).

The measurement needs a real network - that is the whole point of it - but the rule that turns
arms into a verdict does not, and it is the part that decides whether a published constant
changes. So the rule is exercised here against constructed arms, one test per way a run can
fail to be adoptable, plus an end-to-end drive against the fake transport for the record's
shape.

**Round 28's first validation is why this file exists in this form.** That run compared two
deadlines on queries that made four Gmail requests, neither of which came near either
deadline, and reported "adoptable" - true and empty. The conditions below are the corrections:
a shipped-baseline arm that has to show the deadline matters at all, non-empty evidence before
a query counts as informative, stability across repeats, and no attribution of a refusal to a
cause the refusal did not state.

No fixture here carries real or realistic personal mail.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mailweave_harness.validation import deadline
from tests.test_mcp_surface_round24 import make_service
from tests.test_round26 import TERM, _thread_mailbox
from tests.test_round27 import multi_thread_mailbox
from tests.test_round28 import RECOMMENDATION_FIXTURE_MESSAGES, RECOMMENDATION_FIXTURE_WORDS

SAME = (("m1", "body_clean"), ("m2", "snippet"))
LESS = (("m1", "body_clean"),)


def _arm(
    label: str,
    ms: int,
    *,
    evidence: tuple[tuple[str, str], ...],
    caps: tuple[str, ...] = (),
    declined: bool = False,
    partial: bool = False,
    withheld: tuple[tuple[str, str], ...] = (),
    not_included: int = 0,
    repeat: int = 0,
    remediation: str = "the A.9a ladder ran every published step",
) -> deadline.ArmResult:
    decline = (
        deadline.Decline.of({"code": "budget_exhausted", "remediation": remediation})
        if declined
        else None
    )
    return deadline.ArmResult(
        label=label,
        deadline_ms=ms,
        repeat=repeat,
        position=0,
        decline=decline,
        evidence=evidence,
        partial=partial,
        withheld=withheld,
        not_included=not_included,
        budget_caps_hit=caps,
        http_requests=13,
        api_calls=13,
        quota_units=400,
        search_wall_ms=4200,
        expansion_wall_ms=900,
        rendered_chars=18_000,
        recommendation=None,
        recommendation_executed=None,
        recommendation_returned=(),
    )


def _three(
    label: str,
    *,
    baseline: deadline.ArmResult,
    candidate: deadline.ArmResult,
    bound: deadline.ArmResult,
) -> deadline.Comparison:
    return deadline.Comparison(arms=[baseline, candidate, bound])


def _healthy() -> deadline.Comparison:
    """The shape the rule is meant to accept: baseline visibly worse, the other two equal."""
    return _three(
        "q",
        baseline=_arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True),
        candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
        bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
    )


# --- the rule accepts only the shape it is supposed to ---------------------------------------


def test_the_candidate_is_adoptable_when_the_baseline_differs_and_the_other_two_do_not() -> None:
    verdict = deadline.judge(_healthy())
    assert verdict.adoptable
    assert verdict.informative_queries == 1
    assert verdict.differences == ()
    assert verdict.baseline_evidence and "declined" in verdict.baseline_evidence[0]


@pytest.mark.parametrize(
    ("how", "baseline"),
    (
        (
            "declines",
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True),
        ),
        (
            "hits the clock",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=SAME,
                caps=("max_server_ms",),
            ),
        ),
        ("returns less", _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=LESS)),
        (
            "comes back partial",
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=SAME, partial=True),
        ),
    ),
)
def test_each_way_the_baseline_may_show_the_deadline_matters(
    how: str, baseline: deadline.ArmResult
) -> None:
    """Requirement 7: decline, clock cap, partial, or materially less evidence. All four count,
    and the rule names which one it saw rather than only that it saw one."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=baseline,
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert verdict.adoptable, how
    assert verdict.baseline_shows_a_difference and verdict.baseline_evidence


# --- and refuses every other shape -----------------------------------------------------------


def test_a_baseline_that_behaved_identically_blocks_adoption() -> None:
    """**The defect that made round 28's first run meaningless.** If the shipped deadline
    returned the same evidence with no cap and no truncation, the run has not shown that the
    deadline matters, so it cannot have shown which larger value to take."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=SAME),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert not verdict.adoptable
    assert not verdict.baseline_shows_a_difference
    assert verdict.equivalent_evidence and verdict.informative_queries == 1


def test_empty_evidence_is_never_informative_however_equal_it_is() -> None:
    """Requirement 4. Two arms agreeing on nothing agree about nothing: an empty result is
    equally empty under any deadline, so it cannot support adopting one."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=()),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=()),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=()),
        )
    )
    assert not verdict.adoptable
    assert verdict.informative_queries == 0
    assert verdict.uninformative and "equally empty" in verdict.uninformative[0]


def test_a_depth_that_differs_is_a_difference_even_with_the_same_ids() -> None:
    shallower = (("m1", "body_clean"), ("m2", "stub"))
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(
                deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True
            ),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=shallower),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert not verdict.adoptable and not verdict.equivalent_evidence
    assert "evidence differs" in verdict.differences[0]


def test_the_candidate_hitting_the_clock_blocks_adoption_even_with_matching_evidence() -> None:
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(
                deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True
            ),
            candidate=_arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                caps=("max_server_ms",),
            ),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert not verdict.adoptable and not verdict.candidate_never_hit_the_clock


@pytest.mark.parametrize("which", ("candidate", "bound"))
def test_an_asymmetric_decline_blocks_adoption_in_either_direction(which: str) -> None:
    """Requirement 5. One of the two refusing where the other answered is a difference whatever
    else matched, and it blocks whichever way round it happened."""
    declining, answering = (
        (deadline.CANDIDATE_MS, deadline.UPPER_BOUND_MS)
        if which == "candidate"
        else (deadline.UPPER_BOUND_MS, deadline.CANDIDATE_MS)
    )
    verdict = deadline.judge(
        deadline.Comparison(
            arms=[
                _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True),
                _arm(deadline.ACCEPTANCE_LABEL, declining, evidence=(), declined=True),
                _arm(deadline.ACCEPTANCE_LABEL, answering, evidence=SAME),
            ]
        )
    )
    assert not verdict.adoptable and not verdict.no_asymmetric_decline
    assert "declined where the" in verdict.differences[0]


def test_repeats_that_disagree_block_adoption_so_one_fluctuation_cannot_choose_a_default() -> None:
    """Requirement 9. A (query, arm) pair that disagreed with itself is not averaged into a
    decision; it stops the run."""
    comparison = deadline.Comparison(
        arms=[
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=0,
            ),
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=1,
            ),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=LESS, repeat=1),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert not verdict.adoptable and not verdict.stable
    assert any("repeats disagree" in difference for difference in verdict.differences)


# --- what a refusal is allowed to be blamed on -----------------------------------------------


def test_two_declines_are_uninformative_and_no_cause_is_attributed_to_them() -> None:
    """Requirement 5's second half. Round 28's first run asserted that a pair of refusals were
    R-MCP-033's width limit. That was a guess. The rule now records the code, the remediation
    and the cap names the remediation itself contains, and attributes nothing."""
    verdict = deadline.judge(
        _three(
            "wide",
            baseline=_arm("wide", deadline.BASELINE_MS, evidence=(), declined=True),
            candidate=_arm("wide", deadline.CANDIDATE_MS, evidence=(), declined=True),
            bound=_arm("wide", deadline.UPPER_BOUND_MS, evidence=(), declined=True),
        )
    )
    assert verdict.differences == ()
    note = verdict.uninformative[0]
    assert "cause not attributed here" in note
    assert "R-MCP-033" not in note and "width" not in note
    assert not verdict.adoptable  # nothing exercised the clock


def test_a_refusal_records_the_cap_names_its_own_remediation_mentions() -> None:
    """The only classification allowed: which published cap names appear in the text Gmail's
    caller was actually shown. Read off the string, not inferred from the situation."""
    said = deadline.Decline.of(
        {
            "code": "budget_exhausted",
            "remediation": "max_server_ms: 2000 of 2000; ask for a narrower slice",
            "retry_with": {"tool": "mailweave_search", "args": {"query": "q"}},
        }
    )
    assert said.caps_named_in_remediation == ("max_server_ms",)
    assert said.retry_with is not None
    quiet = deadline.Decline.of({"code": "budget_exhausted", "remediation": "no cap named here"})
    assert quiet.caps_named_in_remediation == ()


# --- the mechanics ---------------------------------------------------------------------------


def test_no_arm_ever_sits_in_the_same_position_and_every_arm_takes_every_place() -> None:
    """Requirement 2. Whichever arm runs last meets the warmest connection, so no arm may
    consistently run last."""
    for query_index in range(4):
        positions = [
            deadline.running_order(repeat, query_index).index(deadline.CANDIDATE_MS)
            for repeat in range(3)
        ]
        assert sorted(positions) == [0, 1, 2], query_index
    for repeat in range(3):
        orders = {deadline.running_order(repeat, q) for q in range(3)}
        assert len(orders) == 3, repeat


def test_the_pre_registered_queries_are_the_acceptance_call_its_predecessor_and_a_control() -> None:
    """Requirement 8, pinned so they cannot be swapped for ones that behaved better.

    Round 30 re-registered these, and the assertion is written to make the re-registration
    visible rather than to wave it through: the acceptance call at the width it failed at, the
    width-3 query runs 1 and 2 used so the records stay comparable, and a structurally narrower
    control at the published width. The arms are deliberately not re-registered.
    """
    assert [spec.label for spec in deadline.PRE_REGISTERED] == [
        "after:2026/09/01 [hit_threads=1]",
        "after:2026/09/01 [hit_threads=3]",
        "after:2026/09/08 [hit_threads=1]",
    ]
    acceptance = deadline.PRE_REGISTERED[0]
    assert acceptance.label == deadline.ACCEPTANCE_LABEL, "the rule names this query by label"
    assert acceptance.budget(7_700) == {"max_server_ms": 7_700, "max_hit_threads": 1}
    control = deadline.PRE_REGISTERED[2]
    # R-V30-007: the control carries the acceptance width so breadth is the only difference.
    assert control.max_hit_threads == acceptance.max_hit_threads
    assert control.query != acceptance.query
    assert deadline.ARMS == (2_000, 7_700, 12_300), "the arms are not re-registered"
    assert deadline.QuerySpec("plain").budget(2_000) == {"max_server_ms": 2_000}


def test_the_baseline_arm_is_the_figure_that_shipped_when_the_runs_were_taken() -> None:
    """`BASELINE_MS` read `MAX_SERVER_MS` until the owner adopted 7,700 on 2026-09-09.

    It was right while the shipped value was the thing under test, and wrong the moment the
    candidate became the shipped value: `ARMS` would have collapsed to `(7,700, 7,700, 12,300)`,
    which is a counterbalanced order over a duplicate rather than a comparison. Pinned to the
    figure runs 1, 2 and 3 were actually taken against, so every record already written keeps
    meaning what it said, and asserted here so a future re-registration is deliberate.
    """
    from mailweave.constants import MAX_SERVER_MS

    assert deadline.BASELINE_MS == 2_000
    assert deadline.ARMS == (2_000, 7_700, 12_300)
    assert MAX_SERVER_MS == 7_700, "the shipped default is no longer the baseline arm"
    assert deadline.BASELINE_MS != MAX_SERVER_MS


def test_the_harness_records_every_quantity_and_keeps_the_two_clocks_apart(tmp_path: Any) -> None:
    """Requirement 3, end to end against the fake transport: shape of the record, not values."""
    # Eleven messages, not twelve, since round 29: the arm must carry a recommendation, and
    # the twelve-message thread now sits past the cap edge at A.9a step 3 (see
    # `RECOMMENDATION_FIXTURE_MESSAGES` in `test_round28.py` for the measurement).
    comparison = deadline.compare(
        make_service(
            _thread_mailbox(
                messages=RECOMMENDATION_FIXTURE_MESSAGES, words=RECOMMENDATION_FIXTURE_WORDS
            )
        ),
        specs=[deadline.QuerySpec(TERM)],
        repeats=1,
    )
    verdict = deadline.judge(comparison)
    written = deadline.write_record(comparison, verdict, tmp_path, name="run.json")
    record = json.loads(written.read_text())
    assert record["schema"] == 2
    assert record["arms_ms"] == {
        "baseline_shipped": deadline.BASELINE_MS,
        "candidate": 7_700,
        "upper_bound": 12_300,
    }
    assert len(record["arms"]) == 3
    for arm in record["arms"]:
        for key in (
            "evidence",
            "budget_caps_hit",
            "partial",
            "withheld",
            "http_requests",
            "search_wall_ms",
            "expansion_wall_ms",
            "rendered_chars",
            "recommendation",
            "recommendation_executed",
            "position",
            "repeat",
            "decline",
        ):
            assert key in arm, key
        assert arm["search_wall_ms"] != arm["expansion_wall_ms"]
    served = [arm for arm in comparison.arms if not arm.declined]
    assert served and all(arm.recommendation is not None for arm in served)
    assert all(arm.recommendation_executed for arm in served)
    assert all(arm.expansion_wall_ms is not None for arm in served)
    assert deadline.render(comparison, verdict)


def test_a_multi_thread_search_is_recorded_with_its_endpoint_counts() -> None:
    comparison = deadline.compare(
        make_service(multi_thread_mailbox(threads=4)),
        specs=[deadline.QuerySpec(TERM)],
        repeats=1,
        execute_recommendation=False,
    )
    for arm in comparison.arms:
        if arm.declined:
            assert arm.decline is not None and arm.decline.remediation
            continue
        assert arm.http_requests > 0 and arm.api_calls > 0 and arm.rendered_chars > 0
        assert arm.expansion_wall_ms is None


# --- the three gaps found before Run 2 --------------------------------------------------------
#
# All three were the same shape as the defect this file already documents: a check that passes
# without exercising what it is about. Stability compared two fields out of six; adoption read
# observation [0] and took the rest on trust; "less evidence" compared sets of `(id, depth)`
# with a strict subset, which cannot see a message that came back shallower.


@pytest.mark.parametrize(
    ("field", "wobbly"),
    (
        (
            "partial",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                partial=True,
                repeat=1,
            ),
        ),
        (
            "withheld",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                withheld=(("m9", "cap"),),
                repeat=1,
            ),
        ),
        (
            "not_included",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                not_included=2,
                repeat=1,
            ),
        ),
        (
            "budget_caps_hit",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                caps=("max_hit_threads",),
                repeat=1,
            ),
        ),
    ),
)
def test_stability_covers_the_whole_result_state_and_not_only_evidence(
    field: str, wobbly: deadline.ArmResult
) -> None:
    """Gap 1. Two repeats that returned the same matched rows have not agreed with themselves
    if one of them was partial, withheld more, dropped more sources, or hit a different cap:
    the caller was told a different thing about what it did not get. The rule names the field
    it saw move rather than only reporting that something did."""
    comparison = deadline.Comparison(
        arms=[
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=0,
            ),
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=1,
            ),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            wobbly,
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert not verdict.adoptable and not verdict.stable
    assert any(field in difference for difference in verdict.differences), verdict.differences


def test_a_candidate_that_hit_the_clock_on_a_later_repeat_blocks_adoption() -> None:
    """Gap 1, third clause. The old rule read `runs[CANDIDATE_MS][0]`, so a wall reached on the
    second repetition was invisible to the clock condition. Stability catches this too - that
    is not the point; the point is that the clock condition itself must report it, because a
    condition that depends on another condition having held is not a check."""
    comparison = deadline.Comparison(
        arms=[
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=repeat,
            )
            for repeat in (0, 1)
        ]
        + [
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                caps=("max_server_ms",),
                repeat=1,
            ),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert not verdict.adoptable
    assert not verdict.candidate_never_hit_the_clock
    assert any("repeat 1" in difference for difference in verdict.differences)


def test_an_asymmetric_decline_on_a_later_repeat_blocks_adoption() -> None:
    """Gap 1. Same reason, different condition: the decline symmetry check must look at every
    repetition, and must set its own flag when it finds one."""
    comparison = deadline.Comparison(
        arms=[
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.BASELINE_MS,
                evidence=(),
                declined=True,
                repeat=repeat,
            )
            for repeat in (0, 1)
        ]
        + [
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=(),
                declined=True,
                repeat=1,
            ),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert not verdict.adoptable and not verdict.no_asymmetric_decline
    assert any("repeat 1" in difference for difference in verdict.differences)


def test_repeats_are_paired_by_their_own_index_and_not_by_arrival_order() -> None:
    """Gap 1, the mechanics of examining every repetition. The three arms are appended in a
    rotated running order, so pairing by list position would compare repeat 0's baseline with
    repeat 1's bound. Judged correctly, this run is adoptable in both repeats."""
    comparison = deadline.Comparison(
        arms=[
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=LESS, repeat=1),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=LESS, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert verdict.adoptable and verdict.stable
    assert verdict.informative_queries == 1
    assert len(verdict.baseline_evidence) == 1  # one finding, not one per repeat


def test_a_baseline_that_only_sometimes_shows_the_difference_does_not_count() -> None:
    """Gap 1. If the baseline matched the bound on one repetition and fell short on another,
    the run has not demonstrated that the deadline matters - it has demonstrated a fluctuation.
    (Which is also an instability, and both are reported.)"""
    comparison = deadline.Comparison(
        arms=[
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=LESS, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=SAME, repeat=1),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, repeat=1),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=0),
            _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, repeat=1),
        ]
    )
    verdict = deadline.judge(comparison)
    assert not verdict.adoptable and not verdict.baseline_shows_a_difference
    assert verdict.informative_queries == 1  # candidate and bound did agree, every time


@pytest.mark.parametrize(
    ("field", "candidate"),
    (
        (
            "partial",
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, partial=True),
        ),
        (
            "withheld",
            _arm(
                deadline.ACCEPTANCE_LABEL,
                deadline.CANDIDATE_MS,
                evidence=SAME,
                withheld=(("m9", "max_body_bytes"),),
            ),
        ),
        (
            "not_included",
            _arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME, not_included=1),
        ),
    ),
)
def test_the_same_matched_rows_are_not_equivalence_if_the_result_is_less_complete(
    field: str, candidate: deadline.ArmResult
) -> None:
    """Gap 2. Requirement 4 asked for identical matched evidence; identical matched rows are
    not the same claim as an identical result. A candidate that returns the same rows but
    reports the result as partial, withholds a record the bound did not, or leaves a source out
    is telling the caller it got less, and that blocks adoption."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(
                deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True
            ),
            candidate=candidate,
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert not verdict.adoptable, field
    assert not verdict.equivalent_evidence
    assert verdict.informative_queries == 0
    assert any("different result" in difference for difference in verdict.differences)


def test_the_bound_reporting_less_completeness_blocks_it_the_other_way_round_too() -> None:
    """The completeness comparison is symmetric: it is an equality, not a direction."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(
                deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(), declined=True
            ),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
            bound=_arm(
                deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME, not_included=3
            ),
        )
    )
    assert not verdict.adoptable and not verdict.equivalent_evidence


# --- gap 3: "less evidence" has to count depth ------------------------------------------------

SHALLOW = (("m1", "stub"), ("m2", "snippet"))
DEEPER = (("m1", "body_full"), ("m2", "snippet"))


def test_the_same_message_arriving_shallower_under_the_baseline_is_less_evidence() -> None:
    """Gap 3, the case the old rule could not see. `("m1", "stub")` and `("m1", "body_clean")`
    are not in a subset relation in either direction, so `set(baseline) < set(bound)` was False
    and the baseline looked no worse - while in fact it returned a stub where the bound
    returned the message. Keyed on the id, this is a difference and it is named."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=SHALLOW),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert verdict.adoptable
    assert verdict.baseline_shows_a_difference
    assert "m1 as stub where the bound had body_clean" in verdict.baseline_evidence[0]


def test_a_baseline_that_returned_more_than_the_bound_is_not_less_evidence() -> None:
    """The comparison is directional on purpose: deeper is not "less". A baseline that came back
    with the same ids at a *greater* depth has not shown that raising the deadline helps, and
    must not be counted as though it had."""
    verdict = deadline.judge(
        _three(
            "q",
            baseline=_arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=DEEPER),
            candidate=_arm(deadline.ACCEPTANCE_LABEL, deadline.CANDIDATE_MS, evidence=SAME),
            bound=_arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME),
        )
    )
    assert not verdict.adoptable and not verdict.baseline_shows_a_difference


def test_materially_less_names_both_missing_ids_and_shallower_ones() -> None:
    """The unit underneath, so the two halves are visible separately."""
    bound = _arm(deadline.ACCEPTANCE_LABEL, deadline.UPPER_BOUND_MS, evidence=SAME)
    assert (
        deadline._materially_less(
            _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=SAME), bound
        )
        is None
    )
    missing = deadline._materially_less(
        _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=LESS), bound
    )
    assert missing is not None and "did not return ['m2']" in missing
    both = deadline._materially_less(
        _arm(deadline.ACCEPTANCE_LABEL, deadline.BASELINE_MS, evidence=(("m1", "stub"),)), bound
    )
    assert both is not None and "did not return ['m2']" in both and "m1 as stub" in both


def test_the_depth_ladder_the_comparison_uses_is_the_published_one() -> None:
    """The rank is read off the published `Depth` vocabulary, in disclosure order, and an
    unrecognised depth ranks below every known one so it is reported rather than accepted."""
    from mailweave.envelope.vocab import Depth

    assert tuple(depth.value for depth in Depth) == deadline._DEPTH_ORDER
    ranks = [deadline._depth_rank(depth) for depth in deadline._DEPTH_ORDER]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
    assert deadline._depth_rank("something_new") < min(ranks)


def test_adoption_requires_the_acceptance_query_itself_to_be_informative() -> None:
    """R-V30-008: `informative` is counted per label, so it bound *some* query and not this one.

    The failure it allowed is exact and was demonstrated by the reviewer: the acceptance call
    returns zero rows under all three arms in every repeat, the other two labels behave, and the
    verdict reads `adoptable: true, informative_queries: 2` while the call the whole run exists
    to settle is filed under `uninformative`. A deadline adopted on that evidence would have been
    adopted on evidence about different queries.

    Asserted on the verdict model rather than through a live run, because the defect is in the
    adoption rule and not in any measurement.
    """

    def verdict(*, informative: int, acceptance: bool) -> deadline.Verdict:
        return deadline.Verdict(
            stable=True,
            equivalent_evidence=True,
            candidate_never_hit_the_clock=True,
            no_asymmetric_decline=True,
            baseline_shows_a_difference=True,
            informative_queries=informative,
            acceptance_query_informative=acceptance,
            differences=(),
            uninformative=(),
            baseline_evidence=(),
        )

    without = verdict(informative=2, acceptance=False)
    assert not without.adoptable, "two other informative queries must not carry the adoption"
    assert without.as_record()["acceptance_query"] == deadline.ACCEPTANCE_LABEL
    assert without.as_record()["acceptance_query_informative"] is False

    with_it = verdict(informative=1, acceptance=True)
    assert with_it.adoptable, "every condition met, the acceptance query among them"

    # And the label the rule names is the one the specs actually run.
    assert deadline.ACCEPTANCE_LABEL in {spec.label for spec in deadline.PRE_REGISTERED}
