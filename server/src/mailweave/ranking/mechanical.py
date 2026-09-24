"""`mailweave/mechanical-v1`: the deterministic ranking that always runs (AD D.7, RANK-03).

**Two tiers, and this is the one with no model in it.** D.7: "Mechanical ranking runs
whenever more than one candidate is disclosed. Deterministic composite over structural
signals; `score.method = "mailweave/mechanical-v1"` with the firing components listed.
Reproducible given the same inputs (C-04b)." Everything below is a set intersection, an
integer comparison or a table lookup; nothing reads a model, an embedding or a corpus.

**Why the components are an enum with published integer weights.** The same argument
`disclosure.weights` makes for the E4 fill, one layer out: a weight that can move is a
weight that can be tuned to a benchmark, and a composite whose components are prose is a
composite nobody can check. The reason string a ranked candidate carries is built from the
enum, so a component added later has to be given a weight, a name and a reason in one edit.

**What this ranks, and what it does not.** It ranks *candidates the response will disclose*
against each other - today, threads. It does not decide what is disclosed (A.9a's ladder
does) and it does not decide what is in `H` (the ladder and the shortlist do). A ranking
that could remove a candidate would be a disclosure policy wearing a ranking's name.

**A row Gmail's `q` selected carries no numeric score** (D.7). That rule is not enforced
here because it cannot be: this module computes an ordering over candidates, and whether a
candidate's *row* carries a `Score` is `assemble`'s decision. It is stated here because the
number this module produces is the one that would be wrong to attach.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

#: The method string every mechanical score carries. A constant so the wire and this module
#: cannot drift; D.7 names this exact spelling.
MECHANICAL_METHOD: Final[str] = "mailweave/mechanical-v1"


class RankComponent(StrEnum):
    """D.6's structural signals, as the ranking's components."""

    #: The candidate carries a message the query's own routes admitted as a hit.
    QUERY_HIT = "query_hit"
    #: More than one of this candidate's messages was admitted: concentration of evidence.
    HIT_CONCENTRATION = "hit_concentration"
    #: An address the query named appears on this candidate's own headers (C-02b, STR-02).
    PARTICIPANT_MATCH = "participant_match"
    #: The candidate's newest message lies inside the window the query parsed (A.6a rule 4).
    INSIDE_QUERY_WINDOW = "inside_query_window"
    #: The candidate was reached by a rung that enforced every constraint of the query.
    UNRELAXED_ROUTE = "unrelaxed_route"


#: Published weights, small integers so ties are exact rather than float-adjacent - the
#: same reasoning `E4_WEIGHTS` gives. Ordered by how query-driven the component is: a
#: component that fires identically for every query against a mailbox may break a tie and
#: may never by itself order one candidate ahead of another the query reached.
MECHANICAL_WEIGHTS: Final[Mapping[RankComponent, int]] = {
    RankComponent.QUERY_HIT: 5,
    RankComponent.UNRELAXED_ROUTE: 4,
    RankComponent.PARTICIPANT_MATCH: 3,
    RankComponent.INSIDE_QUERY_WINDOW: 2,
    RankComponent.HIT_CONCENTRATION: 1,
}


@dataclass(frozen=True)
class Candidate:
    """One thing to be ranked, projected down to the facts the components read.

    Every field is something an observation stated or a rung recorded. Nothing here is text
    and nothing here is derived from a model, which is what makes the score reproducible
    from the response itself (C-04b).
    """

    key: str
    hit_messages: int = 0
    participant_match: bool = False
    inside_query_window: bool = False
    unrelaxed_route: bool = False


@dataclass(frozen=True)
class Ranked:
    """One ranked candidate: its value, the components that fired, and the sentence."""

    key: str
    value: int
    components: tuple[RankComponent, ...]

    @property
    def basis(self) -> str:
        """What this number was computed from - the `basis` every numeric score carries.

        Named components rather than "structural signals", because `basis` exists so a
        reader can tell two scores apart, and every mechanical score would otherwise carry
        the same sentence.
        """
        if not self.components:
            return "no mechanical component fired"
        return "structural signals: " + ", ".join(component.value for component in self.components)


def _components_of(candidate: Candidate) -> tuple[RankComponent, ...]:
    fired: list[RankComponent] = []
    if candidate.hit_messages >= 1:
        fired.append(RankComponent.QUERY_HIT)
    if candidate.unrelaxed_route:
        fired.append(RankComponent.UNRELAXED_ROUTE)
    if candidate.participant_match:
        fired.append(RankComponent.PARTICIPANT_MATCH)
    if candidate.inside_query_window:
        fired.append(RankComponent.INSIDE_QUERY_WINDOW)
    if candidate.hit_messages >= 2:
        fired.append(RankComponent.HIT_CONCENTRATION)
    return tuple(fired)


def mechanical_rank(candidates: Sequence[Candidate]) -> tuple[Ranked, ...]:
    """Rank `candidates`, highest first, ties broken by key.

    **The tie-break is part of the contract, not a detail.** Two candidates on which the
    same components fire are genuinely indistinguishable to this ranking, and an order that
    depended on input order would make the response's ordering a fact about dictionary
    iteration. C-04b asks for reproducibility given the same inputs; a total order is what
    that means when the inputs tie.

    **Runs whatever the candidate count is, and says nothing when there is one.** D.7 scopes
    mechanical ranking to "more than one candidate disclosed"; a single candidate has no
    ordering to state, and this returns its score anyway so the caller decides whether a
    number that orders nothing belongs on the wire.
    """
    ranked = [
        Ranked(
            key=candidate.key,
            value=sum(MECHANICAL_WEIGHTS[component] for component in _components_of(candidate)),
            components=_components_of(candidate),
        )
        for candidate in candidates
    ]
    return tuple(sorted(ranked, key=lambda row: (-row.value, row.key)))


__all__ = [
    "MECHANICAL_METHOD",
    "MECHANICAL_WEIGHTS",
    "Candidate",
    "RankComponent",
    "Ranked",
    "mechanical_rank",
]
