"""The clause decision tables, exercised through the real gate, planner and command.

`harness/src/mailweave_harness/evaluation/contracts.py` states, per clause, what coverage it
needs, which instruments make its observations valid, and what it expects the factor to do.
This file is the evidence that the table decides the verdict, and that it decides it the same
way when the numbers come from the product instead of from a literal.

**Hand-built `CaseRun`s alone are not enough**, which is why the six scenarios the recheck
named each reach for the thing they are about:

* `mailweave.ranking.gate.rerank_gate` for the exact-lookup prohibition (N-1). The runner's
  claim is that a correct server records zero rerank calls on F1; that claim is only worth
  making against the gate that produces the zero.
* `mailweave.disclosure.plan.plan_thread` with the shipped `QueryAwareFill` for consultation
  against admission (N-2), and for a row that was admitted and then compressed away.
* `mailweave_harness.evaluation.__main__.main(["--dry-run"])` for the five layers reaching the
  record, and for the declared-lexical baseline not invalidating its own hypothesis.

Nothing here changes product policy, the corpus, or the registered hypotheses.
"""

from __future__ import annotations

import json
from pathlib import Path

from datetime import UTC, datetime


from mailweave.disclosure.plan import QueryAwareFill, plan_thread
from mailweave.disclosure.weights import QueryFacts
from mailweave.query.analysis import analyse
from mailweave.ranking.gate import RerankProhibition, rerank_gate
from mailweave.retrieval.signals import ExactBranch, ExactSignal

from mailweave_harness.evaluation import Measured, Verdict, evaluate
from mailweave_harness.evaluation.arms import (
    FIXED_WINDOW,
    FULL,
    HYPOTHESIS_PAIRS,
    NO_RERANK,
    SEM_OFF,
    CaseRun,
    CountingSelector,
    Disclosure,
    Reach,
    Terminal,
)
from mailweave_harness.evaluation.contracts import BY_NAME, Execution, Instrument, Kind
from mailweave_harness.evaluation.hypotheses import Scoring

from mailweave.disclosure.plan import ThreadInput

from tests.test_round25 import epoch_ms, oracle_thread

SPAN = "the quoted span"
NEEDED = "m-required"


def _case(
    case: str,
    arm: str,
    *,
    family: str,
    got: bool = True,
    order: tuple[str, ...] = ("a", "b"),
    embed: int | None = 1,
    rerank: int | None = 1,
    select: int | None = 4,
    admitted: int | None = 2,
    delivered: int | None = 2,
    pool: frozenset[str] | None = frozenset({NEEDED, "m-other"}),
    semantic_arm: bool | None = True,
    backend: bool | None = True,
    cost: dict[str, int] | None = None,
) -> CaseRun:
    content = {NEEDED: SPAN} if got else {}
    return CaseRun(
        case_id=case,
        family=family,
        arm=arm,
        terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id=content),
        reach=Reach(first_response=frozenset(content)),
        order=order,
        embed_calls=embed,
        embed_texts=embed,
        rerank_calls=rerank,
        rerank_pairs=rerank,
        semantic_arm=semantic_arm,
        backend_available=backend,
        select_calls=select,
        rows_admitted=admitted,
        fill_rows_delivered=delivered,
        semantic_cost=cost,
        pool_ids=pool,
        pool_source="constructed for this test, not a measurement of retrieval",
    )


def _clause(runs: list[CaseRun], hypothesis: str, name: str):
    required = {one.case_id: {NEEDED: SPAN} for one in runs}
    results = {
        one.id: one
        for one in evaluate(runs, scoring=Scoring.coerce(None, required, None), pairs=HYPOTHESIS_PAIRS)
    }
    return next(one for one in results[hypothesis].clauses if one.name == name)


# ------------------------------------------------- the tables themselves, before any scenario


def test_every_clause_states_all_three_columns_and_its_registered_falsifier() -> None:
    """A decision table with a blank column decides nothing; the recheck's complaint was that
    one generic rule stood in for all eight. Each contract has to say its own three answers."""
    for contract in BY_NAME.values():
        assert contract.coverage.families, contract.name
        assert contract.quoted, contract.name
        assert contract.holds_when and contract.falsified_when and contract.not_evaluable_when
        # Execution and factor are one decision, not two: a clause that expects the factor to
        # run has to name which factor, and one that does not must not name one.
        if contract.execution is Execution.NOT_APPLICABLE:
            assert contract.factor is None, contract.name
        else:
            assert contract.factor is not None, contract.name


