"""Reasons for nodes **Orivra** puts in a graph, which MailWeave never returns a row for.

MailWeave's `envelope.reasons.Reason` is a closed discriminated union: one member per way a
*message row* came to be in a Gmail response, and every member's parameters are rendered
verbatim onto the disclosed wire (R-SEC-032). A `PERSON` node is not a message row, has no
rung, no query and no thread position, and MailWeave has no reason to describe one because
MailWeave never emits one.

**So the vocabulary is added here rather than there**, and the extension is deliberately the
smallest one that is accurate:

* MailWeave's `ReasonKind` is untouched. `ALL_REASON_KINDS` is unchanged, `MessageRow.reason`
  still accepts exactly the fourteen it always did, and the published `mailweave_*` tool
  schemas are byte-identical. A caller reading the Gmail tools sees no new vocabulary.
* `EvidenceNode.reason` widens to `Reason | GraphReason` - a union that is a superset in
  Orivra and nowhere else. The discriminator values cannot collide: every member here is
  namespaced `orivra.`, and no MailWeave kind carries a dot.
* The parameters take the same discipline as MailWeave's. An address is a string a sender
  influenced, so it goes through `ReasonScalar`'s single-line check rather than arriving as a
  free `str` - the field is on the same route to a reader that R-SEC-032 was filed about.

`tests/test_orivra_graph_reason_compat.py` holds all four of those claims, including the one
that matters most: a graph reason is **refused** by `MessageRow`, so widening Orivra's node
cannot widen MailWeave's wire by accident.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from mailweave.envelope.reasons import ReasonScalar, _ReasonBase
from orivra.contracts.vocab import GraphReasonKind


class ParticipantIn(_ReasonBase):
    """A person node: this address took part in this thread, in the roles named.

    `roles` is what the thread's own participant index recorded - authored, addressed,
    copied - and not an interpretation of them. The address is the identity and the display
    name is not: a display name is free text a sender typed, which is the whole reason
    `ThreadParticipant` is keyed on the addr-spec.
    """

    kind: Literal[GraphReasonKind.PARTICIPANT_IN] = GraphReasonKind.PARTICIPANT_IN
    address: ReasonScalar
    thread_id: ReasonScalar
    roles: tuple[ReasonScalar, ...] = ()

    def render(self) -> str:
        where = ", ".join(self.roles) if self.roles else "took part"
        return f"{self.address} in thread {self.thread_id}: {where}"


GraphReason = Annotated[ParticipantIn, Field(discriminator="kind")]

#: Every kind this module defines, for the compatibility sweep that asserts disjointness.
ALL_GRAPH_REASON_KINDS: frozenset[GraphReasonKind] = frozenset(GraphReasonKind)

__all__ = ["ALL_GRAPH_REASON_KINDS", "GraphReason", "ParticipantIn"]
