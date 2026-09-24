"""Orivra's hierarchical budget: its own, measured, and never inherited (plan §2.3).

`MAX_SERVER_MS = 7,700` was selected by owner decision for **one Gmail search on one
connector** (amendment A13, adopted 2026-09-10). It does not cover three connectors, a cold
local model load, semantic retrieval, reranking, freshness verification, graph construction
and disclosure. Assuming it did would repeat R-RETR-065 exactly: a deadline never measured
against the work it has to cover.

So there are two budgets in this repository and they do not touch.

* **The legacy path keeps 7,700 ms, unchanged.** `mailweave_search` and its three siblings
  enforce it inside `MailweaveService`, and nothing here alters that.
* **Orivra has a stage per phase that can consume wall time**, and every figure starts as
  `None`. A `None` stage does not bind: it is declared unmeasured in the response rather
  than defaulted to something plausible.

**No Orivra deadline constant ships before the milestone that measures it.** `Stage` is
therefore not a bare integer but a figure plus its provenance - the date, the evidence, and
whether it was *validated* by a pre-registered run or *selected* by an owner decision, which
are different things and were confused once already (A13's own record says so). A figure with
no provenance is refused at construction, which is the mechanical form of that rule.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from orivra.contracts.refs import Frozen
from orivra.contracts.vocab import ConnectorId


class StageName(StrEnum):
    """The phases that can consume wall time, one entry per row of plan §2.3's table."""

    COLD_START = "cold_start_ms"
    RETRIEVAL = "retrieval_ms"
    SEMANTIC = "semantic_ms"
    RERANK = "rerank_ms"
    FRESHNESS = "freshness_ms"
    GRAPH = "graph_ms"
    DISCLOSURE = "disclosure_ms"
    RECOVERY = "recovery_ms"


class Provenance(StrEnum):
    """How a figure came to be, kept apart because A13 showed the two get confused.

    `VALIDATED` - a pre-registered experiment ran and its decision rule was satisfied.
    `SELECTED` - an owner chose it, on evidence, with the validation formally not passed.
    A `SELECTED` figure is not a passed validation and the record must never read as one.
    """

    VALIDATED = "validated"
    SELECTED = "selected"


class Measurement(Frozen):
    """What a figure is made of. A figure with none of this is not a deadline."""

    milliseconds: int = Field(gt=0)
    measured_on: date
    provenance: Provenance
    evidence: str = Field(min_length=1, max_length=600)
    """What was run, over what, and what it showed. A sentence, not a citation."""

    adoptable: bool
    """Whether the pre-registered decision rule was actually satisfied.

    `False` with `provenance: SELECTED` is a legitimate and recorded state - it is A13's -
    and it is here so a later reader cannot mistake the adoption for a passed validation."""

    @model_validator(mode="after")
    def _a_validated_figure_is_one_whose_rule_was_satisfied(self) -> Self:
        if self.provenance is Provenance.VALIDATED and not self.adoptable:
            raise ValueError(
                "a figure marked validated records that its decision rule was not satisfied; "
                "that is a selection, not a validation, and writing it as one is how a "
                "declined experiment becomes a passed one in the next reader's hands"
            )
        return self


class Stage(Frozen):
    """One budget stage: a name, an optional figure, and why it is absent when it is."""

    name: StageName
    connector: ConnectorId | None = None
    """Set for `retrieval_ms`, which is per connector. `None` for the stages that are not."""

    measurement: Measurement | None = None
    unmeasured_because: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _an_absent_figure_says_why(self) -> Self:
        if self.measurement is None and not self.unmeasured_because:
            raise ValueError(
                f"stage {self.name.value} has no figure and no account of why; an unmeasured "
                "stage is a normal state and a silent one is not - the response declares it"
            )
        if self.measurement is not None and self.unmeasured_because:
            raise ValueError(
                f"stage {self.name.value} carries both a figure and a reason it has none"
            )
        if self.name is StageName.RETRIEVAL and self.connector is None:
            raise ValueError(
                "retrieval_ms is per connector and names none; one figure for every source "
                "is the assumption plan §2.3 exists to refuse"
            )
        if self.name is not StageName.RETRIEVAL and self.connector is not None:
            raise ValueError(
                f"stage {self.name.value} names a connector; only retrieval_ms is per source"
            )
        return self

    @property
    def binds(self) -> bool:
        """Whether this stage can stop anything. An unmeasured stage never does."""
        return self.measurement is not None

    @property
    def limit_ms(self) -> int | None:
        return None if self.measurement is None else self.measurement.milliseconds


