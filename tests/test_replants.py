"""Every behaviour rounds 18 and 19 changed fails a test when it is removed.

R-RETR's finding about round 17 was not about either fix: it was about the suite. Planting
R-RETR-026's and R-RETR-028's defects back left all 2,248 tests green, so both repairs were
undefended and a later refactor could have reverted either without anything going red. **A fix
no test defends is a fix the next round silently undoes**, and the answer to that is a
manifest, executed - `tests/fixtures/replants.py` - rather than two more assertions.

Three tests here, and they answer three different questions:

  * are the manifest's anchors still real? A manifest whose anchors have rotted reports MISSED
    for free, and reports it in a review rather than in CI. This runs on every suite run;
  * does the harness test the tree it planted into? Both prior instances of this project hit
    the editable-`.pth` trap, in which a subprocess imports the *working* tree and every plant
    reports CAUGHT while nothing was changed. This runs on every suite run;
  * does each plant actually fail the test named against it? That one plants and re-runs, so
    it is the slow one and it is marked `replant`. **It is not deselected from the default
    run** - this docstring said it was, and `-m "not network"` collects and runs it, which
    R-RETR checked and the docstring did not (R-RETR-042). The marker exists so that
    `pytest -m replant` reproduces the round's table on its own, not so that CI skips it.
"""

from __future__ import annotations

import pytest

from tests.fixtures.replants import (
    REPLANTS,
    anchor_counts,
    assert_imports_resolve_into_the_scratch_tree,
    importable_packages,
    make_scratch_tree,
    run_replants,
)


def test_every_replant_anchor_matches_exactly_once_in_the_tree() -> None:
    """The manifest describes this tree, and it is checked against it rather than asserted.

    An anchor that matches zero times plants nothing: the harness then runs an unmodified tree
    and reports the behaviour defended. An anchor that matches twice plants more than the
    manifest says, so a CAUGHT row names the wrong cause. Both are silent, and both are the
    reason this is a test rather than a comment in a script.
    """
    counts = anchor_counts()
    assert counts, "the manifest is not empty"
    assert {name: count for name, count in counts.items() if count != 1} == {}, counts
    # And every replant names at least one test, so "caught" is a named failure rather than
    # any failure at all.
    assert all(replant.caught_by for replant in REPLANTS)


def test_every_replant_names_a_test_that_exists() -> None:
    """A citation that does not resolve is a claim, exactly as in a docstring."""
    from pathlib import Path

    tree = Path(__file__).resolve().parents[1]
    for replant in REPLANTS:
        for citation in replant.caught_by:
            path, _, name = citation.partition("::")
            source = (tree / path).read_text()
            assert f"def {name}(" in source, citation


@pytest.mark.replant
def test_the_replant_harness_tests_the_scratch_tree_and_not_the_real_one(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The trap three agents have hit, executed rather than avoided by care.

    The venv installs `mailweave` as an editable `.pth`, so a subprocess that merely prepends
    a `PYTHONPATH` can import the working tree's package and report every plant CAUGHT while
    the plants changed a copy nobody imported. Both `mailweave.__file__` and `tests.__file__`
    are asserted to resolve **inside** the scratch tree and **not** into the working tree; the
    second assertion is not redundant, because a scratch path underneath the working tree
    satisfies the first.
    """
    scratch = make_scratch_tree(tmp_path_factory.mktemp("replant-guard") / "tree")
    resolved = assert_imports_resolve_into_the_scratch_tree(scratch)
    # **Not a literal count.** Round 19 pinned this at two and it stopped covering what it
    # named the day `mailweave_harness` arrived; M1 would have repeated that with `orivra`.
    # The expected list is derived from the workspace, so a package that exists and is not
    # covered fails here rather than passing quietly.
    assert len(resolved) == len(importable_packages(scratch)), resolved
    for path in resolved:
        assert str(scratch) in path, path


@pytest.mark.replant
def test_every_behaviour_these_rounds_changed_fails_a_test_when_it_is_removed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The manifest, planted one at a time, each against the test named for it.

    Marked `replant` because it copies the tree and re-runs pytest once per entry. It is the
    evidence for the round's central claim, so it lives in the suite where the next round will
    find it rather than in a scratch script that will not survive the round.

    `run_replants` proves the copy sound before it plants anything - every test the manifest
    names passes on the pristine copy - so a CAUGHT row is a test that changed its mind rather
    than a test that was already failing (round 19, R-RETR-042).

    **Every citation is run alone and every one of them must fail** (R-RETR-061). Reading one
    return code over the whole `caught_by` list answers "did at least one of them catch",
    which is not what a citation claims - and two of round 21's citations named a test that
    caught nothing, which is how the vacuous commonality matrix went unnoticed for a round.
    """
    scratch = make_scratch_tree(tmp_path_factory.mktemp("replants") / "tree")
    missed = []
    for result in run_replants(scratch):
        assert result.anchor_matches == 1, result.replant.name
        assert result.file_changed, result.replant.name
        if not result.caught:
            missed.append(
                (
                    result.replant.name,
                    result.citations_that_do_not_catch,
                    result.replant.behaviour,
                    result.detail,
                )
            )
    assert missed == [], missed
