"""`python -m mailweave_harness.acceptance` - M2's acceptance evidence, as a status command.

    --plan     what each item claims, what would run, and what each blocked half needs.
               Needs nothing but this repository.
    --check    resolve every citation. Fails if one names nothing.
    --run      run the runnable checks and report per item.

**A green `--run` is not an acceptance verdict.** It says every check that can run in this
repository did and passed, and it prints, beside that, everything still waiting on a corpus,
a mailbox, a network or a runtime. Only a reviewer who did not write the code may move a
rubric criterion to PASS.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mailweave_harness.acceptance.runner import Status, run, unresolved
from mailweave_harness.acceptance.spec import ITEMS

REPO_ROOT = Path(__file__).resolve().parents[4]

_MARK = {
    Status.PASS: "ok     ",
    Status.FAIL: "FAILED ",
    Status.BLOCKED: "blocked",
    Status.UNRESOLVED: "BROKEN ",
}


def _wrap(text: str, *, indent: str, width: int = 96) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width and current.strip():
            lines.append(current.rstrip())
            current = indent
        current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    return lines


def _plan() -> str:
    lines = ["M2 acceptance - what has executable support here, and what is waiting", ""]
    for item in ITEMS:
        lines.append(f"[{item.id}] {item.title}")
        lines += _wrap(f"criterion: {item.criterion}", indent="      ")
        for check in item.checks:
            if check.needs:
                lines.append(f"    - {check.id}: BLOCKED")
                for need in check.needs:
                    lines += _wrap(f"* {need}", indent="        ")
            else:
                lines.append(f"    - {check.id}: runs {len(check.runs)} citation(s)")
                lines += _wrap(check.establishes, indent="        ")
                for citation in check.runs:
                    lines.append(f"        $ pytest {citation}")
        lines.append("")
    lines.append(
        "Nothing above is a verdict. A check that passes is a citation a gating reviewer can "
        "re-run; a blocked one names a prerequisite, not a task."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailweave-acceptance", description=__doc__)
    parser.add_argument("--plan", action="store_true", help="the plan; needs nothing")
    parser.add_argument("--check", action="store_true", help="resolve every citation")
    parser.add_argument("--run", action="store_true", help="run the runnable checks")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if args.check:
        problems = unresolved(root=args.root)
        for problem in problems:
            print(f"unresolved citation - {problem}")
        print(f"{len(problems)} unresolved citation(s)")
        return 0 if not problems else 2

    if not args.run:
        print(_plan())
        return 0

    results = run(root=args.root, execute=True)
    worst = 0
    for item in results:
        print(f"[{item.item.id}] {item.item.title}")
        for result in item.results:
            print(f"  {_MARK[result.status]} {result.check.id}")
            if result.status is Status.BLOCKED:
                for need in result.check.needs:
                    for line in _wrap(f"needs: {need}", indent="            "):
                        print(line)
            elif result.detail:
                print(f"            {result.detail}")
            if result.status in (Status.FAIL, Status.UNRESOLVED):
                worst = 2
        blocked = sum(1 for r in item.results if r.status is Status.BLOCKED)
        print(
            f"  -> runnable half {'green' if item.green else 'NOT green'}; "
            f"{blocked} check(s) blocked\n"
        )
    print(
        "This is evidence status, not acceptance. Every blocked line above is a thing M2 "
        "still owes, and a green runnable half does not shorten that list."
    )
    return worst


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