def test_the_exact_lookup_clauses_do_not_wait_for_a_prohibited_factor() -> None:
    """N-1 as a property of the table rather than of one run.

    `F1-ordering-unchanged` is about a family the product forbids the cross-encoder on, so its
    execution column has to read PROHIBITED. `F12-does-not-regress` is a control and varies no
    factor at all. Either one written REQUIRED makes H2 permanently unevaluable.
    """
    assert BY_NAME["F1-ordering-unchanged"].execution is Execution.PROHIBITED
    assert BY_NAME["F1-ordering-unchanged"].kind is Kind.INVARIANT
    assert BY_NAME["F12-does-not-regress"].execution is Execution.NOT_APPLICABLE
    # And the invariant reads the delivered order, not the seam: the falsifier is about what
    # the reader got, and no instrument on the reranker can answer that.
    assert BY_NAME["F1-ordering-unchanged"].validity == (Instrument.ORDER,)


# ------------------------------------------------------- 1. a correct exact lookup, end to end


def test_the_real_gate_prohibits_reranking_on_an_exact_hit() -> None:
    """The product's own answer, so the rest of this file is not arguing with a literal."""
    parsed = analyse(
        '"quarterly cadence" from:ana@team.example',
        now=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
    )
    gate = rerank_gate(
        parsed,
        exact=ExactSignal(
            fired=True, branch=ExactBranch.E_A, phrase_tokens=2, hit_count=3, verified_locally=True
        ),
        hit_count=3,
        thread_count=2,
        term_coverage=0.5,
    )
    assert gate.fires is False
    assert gate.prohibited_by is RerankProhibition.EXACT_SIGNAL_MATCH


def test_a_correct_exact_lookup_run_can_reach_holds_with_zero_rerank_calls() -> None:
    """N-1's first half. The gate above produces `rerank_calls == 0` on every F1 case, and the
    registered falsifier is "F1 ordering changes" - which those zeros do not prevent reading."""
    cases = [f"f1-{index:02d}" for index in range(10)]
    runs = [
        _case(case, arm, family="exact_lookup", rerank=0, order=("a", "b"))
        for case in cases
        for arm in (FULL.name, NO_RERANK.name)
    ]
    clause = _clause(runs, "H2", "F1-ordering-unchanged")
    assert clause.verdict is Verdict.HOLDS, clause.detail
    assert "cross-encoder" not in clause.detail


def test_a_reordered_exact_lookup_falsifies_even_though_the_reranker_never_ran() -> None:
    """N-1's second half, and the failure it hid: a real F1 reorder was reported as an
    isolation note because the clause was still waiting for a call the gate forbids."""
    cases = [f"f1-{index:02d}" for index in range(10)]
    runs = [
        _case(case, arm, family="exact_lookup", rerank=0, order=("a", "b"))
        for case in cases
        for arm in (FULL.name, NO_RERANK.name)
    ]
    runs[1] = _case("f1-00", NO_RERANK.name, family="exact_lookup", rerank=0, order=("b", "a"))
    clause = _clause(runs, "H2", "F1-ordering-unchanged")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail
    assert "f1-00" in clause.detail
    assert "no case floor applies" in clause.detail


# --------------------------------------------------------------------- 2. the model is missing


def test_a_semantic_arm_whose_backend_never_loaded_invalidates_rather_than_passes() -> None:
    """Layer (1), recorded rather than inferred. An arm that ran lexical because the model was
    absent produces lexical numbers; reading them as the semantic path's is the whole defect."""
    cases = [f"f4-{index:02d}" for index in range(12)]
    runs = [
        _case(case, arm, family="semantic_paraphrase", got=index < 6, backend=False, embed=0)
        for index, case in enumerate(cases)
        for arm in (FULL.name, SEM_OFF.name)
    ]
    clause = _clause(runs, "H1", "F4-recall-rises")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "did not load" in clause.detail
    assert "not a measurement of the semantic path" in clause.detail


