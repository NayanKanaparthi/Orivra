"""The M2 content gate, frozen 2026-09-16 before any generator edit.

**What this file is.** The exact evaluation the corpus repair is judged by: which solver, which
scoring rule, which population, which denominators. It is written and hashed *before* the
generator is touched, because a bar set after seeing a score is a description of the score.

**The four criteria, as approved.**

  * **C1 - shape.** Every `(length, participants, senders, distinct hours)` value maps to at
    least two families. That tuple is EP §2.4.5's Tier-1 redacted observable; requiring it to be
    ambiguous everywhere is checkable and asks for nothing about overall entropy.
  * **C2 - no family solved outright.** The frozen query-free solver scores **below 100%** on
    every family that has at least one scored thread.
  * **C3 - bounded residual.** The solver scores **at most 40%** over the whole population.
  * **C4 - the independent read returns YES.** Not computed here. It is a human judgement and
    this file does not simulate one.

**C3's 40% is a provisional engineering threshold for this repair. It is not a statistically
established validity threshold**, it has no power analysis behind it, and passing it is not
evidence that the corpus is free of shortcuts - only that this solver, on this population, under
this scoring rule, is below the line that was drawn before the work started.

**The solver is handed the correct conversation.** `queryfree.select_within_thread` receives the
thread the declared evidence is in and answers within it. The retrieval half of the problem is
done for it. A score from it is therefore an **upper bound on register leakage given perfect
retrieval**, not a lower bound on any system's difficulty.

**Two numbers that are not the same baseline.** The 24/39 the fifth independent read reported is
this population - scored threads of the generated corpus. The 6/13 the diagnostic runner prints
is `qf-1` over the *thirteen authored diagnostic cases*. Different populations, different
denominators, different selection. **They are not comparable and must never be differenced.**
This gate uses the corpus population and says so in every record it writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mailweave_harness.evaluation import queryfree
from mailweave_harness.seed import corpus
from mailweave_harness.seed.manifest import Manifest

#: Frozen together with this file. A change to either invalidates every comparison made with it.
GATE_VERSION: Final[str] = "gate-1"
SOLVER_VERSION: Final[str] = queryfree.VERSION

#: The population. **Every thread the generator built for a family and gave a declared answer**,
#: at the profile and seed named on the manifest. Not the diagnostic cases; not a sample.
#: A thread with no `family` is filler and is not scored. A family thread with an empty `answer`
#: is excluded and counted separately, because scoring "did the solver find the answer" against
#: a thread that declares none measures nothing (F8's decoy is the deliberate instance).
POPULATION: Final[str] = (
    "every ThreadTruth in the manifest with a non-empty `family` and a non-empty `answer`"
)

#: The scoring rule. One point per thread, **won only when the message the solver picks is one
#: of that thread's declared `evidence_positions`**. No partial credit, no ranking credit.
SCORING: Final[str] = (
    "1 if the picked message's position is in the thread's evidence_positions, else 0"
)

C3_CEILING: Final[float] = 0.40
C1_MIN_FAMILIES_PER_SHAPE: Final[int] = 2
C2_MAX_PER_FAMILY: Final[float] = 1.0  # strictly below


@dataclass(frozen=True)
class FamilyResult:
    family: str
    scored: int
    won: int

    @property
    def rate(self) -> float:
        return self.won / self.scored if self.scored else 0.0


def solver_fingerprint() -> dict[str, str]:
    """What was actually run, by content hash, so a later reader can tell whether it moved."""
    import mailweave_harness.evaluation.queryfree as qf

    return {
        "version": SOLVER_VERSION,
        "queryfree_py_sha256": hashlib.sha256(
            Path(qf.__file__).read_bytes()
        ).hexdigest(),
        "gate_py_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "gate_version": GATE_VERSION,
    }


def _bodies(manifest: Manifest) -> dict[str, list[Any]]:
    by_thread: dict[str, list[Any]] = defaultdict(list)
    for message in manifest.messages:
        by_thread[message.thread_key].append(message)
    for rows in by_thread.values():
        rows.sort(key=lambda one: one.position)
    return by_thread


def _epoch_ms(message: Any, fallback: int) -> int:
    """Ordering only. The solver's tie-break is recency, so the order has to be the thread's."""
    from email.utils import parsedate_to_datetime

    try:
        return int(parsedate_to_datetime(message.date_rfc2822).timestamp() * 1000)
    except (TypeError, ValueError):  # pragma: no cover - the generator always writes one
        return fallback


def run_solver(manifest: Manifest) -> tuple[tuple[FamilyResult, ...], list[dict[str, Any]]]:
    """`qf-1` over the frozen population, per family, plus one row per thread."""
    by_thread = _bodies(manifest)
    per_family: dict[str, list[int]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for truth in manifest.answer_key.threads:
        if not truth.family or not truth.answer:
            continue
        messages = by_thread.get(truth.thread_key, [])
        if not messages:
            continue
        candidates = [
            queryfree.Candidate(
                message_id=one.rfc822_message_id,
                position=one.position,
                subject=one.subject,
                body=one.body,
                epoch_ms=_epoch_ms(one, index),
            )
            for index, one in enumerate(messages)
        ]
        picked = queryfree.select_within_thread(candidates)
        at = next(
            (one.position for one in messages if one.rfc822_message_id == picked), None
        )
        won = int(at is not None and at in truth.evidence_positions)
        per_family[truth.family].append(won)
        rows.append(
            {
                "thread_key": truth.thread_key,
                "family": truth.family,
                "picked_position": at,
                "evidence_positions": list(truth.evidence_positions),
                "won": bool(won),
            }
        )
    results = tuple(
        FamilyResult(family=name, scored=len(wins), won=sum(wins))
        for name, wins in sorted(per_family.items())
    )
    return results, rows


def shape_map(manifest: Manifest) -> dict[str, Any]:
    """C1: `(length, participants, senders, distinct hours)` to the families that use it."""
    from email.utils import parsedate_to_datetime

    by_thread = _bodies(manifest)
    families_by_shape: dict[tuple[int, int, int, int], set[str]] = defaultdict(set)
    for truth in manifest.answer_key.threads:
        if not truth.family:
            continue
        messages = by_thread.get(truth.thread_key, [])
        if not messages:
            continue
        hours = set()
        for one in messages:
            try:
                hours.add(parsedate_to_datetime(one.date_rfc2822).hour)
            except (TypeError, ValueError):  # pragma: no cover
                pass
        shape = (
            truth.length,
            len(truth.participants),
            len({one.sender for one in messages}),
            len(hours),
        )
        families_by_shape[shape].add(truth.family)
    singles = {
        "|".join(str(part) for part in shape): sorted(names)
        for shape, names in sorted(families_by_shape.items())
        if len(names) < C1_MIN_FAMILIES_PER_SHAPE
    }
    return {
        "distinct_shapes": len(families_by_shape),
        "shapes_mapping_to_one_family": len(singles),
        "families_named_by_a_unique_shape": sorted(
            {name for names in singles.values() for name in names}
        ),
        "detail": singles,
    }


def evaluate(manifest: Manifest) -> dict[str, Any]:
    results, rows = run_solver(manifest)
    scored = sum(one.scored for one in results)
    won = sum(one.won for one in results)
    overall = won / scored if scored else 0.0
    shapes = shape_map(manifest)
    at_or_above_one = [one.family for one in results if one.rate >= C2_MAX_PER_FAMILY]
    c1 = shapes["shapes_mapping_to_one_family"] == 0
    c2 = not at_or_above_one
    c3 = overall <= C3_CEILING
    return {
        "gate": solver_fingerprint(),
        "population": POPULATION,
        "scoring": SCORING,
        "solver_is_given_the_correct_conversation": True,
        "not_comparable_to": (
            "the diagnostic runner's qf-1 line, which scores the thirteen authored diagnostic "
            "cases. Different population and different denominators; the two are never "
            "differenced"
        ),
        "corpus": {
            "generator_version": manifest.generator_version,
            "master_seed": manifest.master_seed,
            "size_profile": manifest.size_profile,
            "messages": len(manifest.messages),
            "threads": len(manifest.answer_key.threads),
        },
        "denominators": {one.family: one.scored for one in results},
        "per_family": {
            one.family: {"scored": one.scored, "won": one.won, "rate": round(one.rate, 4)}
            for one in results
        },
        "overall": {"scored": scored, "won": won, "rate": round(overall, 4)},
        "C1_shape_ambiguous": {"passed": c1, **shapes},
        "C2_no_family_solved_outright": {"passed": c2, "families_at_100_percent": at_or_above_one},
        "C3_residual_at_or_below_ceiling": {
            "passed": c3,
            "ceiling": C3_CEILING,
            "observed": round(overall, 4),
            "threshold_is": (
                "a provisional engineering threshold for this repair. NOT a statistically "
                "established validity threshold: no power analysis stands behind it, and "
                "passing it is not evidence the corpus is free of shortcuts"
            ),
        },
        "C4_independent_read": {
            "passed": None,
            "note": "a human judgement; this file does not compute or simulate it",
        },
        "verdict": "PASS" if (c1 and c2 and c3) else "FAIL",
        "verdict_covers": "C1-C3 only. C4 is outside this file and the gate is not passed without it",
        "threads": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=4311)
    parser.add_argument("--profile", default="sample")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.manifest is not None:
        manifest = Manifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    else:
        manifest = corpus.generate(master_seed=args.seed, size_profile=args.profile)
    report = evaluate(manifest)
    text = json.dumps(report, indent=1)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"written: {args.out}")
    summary = {k: v for k, v in report.items() if k != "threads"}
    print(json.dumps(summary, indent=1))
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
