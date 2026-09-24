"""Orivra's budget is its own, and no figure ships before the milestone that measures it.

The rule under test is plan §2.3's, and it is a rule about *provenance* rather than about
numbers: `MAX_SERVER_MS = 7,700` was selected by owner decision for one Gmail search on one
connector, and treating it as though it covered three connectors, a model load, semantic
retrieval, reranking, freshness verification, graph construction and disclosure would repeat
R-RETR-065 exactly - a deadline never measured against the work it has to cover.

So M1 ships a budget in which **nothing binds**, and says so. That is deliberately
inconvenient and it is the honest state.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from mailweave.constants import MAX_SERVER_MS
from orivra.budget import (
    Measurement,
    OrivraBudget,
    Provenance,
    Stage,
    StageName,
    m1_budget,
)
from orivra.contracts import ConnectorId


def test_m1_ships_a_budget_in_which_nothing_binds() -> None:
    budget = m1_budget()
    assert budget.binding == ()
    assert len(budget.unmeasured) == len(StageName)


def test_every_unmeasured_stage_says_why_it_is_unmeasured() -> None:
    """An unmeasured stage is a normal state; a silent one is not."""
    for stage in m1_budget().unmeasured:
        assert stage.unmeasured_because
        assert stage.limit_ms is None


def test_a_stage_with_no_figure_and_no_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="no account of why"):
        Stage(name=StageName.GRAPH)


def test_retrieval_is_per_connector_and_every_other_stage_is_not() -> None:
    """One figure for every source is the assumption plan §2.3 exists to refuse."""
    with pytest.raises(ValidationError, match="per connector and names none"):
        Stage(name=StageName.RETRIEVAL, unmeasured_because="x")
    with pytest.raises(ValidationError, match="only retrieval_ms is per source"):
        Stage(name=StageName.GRAPH, connector=ConnectorId.GMAIL, unmeasured_because="x")


def test_a_budget_that_omits_a_stage_is_refused() -> None:
    """A stage left out of the object is a phase the response cannot declare."""
    partial = tuple(stage for stage in m1_budget().stages if stage.name is not StageName.GRAPH)
    with pytest.raises(ValidationError, match="omits"):
        OrivraBudget(stages=partial)


def test_two_figures_for_one_phase_are_refused() -> None:
    stage = Stage(name=StageName.GRAPH, unmeasured_because="no graph before M3")
    with pytest.raises(ValidationError, match="appears twice"):
        OrivraBudget(stages=(*m1_budget().stages, stage))


def test_a_selected_figure_may_record_that_its_rule_was_not_satisfied() -> None:
    """A13's own state: adopted by owner decision, formally not a passed validation."""
    selected = Measurement(
        milliseconds=MAX_SERVER_MS,
        measured_on=date(2026, 9, 10),
        provenance=Provenance.SELECTED,
        evidence=(
            "deadline run 3 declined: the 12,300 ms reference arm received "
            "upstream_rate_limited 403 responses, so the registered rule was not satisfied"
        ),
        adoptable=False,
    )
    assert selected.provenance is Provenance.SELECTED
    assert selected.adoptable is False


def test_a_declined_experiment_cannot_be_recorded_as_a_passed_validation() -> None:
    """The one direction that must never be writable: it is how a declined run becomes a
    passed one in the next reader's hands."""
    with pytest.raises(ValidationError, match="that is a selection, not a validation"):
        Measurement(
            milliseconds=7_700,
            measured_on=date(2026, 9, 10),
            provenance=Provenance.VALIDATED,
            evidence="run 3",
            adoptable=False,
        )


def test_orivras_budget_holds_no_copy_of_the_legacy_deadline() -> None:
    """The legacy path keeps 7,700 ms and Orivra does not inherit it. A copy here would be
    the inheritance plan §2.3 forbids, with the provenance left behind."""
    figures = {stage.limit_ms for stage in m1_budget().stages}
    assert figures == {None}
    assert MAX_SERVER_MS == 7_700
