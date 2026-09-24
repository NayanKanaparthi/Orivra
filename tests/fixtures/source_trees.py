"""Walking both source trees, for the sweeps that read this project's own code.

Two standing-cycle files sweep the same two trees for the same kind of thing, and each
started with its own copy of "list the Python files, skip `__pycache__`, skip the module
that is allowed to do this". Two copies of a file walker is a small instance of the exact
defect those sweeps exist to catch, so there is one walker and it lives here.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


def _members() -> tuple[str, ...]:
    """The workspace members, read from `pyproject.toml` rather than listed here.

    **The same fix `tools/guards` got, applied to the other sweeper** (review finding
    R-M1-015). This tuple was `("server/src", "harness/src")`, so when `orivra/src` arrived
    every standing-cycle sweep silently stopped covering a third of the repository - and one
    of those sweeps is `test_no_module_renders_a_validation_error_any_other_way`, which
    exists so that R-SEC-043 cannot recur. It recurred, in `orivra/surface/server.py`, and
    this is why nothing caught it.
    """
    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as handle:
        configuration = tomllib.load(handle)
    members = configuration["tool"]["uv"]["workspace"]["members"]
    return tuple(str(member) for member in members)


#: Every workspace member's source tree. Tests are not swept: a test that plants a forbidden
#: idiom in order to prove a sweep fires is not a violation, and a sweep that said otherwise
#: would make its own reintroduction check impossible.
TREES = tuple(Path(member) / "src" for member in _members())


def source_files(*, excluding: str = "") -> list[Path]:
    """Every module in both trees, optionally minus the one allowed to hold the shape.

    `excluding` is a path suffix (`"mailweave/constants.py"`), matched against the whole
    path rather than the basename, so excluding one module never silently excludes another
    of the same name in the other tree.
    """
    found: list[Path] = []
    for tree in TREES:
        found.extend(
            path
            for path in sorted(tree.rglob("*.py"))
            if "__pycache__" not in path.parts and not (excluding and str(path).endswith(excluding))
        )
    return found


def parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
