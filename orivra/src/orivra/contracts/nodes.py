"""`EvidenceNode`: a row that knows its source, its version and how far it is trusted.

Generalises MailWeave's `MessageRow` and `Source` (plan §4.4). The invariant that a thread
is a `Source` with a `stated_total` becomes source-independent here: **a container is a node
whose children are known to a stated count**, and a container that cannot state its count is
refused rather than published with an implied one.

**What this module deliberately does not do: fence.** MailWeave puts mail-derived text
inside a per-response nonce fence (`envelope/fence.py`), and that is right at the point of
emission. A node is not an emission - it lives inside a `QueryGraph` that outlives the
response that built it, by design, so `orivra_expand` can address it. Fencing here would
stamp one response's nonce onto text a later response will emit under a different one, which
is the fence failing open. The node carries the text and the `Trust` label; the envelope
carries the fence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from mailweave.envelope.reasons import Reason
from mailweave.envelope.vocab import Depth, Role, Trust
from orivra.contracts.reasons import GraphReason
from orivra.contracts.refs import FreshnessStatus, Frozen, SourceReference
from orivra.contracts.vocab import NodeKind, Origin

#: The node kinds that are containers: they have children, and they state how many.
#:
#: A container's `stated_total` is the source's own count, never a length of what was
#: fetched. That is MailWeave's A4 rule ("stubs count") carried across sources: a thread of
#: forty messages of which four were disclosed states forty, and the difference is an
#: omission record rather than a smaller number.
CONTAINERS: frozenset[NodeKind] = frozenset({NodeKind.THREAD, NodeKind.CONVERSATION, NodeKind.FILE})


class Timestamps(Frozen):
    """The instants a source reports for one item, each optional and none invented.

    Closes R-DEMO-002 at the schema rather than at each renderer: the demonstrations found
    rows whose date a reader had to infer from position, because the row carried no instant
    at all. Every node now has this field; a source that reports none produces an all-`None`
    `Timestamps`, which is a visible absence rather than an invisible one.

    **`sent` and `authored` are kept apart** because Gmail reports both and they differ:
    `internalDate` is when the mailbox received it and the `Date` header is what the sender
    claimed. A single "date" field would have to pick one and would be read as the other.
    """

    authored: datetime | None = None
    """What the item itself claims - Gmail's `Date` header, a document's authored date.
    Sender-controlled, and therefore untrusted in exactly the way the body is."""

    sent: datetime | None = None
    """What the source's own infrastructure recorded - Gmail `internalDate`, Slack `ts`."""

    modified: datetime | None = None
    edited: datetime | None = None

    @model_validator(mode="after")
    def _every_instant_carries_an_offset(self) -> Self:
        for name in ("authored", "sent", "modified", "edited"):
            value: datetime | None = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(
                    f"{name} carries no UTC offset; an instant without one is ambiguous by "
                    "the amount that decides which of two messages came first"
                )
        return self

    @property
    def any_stated(self) -> bool:
        return any(
            getattr(self, name) is not None for name in ("authored", "sent", "modified", "edited")
        )


class DerivationMethod(Frozen):
    """What produced a derived node, versioned so a stored one can be invalidated.

    `name@version` rather than a bare name: a cache entry, a trace line and an edge all
    record the method, and a rule that changed without its version changing is a stored
    result that no longer matches the code that would produce it today.
    """

    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+(/[a-z0-9_.-]+)*$")
    version: str = Field(min_length=1, max_length=40)

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


