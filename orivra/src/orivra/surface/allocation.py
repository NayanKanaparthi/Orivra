"""How much of the host's result cap MailWeave's container may have.

**The defect this exists for.** `orivra_ask` composes two things: MailWeave's container, built
by MailWeave's disclosure ladder, and Orivra's own block - the query id, the per-source spend,
the stage budget, the graph entry and the link to the whole graph. The ladder fits the
container to `HOST_RESULT_CHAR_CAP`, because on `mailweave_search`'s own path that is exactly
right: the container *is* the response. Inside `orivra_ask` it is not. Orivra's block then
spends characters the ladder had already promised away, the composed result goes over the cap,
and it is refused - reachable, as a live Claude Desktop run showed on 2026-09-19, from
`orivra_ask({"query": "..."})` with no arguments at all.

`service.py::_too_large` described the mechanism correctly and drew the wrong conclusion from
it: it treated "the container was fitted to the cap and Orivra's block spends the same
characters" as a fact to report in a refusal, rather than as an allocation nobody had made.

**What this module does.** It makes the allocation, before the container is built, and it does
it by *rendering* rather than by guessing. `reserve_for` composes a probe block out of the real
fields, at the widths they can actually reach, and measures it with the same two renderers the
response itself uses - `json.dumps` for the structured half and `OrivraResponse.text()` for the
text half. A field added to the block, or a stage added to the budget, changes the reserve on
the next call without anybody remembering to update a number, because the number is the
measurement of the thing itself.

**The reserve is an estimate; the guarantee is elsewhere.** A probe cannot be a proven upper
bound on the graph entry, because `caps_hit` is documented as open-ended names rather than a
closed enum and a graph's omission list has no fixed length. So this module does not claim one.
It makes the reserve tight enough that the ordinary answer is served whole, and
`service.ask` enforces the invariant by measuring the composed response and compacting its own
block - never the evidence - until it fits. An estimate that is occasionally low costs a
compaction, which is declared and recoverable. An estimate that is absent costs a refusal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.reasons import RungId
from orivra.contracts import ConnectorId, OrivraToolName
from orivra.surface.projection import OrivraResponse

#: Characters allowed per connector row for `caps_hit`, whose names are **not** a closed enum
#: (`contracts/trace.py` says so and gives the reason: a union enum over three sources would
#: have to be edited for every connector). `rungs_executed` needs no such allowance because
#: `RungId` *is* closed and the probe below carries every member of it.
CAPS_HIT_ALLOWANCE: Final[int] = 48

#: Characters allowed for the compact graph entry - the form `service.ask` falls back to when
#: the built block will not fit. Its shape is fixed (built, holds_evidence, counts, seeds,
#: routing, the compaction record and its executable calls) and this is measured against that
#: shape by `test_the_reserve_covers_the_compact_entry_it_promises`, so it is an allowance with
#: a test behind it rather than a number somebody liked.
GRAPH_ENTRY_ALLOWANCE: Final[int] = 700

#: What a response is left with if the reserve ever swallowed the whole cap. Not a policy
#: figure: a guard, so a mistake here shows up as a refusal naming this module rather than as
#: a container asked to fit in nothing.
MIN_CONTAINER_CHARS: Final[int] = 4_000


@dataclass(frozen=True)
class Allocation:
    """The split of one host result between MailWeave's container and Orivra's block."""

    #: The host's cap. Never moved by anything here.
    cap: int
    #: What Orivra's own block is expected to spend, across both projections.
    reserve: int
    #: What the container is told it has. `cap - reserve`.
    container: int

    def declaration(self) -> dict[str, Any]:
        """What the response says about its own sizing, in the response.

        **Declared on every answer, not only a narrowed one.** A caller comparing this against
        `mailweave_search` needs to know the two were fitted to different rooms whether or not
        the difference happened to change the evidence this time; a declaration that appears
        only when it bites is a declaration you cannot rely on the absence of.
        """
        return {
            "host_cap_chars": self.cap,
            "orivra_reserve_chars": self.reserve,
            "container_chars": self.container,
            "why": (
                "container fitted to the room left after Orivra's block, not the whole cap, "
                "so both fit. mailweave_search gets the whole cap and may disclose more; any "
                "difference is accounted in this response's omission records"
            ),
        }


def _probe_source_row(connector: ConnectorId) -> dict[str, Any]:
    """One per-source row at the width it can reach.

    Every rung, because `RungId` is closed and a query may execute all of them; a `caps_hit`
    filled to `CAPS_HIT_ALLOWANCE`, because those names are not closed and cannot be counted.
    The numeric fields are given nine digits, which is more quota units than a query can spend
    and costs eight characters to be sure of.
    """
    return {
        "connector": connector.value,
        "state": "ready",
        "asked": True,
        "hits": 999_999_999,
        "quota_units": 999_999_999,
        "rungs_executed": [rung.value for rung in RungId],
        "caps_hit": ["c" * CAPS_HIT_ALLOWANCE],
    }


def reserve_for(
    *,
    query_id: str,
    budget: dict[str, Any],
    connectors: tuple[ConnectorId, ...],
    resource_link: str,
    with_graph: bool,
) -> int:
    """What Orivra's block is expected to spend on this call, measured rather than assumed.

    Rendered through both projections, because both are handed to the host and the cap is over
    the pair. `with_graph` is false for a routing decision that builds none: a response whose
    graph block is `{"built": false, "routing": ...}` should not reserve room for an entry it
    will not carry, and handing the container that room back is the difference between a whole
    answer and a narrowed one on a query the graph was never going to help.
    """
    body: dict[str, Any] = {
        "query_id": query_id,
        "per_source": [_probe_source_row(connector) for connector in connectors],
        # **The digest, not the full stage payload.** The reserve is what the block costs in
        # its *compacted* form, because compaction is what `service.ask` guarantees and the
        # full form is what it serves when there happens to be room. Reserving the full form
        # instead would hold back ~1,200 characters on every call for something the response
        # is willing to give up first - and `mailweave`'s ladder is quantised finely enough
        # that those characters are sometimes the difference between five messages and none.
        "budget": budget,
        "allocation": Allocation(cap=HOST_RESULT_CHAR_CAP, reserve=0, container=0).declaration(),
    }
    if with_graph:
        body["graph"] = {"entry": "g" * GRAPH_ENTRY_ALLOWANCE}
        body["resource_link"] = resource_link
    else:
        body["graph"] = {"built": False, "routing": "r" * 200}
    text = OrivraResponse(tool=OrivraToolName.ASK, body=body, mirror="").text()
    return len(json.dumps(body, default=str)) + len(text)


def allocate(
    *,
    query_id: str,
    budget: dict[str, Any],
    connectors: tuple[ConnectorId, ...],
    resource_link: str,
    with_graph: bool,
    cap: int = HOST_RESULT_CHAR_CAP,
) -> Allocation:
    """The split, for one call.

    The cap does not move. The container gets what is left, and `MIN_CONTAINER_CHARS` is a
    floor on that rather than on the reserve: if the block's own accounting ever grew to the
    point of crowding out the evidence, the right failure is a container too small to fill -
    which `mailweave`'s ladder declines in band, naming its own arithmetic - and not a silently
    shrinking answer.
    """
    reserve = reserve_for(
        query_id=query_id,
        budget=budget,
        connectors=connectors,
        resource_link=resource_link,
        with_graph=with_graph,
    )
    container = max(MIN_CONTAINER_CHARS, cap - reserve)
    return Allocation(cap=cap, reserve=reserve, container=container)


__all__ = [
    "CAPS_HIT_ALLOWANCE",
    "GRAPH_ENTRY_ALLOWANCE",
    "MIN_CONTAINER_CHARS",
    "Allocation",
    "allocate",
    "reserve_for",
]
