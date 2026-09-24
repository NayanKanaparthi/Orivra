"""The acceptance test for A9-A2: a newly registered operator is covered, with no test edited.

R-RETR's method, run against this round's code. Round 18's region predicate asked how a token
was spelled, so registering a region-selecting operator left the whole suite green while every
probe dropped it, L2 relaxed it away and L3 widened out of it (R-RETR-036). Round 19 puts the
question to `KIND_BY_OPERATOR`, which is where an operator's behaviour is registered, so the
claim to test is that the registration alone is enough.

Both halves run, and the control is not decoration: a fix that classified *every* operator as a
region would pass the first half and destroy the ladder's recovery, which is what the second
half fails on.

Marked `replant` because each half copies the tree and runs pytest in a subprocess.
"""

from __future__ import annotations

import pytest

from tests.fixtures.new_operator import (
    FILTER_OPERATOR,
    FILTER_PROBE,
    SCOPE_OPERATOR,
    SCOPE_PROBE,
    register_and_check,
)

#: The modules that decide the region asymmetry and the ladder's behaviour. Running these in
#: the planted tree is what says "no test had to be edited": they are the ones whose oracles a
#: fix by enumeration would have had to grow.
SWEEPS = [
    "tests/test_lexical_ladder.py",
    "tests/test_region_kind_round19.py",
    "tests/test_region_and_provenance_round18.py",
    "tests/test_query_analysis.py",
]


@pytest.mark.replant
def test_a_newly_registered_region_operator_is_covered_without_editing_a_test(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Register `mailbox:` with `OperatorKind.REGION` and ask whether it is preserved.

    The assertions live in `SCOPE_PROBE` and are about the new operator alone: it is read as a
    region declaration in both polarities, every probe of every rung carries it, no probe sets
    `includeSpamTrash`, and no rung widens the query to the whole mailbox. Nothing in the tree
    names `mailbox:`; the sweeps that cover it are generated from the registry.
    """
    behaviour, summary = register_and_check(
        tmp_path_factory.mktemp("new-scope-operator") / "tree", SCOPE_OPERATOR, SCOPE_PROBE, SWEEPS
    )
    assert behaviour.startswith("SCOPE OPERATOR COVERED"), behaviour
    assert "failed" not in summary, summary


@pytest.mark.replant
def test_a_newly_registered_filtering_operator_is_still_a_filter(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The control: `priority:` with `OperatorKind.TEXT` stays relaxable, droppable, broadenable.

    Round 18 got this half right - which is what established that the machinery worked and its
    input was wrong - and it is asserted here so that this round cannot pass its other half by
    making everything a region.
    """
    behaviour, summary = register_and_check(
        tmp_path_factory.mktemp("new-filter-operator") / "tree",
        FILTER_OPERATOR,
        FILTER_PROBE,
        SWEEPS,
    )
    assert behaviour.startswith("FILTER OPERATOR COVERED"), behaviour
    assert "failed" not in summary, summary
