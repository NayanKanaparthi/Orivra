"""Observed edges: the relations a Gmail response *states*, never ones it suggests.

Four relations come out of one `Envelope` and no others:

* `obs.meta.reply_to` - from `MessageRow.linkage` and `reply_parent_id`.
* `obs.meta.thread_member` - from the thread each row was returned in.
* `obs.meta.authored_by` / `obs.meta.sent_to` - from `Source.participants`.

The participant half needs a `PERSON` node, and a node needs a reason. That reason is
`orivra.contracts.reasons.ParticipantIn` and **not** a new member of MailWeave's sealed
`ReasonKind`: a person is not a message row, MailWeave never returns one, and widening the
Gmail wire's vocabulary to describe a node only Orivra builds would move schemas that have no
stake in it. The two vocabularies are disjoint by namespace and the compatibility tests hold
that.

The address is the identity and the display name is not. `ThreadParticipant` is keyed on the
addr-spec precisely because a display name is free text a sender typed, so `From: "Ana Lee"
<mallory@elsewhere.invalid>` is one person here - the one who actually sent it.

**The one that is deliberately absent is the interesting one.** `Linkage.NO_REPLY_HEADERS`
is spelled "date-adjacent (no RFC reply headers)": MailWeave found no `In-Reply-To` and no
`References`, and the row sits next to another row in time. Contract C-02a forbids exactly
the inference a reader makes from that - *a row printed after another is a reply to it* - so
this module emits **no edge at all** for it. It cannot be rescued as an inferred edge either:
an inferred relation must quote spans, and there is nothing to quote; date adjacency is not
something a message said.

That absence is not silence. `observed_edges` returns the rows whose parent was not
determined, per thread, so the graph can account for them rather than let a reader conclude
from a flat thread that every message stood alone.

Every edge here is metadata, so by the edge model's own reading of the relation it carries no
spans and no confidence. A quotation attached to a header field invites a reader to check the
fact against text that did not produce it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, Linkage, Role
from mailweave.envelope.wire import Source
from orivra.contracts import (
    DerivationMethod,
    EvidenceEdge,
    EvidenceNode,
    FreshnessStatus,
    NodeKind,
    ParticipantIn,
    RefKind,
    Relation,
    SourceReference,
    requirements_of,
)

#: The linkages that are a **found parent**, and therefore an edge. `MessageRow`'s own
#: validator holds `reply_parent_id` non-`None` to exactly these two, so this set and that
#: rule cannot drift apart without the row failing first.
LINKED: frozenset[Linkage] = frozenset({Linkage.IN_REPLY_TO, Linkage.REFERENCES})

#: One method per relation, versioned, so a graph read back later says which rule drew it.
#: The names are the *observation* the edge came from rather than a description of the
#: relation, because that is the thing a reader can go and check.
OBSERVED_METHODS: dict[Relation, DerivationMethod] = {
    Relation.REPLY_TO: DerivationMethod(name="metadata/rfc5322_reply_headers", version="1"),
    Relation.THREAD_MEMBER: DerivationMethod(name="metadata/threads_get_membership", version="1"),
    Relation.AUTHORED_BY: DerivationMethod(name="metadata/participant_authored", version="1"),
    Relation.SENT_TO: DerivationMethod(name="metadata/participant_addressed", version="1"),
}


class References(Protocol):
    """The one thing this module needs from an adapter: a reference for a native id.

    A `Protocol` rather than an import of `GmailAdapter`, because the graph is built over
    contracts and taking the concrete adapter here would make the package Gmail-shaped for
    no gain - M4 and M5 are out of this release's scope but they are not out of the design's.
    """

    def reference(self, native_id: str, *, kind: RefKind = ...) -> SourceReference: ...


@dataclass(frozen=True)
class UndeterminedParent:
    """A row whose reply parent this response could not establish, and why.

    Carried out of the builder rather than logged, because a thread rendered with no reply
    edges and no note reads as a thread of unrelated messages. What a reader does with this
    is an `OmissionRecord`; what this module knows is which rows and which gap.
    """

    message_id: str
    thread_id: str
    linkage: Linkage
    #: Where the row sat in the order this response returned, and whether that order was the
    #: whole thread. Together they are the only honest way to separate the two things a
    #: missing parent can mean - see `explained_by_being_first`.
    position: int = 0
    thread_complete: bool = False

    @property
    def explained_by_being_first(self) -> bool:
        """Whether "no parent" is the expected answer rather than a gap in what was observed.

        The first message of a thread has no parent and never did, so reporting it beside a
        broken reply chain as the same fact would bury the one a reader can act on under one
        nobody needs to. But "first" is only knowable when the response holds the **whole**
        thread: in a truncated one, the earliest row returned may have a parent that was
        simply not fetched, and calling that a thread start would be the response explaining
        away a gap with a fact it does not have.

        So both halves are required, and when the thread is incomplete this stays `False`
        and the row is reported as the gap it may well be.
        """
        return self.position == 0 and self.thread_complete


@dataclass(frozen=True)
class ObservedEdges:
    """What one response's metadata produced, and what it could not."""

    #: Person nodes this module minted. Message and thread nodes come from the adapter, which
    #: already builds them from the response's own rows; these are the ones that exist only
    #: because a graph was asked for.
    nodes: tuple[EvidenceNode, ...] = ()
    edges: tuple[EvidenceEdge, ...] = ()
    undetermined: tuple[UndeterminedParent, ...] = ()
    #: Reply edges this response *would* have drawn and did not, because the named parent is
    #: not a row this response holds. Distinct from `undetermined`: the parent was identified,
    #: it is simply outside the graph, and an edge to a node the graph does not hold is
    #: refused by `QueryGraph` itself. A different fact, and a different recovery.
    parent_outside_graph: tuple[UndeterminedParent, ...] = field(default=())


