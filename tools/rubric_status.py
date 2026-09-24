"""Rubric status tooling (WS-19).

Reads `docs/RELEASE_RUBRIC.md` - never writes it - and reports the state of every
criterion. Its reason for existing is one rule from AGENT_LOOP §1 and §6:

    Only a reviewer that did not write the code may set a criterion to PASS, and every
    transition records the round number and the reviewer ID.

A markdown table cannot enforce that on its own, so `--check` fails when a criterion is
marked PASS in the rubric without a matching row in `docs/reviews/RUBRIC_TRANSITIONS.md`
naming a reviewer domain and reproduction evidence. An implementer that marks its own work
PASS therefore breaks CI rather than moving a gate.

## What this check cannot do (R-ARCH-012), stated rather than implied

This is a **structural** check on records, and structure is all it can see. It verifies
that a PASS row exists, that it is signed by a name in `REVIEWER_DOMAINS`, that it names a
round, and that its evidence cell is not empty. It cannot verify that any of that is
**true**:

  * a row citing `tests/test_that_does_not_exist.py::test_invented` passes cleanly, because
    nothing here opens the file it names or runs the test it claims;
  * a row signed `R-SEC` passes whoever wrote it, because the signature is a string in a
    markdown cell, not an identity - the separation of implementer from reviewer is
    enforced by the loop, not by this tool;
  * a row can cite evidence that exists but does not support the criterion it is filed
    against. That is exactly the defect R-ARCH-009 and R-ARCH-010 found in Round 4: two
    criteria recorded as unqualified PASS on reviewer reports that had recommended a
    *scoped* pass. Both rows were well-formed and both would pass this check today.

No amount of markdown parsing closes that. A tool that reads records can check the records
are well-formed; only a reader who re-runs the cited evidence can check they are true, and
that reader is the next round's gating reviewer. So the honest statement of what a green
`--check` means is: **no criterion is marked PASS without a signed, round-numbered,
non-empty citation** - not "every PASS is earned".

Two consequences worth naming, because they are what the ceiling costs:

  * a fabricated-evidence row is caught by a human or a reviewer re-running the citation,
    or it is not caught. It is a review obligation, not a CI one;
  * therefore the value of this check is bounded by how often those citations are actually
    re-run. Round 4's ledger population found fifteen Round 1 findings never re-verified
    because two gating reviewers never reported; nothing in this file could have noticed
    that either, and pointing at a green gate would have been the wrong reassurance.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUBRIC_PATH = REPO_ROOT / "docs" / "RELEASE_RUBRIC.md"
TRANSITIONS_PATH = REPO_ROOT / "docs" / "reviews" / "RUBRIC_TRANSITIONS.md"

#: AGENT_LOOP §2.3 reviewer domains, plus the adversarial reviewer of §2.4.
REVIEWER_DOMAINS = frozenset(
    {"R-RETR", "R-DISC", "R-ARCH", "R-SEC", "R-PERF", "R-MCP", "R-GMAIL", "R-DOC", "R-ADV"}
)


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKER = "BLOCKER"
    NOT_TESTED = "NOT TESTED"


class Flag(StrEnum):
    MANDATORY = "M"
    CONDITIONAL = "C"
    OPTIONAL = "O"


_ID = r"[A-Z][A-Z0-9]*-\d+[a-z]?"
_STATUS = r"PASS|FAIL|BLOCKER|NOT TESTED"

_SUMMARY_ROW = re.compile(rf"^\|\s*({_ID})\s*\|\s*(.+?)\s*\|\s*([MCO])\s*\|\s*({_STATUS})\s*\|\s*$")
_DETAIL_HEADER = re.compile(rf"^\*\*({_ID})\s*·\s*(.+?)\s*·\s*([MCO])\s*·\s*({_STATUS})\*\*\s*$")
_TRANSITION_ROW = re.compile(
    rf"^\|\s*({_ID})\s*\|\s*(\d+)\s*\|\s*([A-Z-]+)\s*\|\s*({_STATUS}|-)\s*"
    rf"\|\s*({_STATUS})\s*\|\s*(.+?)\s*\|\s*$"
)


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    flag: Flag
    status: Status
    line: int


@dataclass(frozen=True)
class Transition:
    criterion: str
    round: int
    reviewer: str
    from_status: str
    to_status: Status
    evidence: str
    line: int


@dataclass(frozen=True)
class RubricView:
    summary: dict[str, Criterion]
    detail: dict[str, Criterion]
    transitions: tuple[Transition, ...]

    @property
    def criteria(self) -> dict[str, Criterion]:
        """Detail blocks are the criterion definitions; the summary is an index of them."""
        return self.detail or self.summary


def parse_rubric(text: str) -> tuple[dict[str, Criterion], dict[str, Criterion]]:
    summary: dict[str, Criterion] = {}
    detail: dict[str, Criterion] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = _SUMMARY_ROW.match(line)
        if match:
            cid, name, flag, status = match.groups()
            summary[cid] = Criterion(cid, name, Flag(flag), Status(status), number)
            continue
        match = _DETAIL_HEADER.match(line)
        if match:
            cid, name, flag, status = match.groups()
            detail[cid] = Criterion(cid, name, Flag(flag), Status(status), number)
    return summary, detail


def parse_transitions(text: str) -> tuple[Transition, ...]:
    rows: list[Transition] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _TRANSITION_ROW.match(line)
        if match:
            cid, rnd, reviewer, before, after, evidence = match.groups()
            rows.append(
                Transition(cid, int(rnd), reviewer, before, Status(after), evidence, number)
            )
    return tuple(rows)


def load(rubric_path: Path = RUBRIC_PATH, transitions_path: Path = TRANSITIONS_PATH) -> RubricView:
    summary, detail = parse_rubric(rubric_path.read_text(encoding="utf-8"))
    transitions = (
        parse_transitions(transitions_path.read_text(encoding="utf-8"))
        if transitions_path.exists()
        else ()
    )
    return RubricView(summary=summary, detail=detail, transitions=transitions)


def check(view: RubricView) -> list[str]:
    """Return the list of gate-integrity problems. Empty means the records are consistent."""
    problems: list[str] = []
    criteria = view.criteria

    if view.summary and view.detail:
        only_summary = sorted(set(view.summary) - set(view.detail))
        only_detail = sorted(set(view.detail) - set(view.summary))
        for cid in only_summary:
            problems.append(f"{cid}: listed in the status summary with no criterion block")
        for cid in only_detail:
            problems.append(f"{cid}: has a criterion block but is missing from the status summary")
        for cid in sorted(set(view.summary) & set(view.detail)):
            if view.summary[cid].status is not view.detail[cid].status:
                problems.append(
                    f"{cid}: status summary says {view.summary[cid].status.value} but the "
                    f"criterion block says {view.detail[cid].status.value}"
                )

    certified: dict[str, list[Transition]] = {}
    for transition in view.transitions:
        if transition.criterion not in criteria:
            problems.append(
                f"RUBRIC_TRANSITIONS.md:{transition.line}: transition names unknown "
                f"criterion {transition.criterion}"
            )
        if transition.reviewer not in REVIEWER_DOMAINS:
            problems.append(
                f"RUBRIC_TRANSITIONS.md:{transition.line}: {transition.reviewer} is not a "
                f"reviewer domain ({', '.join(sorted(REVIEWER_DOMAINS))})"
            )
        if not transition.evidence.strip() or transition.evidence.strip() in {"-", "n/a"}:
            problems.append(
                f"RUBRIC_TRANSITIONS.md:{transition.line}: transition for "
                f"{transition.criterion} records no reproduction evidence"
            )
        if transition.to_status is Status.PASS:
            certified.setdefault(transition.criterion, []).append(transition)

    for cid, criterion in sorted(criteria.items()):
        if criterion.status is not Status.PASS:
            continue
        if cid not in certified:
            problems.append(
                f"{cid} is marked PASS with no reviewer transition in "
                "docs/reviews/RUBRIC_TRANSITIONS.md. Only a reviewer that did not write "
                "the code may set PASS (AGENT_LOOP §1, §6)."
            )
    return problems


def gate_blockers(view: RubricView) -> list[str]:
    """Criteria that block the release gate: NOT TESTED counts exactly like FAIL (PROC-01)."""
    return sorted(
        cid
        for cid, criterion in view.criteria.items()
        if criterion.flag is not Flag.OPTIONAL
        and criterion.status in {Status.NOT_TESTED, Status.FAIL, Status.BLOCKER}
    )


def report(view: RubricView) -> str:
    counts = Counter(criterion.status for criterion in view.criteria.values())
    flags = Counter(criterion.flag for criterion in view.criteria.values())
    lines = [
        f"criteria: {len(view.criteria)}  "
        f"(mandatory {flags[Flag.MANDATORY]}, conditional {flags[Flag.CONDITIONAL]}, "
        f"optional {flags[Flag.OPTIONAL]})",
        "status:",
    ]
    for status in Status:
        lines.append(f"  {status.value:<12} {counts[status]}")
    lines.append(f"reviewer transitions recorded: {len(view.transitions)}")
    blockers = gate_blockers(view)
    lines.append(f"gate-blocking criteria (NOT TESTED / FAIL / BLOCKER): {len(blockers)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", type=Path, default=RUBRIC_PATH)
    parser.add_argument("--transitions", type=Path, default=TRANSITIONS_PATH)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if any criterion is PASS without a reviewer transition, or the records "
        "are internally inconsistent",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="fail if any mandatory criterion is NOT TESTED, FAIL or BLOCKER (release gate)",
    )
    args = parser.parse_args(argv)

    view = load(args.rubric, args.transitions)
    print(report(view))

    exit_code = 0
    if args.check:
        problems = check(view)
        for problem in problems:
            print(f"GATE INTEGRITY: {problem}", file=sys.stderr)
        if problems:
            exit_code = 1
    if args.gate:
        blockers = gate_blockers(view)
        if blockers:
            print(
                f"RELEASE GATE: {len(blockers)} criteria are not PASS: "
                f"{', '.join(blockers[:10])}{' ...' if len(blockers) > 10 else ''}",
                file=sys.stderr,
            )
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
