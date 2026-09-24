"""`python -m tools.guards` - run every source guard over every server-side source tree.

**Every tree, derived from the workspace rather than listed.** The default target was
`server/src` alone, and `orivra/src` arrived as a second tree that runs with the *server*
credential and was swept by nothing - so the destructive-scope sweep, the generative-client
sweep and the unaudited-disk-write sweep all covered a subset of what they name. That is the
same shape as R-RETR-042 in the replant harness, and the fix is the same: read the members
from `[tool.uv.workspace]` and sweep each one's `src/`.

**The harness is excluded, and it is the only exclusion.** `mailweave_harness` owns the
destructive scope literal by design - `scopes.py` is where `SEEDER_SCOPE` lives and the
scope-literal sweep exists precisely to keep it out of the trees that must never hold it -
so sweeping the harness would fail on the one file that is supposed to contain it.
`tests/test_guards.py` asserts that this set is exactly `{"harness"}`, so a second exclusion
cannot be added without a test changing with it.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from tools.guards.sweeps import GUARDS, run_all

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The one workspace member these guards do not sweep. See the module docstring.
DESTRUCTIVE_CAPABLE: frozenset[str] = frozenset({"harness"})


def workspace_members(root: Path = REPO_ROOT) -> tuple[str, ...]:
    """The workspace members, read from `pyproject.toml` rather than listed here."""
    with (root / "pyproject.toml").open("rb") as handle:
        configuration = tomllib.load(handle)
    members = configuration["tool"]["uv"]["workspace"]["members"]
    return tuple(str(member) for member in members)


def guarded_trees(root: Path = REPO_ROOT) -> tuple[Path, ...]:
    """Every server-side source tree these guards sweep, in workspace order."""
    return tuple(
        root / member / "src"
        for member in workspace_members(root)
        if member not in DESTRUCTIVE_CAPABLE and (root / member / "src").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MailWeave CI source guards.")
    parser.add_argument("target", nargs="?", type=Path, default=None)
    parser.add_argument("--guard", action="append", choices=sorted(GUARDS), default=None)
    args = parser.parse_args(argv)

    targets = (args.target.resolve(),) if args.target is not None else guarded_trees()
    for target in targets:
        if not target.exists():
            print(f"guard target {target} does not exist", file=sys.stderr)
            return 2

    violations = [one for target in targets for one in run_all(target, args.guard)]
    for violation in violations:
        print(violation.render(REPO_ROOT), file=sys.stderr)
    names = args.guard or sorted(GUARDS)
    if violations:
        print(f"\n{len(violations)} violation(s) across {len(names)} guard(s)", file=sys.stderr)
        return 1
    # A reviewer runs this against a scratch directory of planted violations, which is
    # not under the repo root; `relative_to` used to raise there and turn a clean result
    # into a traceback.
    shown = ", ".join(
        str(target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target)
        for target in targets
    )
    print(f"guards clean: {', '.join(names)} over {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
