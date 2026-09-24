"""The standing check, as a test rather than as a habit (round 11).

The foundation carried one item forward as a *standing check* rather than a finding: **"one
shape validated, peers trusted" has appeared six times**, most recently inside round 10's own
diff, where `envelope/reasons.py::_one_line` reimplemented
`envelope/disposition.py::_is_one_line` using the same primitive, written twice
(R-ARCH-031).

Round 11 found a seventh instance in its own diff - the preflight record writer needed the
same predicate a fourth time, in the harness package, where `envelope/`'s private helpers are
not reachable at all - and closed it by moving the implementation to `mailweave.constants`,
the module every layer already imports for `GMAIL_NUMERIC_ID_RE`.

A habit that has failed six times is not closed by being careful a seventh. These tests are
the mechanism: a sweep over both source trees for a *second* implementation of a shape that
already has one. They are deliberately narrow - they cover the two idioms that have actually
recurred, not "duplication" in general - because a guard that reports innocent code is a
guard that gets switched off.
"""

from __future__ import annotations

import ast
from pathlib import Path

from mailweave.constants import GMAIL_NUMERIC_ID_RE, REMOTE_SLUG_RE, clean_slug, is_one_line
from tests.fixtures.source_trees import source_files

#: The one module allowed to implement these shapes.
HOME = "mailweave/constants.py"


def python_files() -> list[Path]:
    """`fixtures.source_trees.source_files`, which round 12 moved out of this file.

    Round 12 needed the same walk for its own sweeps and wrote a second copy of it, in the
    pair of files whose subject is second copies. One walker, imported by both.
    """
    return source_files(excluding=HOME)


def _is_splitlines_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "splitlines"
    )


def test_no_module_reimplements_the_one_line_predicate() -> None:
    """The R-ARCH-031 shape: `value.splitlines() == [value]`, written out a second time."""
    offenders: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and (
                _is_splitlines_call(node.left)
                or any(_is_splitlines_call(item) for item in node.comparators)
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], (
        "a module compares against `str.splitlines()` instead of importing "
        f"`constants.is_one_line`: {offenders}. That is R-ARCH-031's exact shape."
    )


def test_no_module_spells_a_remote_slug_check_as_isidentifier() -> None:
    """The round-11 instance: two layers checking one remote-API shape two different ways.

    `str.isidentifier()` accepts every Unicode identifier - Arabic, CJK, Greek - and Google
    emits none of them as an error code. The consent flow used it while the Gmail client used
    an anchored ASCII pattern for the same class of value.
    """
    offenders: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "isidentifier"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], (
        f"a remote-API slug is checked with `str.isidentifier()`: {offenders}. Use "
        "`constants.clean_slug`, which is anchored and ASCII, and is what the other layer uses."
    )


#: The Gmail numeric-id shape as it would be re-spelled: a digit class bounded at the decimal
#: width of a uint64. Narrower than "a bounded digit class", deliberately - the first version
#: of this sweep matched `\d{1,2}` inside the quote stripper's calendar-date pattern, which is
#: innocent code, and a guard that reports innocent code is a guard that gets switched off.
_ID_PATTERN_SPELLINGS = ("[0-9]{1,20}", "\\d{1,20}", "[0-9]{1,19}", "[0-9]{1,21}")


def test_no_module_reimplements_the_gmail_numeric_shape() -> None:
    """The R-SEC-030 / R-SEC-032 shape, found at three layers across two rounds."""
    offenders: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and any(spelling in node.value for spelling in _ID_PATTERN_SPELLINGS)
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], (
        f"a module writes its own decimal-id pattern: {offenders}. There is one, in "
        "`constants.GMAIL_NUMERIC_ID_RE`, and it is imported by every layer that needs it."
    )


def test_the_sweeps_would_actually_catch_a_planted_instance(tmp_path: Path) -> None:
    """A guard that has never been shown to fire is a guard nobody has tested.

    Each sweep is re-run over a file containing exactly the idiom it looks for, so the three
    tests above are known to be reporting an empty result rather than an empty search.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def check(v: str) -> bool:\n"
        "    return v.splitlines() == [v] and v.isidentifier()\n"
        'PATTERN = "[0-9]{1,20}"\n',
        encoding="utf-8",
    )
    tree = ast.parse(planted.read_text(encoding="utf-8"))
    compares = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and (
            _is_splitlines_call(node.left)
            or any(_is_splitlines_call(item) for item in node.comparators)
        )
    ]
    identifiers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "isidentifier"
    ]
    patterns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(spelling in node.value for spelling in _ID_PATTERN_SPELLINGS)
    ]
    assert len(compares) == 1
    assert len(identifiers) == 1
    assert len(patterns) == 1


def test_the_shared_checkers_behave_as_their_call_sites_expect() -> None:
    """One implementation means one behaviour, so it is asserted once, here."""
    assert is_one_line("a single line") is True
    assert is_one_line("two\nlines") is False
    assert is_one_line("paragraph separator") is False
    assert is_one_line("trailing\n") is False
    assert clean_slug("userRateLimitExceeded") == "userRateLimitExceeded"
    assert clean_slug("invalid_grant") == "invalid_grant"
    assert clean_slug("not a slug at all") is None
    assert clean_slug("١٣") is None
    assert clean_slug(None) is None
    assert REMOTE_SLUG_RE.match("ok\n") is None
    assert GMAIL_NUMERIC_ID_RE.match("99120034\n") is None