def test_a_declared_lexical_baseline_is_not_a_blind_spot() -> None:
    """The other side of the same rule, and a trap the strict reading walked into.

    `sem-off` is built with `semantic=False`, so no counting backend is registered for it and
    its seam counts are `None` on every case *by construction*. Demanding the instrument there
    made H1's own registered baseline invalidate H1 on every real run - N-1's shape again.
    """
    cases = [f"f4-{index:02d}" for index in range(12)]
    runs = [
        _case(case, FULL.name, family="semantic_paraphrase", got=index < 10)
        for index, case in enumerate(cases)
    ] + [
        _case(
            case,
            SEM_OFF.name,
            family="semantic_paraphrase",
            got=index < 4,
            semantic_arm=False,
            backend=None,
            embed=None,
            rerank=None,
        )
        for index, case in enumerate(cases)
    ]
    clause = _clause(runs, "H1", "F4-recall-rises")
    assert clause.verdict is Verdict.HOLDS, clause.detail


def test_a_lexical_baseline_that_reports_semantic_work_is_caught() -> None:
    """...and the declaration is not taken on trust: the response's own accounting is read."""
    cases = [f"f4-{index:02d}" for index in range(12)]
    runs = [
        _case(case, FULL.name, family="semantic_paraphrase", got=index < 10)
        for index, case in enumerate(cases)
    ] + [
        _case(
            case,
            SEM_OFF.name,
            family="semantic_paraphrase",
            got=index < 4,
            semantic_arm=False,
            backend=None,
            embed=None,
            rerank=None,
            cost={"embed_texts": 12, "rerank_pairs": 0},
        )
        for index, case in enumerate(cases)
    ]
    clause = _clause(runs, "H1", "F4-recall-rises")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "declared lexical" in clause.detail
    assert "does not isolate anything" in clause.detail


# ------------------------------------------------------------ 3. a partly instrumented family


def test_one_instrumented_case_does_not_license_seven_uninstrumented_ones() -> None:
    """N-6. The superseded rule filtered to the instrumented subset and asked whether any of
    *those* ran, so a single instrumented case carried the family. Missing instrumentation
    invalidates the comparison; it does not narrow it."""
    cases = [f"f16-{index:02d}" for index in range(8)]
    runs = []
    for index, case in enumerate(cases):
        instrumented = index == 0
        runs.append(
            _case(
                case,
                FULL.name,
                family="ranking_stress",
                got=index < 4,
                embed=1 if instrumented else None,
                rerank=3 if instrumented else None,
            )
        )
        runs.append(_case(case, NO_RERANK.name, family="ranking_stress", got=index < 4, rerank=0))
    clause = _clause(runs, "H2", "F16-cut-loss-falls")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "7 of 8 case(s)" in clause.detail
    assert "partly instrumented family is not a measured one" in clause.detail


# ------------------------------------------- 4 and 5. consultation, admission, delivery, apart


def _discriminating_thread() -> ThreadInput:
    """Eight messages, one hit, and two messages the query can tell from the other five.

    `oracle_thread` deliberately cannot be used here: every one of its messages carries the
    same subject, the same address and the same snippet shape, so A11's all-or-none sweep
    removes every component and the shipped selector admits nothing on it - correctly. That
    thread is the *zero* case below; this one is the case where selection actually happens.
    """
    order = tuple(f"d-{index:03d}" for index in range(8))
    return ThreadInput(
        thread_id="t-mixed",
        rank=0,
        hit_bearing=True,
        order=order,
        positions={message_id: index for index, message_id in enumerate(order)},
        hit_ids=frozenset({"d-005"}),
        parent_of={order[i]: (order[i - 1] if i else None) for i in range(8)},
        children_of={order[i]: ((order[i + 1],) if i + 1 < 8 else ()) for i in range(8)},
        subjects=dict.fromkeys(order, "budget thread"),
        snippets={
            message_id: (
                "the rollback decision was reversed"
                if message_id in ("d-001", "d-002")
                else f"routine note {index}"
            )
            for index, message_id in enumerate(order)
        },
        internal_dates={
            message_id: epoch_ms(2026, 7, 1) + index * 3_600_000
            for index, message_id in enumerate(order)
        },
        addresses={
            message_id: (
                frozenset({"lead@team.example"})
                if message_id == "d-001"
                else frozenset({"ana@team.example"})
            )
            for message_id in order
        },
        coverage={"d-005": frozenset({"terms"})},
    )