def _edge(
    *,
    edge_id: str,
    source: str,
    target: str,
    relation: Relation,
    support: Sequence[SourceReference],
    freshness: FreshnessStatus,
) -> EvidenceEdge:
    """One metadata edge, with its conjunction **derived** from its own support.

    `requires` is never typed out here. The edge model re-derives it and refuses a mismatch,
    so a hand-written conjunction could only ever be right by accident or wrong by omission -
    and the failure mode of getting it wrong is a second source's requirement quietly
    ceasing to be asked about.
    """
    references = tuple(support)
    return EvidenceEdge(
        edge_id=edge_id,
        source=source,
        target=target,
        relation=relation,
        support=references,
        method=OBSERVED_METHODS[relation],
        requires=requirements_of(references),
        freshness=freshness,
    )


def _reply_edges(
    source: Source,
    *,
    held: frozenset[str],
    adapter: References,
    freshness: FreshnessStatus,
) -> tuple[list[EvidenceEdge], list[UndeterminedParent], list[UndeterminedParent]]:
    edges: list[EvidenceEdge] = []
    undetermined: list[UndeterminedParent] = []
    outside: list[UndeterminedParent] = []
    # Complete as the source itself reports it, which is the only completeness this response
    # has. A thread Gmail says has eleven messages and returned eleven rows for is whole; one
    # the ladder cut to five is not, and its earliest row's missing parent is a real gap.
    complete = source.included == source.stated_total
    for row in source.messages:
        if row.linkage not in LINKED or row.reply_parent_id is None:
            undetermined.append(
                UndeterminedParent(
                    message_id=row.id,
                    thread_id=source.thread_id,
                    linkage=row.linkage,
                    position=row.position,
                    thread_complete=complete,
                )
            )
            continue
        if row.reply_parent_id not in held:
            outside.append(
                UndeterminedParent(
                    message_id=row.id,
                    thread_id=source.thread_id,
                    linkage=row.linkage,
                    position=row.position,
                    thread_complete=complete,
                )
            )
            continue
        child = adapter.reference(row.id)
        parent = adapter.reference(row.reply_parent_id)
        edges.append(
            _edge(
                edge_id=f"obs.meta.reply_to/{row.id}->{row.reply_parent_id}",
                source=f"gmail/message/{row.id}",
                target=f"gmail/message/{row.reply_parent_id}",
                relation=Relation.REPLY_TO,
                support=(child, parent),
                freshness=freshness,
            )
        )
    return edges, undetermined, outside


def _membership_edges(
    source: Source, *, adapter: References, freshness: FreshnessStatus
) -> list[EvidenceEdge]:
    thread = adapter.reference(source.thread_id, kind=RefKind.THREAD)
    return [
        _edge(
            edge_id=f"obs.meta.thread_member/{row.id}",
            source=f"gmail/message/{row.id}",
            target=f"gmail/thread/{source.thread_id}",
            relation=Relation.THREAD_MEMBER,
            support=(adapter.reference(row.id), thread),
            freshness=freshness,
        )
        for row in source.messages
    ]


def _person_node_id(address: str) -> str:
    return f"gmail/person/{address}"


