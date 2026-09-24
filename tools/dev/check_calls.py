"""Check a call-diagnostics file against the timing claims the retest makes.

Reads the JSONL `MAILWEAVE_DIAGNOSTICS` writes and answers, per call, the two questions
`docs/RETEST_2026-09-21.md` asks of it: did every call the server received also end, and did
any call run past the allowance it bound by more than the tolerance? **The outcome does not
excuse the timing.** A `budget_exhausted` decline that arrived late is late: the check is
`overrun_ms <= tolerance` for every end line that carries an allowance, whatever its outcome,
because a decline that says "the budget was spent" and arrived four minutes after the budget
was spent is exactly the behaviour the repairs exist to end.

The tolerance is an argument and not a constant, so the number is stated on the command
line by the person running the check and recorded with the result; `--tolerance-ms` has no
default. `docs/RETEST_2026-09-21.md` gives the figure the retest uses and where it comes from.

    python tools/dev/check_calls.py calls.jsonl --tolerance-ms 750

Exit status 0 when every claim holds, 1 otherwise. The report names each call by its id and
its tool, never by anything else, because the file carries nothing else to name it by.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CallTiming:
    """One call as the file records it: its start, its end, and what the end line said."""

    call_id: str
    tool: str
    surface: str
    ended: bool
    outcome: str | None
    elapsed_ms: int | None
    allowance_ms: int | None
    overrun_ms: int | None
    cold_load_ms: int | None
    code: str | None


@dataclass
class Report:
    calls: list[CallTiming] = field(default_factory=list)
    unended: list[CallTiming] = field(default_factory=list)
    late: list[CallTiming] = field(default_factory=list)
    unbounded: list[CallTiming] = field(default_factory=list)
    ends_without_start: list[str] = field(default_factory=list)
    malformed_lines: int = 0

    @property
    def ok(self) -> bool:
        return not (self.unended or self.late or self.ends_without_start)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_lines(text: str) -> tuple[list[Mapping[str, Any]], int]:
    lines: list[Mapping[str, Any]] = []
    malformed = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            malformed += 1
            continue
        if isinstance(parsed, Mapping) and isinstance(parsed.get("call"), str):
            lines.append(parsed)
        else:
            malformed += 1
    return lines, malformed


def pair_calls(lines: Iterable[Mapping[str, Any]]) -> tuple[list[CallTiming], list[str]]:
    """Start lines paired with their end lines by call id, in start order."""
    starts: dict[str, Mapping[str, Any]] = {}
    order: list[str] = []
    ends: dict[str, Mapping[str, Any]] = {}
    orphans: list[str] = []
    for line in lines:
        call_id = str(line["call"])
        if line.get("event") == "start":
            if call_id not in starts:
                order.append(call_id)
            starts[call_id] = line
        elif line.get("event") == "end":
            if call_id in starts:
                ends[call_id] = line
            else:
                orphans.append(call_id)
    calls: list[CallTiming] = []
    for call_id in order:
        start = starts[call_id]
        end = ends.get(call_id)
        calls.append(
            CallTiming(
                call_id=call_id,
                tool=str(start.get("tool", "?")),
                surface=str(start.get("surface", "?")),
                ended=end is not None,
                outcome=str(end["outcome"]) if end is not None and "outcome" in end else None,
                elapsed_ms=_int_or_none(end.get("elapsed_ms")) if end is not None else None,
                allowance_ms=_int_or_none(end.get("allowance_ms")) if end is not None else None,
                overrun_ms=_int_or_none(end.get("overrun_ms")) if end is not None else None,
                cold_load_ms=(_int_or_none(end.get("cold_load_ms")) if end is not None else None),
                code=str(end["code"]) if end is not None and "code" in end else None,
            )
        )
    return calls, orphans


def check(text: str, *, tolerance_ms: int) -> Report:
    """The claims, evaluated. `tolerance_ms` applies to every ended call with an allowance."""
    if tolerance_ms < 0:
        raise ValueError("a tolerance is a non-negative number of milliseconds")
    lines, malformed = read_lines(text)
    calls, orphans = pair_calls(lines)
    report = Report(calls=calls, ends_without_start=orphans, malformed_lines=malformed)
    for timing in calls:
        if not timing.ended:
            report.unended.append(timing)
            continue
        if timing.allowance_ms is None:
            # A call that bound no deadline made no Gmail request: it ended in argument
            # parsing or in a refusal before the network. It is checked against the
            # tolerance alone, because there is nothing else to check it against.
            report.unbounded.append(timing)
            if timing.elapsed_ms is not None and timing.elapsed_ms > tolerance_ms:
                report.late.append(timing)
            continue
        overrun = timing.overrun_ms
        if overrun is None and timing.elapsed_ms is not None:
            overrun = max(0, timing.elapsed_ms - timing.allowance_ms)
        if overrun is not None and timing.cold_load_ms:
            # PF-4's rule: the model load is paid once per process and sits outside every
            # per-query budget, so a first semantic query is measured net of it. The line
            # says how much was set aside; nothing else is.
            overrun = max(0, overrun - timing.cold_load_ms)
        if overrun is None or overrun > tolerance_ms:
            report.late.append(timing)
    return report


def render(report: Report, *, tolerance_ms: int) -> str:
    out: list[str] = []
    out.append(
        f"{len(report.calls)} call(s); tolerance {tolerance_ms} ms; "
        f"{len(report.unbounded)} bound no deadline; {report.malformed_lines} malformed line(s)"
    )
    for timing in report.calls:
        if not timing.ended:
            out.append(f"  {timing.call_id[:12]} {timing.tool}: started, never ended")
            continue
        allowance = "-" if timing.allowance_ms is None else str(timing.allowance_ms)
        overrun = "-" if timing.overrun_ms is None else str(timing.overrun_ms)
        cold = f" cold_load={timing.cold_load_ms}" if timing.cold_load_ms else ""
        verdict = "LATE" if timing in report.late else "ok"
        code = f" {timing.code}" if timing.code else ""
        out.append(
            f"  {timing.call_id[:12]} {timing.tool}: {timing.outcome}{code} "
            f"elapsed={timing.elapsed_ms} allowance={allowance} overrun={overrun}{cold} {verdict}"
        )
    for orphan in report.ends_without_start:
        out.append(f"  {orphan[:12]}: end line with no start line")
    out.append("RESULT: " + ("every claim holds" if report.ok else "a claim failed"))
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", type=Path, help="the JSONL file MAILWEAVE_DIAGNOSTICS wrote")
    parser.add_argument(
        "--tolerance-ms",
        type=int,
        required=True,
        help="the most an ended call may run past its bound allowance; stated, not defaulted",
    )
    args = parser.parse_args(argv)
    report = check(args.path.read_text(encoding="utf-8"), tolerance_ms=args.tolerance_ms)
    print(render(report, tolerance_ms=args.tolerance_ms))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
