"""The three questions the report exists to answer, and the fourth it refuses.

`report.py` is the only place a number turns into a sentence a reader will quote, so what is
tested here is not the arithmetic - `hypotheses.family_recall` owns that and has its own tests
- but the *claims*: that a gap inside overlapping Wilson intervals is never called a win, that
"still failing" keeps the three states apart instead of merging them into one count, and that
every comparison names the arm it was made against and the factor that arm isolates.

Runs are constructed directly rather than driven through a service. A report test that had to
stand up four arms would be testing the arms; these tests need one thing the arms cannot give
on a six-case dummy corpus, which is a family whose intervals actually separate.
"""

from __future__ import annotations

from collections.abc import Mapping

from mailweave_harness.evaluation.arms import CaseRun, Measured, Reach
from mailweave_harness.evaluation.report import differences, render, still_failing
from mailweave_harness.seed.metrics import Disclosure, Terminal

REQUIRED: Mapping[str, Mapping[str, str]] = {}


def _run(
    case_id: str,
    *,
    arm: str,
    family: str = "semantic_paraphrase",
    first: frozenset[str] = frozenset(),
    expanded: frozenset[str] | None = None,
    surfaced_only: frozenset[str] = frozenset(),
    never_named: frozenset[str] = frozenset(),
    state: Measured = Measured.MEASURED,
    declined: str | None = None,
) -> CaseRun:
    return CaseRun(
        case_id=case_id,
        family=family,
        arm=arm,
        terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id={}),
        reach=Reach(
            first_response=first,
            after_expansion=first if expanded is None else expanded,
            surfaced_only=surfaced_only,
            never_named=never_named,
        ),
        state=state,
        declined=declined,
    )


def _corpus(hits: int, total: int, *, arm: str) -> list[CaseRun]:
    """`total` cases on one arm, the first `hits` of which carried their one required message."""
    out: list[CaseRun] = []
    for index in range(total):
        case_id = f"{arm}-{index:02d}"
        got = frozenset({f"m-{index}"}) if index < hits else frozenset()
        missed = frozenset() if index < hits else frozenset({f"m-{index}"})
        out.append(_run(case_id, arm=arm, first=got, never_named=missed))
    return out


def _required_for(runs: list[CaseRun]) -> dict[str, dict[str, str]]:
    return {
        one.case_id: {f"m-{one.case_id.rsplit('-', 1)[1].lstrip('0') or '0'}": "q"} for one in runs
    }


def test_a_gap_inside_overlapping_intervals_is_reported_as_no_change() -> None:
    """Ten cases, six against five. A three-percentage-point lead is not a finding."""
    left = _corpus(6, 10, arm="candidate")
    right = _corpus(5, 10, arm="baseline")
    required = _required_for(left) | _required_for(right)
    found = differences(
        left + right, required=required, candidate_arm="candidate", baseline_arm="baseline"
    )
    assert len(found) == 1
    one = found[0]
    assert one.delta > 0, "the candidate did carry more evidence"
    assert not one.separated, "but ten cases cannot separate 0.6 from 0.5"
    assert one.verdict == "no change"


def test_a_gap_whose_intervals_separate_is_reported_as_improved() -> None:
    left = _corpus(40, 40, arm="candidate")
    right = _corpus(4, 40, arm="baseline")
    required = _required_for(left) | _required_for(right)
    found = differences(
        left + right, required=required, candidate_arm="candidate", baseline_arm="baseline"
    )
    assert found[0].separated
    assert found[0].verdict == "improved"


def test_a_separated_gap_the_other_way_is_named_a_regression_not_a_null() -> None:
    left = _corpus(4, 40, arm="candidate")
    right = _corpus(40, 40, arm="baseline")
    required = _required_for(left) | _required_for(right)
    found = differences(
        left + right, required=required, candidate_arm="candidate", baseline_arm="baseline"
    )
    assert found[0].verdict == "regressed"


def test_a_family_that_ran_on_only_one_arm_is_omitted_rather_than_scored_against_zero() -> None:
    only = _corpus(3, 3, arm="candidate")
    found = differences(
        only, required=_required_for(only), candidate_arm="candidate", baseline_arm="baseline"
    )
    assert found == ()


def test_the_three_still_failing_states_are_kept_apart() -> None:
    runs = [
        _run("a", arm="x", first=frozenset(), never_named=frozenset({"m-a"})),
        _run("b", arm="x", first=frozenset(), surfaced_only=frozenset({"m-b"})),
        _run("c", arm="x", state=Measured.FAILED, declined="budget_exhausted"),
    ]
    required = {"a": {"m-a": "q"}, "b": {"m-b": "q"}, "c": {"m-c": "q"}}
    states = {one.case_id: one.state for one in still_failing(runs, required=required, arm="x")}
    assert states == {
        "a": "never_named",
        "b": "surfaced_never_carried",
        "c": "failed",
    }


def test_a_failure_carries_the_reason_the_product_gave_not_a_generic_one() -> None:
    runs = [_run("c", arm="x", state=Measured.FAILED, declined="recency_recheck_excluded")]
    entry = still_failing(runs, required={"c": {"m-c": "q"}}, arm="x")[0]
    assert "recency_recheck_excluded" in entry.detail


def test_evidence_reached_only_by_expansion_is_not_still_failing() -> None:
    """It is a recoverability result, not a retrieval failure - and it is not a failure here."""
    runs = [
        _run(
            "a",
            arm="x",
            first=frozenset(),
            expanded=frozenset({"m-a"}),
            surfaced_only=frozenset({"m-a"}),
        )
    ]
    assert still_failing(runs, required={"a": {"m-a": "q"}}, arm="x") == ()


def test_still_failing_reads_only_the_arm_it_was_asked_about() -> None:
    runs = [
        _run("a", arm="x", never_named=frozenset({"m-a"})),
        _run("a", arm="y", first=frozenset({"m-a"})),
    ]
    required = {"a": {"m-a": "q"}}
    assert len(still_failing(runs, required=required, arm="x")) == 1
    assert still_failing(runs, required=required, arm="y") == ()


def test_the_rendered_report_names_both_arms_and_the_factor_isolated() -> None:
    left = _corpus(6, 10, arm="full")
    right = _corpus(5, 10, arm="sem-off")
    text = render(
        left + right,
        required=_required_for(left) | _required_for(right),
        candidate_arm="full",
        baseline_arm="sem-off",
        isolates="the embedding and cross-encoder backends only",
    )
    assert "full vs sem-off" in text
    assert "the embedding and cross-encoder backends only" in text
    assert "NO CHANGE" in text
    assert "IMPROVED" not in text
    assert "Wilson" in text


def test_the_rendered_report_shows_both_stages_separately() -> None:
    runs = [
        _run("a", arm="full", first=frozenset(), expanded=frozenset({"m-0"})),
        _run("a", arm="base", first=frozenset(), expanded=frozenset()),
    ]
    text = render(
        runs,
        required={"a": {"m-0": "q"}},
        candidate_arm="full",
        baseline_arm="base",
        isolates="nothing; this is a shape test",
    )
    assert "first response" in text
    assert "after expansion" in text


def test_a_report_with_nothing_comparable_says_so_rather_than_printing_an_empty_table() -> None:
    only = _corpus(2, 2, arm="full")
    text = render(
        only,
        required=_required_for(only),
        candidate_arm="full",
        baseline_arm="absent",
        isolates="nothing",
    )
    assert "nothing to compare" in text
