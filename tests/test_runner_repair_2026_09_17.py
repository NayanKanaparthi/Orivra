"""The independent runner review's findings, each as a test that failed before the repair.

`docs/reviews/RUNNER_REVIEW_RESULT_2026-09-17.md`, RR-01 to RR-13. The reviewer's own probes
are in `docs/reviews/runner-review-2026-09-17/probes/` and each test below names the probe it
came from, so the two can be read against each other.

**Two adjudications are encoded here as much as the repairs are**, and both were the owner's
call rather than the reviewer's:

* **A sample-size floor does not go on an absolute invariant.** H1's registered falsifier is
  "embedding calls appear on F1/F2 traces" and H2's is "F1 ordering changes"
  (`ORIVRA_V1_PLAN.md:877-878`). One call is one call and one reordered exact-lookup case is
  one reordered case; a floor there would mean the runner saw the forbidden event and declined
  to report it. Floors belong on the rate comparisons - F12, F3 flatness, F16 `cut_loss`, F4,
  F11, F17 - and that is where they are.
* **Non-execution is not inferred from identical outputs.** Two arms can agree because the
  factor did nothing, which is the null effect a campaign exists to find. The runner therefore
  requires *positive* evidence from an instrument that the factor executed, and reports
  NOT_EVALUABLE when that instrument is absent - which is a third thing, distinct from both
  "it ran and changed nothing" and "it did not run".

Several tests go through `main(["--dry-run"])` or `_present`, not through `evaluate` alone.
That is the review's own lesson: the H2 wiring failure lived between the declaration and the
call, and every test of it went through the call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailweave_harness.evaluation import Measured, Verdict, evaluate
from mailweave_harness.evaluation.arms import (
    FIXED_WINDOW,
    FULL,
    HYPOTHESIS_PAIRS,
    NO_RERANK,
    SEM_OFF,
    CaseRun,
    Disclosure,
    Reach,
    Terminal,
    TraceCursor,
)
from mailweave_harness.evaluation.hypotheses import (
    control_report,
    embedding_calls,
    factor_ran,
    mean_cut_loss,
    recoverability,
)
from tests.fixtures.eval_dummy import (
    dummy_arms,
    dummy_case_file,
    dummy_manifest,
    mailbox_of,
)

# --------------------------------------------------------------------------------- fixtures

REQUIRED_ID = "m-required"
POOL = frozenset({REQUIRED_ID, "m-other"})


def _run(
    case: str,
    arm: str,
    *,
    family: str = "ranking_stress",
    disclosed: bool = True,
    order: tuple[str, ...] = ("a", "b"),
    embed: int | None = 1,
    rerank: int | None = 1,
    select: int | None = 1,
    admitted: int | None = 1,
    delivered: int | None = 1,
    pool: frozenset[str] | None = POOL,
) -> CaseRun:
    """One case run, with the five layers set apart rather than collapsed into `select`.

    `select` is layer (3), *consultation*, which `plan_thread` does for every planned thread
    whatever the ladder then decides; `admitted` is layer (4), the selector actually choosing a
    row, which is the factor acting; `delivered` is layer (5), what survived compression. The
    fixture defaults to all three positive because the tests below are about scoring, not about
    instrument gaps - the tests that *are* about gaps pass `admitted=0` or `admitted=None` and
    say so.
    """
    content = {REQUIRED_ID: "the quoted span"} if disclosed else {}
    return CaseRun(
        case_id=case,
        family=family,
        arm=arm,
        terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id=content),
        reach=Reach(first_response=frozenset(content)),
        order=order,
        embed_calls=embed,
        rerank_calls=rerank,
        select_calls=select,
        rows_admitted=admitted,
        fill_rows_delivered=delivered,
        pool_ids=pool,
        pool_source="constructed fixture, not a measurement",
    )


def _required(cases: list[str]) -> dict[str, dict[str, str]]:
    return {one: {REQUIRED_ID: "the quoted span"} for one in cases}


# ------------------------------------------------------- RR-01 the operator is the falsifier's


def test_equal_f17_recall_does_not_falsify_h3() -> None:
    """RR-01, probe `p11_unexercised_factor.py`.

    The registered falsifier is "F17 reversal recall **drops** in the query-aware arm". Equal
    recall is not a drop. It was scored with H1's "does not rise" operator, so H3 reported
    FALSIFIED on every equal result - and R-M2-098 says the two arms are wire-identical on
    this corpus, which made that the certain outcome of the first real campaign.
    """
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = [
        _run(case, arm, family="decision_reversal", disclosed=True)
        for case in cases
        for arm in (FULL.name, FIXED_WINDOW.name)
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(cases),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            selection_baseline_arm=FIXED_WINDOW.name,
        )
    }
    clause = next(one for one in results["H3"].clauses if one.name == "F17-reversal-holds")
    assert clause.verdict is Verdict.HOLDS, clause.detail


def test_f17_recall_below_the_baseline_still_falsifies() -> None:
    """The other half: "does not drop" must still catch a drop, or the repair removed the
    clause rather than fixing it."""
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = [
        _run(case, FULL.name, family="decision_reversal", disclosed=index >= 4)
        for index, case in enumerate(cases)
    ] + [
        _run(case, FIXED_WINDOW.name, family="decision_reversal", disclosed=True)
        for case in cases
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(cases),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            selection_baseline_arm=FIXED_WINDOW.name,
        )
    }
    clause = next(one for one in results["H3"].clauses if one.name == "F17-reversal-holds")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail


# ------------------------------------------- RR-02 floors, and where a floor must NOT be put


def test_one_embedding_call_on_one_f1_case_falsifies_h1() -> None:
    """RR-02 adjudicated, probe `p2_floors.py` case (b).

    **No floor.** The registered falsifier is an existence statement, and the reviewer's
    proposal to floor it would have had the runner observe the forbidden event and report
    NOT_EVALUABLE.
    """
    runs = [
        _run("f1-00", FULL.name, family="exact_lookup", embed=1, rerank=0),
        _run("f1-00", SEM_OFF.name, family="exact_lookup", embed=0, rerank=0),
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(["f1-00"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
        )
    }
    clause = next(one for one in results["H1"].clauses if one.name == "no-embedding-on-F1-F2")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail
    assert results["H1"].verdict is Verdict.FALSIFIED


def test_one_reordered_f1_case_falsifies_h2_when_the_reranker_ran() -> None:
    """RR-02 adjudicated, probe `p2_floors.py` case (a). Existence falsifier, no floor - but
    it does need the factor to have executed, which is RR-04."""
    runs = [
        _run("f1-00", FULL.name, family="exact_lookup", order=("a", "b"), rerank=3),
        _run("f1-00", NO_RERANK.name, family="exact_lookup", order=("b", "a"), rerank=0),
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(["f1-00"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            rerank_baseline_arm=NO_RERANK.name,
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F1-ordering-unchanged")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail


def test_f12_needs_the_registered_number_of_cases() -> None:
    """RR-02 demonstrated, probe `p2_floors.py` case (d). A rate comparison, so a floor."""
    runs = [
        _run("f12-00", FULL.name, family="semantic_negative_control", rerank=2),
        _run("f12-00", NO_RERANK.name, family="semantic_negative_control", rerank=0),
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(["f12-00"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            rerank_baseline_arm=NO_RERANK.name,
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F12-does-not-regress")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "F12 on full: 1 of 10" in clause.detail
    assert "EP §4.3/§4.7 register these per seed" in clause.detail


def test_two_f3_cases_cannot_decide_h3_flatness() -> None:
    """RR-02 demonstrated, probe `p2_floors.py` case (c). Two positions was the only guard."""
    runs = []
    for index, case in enumerate(("f3-00", "f3-01")):
        for arm in (FULL.name, FIXED_WINDOW.name):
            run = _run(case, arm, family="buried_evidence", disclosed=index == 0)
            runs.append(
                CaseRun(**{**run.__dict__, "position": 2 if index == 0 else 75})
            )
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(["f3-00", "f3-01"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            selection_baseline_arm=FIXED_WINDOW.name,
        )
    }
    clause = next(one for one in results["H3"].clauses if one.name == "F3-flatness-improves")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "F3 on full: 2 of 84" in clause.detail
    assert "EP §4.3/§4.7 register these per seed" in clause.detail


# ---------------------------------------------------------- RR-03 an absent instrument is not 0


def test_an_absent_counter_is_unmeasured_and_never_zero() -> None:
    """RR-03, probe `p4_counter_absent.py`.

    On a machine where the models do not load, every semantic arm is silently lexical and the
    counter is `None`. That used to be recorded as `embed_calls=0` and H1's clause read the
    zero as a measurement and reported HOLDS - the strongest verdict the runner can give,
    from an instrument that was not there.
    """
    runs = [
        _run("f1-00", FULL.name, family="exact_lookup", embed=None, rerank=None),
        _run("f1-00", SEM_OFF.name, family="exact_lookup", embed=None, rerank=None),
    ]
    assert runs[0].counter_state is Measured.UNMEASURED
    assert runs[0].embed_calls is None
    seam = embedding_calls(runs, families=("exact_lookup",), arm=FULL.name)
    assert seam.state is Measured.UNMEASURED
    assert seam.cases == 0 and seam.seen == 1
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(["f1-00"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
        )
    }
    clause = next(one for one in results["H1"].clauses if one.name == "no-embedding-on-F1-F2")
    assert clause.verdict is Verdict.NOT_EVALUABLE, clause.detail
    assert "absent instrument" in clause.detail


def test_the_two_cost_instruments_are_compared_and_a_disagreement_is_not_a_verdict() -> None:
    """RR-03's second half. The brief claimed the seam counter and the response's own
    `semantic_cost` were compared; nothing compared them and neither was recorded together."""
    run = _run("f1-00", FULL.name, family="exact_lookup", embed=0, rerank=0)
    agreeing = CaseRun(**{**run.__dict__, "semantic_cost": {"rerank_pairs": 0}})
    disagreeing = CaseRun(**{**run.__dict__, "semantic_cost": {"rerank_pairs": 40}})
    assert agreeing.cross_check()[0] is Measured.UNMEASURED
    # No `first_response_calls`, so the two instruments cannot be compared call for call - but
    # the wire's first-response count still cannot exceed the seam's run total, and 40 > 0 is
    # a contradiction no split explains. Recording that as UNMEASURED would file a verified
    # disagreement as an absent one.
    assert disagreeing.cross_check()[0] is Measured.FAILED
    assert "40" in disagreeing.cross_check()[1]
    results = {
        one.id: one
        for one in evaluate(
            [disagreeing],
            required=_required(["f1-00"]),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
        )
    }
    clause = next(one for one in results["H1"].clauses if one.name == "no-embedding-on-F1-F2")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "disagree" in clause.detail


# --------------------------------------------------- RR-04 positive evidence, not an inference


def test_a_pair_whose_factor_never_ran_is_not_evaluable() -> None:
    """RR-04, probe `p11_unexercised_factor.py`."""
    cases = [f"f16-{index:02d}" for index in range(8)]
    runs = [
        _run(case, arm, rerank=0)
        for case in cases
        for arm in (FULL.name, NO_RERANK.name)
    ]
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(cases),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            rerank_baseline_arm=NO_RERANK.name,
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F16-cut-loss-falls")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "did not exercise the factor" in clause.detail


def test_identical_outputs_with_the_factor_exercised_are_a_result_not_a_gap() -> None:
    """**The adjudication, tested.** Two arms that agree while the factor demonstrably ran is
    a null effect, and the runner must report it rather than calling it unmeasured. Inferring
    non-execution from identical outputs would throw away the finding a campaign is for."""
    cases = [f"f16-{index:02d}" for index in range(8)]
    runs = [
        _run(case, FULL.name, rerank=5)
        for case in cases
    ] + [_run(case, NO_RERANK.name, rerank=0) for case in cases]
    assert factor_ran(runs, families=("ranking_stress",), arm=FULL.name, factor="rerank") is None
    results = {
        one.id: one
        for one in evaluate(
            runs,
            required=_required(cases),
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            rerank_baseline_arm=NO_RERANK.name,
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F16-cut-loss-falls")
    assert clause.verdict is not Verdict.NOT_EVALUABLE, clause.detail


def test_an_uninstrumented_selector_is_unmeasured_rather_than_assumed_either_way() -> None:
    """RR-04 for H3. There was no selection instrument at all, and the review read the gap as
    non-execution. Neither reading is available now: with no instrument the clause says so."""
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = [
        # Layer (3) and layer (4) both absent: no instrument at the selector at all, which is
        # the state RR-04 found and read as non-execution.
        _run(case, arm, family="decision_reversal", select=None, admitted=None)
        for case in cases
        for arm in (FULL.name, FIXED_WINDOW.name)
    ]
    why = factor_ran(
        runs, families=("decision_reversal",), arm=FULL.name, factor="selection"
    )
    assert why is not None and "not instrumented" in why
    assert "identical" in why


# ------------------------------------------------------------- RR-08 a negative case, not a mean


def test_one_impossible_cut_loss_case_is_not_averaged_away() -> None:
    """RR-08, probe `p2_floors.py` P3. Seven at +1.0 and one at -1.0 averaged to +0.75 and
    reported MEASURED; the shortlist is a subset of the pool, so one negative case says the
    pool that was read is not the pool the disclosure came out of."""
    runs = [_run(f"f16-{index:02d}", FULL.name, disclosed=False) for index in range(7)]
    runs.append(
        _run("f16-07", FULL.name, disclosed=True, pool=frozenset({"m-other"}))
    )
    loss = mean_cut_loss(
        runs,
        family="ranking_stress",
        arm=FULL.name,
        required=_required([one.case_id for one in runs]),
    )
    assert loss.state is Measured.INCONCLUSIVE
    assert loss.value is None
    assert "negative cut_loss" in (loss.note or "")


# ------------------------------------------------------------------------- RR-11 the controls


def test_controls_are_excluded_from_recoverability_and_reported_on_their_own() -> None:
    """RR-11, probe `p2_floors.py` P9. Controls have an empty required set, so every term was
    zero for them while they still counted in the denominator - and nothing anywhere reported
    whether a control had been answered, which is the only question a control asks."""
    runs = [
        _run("ans-00", FULL.name, family="exact_lookup"),
        _run("ctl-00", FULL.name, family="unanswerable_control", disclosed=True),
    ]
    report = recoverability(runs, arm=FULL.name)
    assert report["cases"] == 1, report
    controls: Any = report["controls"]
    assert controls["cases"] == 1
    assert controls["answered_with_content"] == 1
    assert controls["answered_case_ids"] == ["ctl-00"]
    assert control_report([], arm=FULL.name)["controls"]["cases"] == 0


# -------------------------------------------------------------------- RR-12 scoring cardinality


def test_an_any_of_case_is_scored_any_of(tmp_path: Path) -> None:
    """RR-12, probe `p10_any_of.py`. `cases.py` validated the cardinality, `--schema`
    advertised it, `ResolvedCase.any_of` was computed, and every metric scored all-of."""
    run = _run("f4-00", FULL.name, family="semantic_paraphrase", disclosed=True)
    required = {"f4-00": {REQUIRED_ID: "the quoted span", "m-second": "another span"}}
    any_of = {"f4-00": {REQUIRED_ID: "the quoted span", "m-second": "another span"}}
    from mailweave_harness.evaluation.hypotheses import family_recall

    all_of_score = family_recall(
        [run], family="semantic_paraphrase", arm=FULL.name, required=required
    )
    any_of_score = family_recall(
        [run], family="semantic_paraphrase", arm=FULL.name, required=required, any_of=any_of
    )
    assert all_of_score is not None and any_of_score is not None
    assert all_of_score.mean_recall == pytest.approx(0.5)
    assert all_of_score.strict_rate == pytest.approx(0.0)
    assert any_of_score.mean_recall == pytest.approx(1.0)
    assert any_of_score.strict_rate == pytest.approx(1.0)


# ------------------------------------------------------- RR-09 / RR-13 isolation between runs


def test_a_reused_trace_root_does_not_feed_the_first_case_another_runs_pool(
    tmp_path: Path,
) -> None:
    """RR-13, probe `p5_trace_reuse.py`. `TraceSink` appends and the cursor started at 0."""
    from mailweave.trace.sink import TraceSink

    sink = TraceSink(tmp_path / "arm")
    sink.path.parent.mkdir(parents=True, exist_ok=True)
    sink.path.write_text('{"not": "read"}\n', encoding="utf-8")
    cursor = TraceCursor(sink)
    assert cursor.offset == sink.path.stat().st_size
    assert cursor.take() == ()


def test_a_failed_first_search_does_not_leak_its_fetches_into_the_next_case() -> None:
    """RR-09, probe `p6_failed_case_leak.py`. The exception path returned without draining."""
    from mailweave_harness.evaluation.arms import run_case
    from mailweave_harness.evaluation.observe import FetchLog

    class _Boom:
        trace_sink = None

        def search(self, _request: Any) -> Any:
            log.record("g-leaked-000")
            raise RuntimeError("raised after fetching")

    log = FetchLog()
    arm = type("_Arm", (), {})()
    arm.spec = FULL
    arm.service = _Boom()
    arm.counter = None
    arm.selector = None
    arm.cursor = None
    arm.fetch_log = log
    arm.name = FULL.name
    case = dummy_case_file(dummy_manifest()).cases[0]
    resolved = type("_R", (), {})()
    resolved.case = case
    resolved.required = {}
    resolved.distractor_ids = frozenset()
    resolved.thread_lengths = {}
    run = run_case(arm, resolved)
    assert run.state is Measured.FAILED
    assert log.take() == frozenset(), "the failed case left its fetches in the next case's pool"


# ------------------------------------------------ RR-05 / RR-06 through the command, not beside it


def test_the_command_reports_a_comparison_for_every_hypothesis_pair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """RR-05, and the review's own lesson about where to test it.

    The hand-written comparison tuple carried no `full vs no-rerank` block, so H2's verdict
    was printed with no table for its own baseline. Both the table and `evaluate`'s baselines
    are derived from `HYPOTHESIS_PAIRS` now, and this asserts it **through the command**.
    """
    from mailweave_harness.evaluation.__main__ import main

    out = tmp_path / "record.json"
    main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)])
    printed = capsys.readouterr().out
    for candidate, baseline in HYPOTHESIS_PAIRS.values():
        assert f"{candidate} vs {baseline}" in printed, (
            f"no comparison block for {candidate} vs {baseline}, which is a hypothesis pair"
        )
    record = json.loads(out.read_text(encoding="utf-8"))
    for candidate, baseline in HYPOTHESIS_PAIRS.values():
        assert f"{candidate} vs {baseline}" in record["report"]


def test_the_dry_run_and_the_campaign_build_arms_through_one_constructor() -> None:
    """RR-06. Two independent copies, and the differences between them were exactly where the
    instrument gaps were. Asserted on the source, because the live path needs a credential."""
    import inspect

    from mailweave_harness.evaluation import __main__ as cli
    from tests.fixtures import eval_dummy

    assert "build_arm(" in inspect.getsource(cli._run)
    assert "build_arm(" in inspect.getsource(eval_dummy.dummy_arms)
    assert "Arm(\n" not in inspect.getsource(cli._run)


def test_every_arm_the_dry_run_builds_carries_a_selection_instrument(tmp_path: Path) -> None:
    """RR-04/RR-06/RR-07 together, through the fixture the command uses.

    The candidate arm injects no selector - `None` is the shipped `QueryAwareFill` - so
    before the repair the arm every H3 comparison is *about* carried no selection instrument
    at all.
    """
    built = dummy_arms(
        *_dummy_inputs(), traces=tmp_path / "traces"
    )
    assert all(one.selector is not None for one in built)
    names = {one.service.watermark_path for one in built if one.service.watermark_path}
    assert len(names) == len(built), "two arms shared a watermark file"


def _dummy_inputs() -> tuple[Any, Any]:
    manifest = dummy_manifest()
    box, _report = mailbox_of(manifest)
    return manifest, box


def test_the_run_record_keeps_both_instruments_and_their_states(tmp_path: Path) -> None:
    """RR-03's record half: a campaign record that cannot be cross-checked afterwards is a
    campaign whose instrumentation has to be taken on trust."""
    from mailweave_harness.evaluation.__main__ import main

    out = tmp_path / "record.json"
    main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)])
    record = json.loads(out.read_text(encoding="utf-8"))
    row = record["per_case"][0]
    for key in (
        "embed_calls",
        "rerank_calls",
        "counter_state",
        "select_calls",
        "selection_state",
        "semantic_cost",
        "cross_check",
        "semantic_arm",
        "tokens_returned",
    ):
        assert key in row, f"{key} is missing from the per-case record"


# --------------------------------------------------- RR-10 the entry point names its own scope


def test_the_record_names_the_entry_point_and_what_it_does_not_compute(tmp_path: Path) -> None:
    """RR-10. The review's rubric graded structures that live only in gitignored benchmark
    scripts, while the command computed neither baseline the package put in scope. A record
    that cannot be read back to a named, versioned program is a number without a provenance.
    """
    from mailweave_harness.evaluation.__main__ import SCOPE, main

    out = tmp_path / "record.json"
    main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)])
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["entry_point"]["command"] == "python -m mailweave_harness.evaluation"
    assert record["entry_point"]["version"]
    scope: Any = record["scope"]
    assert scope["plan_baselines_not_implemented_here"], "the omissions have to be stated"
    assert scope["plan_metrics_not_computed_here"]
    assert "boundary.py" in scope["in_this_package_but_not_run_by_this_command"]
    # And the claim has to stay true: nothing in the command may import either module.
    import inspect

    from mailweave_harness.evaluation import __main__ as cli
    from mailweave_harness.evaluation import report

    for module in (cli, report):
        source = inspect.getsource(module)
        assert "import boundary" not in source and "import queryfree" not in source, (
            f"{module.__name__} imports a module SCOPE says this command does not run"
        )
    assert SCOPE["arms_run"]