#: The reason every M1 stage carries, in one place so the wording cannot drift per stage.
#:
#: **Terse on purpose, and the terseness is a sizing decision** (2026-09-19). These strings
#: travel inside every `orivra_ask` response, in both projections, and they are the largest
#: fixed item in Orivra's block: 697 of the budget payload's 1,425 characters were prose here.
#: Every character of that is a character `surface/allocation.py` must reserve and therefore a
#: character the Gmail container does not get to spend on evidence. Each line below still says
#: which stage, why there is no figure, and what would produce one - the whole of what the
#: accounting owes a reader - in a sentence rather than a paragraph. Nothing was moved to
#: another call to be fetched: an accounting record that needs a second round trip is not one
#: a reader has.
_NOT_YET: dict[StageName, str] = {
    StageName.COLD_START: ("M1 measures token refresh only; the model-load figure ships with M2"),
    StageName.RETRIEVAL: (
        "delegated to MailweaveService, which enforces MAX_SERVER_MS = 7,700 ms; a per-"
        "connector figure needs measuring on Orivra's path, not inheriting A13's"
    ),
    StageName.SEMANTIC: "no semantic stage exists before M2",
    StageName.RERANK: "no reranker exists before M2",
    StageName.FRESHNESS: "no change-feed walk runs on Orivra's path before M2",
    # **These two were wrong, not merely long** (2026-09-19). They said the graph and
    # `orivra_expand` arrive with M3; M3 shipped both, and the strings went on telling readers
    # the opposite inside every response that carried a graph. What is true is narrower and is
    # what they now say: the stage exists and its cost is not separately budgeted yet.
    StageName.GRAPH: "the query graph is built; its cost is not yet budgeted as its own stage",
    StageName.DISCLOSURE: (
        "the A.9a ladder runs inside MailweaveService, charged to the legacy deadline; a "
        "separable figure needs a disclosure stage Orivra drives"
    ),
    StageName.RECOVERY: ("orivra_expand ships; its cost is not yet budgeted as its own stage"),
}


class OrivraBudget(Frozen):
    """Every stage, in one object, so a response can declare all of them.

    A caller reading this sees which stages bound the answer and which were never measured -
    and the second list is the interesting one, because a stage that does not bind is a
    stage whose cost nobody yet accounts for.
    """

    stages: tuple[Stage, ...]

    @model_validator(mode="after")
    def _every_stage_appears_once_per_scope(self) -> Self:
        seen = [(stage.name, stage.connector) for stage in self.stages]
        if len(set(seen)) != len(seen):
            raise ValueError(
                "a budget stage appears twice for one scope; two figures for one phase are "
                "two deadlines, and the one that binds is whichever is checked first"
            )
        covered = {stage.name for stage in self.stages}
        missing = sorted(name.value for name in StageName if name not in covered)
        if missing:
            raise ValueError(
                f"the budget omits {missing}; a stage left out of the object is a phase the "
                "response cannot declare, which is the silence plan §2.3 forbids"
            )
        return self

    @property
    def binding(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.stages if stage.binds)

    @property
    def unmeasured(self) -> tuple[Stage, ...]:
        return tuple(stage for stage in self.stages if not stage.binds)


def m1_budget(*, connectors: tuple[ConnectorId, ...] = (ConnectorId.GMAIL,)) -> OrivraBudget:
    """The budget M1 ships: every stage present, every figure `None`, every absence stated.

    This is the honest shape at this milestone and it is deliberately inconvenient - nothing
    here can stop a slow query, and the response says so. The alternative was to reuse 7,700
    ms as though it covered Orivra's path, which is the assumption plan §2.3 was written to
    refuse.
    """
    stages = [
        Stage(
            name=StageName.RETRIEVAL,
            connector=connector,
            unmeasured_because=_NOT_YET[StageName.RETRIEVAL],
        )
        for connector in connectors
    ]
    stages += [
        Stage(name=name, unmeasured_because=_NOT_YET[name])
        for name in StageName
        if name is not StageName.RETRIEVAL
    ]
    return OrivraBudget(stages=tuple(stages))


__all__ = [
    "Measurement",
    "OrivraBudget",
    "Provenance",
    "Stage",
    "StageName",
    "m1_budget",
]