def test_the_real_planner_consults_the_selector_even_when_it_admits_nothing() -> None:
    """N-2, from `plan_thread` rather than from an assertion about it.

    On a thread whose messages the query cannot tell apart, A11's all-or-none sweep leaves no
    component anchored and the shipped selector admits no FILL row - and the planner has still
    consulted it once. That consultation count is what the superseded rule read as "the factor
    ran". Being consulted is not selecting.
    """
    counting = CountingSelector(QueryAwareFill())
    query = QueryFacts.of(
        participants=("ana@team.example",), terms=("quarterly", "cadence"), has_date_window=False
    )
    planned = plan_thread(oracle_thread(), query=query, selector=counting)
    assert counting.select_calls == 1
    assert counting.rows_admitted == 0
    assert not planned.fill


def test_the_real_planner_admits_rows_when_the_query_separates_them() -> None:
    """The same seam where selection does happen, so the zero above is a measurement of the
    product's behaviour and not a property of a fixture that could never admit anything."""
    counting = CountingSelector(QueryAwareFill())
    query = QueryFacts.of(
        participants=(), terms=("rollback", "reversed"), has_date_window=False
    )
    planned = plan_thread(_discriminating_thread(), query=query, selector=counting)
    assert counting.select_calls == 1
    assert counting.rows_admitted == 2
    assert sorted(planned.fill) == ["d-001", "d-002"]


def test_the_two_selector_counts_move_independently_of_each_other() -> None:
    """Layer (3) is constant and layer (4) is not, which is why one cannot stand in for the
    other: two calls to the real planner, the same consultation count, different admissions."""
    query = QueryFacts.of(participants=(), terms=("rollback", "reversed"), has_date_window=False)
    admitting = CountingSelector(QueryAwareFill())
    plan_thread(_discriminating_thread(), query=query, selector=admitting)
    blind = CountingSelector(QueryAwareFill())
    plan_thread(oracle_thread(), query=query, selector=blind)
    assert admitting.select_calls == blind.select_calls == 1
    assert (admitting.rows_admitted, blind.rows_admitted) == (2, 0)


def test_a_selector_that_was_consulted_and_admitted_nothing_cannot_carry_a_comparison() -> None:
    """The verdict side of the same fact, at the registered n."""
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = [
        _case(case, arm, family="decision_reversal", got=index < 6, select=9, admitted=0, delivered=0)
        for index, case in enumerate(cases)
        for arm in (FULL.name, FIXED_WINDOW.name)
    ]
    clause = _clause(runs, "H3", "F17-reversal-holds")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "consulted 72 time(s)" in clause.detail
    assert "Being consulted is not selecting" in clause.detail


def test_rows_selected_and_then_compressed_away_still_permit_the_comparison() -> None:
    """The instruction this file exists to hold: *do not require successful delivery before
    allowing a valid comparison to reveal failure*.

    Layer (4) says the selector chose rows; layer (5) says the ladder compressed them out of
    the response. That is a result about the product, and a rule keyed on delivery would have
    turned the arm's own failure into NOT_EVALUABLE - hiding it behind an instrument gap.
    """
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = []
    for index, case in enumerate(cases):
        runs.append(
            _case(
                case,
                FULL.name,
                family="decision_reversal",
                got=index < 3,
                admitted=5,
                delivered=0,  # selected, then compressed out of the response
            )
        )
        runs.append(_case(case, FIXED_WINDOW.name, family="decision_reversal", got=index < 7))
    clause = _clause(runs, "H3", "F17-reversal-holds")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail


# ------------------------------------------------- 6. equal outcomes after genuine execution


def test_equal_recall_with_the_factor_genuinely_exercised_is_a_result_not_a_gap() -> None:
    """A null effect is the thing a campaign exists to find, and the registered falsifier for
    F17 is "recall **drops**". Equal is not a drop, and the factor having run means the equality
    is about the factor rather than about its absence."""
    cases = [f"f17-{index:02d}" for index in range(8)]
    runs = [
        _case(case, arm, family="decision_reversal", got=index < 6, admitted=3, delivered=3)
        for index, case in enumerate(cases)
        for arm in (FULL.name, FIXED_WINDOW.name)
    ]
    clause = _clause(runs, "H3", "F17-reversal-holds")
    assert clause.verdict is Verdict.HOLDS, clause.detail