class Span(Frozen):
    """A verbatim quotation with its offsets into one node's content.

    Half-open `[start, end)` over `AnnotatedBody.text`, matching `content/annotate.py`'s
    convention exactly so the two can be compared without an off-by-one at the boundary.

    `text` is stored rather than recomputed on demand: the span is evidence, and evidence
    that has to be re-derived from a body that may since have been re-fetched is evidence
    that can quietly change. The validator only checks the span's own internal consistency;
    checking it against the source content is `edges.py`'s job, because that is where the
    source node is in scope.
    """

    node_id: str = Field(min_length=1, max_length=256)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _the_offsets_and_the_text_agree(self) -> Self:
        if self.end <= self.start:
            raise ValueError(
                f"span [{self.start}, {self.end}) is empty or negative; a span names a run "
                "of real characters"
            )
        if self.end - self.start != len(self.text):
            raise ValueError(
                f"span [{self.start}, {self.end}) is {self.end - self.start} characters and "
                f"its text is {len(self.text)}; offsets and quotation that disagree make a "
                "quotation nobody can locate in the source"
            )
        return self


class EvidenceNode(Frozen):
    """One row of evidence, source-independent (plan §4.4).

    Five of its fields are the ones a reader has to be able to trust without asking:
    `ref` says where it came from, `freshness` says when that was last confirmed, `trust`
    says the content is untrusted third-party data, `origin` says whether a source held this
    or Orivra built it, and `depth` says how much of it is actually here. The validators
    below make each of those unable to lie about the others.
    """

    node_id: str = Field(min_length=1, max_length=256)
    ref: SourceReference
    kind: NodeKind
    role: Role
    #: Why this node is here. **`Reason | GraphReason`, and the widening is one-directional.**
    #: MailWeave's union describes the ways a *message row* came to be in a Gmail response and
    #: is unchanged; `GraphReason` adds the kinds only Orivra produces - a person, and later a
    #: claim - for nodes MailWeave never returns a row for. The discriminators are disjoint by
    #: namespace, `MessageRow.reason` is untouched, and no `mailweave_*` schema moves.
    reason: Reason | GraphReason
    """Why this node is in the response.

    MailWeave's existing closed union (`envelope/reasons.py`), reused rather than
    re-declared. It is Gmail-shaped today - `GmailQueryMatch`, `Rfc822MsgId`,
    `HistoryAddition` - which is honest for a Gmail-only M1 and is the boundary the Drive
    and Slack milestones will have to widen. Widening it is a change to MailWeave's own wire
    vocabulary and therefore goes through the replant manifest, not around it.
    """

    depth: Depth
    content: str | None = None
    """The disclosed text at this depth, unfenced. See the module docstring: the fence is
    the emitting envelope's, because its nonce is per-response and this node is not."""

    stated_total: int | None = Field(default=None, ge=0)
    included: int | None = Field(default=None, ge=0)
    trust: Trust = Trust.UNTRUSTED_THIRD_PARTY
    origin: Origin = Origin.SOURCE_BACKED
    derived_from: tuple[str, ...] = ()
    method: DerivationMethod | None = None
    spans: tuple[Span, ...] = ()
    freshness: FreshnessStatus
    timestamps: Timestamps = Timestamps()

    @model_validator(mode="after")
    def _the_node_id_is_the_one_its_reference_produces(self) -> Self:
        """A source-backed node is addressed by its reference and by nothing else.

        Letting the builder pass an id would put the same message in a graph twice under two
        spellings, and an edge would then point at whichever one its builder happened to
        hold. A derived node has no source reference of its own to be named by, so it is
        allowed its own id - and it must not collide with the reference form, which is what
        the prefix rule below is for.
        """
        if self.origin is Origin.SOURCE_BACKED:
            if self.node_id != self.ref.node_id:
                raise ValueError(
                    f"node_id {self.node_id!r} is not the identity its reference produces "
                    f"({self.ref.node_id!r}); two spellings of one item are two nodes, and "
                    "an edge then points at whichever one its builder held"
                )
        elif not self.node_id.startswith("derived/"):
            raise ValueError(
                f"derived node_id {self.node_id!r} must begin with 'derived/' so it cannot "
                "collide with the connector/kind/native_id form a source-backed node uses"
            )
        return self

    @model_validator(mode="after")
    def _a_derived_node_says_what_derived_it(self) -> Self:
        if self.origin is Origin.DERIVED:
            if self.method is None or not self.derived_from:
                raise ValueError(
                    "a derived node carries both a versioned method and the nodes it was "
                    "derived from; without them it is an assertion with no author"
                )
        elif self.method is not None or self.derived_from:
            raise ValueError(
                "a source-backed node carries a derivation method or derived_from; that is "
                "a computed row presenting itself as a row the source held"
            )
        return self

    @model_validator(mode="after")
    def _a_claim_is_always_derived_and_always_quotes(self) -> Self:
        """GraphRAG's covariate rule, made mandatory (plan §4.4).

        The string-match of each span against its source node's content is checked by the
        graph builder, which has the source nodes; what is checked here is the part that is
        checkable from the node alone - that a claim never presents itself as something a
        source stated whole, and never as a claim with nothing behind it.
        """
        if self.kind is not NodeKind.CLAIM:
            return self
        if self.origin is not Origin.DERIVED:
            raise ValueError(
                "a claim node is always derived: a claim is Orivra's reading of content, "
                "and publishing one as source-backed states it in the source's voice"
            )
        if not self.spans:
            raise ValueError(
                "a claim node carries the verbatim spans it was extracted from; a claim "
                "with no quotation is an extraction nobody can check"
            )
        return self

    @model_validator(mode="after")
    def _a_container_states_its_count_and_a_leaf_does_not(self) -> Self:
        if self.kind in CONTAINERS:
            if self.stated_total is None:
                raise ValueError(
                    f"{self.kind.value} is a container and states no total; a container "
                    "whose count the source did not give cannot be published with an "
                    "implied one - the count is what makes an omission visible"
                )
            if self.included is None:
                raise ValueError(
                    f"{self.kind.value} states a total of {self.stated_total} and does not "
                    "say how many of them are here"
                )
            if self.included > self.stated_total:
                raise ValueError(
                    f"{self.included} children are included in a container of "
                    f"{self.stated_total}; more rows than the source says exist"
                )
        elif self.stated_total is not None or self.included is not None:
            raise ValueError(
                f"{self.kind.value} is not a container and states a child count; a leaf "
                "with a total reads as a container whose children were all omitted"
            )
        return self

    @model_validator(mode="after")
    def _depth_and_content_agree(self) -> Self:
        """A depth is a statement about text that is here, not about text that exists.

        MailWeave's rule (`surface/service._bodies_for`: "a view that shows no body fetches
        none"), stated on the schema so a node cannot claim `body_full` while carrying
        nothing. The reverse is also refused: text at `stub` depth is text the response's
        own measurement did not budget for.
        """
        has_text = bool(self.content)
        if self.depth is Depth.STUB and has_text:
            raise ValueError(
                "a stub node carries content; stub is the depth that says no text is here, "
                "and text at that depth is text no ceiling measured"
            )
        if self.depth in {Depth.BODY_CLEAN, Depth.BODY_FULL} and not has_text:
            raise ValueError(
                f"a {self.depth.value} node carries no content; a depth is a statement "
                "about text that is present, and claiming one with nothing behind it makes "
                "the disclosure ladder's own figures wrong"
            )
        return self

    @model_validator(mode="after")
    def _nothing_that_may_not_be_served_is_a_node_with_content(self) -> Self:
        """A node whose freshness failed may exist - it is how an omission is accounted for -
        but it may not carry the content that failed verification.

        This is the schema half of "a failed verification never serves the cached item"
        (plan §4.3). The other half is the cache, which does not hand one back.
        """
        if not self.freshness.servable and self.content:
            raise ValueError(
                f"a node in freshness state {self.freshness.state.value!r} carries content; "
                "a failed verification degrades to a fresh read, a resync or an "
                "inconclusive outcome, and never to serving what could not be verified"
            )
        return self


__all__ = [
    "CONTAINERS",
    "DerivationMethod",
    "EvidenceNode",
    "Span",
    "Timestamps",
]
