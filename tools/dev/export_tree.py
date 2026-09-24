"""Export the working tree for the isolated test runner, and prove what is in it.

**`git archive HEAD` is the wrong tool and it fails silently.** It carries tracked files at
the last commit, so an uncommitted edit, a new test file that has not been `git add`-ed, and a
file staged but not committed are all absent from the export - and nothing says so. The runner
then passes, and what it passed on is not what is being claimed.

This exports the **working tree**: every file git would track plus every untracked file that
is not ignored, which is exactly the set a developer sees. It then writes a manifest with a
sha256 per file, and `--verify` re-reads an extracted copy and refuses unless every path and
every digest matches. A run is tied to a file set rather than to a commit that may not
describe it.

Ignored files stay out, deliberately: `.git`, caches, benchmark output, and - the reason this
matters most - the two OAuth credentials, which are gitignored and must never leave the
machine. The manifest is checked for them by name as well, because "it is gitignored" is a
statement about a config file and the check should be about the archive.

    python tools/dev/export_tree.py --out _to_delete/export        # write tree + manifest
    python tools/dev/export_tree.py --verify <extracted-dir> --manifest <manifest.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from collections.abc import Sequence
from pathlib import Path

#: Names that must never appear in an export, whatever `.gitignore` says. Belt as well as
#: braces: the ignore file is configuration and this is a property of the artefact.
FORBIDDEN = ("mailweave-server-oauth.json", "mailweave-harness-oauth.json")

#: What the test runner needs, by top-level path. **Scoped, and the scope is in the manifest**
#: - which is the difference between narrowing an export and narrowing one silently. The
#: unscoped working tree is 181MB, almost all of it `marketing/`, review snapshots and
#: benchmark output: none of it is imported by a test, and carrying it would make every export
#: a minute of transfer for files nothing reads.
#:
#: A path outside this set is not in the export and the manifest says the scope, so a reader
#: comparing a test run against a claim can see at once whether the claim is about something
#: that was shipped to the runner.
RUNNABLE = (
    "server/",
    "harness/",
    "orivra/",
    "tests/",
    "tools/",
    # **`docs/` is in scope because tests read it.** Several suites use published documents as
    # contract oracles - `test_disclosure_round23` checks the ceilings it enforces against the
    # ones `ARCHITECTURE_DECISION.md` prints. Leaving `docs/` out made three tests fail in the
    # runner for a reason that had nothing to do with the code, which is worse than a gap: it
    # is a false signal. `referenced_paths` below is what stops the next one.
    "docs/",
    "preflight-records/",
    "benchmarks/ground_truth/",
    "pyproject.toml",
    "Makefile",
    "models.lock",
    "models-catalog.json",
)

#: Path literals in the test tree that name repository files. Extracted rather than listed,
#: because a list would be one more declaration to keep in step with the thing it declares -
#: and the failure mode of getting it wrong is a green run on a tree missing what the tests
#: read.
_PATH_LITERAL = re.compile(
    r'["\'](docs|benchmarks|preflight-records|validation-records|marketing)/[A-Za-z0-9_./-]+["\']'
)


def referenced_paths(root: Path, files: Sequence[str]) -> list[str]:
    """Repository paths the test tree mentions by literal, that exist on disk."""
    named: set[str] = set()
    for one in files:
        if not one.startswith("tests/") or not one.endswith(".py"):
            continue
        for match in _PATH_LITERAL.finditer((root / one).read_text(encoding="utf-8")):
            named.add(match.group(0).strip("\"'"))
    return sorted(path for path in named if (root / path).exists())


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "--no-optional-locks", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def working_tree_files(root: Path, scope: tuple[str, ...] | None = RUNNABLE) -> list[str]:
    """Every file a developer sees, inside the scope: tracked plus untracked-and-not-ignored.

    `-c` is cached (tracked), `-o` is other (untracked), `--exclude-standard` applies the
    ignore rules. **`-o` is the point**: a new test file that has not been `git add`-ed is
    invisible to `git archive HEAD`, and exporting from HEAD is how a runner passes on a tree
    that is not the one being claimed. Deleted-but-still-tracked paths are filtered by the
    existence check, so a file removed in the working tree is absent from an export of it.
    """
    listed = _git("-C", str(root), "ls-files", "-co", "--exclude-standard").splitlines()
    chosen = {one for one in listed if one and (root / one).is_file()}
    if scope is not None:
        chosen = {
            one
            for one in chosen
            if any(one == part or one.startswith(part) for part in scope)
        }
    return sorted(chosen)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def export(
    root: Path, out: Path, label: str, scope: tuple[str, ...] | None = RUNNABLE
) -> tuple[Path, Path]:
    files = working_tree_files(root, scope)
    for name in FORBIDDEN:
        if any(one == name or one.endswith(f"/{name}") for one in files):
            raise SystemExit(f"refusing to export: {name} is in the file set")
    # **The check that makes a scope safe rather than hopeful.** A scoped export is fine; a
    # scoped export that drops a file the tests open is a green run on the wrong tree.
    wanted = referenced_paths(root, working_tree_files(root, None))
    absent = [
        one
        for one in wanted
        if (root / one).is_file() and one not in files
    ]
    missing_dirs = [
        one
        for one in wanted
        if (root / one).is_dir() and not any(part.startswith(one) for part in files)
    ]
    if absent or missing_dirs:
        raise SystemExit(
            "refusing to export: the test tree reads paths this scope excludes - "
            + ", ".join(sorted(absent + missing_dirs)[:10])
            + ". Widen RUNNABLE or the runner will fail for a reason that is not the code"
        )
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"tree-{label}.tar.gz"
    manifest_path = out / f"tree-{label}.manifest.json"
    with tarfile.open(archive, "w:gz") as tar:
        for one in files:
            tar.add(root / one, arcname=one)
    manifest = {
        "label": label,
        "head": _git("-C", str(root), "rev-parse", "HEAD").strip(),
        "dirty": bool(_git("-C", str(root), "status", "--porcelain").strip()),
        "scope": list(scope) if scope is not None else None,
        "count": len(files),
        "files": {one: digest(root / one) for one in files},
    }
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return archive, manifest_path


def verify(extracted: Path, manifest_path: Path) -> int:
    """Refuse unless the extracted copy is exactly the manifest, file for file and byte for
    byte. Both directions: a missing file is an incomplete export, and an extra one is an
    export carrying something the manifest does not describe."""
    manifest = json.loads(manifest_path.read_text())
    expected: dict[str, str] = manifest["files"]
    present = {
        str(path.relative_to(extracted))
        for path in extracted.rglob("*")
        if path.is_file()
    }
    missing = sorted(set(expected) - present)
    extra = sorted(present - set(expected))
    changed = [
        one
        for one in sorted(set(expected) & present)
        if digest(extracted / one) != expected[one]
    ]
    for label, rows in (("missing", missing), ("unexpected", extra), ("changed", changed)):
        for row in rows[:20]:
            print(f"{label}: {row}")
        if len(rows) > 20:
            print(f"{label}: ... and {len(rows) - 20} more")
    if missing or extra or changed:
        print(
            f"VERIFY FAILED: {len(missing)} missing, {len(extra)} unexpected, "
            f"{len(changed)} changed"
        )
        return 1
    print(
        f"VERIFY OK: {len(expected)} files match the manifest "
        f"(head {manifest['head'][:10]}, dirty={manifest['dirty']}, "
        f"scope={manifest.get('scope')})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--label", default="wt")
    parser.add_argument(
        "--whole-tree",
        action="store_true",
        help="export everything git would see rather than the runnable scope",
    )
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    if args.verify is not None:
        if args.manifest is None:
            raise SystemExit("--verify needs --manifest")
        return verify(args.verify, args.manifest)
    if args.out is None:
        raise SystemExit("--out is required when exporting")
    archive, manifest_path = export(
        args.root, args.out, args.label, None if args.whole_tree else RUNNABLE
    )
    print(f"{archive}\n{manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
