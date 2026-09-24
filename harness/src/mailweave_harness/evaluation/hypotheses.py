"""H1, H2 and H3, evaluated by their own falsification conditions rather than by a reader.

`ORIVRA_V1_PLAN.md` §8.2 states each hypothesis and, beside it, exactly what falsifies it. Those
conditions are the specification this module implements, clause for clause, and each verdict
quotes the one it implements so a report cannot drift from the plan:

  * **H1** - falsified if F4/F11 recall does not rise over the lexical arm, **or** embedding
    calls appear on F1/F2 traces.
  * **H2** - falsified if F16 `cut_loss` does not fall, **or** F1 ordering changes, **or** F12
    (semantic negative control) regresses.
  * **H3** - falsified if F3 position-flatness does not improve, **or** F17 reversal recall
    drops in the query-aware arm.

**Recall is reported at two stages and the clauses read the first.** `first_response` is what
one call put in the reader's hands; `after_expansion` is what following the response's own
affordances reached. A hypothesis about *retrieval* is about the first - a system that surfaces
everything and carries nothing has not retrieved it - and the second is reported beside it
because the difference is the product's recoverability and is worth a number of its own.

**Four states, never three.** `MEASURED`, `FAILED` (the product failed), `INCONCLUSIVE` (ran,
cannot be decided) and `UNMEASURED` (the instrument was absent) license different conclusions,
and a clause that collapsed any two would say more than it knows. `NOT_EVALUABLE` is a verdict
and is never rounded to `HOLDS`: a hypothesis holding on two of three clauses is not a
hypothesis that holds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from enum import StrEnum

from mailweave_harness.evaluation.arms import HYPOTHESIS_PAIRS, CaseRun, Measured
from mailweave_harness.evaluation.cases import FAMILY_LABELS as FAMILY_LABEL
from mailweave_harness.evaluation.cases import REGISTERED_N
from mailweave_harness.evaluation.contracts import (
    ClauseContract,
    Execution,
    Instrument,
    for_hypothesis,
)
from mailweave_harness.seed.metrics import evidence_recall, wilson_interval


class Verdict(StrEnum):
    HOLDS = "holds"
    FALSIFIED = "falsified"
    NOT_EVALUABLE = "not_evaluable"


class Stage(StrEnum):
    """Which measurement a figure is about."""

    FIRST_RESPONSE = "first_response"
    AFTER_EXPANSION = "after_expansion"


@dataclass(frozen=True)
class Clause:
    name: str
    quoted: str
    verdict: Verdict
    detail: str


@dataclass(frozen=True)
class HypothesisResult:
    id: str
    statement: str
    clauses: tuple[Clause, ...]

    @property
    def verdict(self) -> Verdict:
        if any(one.verdict is Verdict.FALSIFIED for one in self.clauses):
            return Verdict.FALSIFIED
        if any(one.verdict is Verdict.NOT_EVALUABLE for one in self.clauses):
            return Verdict.NOT_EVALUABLE
        return Verdict.HOLDS


@dataclass(frozen=True)
class FamilyRecall:
    """One family on one arm at one stage, with the counts that say what it rests on."""

    family: str
    arm: str
    stage: Stage
    cases: int
    mean_recall: float
    strict_rate: float
    interval: tuple[float, float]
    failed: int = 0
    inconclusive: int = 0
    surfaced_never_carried: int = 0

    def render(self) -> str:
        stuck = (
            f", {self.surfaced_never_carried} surfaced-never-carried"
            if self.surfaced_never_carried
            else ""
        )
        return (
            f"{self.mean_recall:.3f} mean / {self.strict_rate:.3f} strict over {self.cases} "
            f"case(s) [CI {self.interval[0]:.3f}-{self.interval[1]:.3f}]"
            f"{f', {self.failed} failed' if self.failed else ''}"
            f"{stuck}"
        )


@dataclass(frozen=True)
class Scoring:
    """Required evidence **and its cardinality**, in one object, for every metric and report.

    N-7. `any_of` reached `family_recall` and nothing else: `mean_cut_loss`, `position_spread`
    and the printed report all scored every case all-of, so the verdict path and the table
    disagreed and an F16 case whose any-of evidence was satisfied counted as a 0.5 cut loss.
    One object now carries both, every metric takes it, and `satisfied` is the only place that
    knows what a cardinality means.
    """

    required: Mapping[str, Mapping[str, str]]
    any_of: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def of(cls, resolved: Sequence[Any]) -> Scoring:
        """Built from resolved cases. A case that declares no cardinality is scored all-of."""
        return cls(
            required={one.case.case_id: dict(one.required) for one in resolved},
            any_of={
                one.case.case_id: dict(one.any_of)
                for one in resolved
                if getattr(one.case, "evidence_cardinality", "all_of") == "any_of"
            },
        )

    @classmethod
    def coerce(
        cls,
        scoring: Scoring | None,
        required: Mapping[str, Mapping[str, str]] | None,
        any_of: Mapping[str, Mapping[str, str]] | None,
    ) -> Scoring:
        if scoring is not None:
            return scoring
        return cls(required=required or {}, any_of=any_of or {})

    def needed(self, case_id: str) -> Mapping[str, str]:
        return self.required.get(case_id, {})

    def alternatives(self, case_id: str) -> Mapping[str, str] | None:
        found = self.any_of.get(case_id)
        return found or None

    def satisfied(self, case_id: str, got: frozenset[str]) -> tuple[float, bool]:
        """`(recall, strict)` for one case, under its declared cardinality.

        The single cardinality-aware scorer. Any-of is satisfied by one of its alternatives and
        scores 1.0; all-of scores the fraction reached and is strict only when all of it was.
        """
        alternatives = self.alternatives(case_id)
        if alternatives:
            reached = bool(got & frozenset(alternatives))
            return (1.0 if reached else 0.0, reached)
        needed = self.needed(case_id)
        if not needed:
            return (0.0, False)
        return (len(got & frozenset(needed)) / len(needed), got >= frozenset(needed))


def _reached(run: CaseRun, stage: Stage) -> frozenset[str]:
    return run.reach.first_response if stage is Stage.FIRST_RESPONSE else run.reach.after_expansion


def family_recall(
    runs: Sequence[CaseRun],
    *,
    family: str,
    arm: str,
    required: Mapping[str, Mapping[str, str]] | None = None,
    stage: Stage = Stage.FIRST_RESPONSE,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: Scoring | None = None,
) -> FamilyRecall | None:
    """Recall over one family on one arm at one stage, or `None` when no case ran.

    `None` rather than zero: "no cases of this family were run" and "every case scored zero"
    are different facts, and a clause that confused them would report a hypothesis falsified by
    an empty corpus. A **failed** run scores zero and is counted separately, because the
    product failing is a result and hiding it inside a mean is not.
    """
    score = Scoring.coerce(scoring, required, any_of)
    selected = [one for one in runs if one.family == family and one.arm == arm]
    if not selected:
        return None
    recalls: list[float] = []
    strict = 0
    failed = 0
    inconclusive = 0
    surfaced = 0
    for run in selected:
        if not score.needed(run.case_id):
            continue
        if run.state is Measured.FAILED:
            failed += 1
            recalls.append(0.0)
            continue
        got = _reached(run, stage)
        # One scorer, shared with `mean_cut_loss`, `position_spread` and the report (N-7).
        recall, is_strict = score.satisfied(run.case_id, got)
        recalls.append(recall)
        if is_strict:
            strict += 1
        elif run.reach.surfaced_only:
            surfaced += 1
            inconclusive += 1
    if not recalls:
        return None
    return FamilyRecall(
        family=family,
        arm=arm,
        stage=stage,
        cases=len(recalls),
        mean_recall=sum(recalls) / len(recalls),
        strict_rate=strict / len(recalls),
        interval=wilson_interval(strict, len(recalls)),
        failed=failed,
        inconclusive=inconclusive,
        surfaced_never_carried=surfaced,
    )


def position_spread(
    runs: Sequence[CaseRun],
    *,
    arm: str,
    required: Mapping[str, Mapping[str, str]] | None = None,
    stage: Stage = Stage.FIRST_RESPONSE,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: Scoring | None = None,
) -> float | None:
    """EP §4.4's `spread = max - min` over the seven-point recall vector on F3.

    `None` when fewer than two positions ran: a spread over one position is zero for every
    system, including the oldest-K and newest-K behaviour the sweep exists to catch.
    """
    score = Scoring.coerce(scoring, required, any_of)
    by_position: dict[int, list[float]] = {}
    for run in runs:
        if run.family != "buried_evidence" or run.arm != arm or run.position is None:
            continue
        if not score.needed(run.case_id):
            continue
        # The shared scorer here too (N-7), so a spread and a recall never disagree about
        # what one case was worth.
        recall, _ = score.satisfied(run.case_id, _reached(run, stage))
        by_position.setdefault(run.position, []).append(recall)
    if len(by_position) < 2:
        return None
    means = [sum(values) / len(values) for values in by_position.values()]
    return max(means) - min(means)


@dataclass(frozen=True)
class CutLoss:
    """`pool_recall - recall` over one family on one arm, with what it rests on."""

    value: float | None
    state: Measured
    cases: int = 0
    note: str = ""


def mean_cut_loss(
    runs: Sequence[CaseRun],
    *,
    family: str,
    arm: str,
    required: Mapping[str, Mapping[str, str]] | None = None,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: Scoring | None = None,
) -> CutLoss:
    """`pool_recall - recall`, averaged, with the state that says why it may be `None`.

    `UNMEASURED` and not zero. A run with no `pool_ids` had neither an exposed candidate set
    nor a network observation, and a cut loss of zero for it would say the ranking cut lost
    nothing when nothing was measured - which is the number a reranker would then be justified
    or refuted by.

    **A negative mean is `INCONCLUSIVE`, never a figure.** The shortlist is a subset of the
    pool, so `pool_recall >= recall` holds by construction; a negative result means the pool
    that was read is not the pool the disclosure came out of, and reporting it as a number
    would let an instrument fault decide EP §6.4's reranker rule.
    """
    score = Scoring.coerce(scoring, required, any_of)
    selected = [one for one in runs if one.family == family and one.arm == arm]
    if not selected:
        return CutLoss(None, Measured.UNMEASURED)
    losses: list[float] = []
    sources: set[str] = set()
    for run in selected:
        if not score.needed(run.case_id) or run.pool_ids is None:
            continue
        # **Both halves scored by the same cardinality rule** (N-7). The pool side used to
        # count "how many of the required ids are in the pool" while the disclosure side used
        # `evidence_recall`, and neither knew about any-of - so a satisfied any-of case
        # produced a 0.5 loss out of nothing.
        pool_recall, _ = score.satisfied(run.case_id, frozenset(run.pool_ids))
        delivered, _ = score.satisfied(run.case_id, frozenset(run.disclosure.content_by_id))
        losses.append(pool_recall - delivered)
        if run.pool_source:
            sources.add(run.pool_source)
    if not losses:
        return CutLoss(None, Measured.UNMEASURED)
    # **RR-08. A single negative case is the fault, not the mean.** The rule below tested the
    # mean only, so seven cases at +1.0 and one at -1.0 - a value the metric's own model
    # forbids, because the shortlist is a subset of the pool - averaged to +0.75 and reported
    # MEASURED. One impossible case says the pool that was read is not the pool the disclosure
    # came out of, and that is true whatever the other cases did.
    impossible = [one for one in losses if one < 0]
    if impossible:
        return CutLoss(
            None,
            Measured.INCONCLUSIVE,
            len(losses),
            f"{len(impossible)} of {len(losses)} case(s) have a negative cut_loss "
            f"(worst {min(impossible):.3f}), which the metric forbids: the disclosure carried "
            f"evidence the recorded pool does not contain. Pool read from: "
            f"{'; '.join(sorted(sources)) or 'unknown'}",
        )
    mean = sum(losses) / len(losses)
    note = "; ".join(sorted(sources))
    if mean < 0:
        return CutLoss(
            None,
            Measured.INCONCLUSIVE,
            len(losses),
            f"mean {mean:.3f} is negative, which the metric forbids: the disclosure carried "
            f"evidence the recorded pool does not contain. Pool read from: {note or 'unknown'}",
        )
    return CutLoss(mean, Measured.MEASURED, len(losses), note)


def orderings(runs: Sequence[CaseRun], *, family: str, arm: str) -> dict[str, tuple[str, ...]]:
    return {one.case_id: one.order for one in runs if one.family == family and one.arm == arm}


@dataclass(frozen=True)
class SeamCount:
    """A count from the semantic seam, with the reason it may not be a count. RR-03.

    Three states, and the third is why this type exists. `UNMEASURED` means no run carried a
    counter - the arm's backend never loaded, or the arm was built without instrumentation -
    and the previous code returned the integer 0 for that case. H1's falsifier is "embedding
    calls appear on F1/F2 traces", an existence test, and an existence test run against an
    absent instrument reports "none appeared" for every product ever written.
    """

    value: int | None
    state: Measured
    #: Cases whose seam actually carried a counter. Never the number of cases that ran.
    cases: int = 0
    #: Cases that ran at all, instrumented or not. The two are separate because "no case ran"
    #: and "cases ran with no instrument" are different NOT_EVALUABLE reasons.
    seen: int = 0
    disagreements: tuple[str, ...] = ()


def embedding_calls(runs: Sequence[CaseRun], *, families: Sequence[str], arm: str) -> SeamCount:
    selected = [one for one in runs if one.family in families and one.arm == arm]
    if not selected:
        return SeamCount(None, Measured.UNMEASURED, 0, 0)
    counted = [one for one in selected if one.counter_state is Measured.MEASURED]
    if not counted:
        return SeamCount(None, Measured.UNMEASURED, 0, len(selected))
    disagreements = tuple(
        f"{one.case_id}: {one.cost_disagreement()}"
        for one in counted
        if one.cost_disagreement() is not None
    )
    total = sum((one.embed_calls or 0) + (one.rerank_calls or 0) for one in counted)
    state = Measured.MEASURED if len(counted) == len(selected) else Measured.UNMEASURED
    return SeamCount(total, state, len(counted), len(selected), disagreements)


def _compare(
    left: FamilyRecall | None,
    right: FamilyRecall | None,
    *,
    name: str,
    quoted: str,
    what: str,
    direction: str = "rises",
) -> Clause:
    """One family, two arms, with the registered-n floor applied before any verdict.

    **A null result falsifies; too few cases does not.** Plan §8.2 makes "recall does not
    rise" a falsification and EP §7.1 calls a no-gain ablation a publishable negative result,
    so equal recall is FALSIFIED and is meant to be. What must not happen is that verdict
    being reached on a corpus smaller than the plan registered, so the floor is
    `cases.REGISTERED_N` - taken from EP §4.3/§4.7 rather than chosen, which means it cannot
    be lowered after seeing a result.
    """
    if left is None or right is None:
        absent = "candidate" if left is None else "baseline"
        return Clause(
            name,
            quoted,
            Verdict.NOT_EVALUABLE,
            f"no {what} cases ran on the {absent} arm, so the comparison has one side",
        )
    floor = REGISTERED_N.get(left.family, 0)
    detail = f"{what} first-response recall: candidate {left.render()} vs baseline {right.render()}"
    if min(left.cases, right.cases) < floor:
        return Clause(
            name,
            quoted,
            Verdict.NOT_EVALUABLE,
            f"{detail}. EP §4.3/§4.7 register {floor} {what} cases per seed and this run had "
            f"{min(left.cases, right.cases)}; a hypothesis answered by fewer cases than the "
            "plan asked for is answered by a corpus nobody registered",
        )
    # **RR-01. The operator is the registered falsifier's, not one operator for every clause.**
    # `_compare` had a single rule, `HOLDS if candidate > baseline`, which is right for H1's
    # falsifier "F4/F11 recall does not rise" and wrong for H3's "F17 reversal recall drops"
    # (`ORIVRA_V1_PLAN.md:877,879`). Equal recall is not a drop. Under the old rule F17
    # reported FALSIFIED on every equal result, and R-M2-098 says the two arms are
    # wire-identical on this corpus, so H3 would have been FALSIFIED on the first real
    # campaign with exit code 2.
    if direction == "rises":
        held = left.mean_recall > right.mean_recall
    elif direction == "not_below":
        held = left.mean_recall >= right.mean_recall
    else:  # pragma: no cover - a typo in a caller, caught at import by the tests
        raise ValueError(f"unknown comparison direction {direction!r}")
    return Clause(name, quoted, Verdict.HOLDS if held else Verdict.FALSIFIED, detail)


def factor_ran(
    runs: Sequence[CaseRun], *, families: Sequence[str], arm: str, factor: str
) -> str | None:
    """Positive evidence that `factor` executed on `arm` over the cases a clause scores.

    RR-04, and deliberately **not** the review's test. The review proposed reading an
    unexercised factor off identical wire output between two arms; two arms can agree because
    the factor did nothing, which is the null effect a hypothesis is entitled to report, and a
    rule that calls that "not executed" throws away the result the campaign is for. The only
    thing that separates a null effect from an absent one is an instrument that counted the
    factor executing, so this reads instruments and nothing else.

    Returns `None` when the factor is evidenced as having run, and otherwise the sentence a
    clause should carry as its NOT_EVALUABLE reason. Three distinct answers, never collapsed:
    no cases, no instrument, or an instrument that counted zero.
    """
    selected = [one for one in runs if one.family in families and one.arm == arm]
    if not selected:
        return f"no {'/'.join(families)} case ran on {arm}"
    if factor == "rerank":
        instrumented = [one for one in selected if one.counter_state is Measured.MEASURED]
        if not instrumented:
            return (
                f"the semantic seam was not instrumented on {arm}, so whether the "
                "cross-encoder ran on these cases is unmeasured. An uninstrumented run is not "
                "a run with zero calls"
            )
        total = sum(one.rerank_calls or 0 for one in instrumented)
        if total == 0:
            return (
                f"the cross-encoder was called 0 times on {arm} across "
                f"{len(instrumented)} instrumented case(s), so this pair did not exercise the "
                "factor it varies and no difference here is attributable to reranking"
            )
        return None
    if factor == "semantic":
        instrumented = [one for one in selected if one.counter_state is Measured.MEASURED]
        if not instrumented:
            return (
                f"the semantic seam was not instrumented on {arm}, so whether stage-A "
                "embedding ran on these cases is unmeasured"
            )
        if sum(one.embed_calls or 0 for one in instrumented) == 0:
            return (
                f"stage-A embedding was called 0 times on {arm} across "
                f"{len(instrumented)} instrumented case(s)"
            )
        return None
    if factor == "selection":
        instrumented = [one for one in selected if one.selection_state is Measured.MEASURED]
        if not instrumented:
            return (
                f"the disclosure selector was not instrumented on {arm}, so whether the "
                "selection factor executed on these cases is unmeasured. It is not inferred "
                "from the two arms' outputs being identical: a selector that agrees and a "
                "selector that never ran look the same from outside"
            )
        if sum(one.select_calls or 0 for one in instrumented) == 0:
            return (
                f"the disclosure selector decided 0 thread fills on {arm} across "
                f"{len(instrumented)} instrumented case(s)"
            )
        return None
    raise ValueError(f"unknown factor {factor!r}")  # pragma: no cover


def _floor_note(what: str, seen: int, floor: int) -> str:
    return (
        f"EP §4.3/§4.7 register {floor} {what} cases per seed and this run had {seen}; a "
        "hypothesis answered by fewer cases than the plan asked for is answered by a corpus "
        "nobody registered"
    )


def _cut_loss_clause(
    contract: ClauseContract, candidate: CutLoss, baseline: CutLoss
) -> Clause:
    """H2's F16 clause, after its table's coverage, validity and execution gates have passed.

    The pool-state and registered-n checks stay here because they are about the *metric* - a
    `cut_loss` needs a measured pool on both sides and the registered number of them - rather
    than about the factor, which `_gate` has already established.
    """
    name, quoted = contract.name, contract.quoted
    if candidate.value is None or baseline.value is None:
        detail = (
            f"cut_loss is {candidate.state.value} on the candidate arm and "
            f"{baseline.state.value} on the baseline"
        )
        extra = "; ".join(one for one in (candidate.note, baseline.note) if one)
        if candidate.state is Measured.UNMEASURED or baseline.state is Measured.UNMEASURED:
            extra = extra or (
                "`pool_ids` is the exposed candidate set where there is one and the ids "
                "observed at the network layer otherwise (EP §6.4), so attach a trace sink "
                "and a `FetchLog` - a reranker is justified by the cut_loss it removes and "
                "by nothing else"
            )
        return Clause(name, quoted, Verdict.NOT_EVALUABLE, f"{detail}. {extra}")
    floor = REGISTERED_N.get("ranking_stress", 0)
    seen = min(candidate.cases, baseline.cases)
    detail = f"F16 cut_loss: candidate {candidate.value:.3f} vs baseline {baseline.value:.3f}"
    if seen < floor:
        return Clause(
            name,
            quoted,
            Verdict.NOT_EVALUABLE,
            f"{detail}. EP §4.3 registers {floor} F16 cases per seed and this run measured a "
            f"pool on {seen}; a reranker justified or refused on fewer cases than the plan "
            "asked for is justified or refused by a corpus nobody registered",
        )
    return Clause(
        name,
        quoted,
        Verdict.HOLDS if candidate.value < baseline.value else Verdict.FALSIFIED,
        detail,
    )


#: The registered statements, verbatim from `docs/ORIVRA_V1_PLAN.md:877-879`. Unchanged by
#: this repair and not paraphrased here.
_STATEMENTS: dict[str, str] = {
    "H1": (
        "Semantic escalation recovers at least one class of evidence lexical retrieval "
        "misses, at zero cost on exact-lookup families"
    ),
    "H2": (
        "Bounded reranking improves top-of-list precision on ambiguous families without "
        "changing exact-match families"
    ),
    "H3": (
        "Query-aware disclosure selects the answering message more often than position-based "
        "selection, without dropping the reply-chain floor"
    ),
}


def _cases_of(runs: Sequence[CaseRun], *, families: Sequence[str], arm: str) -> list[CaseRun]:
    return [one for one in runs if one.family in families and one.arm == arm]


def _coverage_gap(
    contract: ClauseContract, runs: Sequence[CaseRun], *, candidate: str, baseline: str
) -> str | None:
    """Whether the registered corpus actually ran. Column one of the decision table.

    Per family, because `REGISTERED_N` is per family: an invariant over F1 and F2 needs both
    numbers, and reporting the total would let ten F1 cases stand in for a missing F2.
    """
    arms = (candidate, baseline) if contract.coverage.both_arms else (candidate,)
    short: list[str] = []
    for family in contract.coverage.families:
        floor = REGISTERED_N.get(family, 0)
        for arm in arms:
            seen = len({one.case_id for one in _cases_of(runs, families=(family,), arm=arm)})
            if seen < floor:
                short.append(f"{FAMILY_LABEL.get(family, family)} on {arm}: {seen} of {floor}")
    if not short:
        return None
    return (
        "the registered case counts did not run - "
        + "; ".join(short)
        + ". EP §4.3/§4.7 register these per seed, and a hypothesis answered by fewer cases "
        "than the plan asked for is answered by a corpus nobody registered"
    )


def _validity_gap(
    contract: ClauseContract, runs: Sequence[CaseRun], *, candidate: str, baseline: str
) -> str | None:
    """Whether the observations are worth reading. Column two.

    **Partial instrumentation invalidates the comparison** (N-6). It does not narrow it to the
    instrumented subset: `factor_ran` used to filter to instrumented runs and ask whether any
    of them ran, so one instrumented case licensed seven uninstrumented ones.
    """
    arms = (candidate, baseline) if contract.coverage.both_arms else (candidate,)
    for instrument in contract.validity:
        for arm in arms:
            scored = _cases_of(runs, families=contract.coverage.families, arm=arm)
            if not scored:
                continue
            if instrument is Instrument.BACKEND:
                if any(one.backend_available is False for one in scored):
                    return (
                        f"the semantic backend did not load on {arm}, so that arm ran lexical "
                        "and its numbers are not a measurement of the semantic path"
                    )
            elif instrument is Instrument.SEMANTIC_SEAM:
                # **An arm declared lexical has no seam to instrument.** `sem-off` is built
                # with `semantic=False`, so no counting backend is registered for it and its
                # seam counts are `None` on every case - by construction, not by oversight.
                # Requiring the instrument there made H1's own registered baseline invalidate
                # H1 on every real run: the same shape as N-1, an instrument demanded of a
                # correct configuration that cannot produce it. What the baseline owes instead
                # is that nothing contradicts the declaration, and the response's own
                # accounting is the instrument that survives on a lexical arm.
                declared_lexical = [one for one in scored if one.semantic_arm is False]
                if declared_lexical and len(declared_lexical) == len(scored):
                    contradicted = [
                        one
                        for one in scored
                        if ((one.semantic_cost or {}).get("embed_texts") or 0)
                        + ((one.semantic_cost or {}).get("rerank_pairs") or 0)
                        > 0
                    ]
                    if contradicted:
                        return (
                            f"{arm} is declared lexical, but {len(contradicted)} of "
                            f"{len(scored)} case(s) carry a semantic_cost block reporting "
                            "semantic work. The arm that is supposed to isolate the factor "
                            "ran it, so this pair does not isolate anything"
                        )
                    continue
                blind = [one for one in scored if one.counter_state is not Measured.MEASURED]
                if blind:
                    return (
                        f"{len(blind)} of {len(scored)} case(s) on {arm} carried no instrument "
                        "at the semantic seam. An absent instrument counts no calls for any "
                        "system, and a partly instrumented family is not a measured one"
                    )
                clashed = [one for one in scored if one.cross_check()[0] is Measured.FAILED]
                if clashed:
                    return (
                        f"the seam counter and the response's semantic_cost disagree on "
                        f"{len(clashed)} case(s) of {arm}: {clashed[0].cross_check()[1]}"
                    )
            elif instrument is Instrument.SELECTION_ADMITTED:
                blind = [one for one in scored if one.selection_state is not Measured.MEASURED]
                if blind:
                    return (
                        f"{len(blind)} of {len(scored)} case(s) on {arm} carried no instrument "
                        "at the disclosure selector"
                    )
            elif instrument is Instrument.POOL:
                blind = [one for one in scored if one.pool_state is not Measured.MEASURED]
                if blind:
                    return (
                        f"{len(blind)} of {len(scored)} case(s) on {arm} exposed no candidate "
                        "pool, so cut_loss is unmeasured there"
                    )
            elif instrument is Instrument.ORDER:
                blind = [one for one in scored if not one.order]
                if blind:
                    return (
                        f"{len(blind)} of {len(scored)} case(s) on {arm} delivered no row "
                        "order, so there is nothing to compare"
                    )
    return None


def _execution_gap(
    contract: ClauseContract, runs: Sequence[CaseRun], *, candidate: str
) -> str | None:
    """Whether the factor did what the clause expects of it. Column three.

    Three expectations, and the third is the one the last repair did not have. `PROHIBITED`
    means the product forbids the factor here and **zero invocations is correct**: the clause
    reads the registered falsifier as written and never waits for evidence that a forbidden
    thing happened (N-1).
    """
    if contract.execution is Execution.NOT_APPLICABLE:
        return None
    scored = _cases_of(runs, families=contract.coverage.families, arm=candidate)
    if not scored:
        return f"no {'/'.join(contract.coverage.families)} case ran on {candidate}"
    if contract.execution is Execution.PROHIBITED:
        # Nothing to wait for. If the product ran the factor anyway *that* is worth saying,
        # but it does not stop the clause: the falsifier is about the outcome, not the cause.
        return None
    if contract.factor == "rerank":
        if sum(one.rerank_calls or 0 for one in scored) == 0:
            return (
                f"the cross-encoder was called 0 times on {candidate} across {len(scored)} "
                "instrumented case(s), so this pair did not exercise the factor it varies and "
                "no difference here is attributable to reranking"
            )
        return None
    if contract.factor == "semantic":
        if sum(one.embed_calls or 0 for one in scored) == 0:
            return (
                f"stage-A embedding was called 0 times on {candidate} across {len(scored)} "
                "instrumented case(s), so the semantic path never ran on this family"
            )
        return None
    if contract.factor == "selection":
        # **Rows admitted, not consultations** (N-2). `plan_thread` consults the selector for
        # every planned thread before the ladder decides anything, so a consultation count is
        # non-zero on every case of every arm and says nothing about the factor acting.
        acted = [one for one in scored if one.selection_acted]
        if not acted:
            admitted = sum(one.rows_admitted or 0 for one in scored)
            consulted = sum(one.select_calls or 0 for one in scored)
            return (
                f"the disclosure selector was consulted {consulted} time(s) on {candidate} and "
                f"admitted {admitted} row(s) across {len(scored)} case(s). Being consulted is "
                "not selecting: no FILL row was chosen, so there is no selection here for a "
                "comparison to be about"
            )
        return None
    raise ValueError(f"unknown factor {contract.factor!r}")  # pragma: no cover


def _gate(
    contract: ClauseContract, runs: Sequence[CaseRun], *, candidate: str, baseline: str
) -> str | None:
    """Coverage, validity and execution in the order the table states them.

    **Every gap that applies is reported, not the first one** (N-4, N-6). A short corpus and a
    seam whose counter disagrees with the wire are two separate defects, and returning only the
    coverage line would let the disagreement leave no trace in the verdict text - the shape the
    recheck called filtering, one level up. They are joined in column order so the reader sees
    which column each came from.
    """
    gaps = [
        gap
        for gap in (
            _coverage_gap(contract, runs, candidate=candidate, baseline=baseline),
            _validity_gap(contract, runs, candidate=candidate, baseline=baseline),
            _execution_gap(contract, runs, candidate=candidate),
        )
        if gap is not None
    ]
    if not gaps:
        return None
    return "; and ".join(gaps)


def _invariant_clause(
    contract: ClauseContract,
    runs: Sequence[CaseRun],
    *,
    candidate: str,
    baseline: str,
    violations: Sequence[str],
    observed: int,
) -> Clause:
    """An absolute invariant, whose two branches are not symmetric (N-3).

    **FALSIFIED needs no coverage**: one verified occurrence is the event the hypothesis says
    does not happen, and a floor there would mean observing it and declining to report it.
    **HOLDS needs all of it**: "no call appeared" over one case of one family is not evidence
    about the registered corpus. So the coverage gate is consulted only on the way to a pass.
    """
    if violations:
        return Clause(
            contract.name,
            contract.quoted,
            Verdict.FALSIFIED,
            f"{len(violations)} verified occurrence(s): {', '.join(violations[:5])}. "
            "An absolute invariant falsifies where it is observed; no case floor applies",
        )
    if observed == 0:
        return Clause(
            contract.name,
            contract.quoted,
            Verdict.NOT_EVALUABLE,
            f"no {'/'.join(contract.coverage.families)} case ran on {candidate}",
        )
    gap = _gate(contract, runs, candidate=candidate, baseline=baseline)
    if gap is not None:
        return Clause(
            contract.name,
            contract.quoted,
            Verdict.NOT_EVALUABLE,
            f"no occurrence was observed, but a pass is a statement about the registered "
            f"corpus and {gap}",
        )
    return Clause(
        contract.name,
        contract.quoted,
        Verdict.HOLDS,
        f"no occurrence across {observed} validly observed case(s), over the registered "
        f"{'/'.join(contract.coverage.families)} counts",
    )


#: What each hypothesis's baseline arm is, per `arms.HYPOTHESIS_PAIRS`, and what that arm
#: holds still. Used only to say what is missing when a caller supplies no baseline: naming the
#: arm is the difference between a reader fixing the call and a reader re-reading the plan.
_REGISTERED_BASELINE: Final[Mapping[str, str]] = {
    name: pair[1] for name, pair in HYPOTHESIS_PAIRS.items()
}
_BASELINE_ISOLATES: Final[Mapping[str, str]] = {
    "H1": "stage-A embedding and the cross-encoder both removed",
    "H2": "the cross-encoder removed and stage-A embedding left running",
    "H3": "query-aware E4 fill against Baseline F's fixed +/-2 window",
}


def evaluate(
    runs: Sequence[CaseRun],
    *,
    required: Mapping[str, Mapping[str, str]] | None = None,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: Scoring | None = None,
    pairs: Mapping[str, tuple[str, str]] | None = None,
    candidate_arm: str | None = None,
    semantic_baseline_arm: str | None = None,
    selection_baseline_arm: str | None = None,
    rerank_baseline_arm: str | None = None,
) -> tuple[HypothesisResult, ...]:
    """All three hypotheses, each decided by its clauses' decision tables in `contracts.py`.

    **`pairs` is the authoritative input** (N-8). Each hypothesis's candidate *and* baseline
    come from that mapping, which is `arms.HYPOTHESIS_PAIRS` on the command path. The previous
    version took the three baselines as separate hand-keyed arguments and one candidate for all
    three, so changing H2's pair reached the printed comparison table and not the verdict - the
    declared-versus-wired shape one step smaller than the failure that started this.

    The four `*_arm` arguments remain for callers that predate `pairs`, including the review
    probes, which are other people's evidence and are not edited. When `pairs` is absent they
    are assembled into one, and the hypotheses are decided from that.

    **The registered hypotheses and falsifiers are unchanged.** Every clause's `quoted` string
    is `contracts.py`'s, which is `ORIVRA_V1_PLAN.md:877-879`'s.
    """
    score = Scoring.coerce(scoring, required, any_of)
    if pairs is None:
        legacy = candidate_arm or ""
        pairs = {
            "H1": (legacy, semantic_baseline_arm or ""),
            "H2": (legacy, rerank_baseline_arm or ""),
            "H3": (legacy, selection_baseline_arm or ""),
        }

    def recall(family: str, arm: str, stage: Stage = Stage.FIRST_RESPONSE) -> FamilyRecall | None:
        return family_recall(runs, family=family, arm=arm, scoring=score, stage=stage)

    results: list[HypothesisResult] = []
    for hypothesis, statement in _STATEMENTS.items():
        candidate, baseline = pairs.get(hypothesis, ("", ""))
        clauses: list[Clause] = []
        for contract in for_hypothesis(hypothesis):
            if not baseline and contract.coverage.both_arms:
                clauses.append(
                    Clause(
                        contract.name,
                        contract.quoted,
                        Verdict.NOT_EVALUABLE,
                        f"{hypothesis} has no baseline arm in the pairs mapping. Its "
                        f"registered baseline is `{_REGISTERED_BASELINE.get(hypothesis, '?')}` "
                        f"- {_BASELINE_ISOLATES.get(hypothesis, 'its own factor')}. Answering "
                        "it against another factor's arm would answer a different question "
                        "under this one's name",
                    )
                )
                continue
            clauses.append(
                _decide(contract, runs, candidate=candidate, baseline=baseline, score=score)
            )
        results.append(HypothesisResult(hypothesis, statement, tuple(clauses)))
    return tuple(results)


def _decide(
    contract: ClauseContract,
    runs: Sequence[CaseRun],
    *,
    candidate: str,
    baseline: str,
    score: Scoring,
) -> Clause:
    """One clause, decided by its own table."""
    if contract.name == "no-embedding-on-F1-F2":
        scored = _cases_of(runs, families=contract.coverage.families, arm=candidate)
        # **Two instruments, either of which can witness the occurrence.** The seam counter is
        # the harness's own; `semantic_cost` is the response's accounting of its first
        # response. The registered falsifier is "embedding calls appear on F1/F2 traces", and a
        # trace whose own cost block reports embedded texts has them whatever the wrapper
        # counted. Reading only the seam would let a counter that was never attached, or was
        # attached to the wrong object, turn a reported violation into a clean pass.
        violations = []
        for one in scored:
            seam = (one.embed_calls or 0) + (one.rerank_calls or 0)
            if one.counter_state is Measured.MEASURED:
                # The seam is present, so it is the instrument of record. Above zero is the
                # occurrence; at zero the case is clean *here* - and if the wire contradicts
                # it, the two disagree and neither reading is verified. That contradiction is
                # a validity failure, handled by `_validity_gap`, not a falsification:
                # falsifying on a contested instrument would assert as observed a thing two
                # instruments cannot agree happened.
                if seam > 0:
                    violations.append(f"{one.case_id}: {seam} call(s) at the seam")
                continue
            # No seam instrument on this case, so the response's own accounting is the only
            # witness there is. Reading only the seam here let a counter that was never
            # attached turn a violation the product itself reported into a clean pass.
            wire = one.semantic_cost or {}
            reported = (wire.get("embed_texts") or 0) + (wire.get("rerank_pairs") or 0)
            if reported > 0:
                violations.append(
                    f"{one.case_id}: no seam instrument, and the response's own semantic_cost "
                    f"reports {reported} embedded/reranked item(s)"
                )
        return _invariant_clause(
            contract, runs, candidate=candidate, baseline=baseline,
            violations=violations, observed=len(scored),
        )
    if contract.name == "F1-ordering-unchanged":
        left = orderings(runs, family="exact_lookup", arm=candidate)
        right = orderings(runs, family="exact_lookup", arm=baseline)
        shared = sorted(set(left) & set(right))
        moved = [one for one in shared if left[one] != right[one]]
        return _invariant_clause(
            contract, runs, candidate=candidate, baseline=baseline,
            violations=[f"{one}: order differs" for one in moved], observed=len(shared),
        )
    gap = _gate(contract, runs, candidate=candidate, baseline=baseline)
    if gap is not None:
        return Clause(contract.name, contract.quoted, Verdict.NOT_EVALUABLE, gap)
    if contract.name == "F16-cut-loss-falls":
        return _cut_loss_clause(
            contract,
            mean_cut_loss(runs, family="ranking_stress", arm=candidate, scoring=score),
            mean_cut_loss(runs, family="ranking_stress", arm=baseline, scoring=score),
        )
    if contract.name == "F3-flatness-improves":
        here = position_spread(runs, arm=candidate, scoring=score)
        there = position_spread(runs, arm=baseline, scoring=score)
        if here is None or there is None:
            return Clause(
                contract.name, contract.quoted, Verdict.NOT_EVALUABLE,
                "fewer than two sweep positions ran on both arms; a spread over one position "
                "is zero for every system including an oldest-K one",
            )
        return Clause(
            contract.name, contract.quoted,
            Verdict.HOLDS if here < there else Verdict.FALSIFIED,
            f"F3 spread: query-aware {here:.3f} vs fixed-window {there:.3f} (lower is flatter)",
        )
    family = contract.coverage.families[0]
    here_recall = family_recall(runs, family=family, arm=candidate, scoring=score)
    there_recall = family_recall(runs, family=family, arm=baseline, scoring=score)
    if here_recall is None or there_recall is None:
        return Clause(
            contract.name, contract.quoted, Verdict.NOT_EVALUABLE,
            f"no {family} case ran on both arms",
        )
    detail = (
        f"{FAMILY_LABEL.get(family, family)} first-response recall: candidate "
        f"{here_recall.render()} vs baseline {there_recall.render()}"
    )
    if contract.name == "F17-reversal-holds":
        held = here_recall.mean_recall >= there_recall.mean_recall
    elif contract.name == "F12-does-not-regress":
        held = here_recall.mean_recall >= there_recall.mean_recall
    else:
        held = here_recall.mean_recall > there_recall.mean_recall
    return Clause(
        contract.name, contract.quoted,
        Verdict.HOLDS if held else Verdict.FALSIFIED,
        detail,
    )


CONTROL_FAMILY = "unanswerable_control"


def control_report(runs: Sequence[CaseRun], *, arm: str) -> dict[str, object]:
    """What the controls did, read for leakage rather than aggregated away. RR-11.

    A control that came back with content carrying a declared answer is a corpus leak or a
    product that answers the unanswerable, and either is a finding. Before this, controls were
    folded into `recoverability`'s denominator and nothing reported whether one was answered.

    `answered` counts controls whose first response carried message content at all: with no
    required set there is nothing to recall, so content delivered against a question with no
    answer is the signal. It is reported, never graded - turning it into a verdict is a
    decision for whoever registers criteria.
    """
    controls = [one for one in runs if one.arm == arm and one.family == CONTROL_FAMILY]
    if not controls:
        return {"controls": {"cases": 0, "note": "no control case ran on this arm"}}
    answered = [one for one in controls if one.disclosure.content_by_id]
    return {
        "controls": {
            "cases": len(controls),
            "declined": sum(1 for one in controls if one.declined is not None),
            "failed": sum(1 for one in controls if one.state is Measured.FAILED),
            "answered_with_content": len(answered),
            "answered_case_ids": sorted(one.case_id for one in answered),
            "note": (
                "controls are excluded from every recoverability term above and are never "
                "aggregated with answerable cases. `answered_with_content` is reported, not "
                "graded"
            ),
        }
    }


def recoverability(runs: Sequence[CaseRun], *, arm: str) -> dict[str, object]:
    """What expansion added over the first response, reported as its own number.

    This is not a hypothesis clause. It is the quantity that separates "MailWeave surfaced the
    evidence" from "the caller got the evidence", and it belongs in every report because the
    two are routinely confused and only one of them is what a reader received.
    """
    # **RR-11. Controls are not recoverability cases and are reported separately.** An
    # `unanswerable_control` has an empty required set, so every per-case term below is zero
    # for it while it still counts in the denominator and in `mean_levels_traversed` - the dry
    # run's "cases: 11" was ten answerable plus one control. Worse, nothing anywhere read
    # whether a control had been *answered*, which is the only thing a control is for.
    answerable = [
        one
        for one in runs
        if one.arm == arm
        and one.state is not Measured.FAILED
        and one.family != CONTROL_FAMILY
    ]
    selected = answerable
    if not selected:
        return {"arm": arm, "state": Measured.UNMEASURED.value, **control_report(runs, arm=arm)}
    gained = sum(len(one.reach.expansion_gained) for one in selected)
    first = sum(len(one.reach.first_response) for one in selected)
    stuck = sum(len(one.reach.surfaced_only) for one in selected)
    unseen = sum(len(one.reach.never_named) for one in selected)
    return {
        "arm": arm,
        "cases": len(selected),
        "evidence_in_first_response": first,
        "evidence_gained_by_expansion": gained,
        "surfaced_never_carried_after_expansion": stuck,
        "never_named_at_all": unseen,
        "mean_levels_traversed": round(
            sum(one.reach.levels for one in selected) / len(selected), 2
        ),
        "failed_runs": sum(
            1
            for one in runs
            if one.arm == arm
            and one.state is Measured.FAILED
            and one.family != CONTROL_FAMILY
        ),
        **control_report(runs, arm=arm),
    }


__all__ = [
    "Clause",
    "CutLoss",
    "FamilyRecall",
    "HypothesisResult",
    "SeamCount",
    "Stage",
    "Verdict",
    "control_report",
    "embedding_calls",
    "evaluate",
    "factor_ran",
    "family_recall",
    "mean_cut_loss",
    "orderings",
    "position_spread",
    "recoverability",
]