#: Which participant-index field feeds which relation, and the role word that goes in the
#: node's reason. `reply_to` and `mentioned` are deliberately absent: a `Reply-To` header is a
#: routing instruction rather than a statement that the address took part, and a mention is
#: something a *body* says, which makes it content the stated-assertion gates own rather than
#: metadata this module may read.
_PARTICIPANT_RELATIONS: tuple[tuple[Relation, str], ...] = (
    (Relation.AUTHORED_BY, "authored"),
    (Relation.SENT_TO, "addressed"),
)


def _participant_nodes(
    source: Source,
    *,
    held: frozenset[str],
    adapter: References,
    freshness: FreshnessStatus,
) -> dict[str, EvidenceNode]:
    """One node per address that touched a row **this response returned**.

    Scoped to held rows on purpose. The participant index names every message an address
    touched in the thread, including ones the disclosure ladder withheld, so an unscoped node
    would carry a role earned entirely by messages the caller was not shown - and its edges
    would then have nowhere to land.
    """
    nodes: dict[str, EvidenceNode] = {}
    for participant in source.participants:
        roles = tuple(
            role
            for _relation, role in _PARTICIPANT_RELATIONS
            if held & frozenset(getattr(participant, role))
        )
        if not roles:
            continue
        nodes[participant.address] = EvidenceNode(
            node_id=_person_node_id(participant.address),
            ref=adapter.reference(participant.address, kind=RefKind.PERSON),
            kind=NodeKind.PERSON,
            role=Role.CONTEXT,
            reason=ParticipantIn(
                address=participant.address, thread_id=source.thread_id, roles=roles
            ),
            depth=Depth.STUB,
            freshness=freshness,
        )
    return nodes


def _participant_edges(
    source: Source,
    *,
    held: frozenset[str],
    people: frozenset[str],
    adapter: References,
    freshness: FreshnessStatus,
) -> list[EvidenceEdge]:
    edges: list[EvidenceEdge] = []
    for participant in source.participants:
        if participant.address not in people:
            continue
        person = adapter.reference(participant.address, kind=RefKind.PERSON)
        person_id = _person_node_id(participant.address)
        for relation, role in _PARTICIPANT_RELATIONS:
            for message_id in sorted(frozenset(getattr(participant, role)) & held):
                edges.append(
                    _edge(
                        edge_id=f"{relation.value}/{message_id}->{participant.address}",
                        source=f"gmail/message/{message_id}",
                        target=person_id,
                        relation=relation,
                        support=(adapter.reference(message_id), person),
                        freshness=freshness,
                    )
                )
    return edges


def _held_ids(sources: Sequence[Source]) -> frozenset[str]:
    """Every message id this response actually returned a row for, at any depth.

    A stub row is held: it is a node the graph may point at, and pointing at it discloses
    nothing the response has not already disclosed. A message that appears only inside an
    omission record is not held, and no edge may name it.
    """
    return frozenset(row.id for source in sources for row in source.messages)


def observed_edges(
    envelope: Envelope,
    *,
    adapter: References,
    freshness: FreshnessStatus,
    people: bool = True,
) -> ObservedEdges:
    """Every relation this response's metadata states, plus the parents it could not state.

    `people` is a knob rather than an assumption. Person nodes are what let a graph join two
    threads that share nobody's reply chain, which is the point on a decision question and
    pure width on an exact lookup. The query-type selector decides; this function does not
    decide for it.
    """
    held = _held_ids(envelope.sources)
    nodes: dict[str, EvidenceNode] = {}
    edges: list[EvidenceEdge] = []
    undetermined: list[UndeterminedParent] = []
    outside: list[UndeterminedParent] = []
    for source in envelope.sources:
        replies, missing, elsewhere = _reply_edges(
            source, held=held, adapter=adapter, freshness=freshness
        )
        edges.extend(replies)
        undetermined.extend(missing)
        outside.extend(elsewhere)
        edges.extend(_membership_edges(source, adapter=adapter, freshness=freshness))
        if people:
            minted = _participant_nodes(source, held=held, adapter=adapter, freshness=freshness)
            nodes.update(minted)
            edges.extend(
                _participant_edges(
                    source,
                    held=held,
                    people=frozenset(minted),
                    adapter=adapter,
                    freshness=freshness,
                )
            )
    return ObservedEdges(
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        undetermined=tuple(undetermined),
        parent_outside_graph=tuple(outside),
    )


__all__ = [
    "LINKED",
    "OBSERVED_METHODS",
    "ObservedEdges",
    "UndeterminedParent",
    "observed_edges",
]
