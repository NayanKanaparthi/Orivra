"""Resolve every citation, then run the checks that can run here.

Two passes and the order matters. `resolve` opens each cited file and looks for the named
test at module level before anything runs, because the failure this guards against is silent:
a node id that names nothing makes `pytest` exit 4 with "no tests ran", which a status tool
reading a return code would have to call either green or red and would be wrong either way.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mailweave_harness.acceptance.spec import ITEMS, Check, Item


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CheckResult:
    check: Check
    status: Status
    detail: str = ""


@dataclass(frozen=True)
class ItemResult:
    item: Item
    results: tuple[CheckResult, ...]

    @property
    def runnable(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is not Status.BLOCKED)

    @property
    def green(self) -> bool:
        """Every check that *can* run here did, and passed. Says nothing about the blocked ones."""
        return bool(self.runnable) and all(r.status is Status.PASS for r in self.runnable)


def _module_and_name(citation: str) -> tuple[str, str | None]:
    path, _, name = citation.partition("::")
    return path, (name or None)


def resolve(citation: str, *, root: Path) -> str:
    """`""` when this citation names something real, otherwise why it does not.

    A file is enough for a whole-module citation; a `::name` citation must find a
    module-level `def name(` in that file's parsed tree. Parsed rather than grepped, for the
    reason the replant manifest's own resolver is: a name inside a string or a comment is not
    a test.
    """
    path, name = _module_and_name(citation)
    target = root / path
    if not target.is_file():
        return f"no such file: {path}"
    if name is None:
        return ""
    tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    defined = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    return "" if name in defined else f"{path} defines no module-level {name}"


def unresolved(*, root: Path) -> list[str]:
    """Every citation in the spec that names nothing. Empty is the only acceptable state."""
    problems: list[str] = []
    for item in ITEMS:
        for check in item.checks:
            for citation in check.runs:
                why = resolve(citation, root=root)
                if why:
                    problems.append(f"{check.id}: {why}")
    return problems


def _run(citations: tuple[str, ...], *, root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not network and not replant",
            "--tb=no",
            "-rf",
            *citations,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = [line for line in proc.stdout.splitlines() if line.strip()]
    summary = tail[-1] if tail else "no output"
    return proc.returncode == 0, summary


def run(*, root: Path, execute: bool = True) -> list[ItemResult]:
    """Every item, with each check either run, blocked, or reported unresolved.

    `execute=False` reports the plan: what would run and what is waiting on what. It needs
    nothing but this repository, which is what makes it usable in a handoff.
    """
    out: list[ItemResult] = []
    for item in ITEMS:
        results: list[CheckResult] = []
        for check in item.checks:
            if check.needs:
                results.append(CheckResult(check, Status.BLOCKED, "; ".join(check.needs)))
                continue
            bad = [why for why in (resolve(c, root=root) for c in check.runs) if why]
            if bad:
                results.append(CheckResult(check, Status.UNRESOLVED, "; ".join(bad)))
                continue
            if not execute:
                results.append(
                    CheckResult(check, Status.PASS, f"{len(check.runs)} citation(s), not run")
                )
                continue
            ok, summary = _run(check.runs, root=root)
            results.append(CheckResult(check, Status.PASS if ok else Status.FAIL, summary))
        out.append(ItemResult(item, tuple(results)))
    return out
