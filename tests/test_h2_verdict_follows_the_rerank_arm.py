"""H2's reported verdict comes from `no-rerank`, on a fixture where `sem-off` would disagree.

**Declaring the pairing is not wiring it, and this repository has now made that mistake once.**
`arms.HYPOTHESIS_PAIRS` named `(full, no-rerank)` as H2's pair, `SPECS` carried the arm, and the
campaign ran it - while `hypotheses.evaluate` still computed every H2 clause against
`semantic_baseline_arm` and `__main__` still passed `SEM_OFF`. A test that asserted the
declaration passed throughout. So this file does not assert the declaration at all; it builds
runs on which the two candidate baselines lead to **opposite** H2 conclusions and checks which
one the reported verdict followed.

`sem-off` removes stage-A embedding *and* the cross-encoder. A verdict computed against it says
"the full semantic stack beats no semantic stack", which is H1's question wearing H2's name -
and on a corpus where the embedding helps and the reranker does not, it says `HOLDS` for a
reranker that made things worse. That is exactly the fixture below.

Corpus-independent: the runs are constructed, not retrieved. This file is about the arithmetic
that turns runs into a verdict, not about retrieval.
"""

from __future__ import annotations

from collections.abc import Mapping

from mailweave_harness.evaluation.arms import (
    FIXED_WINDOW,
    FULL,
    HYPOTHESIS_PAIRS,
    NO_RERANK,
    SEM_OFF,
    CaseRun,
)
from mailweave_harness.evaluation.hypotheses import Verdict, evaluate
from mailweave_harness.seed.metrics import Disclosure, Terminal

#: **Eight cases, because the harness refuses fewer.** EP §4.3 registers 8 F16 cases per seed
#: and `_cut_loss_clause` reports `NOT_EVALUABLE` below that - "a reranker justified or refused
#: on fewer cases than the plan asked for is justified or refused by a corpus nobody
#: registered". That guard is correct and this fixture satisfies it rather than working round
#: it, so what the test exercises is the clause's real path.
CASES = tuple(f"X-RANK-{index:02d}" for index in range(1, 9))
QUOTE = "the agreed figure is 41"
REQUIRED: Mapping[str, Mapping[str, str]] = {case: {"m-evidence": QUOTE} for case in CASES}
#: The pool every arm read. `cut_loss` is `pool_recall - recall`, so a pool that holds the
#: required message and a disclosure that does not is a loss of exactly 1.0.
POOL = frozenset({"m-evidence", "m-decoy"})


def _run(case: str, arm: str, *, disclosed: bool) -> CaseRun:
    """One arm's result on one case, differing only in whether the answer was disclosed.

    Everything else is held: the same pool, the same source for it, the same terminal. So the
    only thing that can move `cut_loss` between two arms is whether the ranking cut kept the
    required message - which is what the clause is about.
    """
    content = {"m-evidence": QUOTE} if disclosed else {"m-decoy": "unrelated"}
    return CaseRun(
        case_id=case,
        family="ranking_stress",
        arm=arm,
        terminal=Terminal.ANSWERED,
        disclosure=Disclosure(content_by_id=content),
        pool_ids=POOL,
        pool_source="constructed fixture, not a measurement",
        # RR-04. The fixture's whole claim is "the cross-encoder lost four answers its own
        # absence would have kept", and a clause may no longer be graded on a pair whose
        # factor never executed. So the arms that run the reranker say so, and `no-rerank`
        # says it ran none - both instrumented, which is the difference between a null effect
        # and an absent instrument.
        embed_calls=1,
        rerank_calls=0 if arm == NO_RERANK.name else 1,
        rerank_pairs=0 if arm == NO_RERANK.name else 12,
    )


#: How many of the eight cases each arm keeps the required message through its ranking cut.
#: `cut_loss` is the mean of `pool_recall - recall`, so an arm that keeps `k` of 8 has a cut
#: loss of `(8 - k) / 8`.
#:
#: **The disagreement, built deliberately, and it is the realistic shape.** The embedding helps
#: and the cross-encoder hurts:
#:
#:   * `full` (embedding on, reranker on) keeps 4 -> cut_loss 0.500
#:   * `sem-off` (neither) keeps 0 -> cut_loss 1.000. Candidate **below** baseline, so against
#:     the semantic arm the clause **holds**: "the full stack beats no stack" - H1's question.
#:   * `no-rerank` (embedding on, reranker off) keeps 8 -> cut_loss 0.000. Candidate **above**
#:     baseline, so against H2's own arm the clause is **falsified**: the reranker lost four
#:     answers its own absence would have kept.
#:
#: A reader who cannot tell those two apart cannot tell a reranking result from a semantic one,
#: which is the whole of why H2 needs its own arm.
KEPT_OF_EIGHT = {FULL.name: 4, NO_RERANK.name: 8, SEM_OFF.name: 0, FIXED_WINDOW.name: 4}


def _runs() -> list[CaseRun]:
    return [
        _run(case, arm, disclosed=index < kept)
        for index, case in enumerate(CASES)
        for arm, kept in KEPT_OF_EIGHT.items()
    ]


def _h2(**baselines: str | None) -> tuple[Verdict, str]:
    results = {
        one.id: one
        for one in evaluate(
            _runs(),
            required=REQUIRED,
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            **baselines,
        )
    }
    clause = next(one for one in results["H2"].clauses if one.name == "F16-cut-loss-falls")
    return clause.verdict, clause.detail


