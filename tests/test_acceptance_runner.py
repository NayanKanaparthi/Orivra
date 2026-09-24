"""The acceptance runner's own citations resolve, and its two halves cannot merge.

This file is short because the runner's job is small, and it is here because the runner is a
*reporting* tool: the failure it can have is the quiet one, where a citation stops naming
anything and a status command reports green for a check that ran nothing. `--check` answers
that, and this runs it on every suite pass so the answer is current rather than remembered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mailweave_harness.acceptance import ITEMS, Check, Status, resolve, run, unresolved

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_every_citation_in_the_acceptance_spec_names_something_real() -> None:
    """A citation that does not resolve is a claim (AGENT_LOOP §6), and `pytest` exits 4 on
    one - which a status tool reading a return code has to call green or red, and would be
    wrong either way."""
    assert unresolved(root=REPO_ROOT) == []


def test_a_check_cannot_be_both_runnable_and_blocked() -> None:
    """The whole point of the split, enforced where a check is constructed.

    A check with both would let a blocked prerequisite hide behind a green citation, which is
    the reporting failure this module exists to prevent - and one with neither says nothing
    while occupying a line that looks like evidence.
    """
    with pytest.raises(ValueError, match="either runs here or names what it needs"):
        Check(id="x", establishes="", runs=("tests/test_guards.py",), needs=("a mailbox",))
    with pytest.raises(ValueError, match="either runs here or names what it needs"):
        Check(id="x", establishes="")


def test_a_blocked_check_states_its_prerequisite_in_the_owners_terms() -> None:
    """Every `needs` entry is a sentence, not a token: a status line reading `needs: corpus`
    tells the reader nothing they did not know."""
    for item in ITEMS:
        for check in item.checks:
            for need in check.needs:
                assert len(need.split()) >= 6, (check.id, need)
            if check.runs:
                assert len(check.establishes.split()) >= 10, check.id


def test_each_item_has_at_least_one_of_each_half() -> None:
    """M2's four lines are all partly runnable and all partly blocked, and a report that lost
    either half of one of them would read as further along, or less far along, than it is."""
    for item in ITEMS:
        assert any(check.runs for check in item.checks), item.id
        assert any(check.needs for check in item.checks), item.id


def test_a_missing_citation_is_reported_rather_than_run(tmp_path: Path) -> None:
    """The negative control for `--check`: against a tree with none of the cited files, every
    runnable check reports UNRESOLVED and nothing is executed."""
    results = run(root=tmp_path, execute=True)
    statuses = {result.status for item in results for result in item.results}
    assert Status.UNRESOLVED in statuses
    assert Status.PASS not in statuses and Status.FAIL not in statuses


def test_resolving_a_name_that_is_only_mentioned_in_the_file_is_not_a_resolution() -> None:
    """Parsed rather than grepped: a name inside a string or a comment is not a test."""
    assert resolve("tests/test_guards.py::run_all", root=REPO_ROOT)
    assert (
        resolve(
            "tests/test_guards.py::test_the_shipped_server_tree_passes_every_guard", root=REPO_ROOT
        )
        == ""
    )
