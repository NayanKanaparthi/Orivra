"""Regenerate `tests/fixtures/v01_input_keys.json` from the `v0.1` tag.

**Why a fixture and not just a `git show` in the test.** The compatibility guard has to run
where the suite runs, and the suite runs in an isolated runner over an exported working tree
with no `.git` in it. A test that reads the tag directly skips there - which is precisely the
run that would have caught `pool.scope` and `pool.window` leaving the schema, and precisely the
run where it would have been silent.

So the tag's key set is checked in, and there are two tests rather than one: one compares the
current schema against the fixture and runs everywhere, and one compares the fixture against
the tag and runs wherever `.git` is present. Neither is the whole check on its own. The tag
stays the source of truth; the fixture is a cache of it, and the second test is what keeps the
cache honest.

    python tools/dev/v01_input_keys.py          # rewrite the fixture from the tag
    python tools/dev/v01_input_keys.py --check  # exit 1 if the fixture is stale
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TAG = "v0.1"
SOURCE = "server/src/mailweave/surface/tools.py"
FIXTURE = Path("tests/fixtures/v01_input_keys.json")

#: Keys that name a schema construct rather than an argument.
STRUCTURAL = frozenset({"properties", "items", "inputSchema", "outputSchema"})


def published_argument_keys(source: str) -> dict[str, list[str]]:
    """Every argument key each tool publishes, as dotted paths, read from module source.

    Source rather than an import, because the whole point is to read a file as it stood at
    another revision, and that revision's imports are not this one's.
    """
    out: dict[str, set[str]] = {}
    tool: str | None = None
    stack: list[tuple[int, str | None]] = []
    for line in source.splitlines():
        found = re.search(r"ToolName\.([A-Z_]+)", line)
        if found:
            tool, stack = found.group(1), []
        if tool is None:
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1][0]:
            stack.pop()
        opens = re.match(r'^\s*"([a-z_]+)"\s*:\s*\{', line)
        if opens:
            name = opens.group(1)
            if name in STRUCTURAL:
                stack.append((indent, None))
                continue
            out.setdefault(tool, set()).add(".".join([p for _, p in stack if p] + [name]))
            stack.append((indent, name))
    return {tool: sorted(keys) for tool, keys in sorted(out.items())}


def from_tag() -> dict[str, object]:
    shown = subprocess.run(
        ["git", "show", f"{TAG}:{SOURCE}"], capture_output=True, check=True
    ).stdout.decode("utf-8")
    commit = subprocess.run(
        ["git", "rev-list", "-n1", TAG], capture_output=True, check=True, text=True
    ).stdout.strip()
    return {
        "_": (
            f"Generated from the {TAG} tag by tools/dev/v01_input_keys.py. Do not hand-edit: "
            "it is a cache of the tag, and tests/test_v01_input_compatibility.py checks it "
            "against the tag wherever .git is present."
        ),
        "tag": TAG,
        "commit": commit,
        "published_argument_keys": published_argument_keys(shown),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the fixture is stale")
    args = parser.parse_args(argv)
    fresh = from_tag()
    rendered = json.dumps(fresh, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not FIXTURE.exists() or FIXTURE.read_text() != rendered:
            print(f"{FIXTURE} is stale; run: python {__file__.split('/')[-1]}", file=sys.stderr)
            return 1
        print(f"{FIXTURE} matches {TAG}")
        return 0
    FIXTURE.write_text(rendered)
    print(f"wrote {FIXTURE} from {TAG} ({fresh['commit'][:12]})")
    return 0


if __name__ == "__main__":  # pragma: no cover - a developer entry point
    raise SystemExit(main())