def test_the_fixture_makes_the_two_baselines_disagree() -> None:
    """Asserted first, because everything below is about which of two answers was reported and
    a fixture where both answers are the same would prove nothing."""
    against_rerank, _ = _h2(rerank_baseline_arm=NO_RERANK.name)
    against_semantic, _ = _h2(rerank_baseline_arm=SEM_OFF.name)
    assert against_rerank is not against_semantic, (
        f"both baselines returned {against_rerank}; the fixture does not discriminate"
    )


def test_h2s_verdict_follows_the_rerank_arm_and_not_the_semantic_one() -> None:
    """**The regression.** On these runs the cross-encoder lost the answer its own absence
    would have kept, so H2's `cut_loss` clause must falsify. Reading `sem-off` instead would
    report the opposite, because `sem-off` lost it too."""
    verdict, detail = _h2(rerank_baseline_arm=NO_RERANK.name)
    assert verdict is Verdict.FALSIFIED, detail
    assert _h2(rerank_baseline_arm=SEM_OFF.name)[0] is not Verdict.FALSIFIED


def test_h2_is_not_evaluable_without_its_own_arm() -> None:
    """A missing baseline is a missing answer. Substituting the semantic arm is what produced
    the defect this file exists for, so the absence is reported instead - the same rule H3 has
    always followed."""
    verdict, detail = _h2()
    assert verdict is Verdict.NOT_EVALUABLE
    # The message names H2's *own* registered baseline and what that arm holds still, so a
    # reader who arrives at this line knows which arm is missing rather than only that one is.
    # (2026-09-18: it used to read "H1's question under H2's name"; the decision-table repair
    # replaced the aside with the arm's name and its isolation, which says strictly more.)
    assert "`no-rerank`" in detail
    assert "cross-encoder removed" in detail
    assert "would answer a different question under this one's name" in detail
    results = {
        one.id: one
        for one in evaluate(
            _runs(),
            required=REQUIRED,
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
        )
    }
    assert results["H2"].verdict is Verdict.NOT_EVALUABLE
    assert all(one.verdict is Verdict.NOT_EVALUABLE for one in results["H2"].clauses)


def test_h1_and_h3_still_read_their_own_baselines() -> None:
    """The wiring change must not move the other two. H1 reads the semantic arm and H3 the
    selection arm, and `no-rerank` appearing in the call changes neither: asserted by comparing
    the clause details produced with and without H2's baseline present."""
    without = {
        one.id: [clause.detail for clause in one.clauses]
        for one in evaluate(
            _runs(),
            required=REQUIRED,
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            selection_baseline_arm=FIXED_WINDOW.name,
        )
    }
    with_h2 = {
        one.id: [clause.detail for clause in one.clauses]
        for one in evaluate(
            _runs(),
            required=REQUIRED,
            candidate_arm=FULL.name,
            semantic_baseline_arm=SEM_OFF.name,
            selection_baseline_arm=FIXED_WINDOW.name,
            rerank_baseline_arm=NO_RERANK.name,
        )
    }
    assert without["H1"] == with_h2["H1"]
    assert without["H3"] == with_h2["H3"]
    assert without["H2"] != with_h2["H2"], "H2 did not move, so it was never wired to the arm"


def test_the_command_itself_passes_h2s_arm(tmp_path: object, monkeypatch: object) -> None:
    """**The other half of the wiring, checked through the command rather than the source.**

    `evaluate` reading the right parameter is worth nothing if the caller passes the wrong arm
    into it, which is exactly the state this repository shipped for a day: the arm existed, the
    pairing was declared, and `__main__` still handed `evaluate` the semantic baseline. So the
    documented command is run - `--dry-run`, the offline pipeline `--run` uses - with
    `evaluate` replaced by a recorder, and the arguments it was actually called with are read
    off the call.
    """
    import mailweave_harness.evaluation.__main__ as cli

    seen: list[dict[str, object]] = []
    # Imported from its own module, patched on the one that calls it: `__main__` binds the name
    # at import, so patching `hypotheses.evaluate` would leave the caller on the original.
    real = evaluate

    def recorder(runs: object, **kwargs: object) -> object:
        seen.append(dict(kwargs))
        return real(runs, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "evaluate", recorder)  # type: ignore[attr-defined]
    cli._dry_run(tmp_path / "traces")  # type: ignore[operator]

    assert seen, "the dry run did not evaluate the hypotheses at all"
    called = seen[0]
    # 2026-09-18, N-8. The command used to hand `evaluate` one candidate and three hand-keyed
    # baselines, so H2's *candidate* could not be changed at all and changing the mapping
    # reached the printed table without reaching the verdict. It now hands over the mapping
    # itself, and this test reads the same fact off the same call: **both** arms of H2's pair,
    # from the authoritative source, not a slot named after the factor.
    pairs = called["pairs"]
    assert pairs is HYPOTHESIS_PAIRS, called
    assert pairs["H2"] == (FULL.name, NO_RERANK.name), called
    assert pairs["H1"] == (FULL.name, SEM_OFF.name), called
    assert pairs["H3"] == (FULL.name, FIXED_WINDOW.name), called
    # And no legacy slot survives beside it, which would let the two disagree again.
    assert "rerank_baseline_arm" not in called, called
    assert "candidate_arm" not in called, called
