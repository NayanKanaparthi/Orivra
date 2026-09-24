"""The comparison, written to answer three questions and to refuse the fourth.

The questions a reader actually has are *what does this improve*, *what does it not improve*,
and *what still fails*. A table of means answers none of them, so the report below is built
around the three:

  * **Improved** - families where the candidate arm put more required evidence in hand than the
    arm it is being read against, with the arm named and the factor it isolates named with it.
  * **No change** - families where it did not. Reported as loudly as the first, because a null
    result is the finding EP §7.1 pre-registered an ablation for.
  * **Still failing** - cases where the evidence was never carried by anybody, split into the
    three states that license different conclusions: the product failed, the evidence was
    surfaced and never carried, or it was never named at all.

The fourth question - *is it better* - is not answered here and cannot be from one corpus at
one seed. Every figure carries its Wilson interval and its n, and a difference inside the
intervals is reported as no change rather than as a small win.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mailweave_harness.evaluation.arms import CaseRun, Measured
from mailweave_harness.evaluation.cases import FAMILY_LABELS
from mailweave_harness.evaluation.hypotheses import (
    FamilyRecall,
    Scoring,
    Stage,
    family_recall,
)


@dataclass(frozen=True)
class Difference:
    """One family, two arms, both stages, and whether the intervals actually separate."""

    family: str
    label: str
    candidate: FamilyRecall
    baseline: FamilyRecall
    candidate_expanded: FamilyRecall | None
    baseline_expanded: FamilyRecall | None

    @property
    def delta(self) -> float:
        return self.candidate.mean_recall - self.baseline.mean_recall

    @property
    def separated(self) -> bool:
        """Whether the strict-rate intervals are disjoint.

        A difference inside overlapping intervals is reported as no change. One corpus at one
        seed is not enough to call a small gap a win, and calling it one is how a null result
        becomes a headline.
        """
        return (
            self.candidate.interval[0] > self.baseline.interval[1]
            or self.baseline.interval[0] > self.candidate.interval[1]
        )

    @property
    def verdict(self) -> str:
        if not self.separated:
            return "no change"
        return "improved" if self.delta > 0 else "regressed"


@dataclass(frozen=True)
class StillFailing:
    """One case nobody carried, and which of the three states it is in."""

    case_id: str
    family: str
    arm: str
    state: str
    detail: str


def differences(
    runs: Sequence[CaseRun],
    *,
    required: Mapping[str, Mapping[str, str]] | None = None,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: "Scoring | None" = None,
    candidate_arm: str,
    baseline_arm: str,
) -> tuple[Difference, ...]:
    families = sorted({one.family for one in runs})
    out: list[Difference] = []
    for family in families:
        # N-7: the table and the verdict path read the same cardinality-aware scorer, so a
        # satisfied any-of case cannot be a pass in one and a shortfall in the other.
        score = Scoring.coerce(scoring, required, any_of)
        candidate = family_recall(runs, family=family, arm=candidate_arm, scoring=score)
        baseline = family_recall(runs, family=family, arm=baseline_arm, scoring=score)
        if candidate is None or baseline is None:
            continue
        out.append(
            Difference(
                family=family,
                label=FAMILY_LABELS.get(family, family),
                candidate=candidate,
                baseline=baseline,
                candidate_expanded=family_recall(
                    runs,
                    family=family,
                    arm=candidate_arm,
                    scoring=Scoring.coerce(scoring, required, any_of),
                    stage=Stage.AFTER_EXPANSION,
                ),
                baseline_expanded=family_recall(
                    runs,
                    family=family,
                    arm=baseline_arm,
                    scoring=Scoring.coerce(scoring, required, any_of),
                    stage=Stage.AFTER_EXPANSION,
                ),
            )
        )
    return tuple(out)


def still_failing(
    runs: Sequence[CaseRun],
    *,
    arm: str,
    required: Mapping[str, Mapping[str, str]] | None = None,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: Scoring | None = None,
) -> tuple[StillFailing, ...]:
    """Cases where the required evidence never reached the reader, by why.

    Three states, kept apart because they license different conclusions: the product failed
    (counts against the arm), the evidence was surfaced and never carried (counts against
    recoverability, not retrieval), or it was never named at all (counts against retrieval).
    """
    out: list[StillFailing] = []
    for run in runs:
        if run.arm != arm:
            continue
        needed = Scoring.coerce(scoring, required, any_of).needed(run.case_id)
        if not needed:
            continue
        if run.state is Measured.FAILED:
            out.append(
                StillFailing(
                    run.case_id,
                    run.family,
                    arm,
                    "failed",
                    run.declined or "the call did not complete",
                )
            )
            continue
        missing = frozenset(needed) - run.reach.after_expansion
        if not missing:
            continue
        if missing & run.reach.surfaced_only:
            out.append(
                StillFailing(
                    run.case_id,
                    run.family,
                    arm,
                    "surfaced_never_carried",
                    f"{len(missing & run.reach.surfaced_only)} required message(s) were named "
                    "and reachable and their content never arrived, even after following the "
                    "response's own calls",
                )
            )
        if missing & run.reach.never_named:
            out.append(
                StillFailing(
                    run.case_id,
                    run.family,
                    arm,
                    "never_named",
                    f"{len(missing & run.reach.never_named)} required message(s) appeared "
                    "nowhere in any response",
                )
            )
    return tuple(out)


def render(
    runs: Sequence[CaseRun],
    *,
    required: Mapping[str, Mapping[str, str]] | None = None,
    any_of: Mapping[str, Mapping[str, str]] | None = None,
    scoring: "Scoring | None" = None,
    candidate_arm: str,
    baseline_arm: str,
    isolates: str,
) -> str:
    """The three questions, in order, with the arm and the factor named at the top."""
    lines = [
        f"{candidate_arm} vs {baseline_arm}",
        f"  the comparison isolates: {isolates}",
        "",
    ]
    # The scorer reaches the comparison table too (N-7). Rendering with the default all-of
    # while the caller asked for any-of printed one cardinality and decided by another.
    found = differences(
        runs,
        scoring=Scoring.coerce(scoring, required, any_of),
        candidate_arm=candidate_arm,
        baseline_arm=baseline_arm,
    )
    if not found:
        lines.append("  no family ran on both arms, so there is nothing to compare")
    for group, title in (
        ("improved", "IMPROVED"),
        ("no change", "NO CHANGE"),
        ("regressed", "REGRESSED"),
    ):
        rows = [one for one in found if one.verdict == group]
        if not rows:
            continue
        lines.append(f"  {title}")
        for one in rows:
            lines.append(
                f"    {one.label:>4} {one.family:<28} first response "
                f"{one.candidate.mean_recall:.3f} vs {one.baseline.mean_recall:.3f} "
                f"(delta {one.delta:+.3f}, n={one.candidate.cases})"
            )
            if one.candidate_expanded is not None and one.baseline_expanded is not None:
                lines.append(
                    f"         {'':>4} {'':<28} after expansion "
                    f"{one.candidate_expanded.mean_recall:.3f} vs "
                    f"{one.baseline_expanded.mean_recall:.3f}"
                )
        lines.append("")
    failing = still_failing(
        runs, arm=candidate_arm, scoring=Scoring.coerce(scoring, required, any_of)
    )
    lines.append(f"  STILL FAILING on {candidate_arm} ({len(failing)} entr(y/ies))")
    if not failing:
        lines.append("    none: every required message reached the reader on every case")
    for entry in failing:
        lines.append(f"    {entry.state:<24} {entry.case_id:<20} {entry.detail}")
    lines += [
        "",
        "  A difference inside overlapping Wilson intervals is reported as no change. One "
        "corpus at one seed cannot call a small gap a win.",
    ]
    return "\n".join(lines)


__all__ = ["Difference", "StillFailing", "differences", "render", "still_failing"]