def test_equal_cut_loss_after_the_reranker_ran_is_a_result_not_a_gap() -> None:
    """The same for H2, where the factor is one the product does run on this family."""
    cases = [f"f16-{index:02d}" for index in range(8)]
    runs = [
        _case(case, FULL.name, family="ranking_stress", got=index < 5, rerank=7)
        for index, case in enumerate(cases)
    ] + [
        _case(case, NO_RERANK.name, family="ranking_stress", got=index < 5, rerank=0)
        for index, case in enumerate(cases)
    ]
    clause = _clause(runs, "H2", "F16-cut-loss-falls")
    assert clause.verdict is not Verdict.NOT_EVALUABLE, clause.detail
    assert "did not exercise the factor" not in clause.detail


# ------------------------------------------------------- the canonical command, not a fixture


def test_the_dry_run_records_the_five_layers_apart(tmp_path: Path) -> None:
    """`main(["--dry-run"])`, because the layers only matter where the numbers come from."""
    from mailweave_harness.evaluation.__main__ import main

    out = tmp_path / "record.json"
    assert main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)]) == 0
    record = json.loads(out.read_text())
    rows = record["per_case"]
    assert rows
    for row in rows:
        for key in (
            "semantic_arm",
            "backend_available",
            "rerank_eligible",
            "select_calls",
            "rows_admitted",
            "fill_rows_delivered",
            "cross_check",
        ):
            assert key in row, f"{key} is missing from the per-case record"
    by_arm = {row["arm"]: row for row in rows}
    assert by_arm[FULL.name]["semantic_arm"] is True
    assert by_arm[SEM_OFF.name]["semantic_arm"] is False
    # Layer (3) is non-zero on arms the planner consulted, which is the count that says nothing.
    assert by_arm[FULL.name]["select_calls"] is not None


def test_the_dry_run_never_blames_the_registered_baseline_for_its_own_configuration(
    tmp_path: Path,
) -> None:
    """The regression guarding `test_a_declared_lexical_baseline_is_not_a_blind_spot` on the
    path that actually builds the arms. H1 is NOT_EVALUABLE on the dummy corpus - it has to be,
    the corpus is ten sentinel cases - but never *because* `sem-off` has no seam instrument."""
    from mailweave_harness.evaluation.__main__ import main

    out = tmp_path / "record.json"
    assert main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)]) == 0
    record = json.loads(out.read_text())
    h1 = next(one for one in record["hypotheses"] if one["id"] == "H1")
    for clause in h1["clauses"]:
        assert "no instrument at the semantic seam" not in clause["detail"], clause
        assert SEM_OFF.name not in clause["detail"] or "did not run" in clause["detail"]


def test_the_command_decides_every_pair_it_prints_a_table_for(tmp_path: Path) -> None:
    """The declared-versus-wired shape, one last time: the table and the verdicts come off the
    same mapping, so a pair with no registered clause is named rather than left to be read as
    evidence."""
    from mailweave_harness.evaluation.__main__ import main

    out = tmp_path / "record.json"
    assert main(["--dry-run", "--traces", str(tmp_path / "traces"), "--out", str(out)]) == 0
    record = json.loads(out.read_text())
    decided = {one["id"] for one in record["hypotheses"]}
    assert decided == set(HYPOTHESIS_PAIRS), (decided, set(HYPOTHESIS_PAIRS))


def test_a_contested_pair_of_instruments_is_not_a_verified_violation() -> None:
    """N-4. The seam says zero and the response says fifty; one of them is wrong and the runner
    does not know which. Falsifying on that would report as observed a thing two instruments
    cannot agree happened - so the case is invalidated and the disagreement is printed."""
    run = _case("f1-00", FULL.name, family="exact_lookup", embed=0, rerank=0,
                cost={"embed_texts": 50, "rerank_pairs": 0})
    assert run.cross_check()[0] is Measured.FAILED
    clause = _clause([run], "H1", "no-embedding-on-F1-F2")
    assert clause.verdict is Verdict.NOT_EVALUABLE
    assert "disagree" in clause.detail
    assert "seam total 0, wire first-response 50" in clause.detail


def test_with_no_seam_instrument_the_response_is_the_witness() -> None:
    """The other half: reading only the seam let a counter that was never attached turn a
    violation the product itself reported into a clean pass."""
    run = _case("f1-00", FULL.name, family="exact_lookup", embed=None, rerank=None,
                cost={"embed_texts": 50, "rerank_pairs": 0})
    clause = _clause([run], "H1", "no-embedding-on-F1-F2")
    assert clause.verdict is Verdict.FALSIFIED, clause.detail
    assert "no seam instrument" in clause.detail
