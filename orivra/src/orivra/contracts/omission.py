"""`OmissionRecord` and `ExpansionHandle`: every omission has a cause and a way back.

Generalises MailWeave's `WithheldRecord`, `WithheldGroup`, `WithheldTail`, `NotIncludedBlock`
and `Affordance` across sources and across the graph (plan §4.7).

**Round 29's rule survives the generalisation unchanged: a withheld record is written at the
granularity of the call that recovers it.** A message the caller can pass to
`mailweave_get_messages` is worth naming one by one. A message inside a thread that was never
mapped is not - the only call that reaches it is a thread map on its thread, so forty-five
records pointing at three thread maps say nothing three records with exact counts do not, and
they cost the ceiling the disclosure needed. `Granularity` is that rule as a field.

**The certificate's sum now runs over graph nodes too.** Every node the graph builder created
is either in the disclosed graph or in an `OmissionRecord`. A pruned branch is
`cause: pruned` with a handle; a hop the budget stopped is `cause: cap` naming `max_hops`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from mailweave.envelope.vocab import ToolName as MailweaveToolName
from orivra.contracts.refs import Frozen
from orivra.contracts.vocab import ConnectorId, OmissionCause


class OrivraToolName(StrEnum):
    """Every tool an `ExpansionHandle` may name, MailWeave's four among them.

    **MailWeave's four are carried here verbatim, not re-spelled.** They are the published
    v0.1 surface and a handle that named `mailweave_threadmap` would be a handle no server
    can execute. `tests` assert this enum contains every `mailweave.envelope.vocab.ToolName`
    value, so a rename over there fails here rather than at a caller's next retry.
    """

    SEARCH = "mailweave_search"
    THREAD_MAP = "mailweave_thread_map"
    GET_MESSAGES = "mailweave_get_messages"
    GET_ATTACHMENT = "mailweave_get_attachment"
    ASK = "orivra_ask"
    SOURCES = "orivra_sources"
    EXPAND = "orivra_expand"
    #: Paged read of a stored graph. It exists because resources are optional in MCP and
    #: tools are not: a client that ignores resources must still be able to see an actual
    #: relationship, not a count of them.
    GRAPH = "orivra_graph"
    TRACE = "orivra_trace"

    @property
    def is_mailweave(self) -> bool:
        return self.value in {name.value for name in MailweaveToolName}


class Granularity(StrEnum):
    """What one omission record is *about* - which is the call that recovers it.

    `NODE` names one thing by id. `CONTAINER` names a thread, conversation or file whose
    members were never individually reached. `BRANCH` names a graph subtree the scorer
    pruned. `REGION` names a slice of a scan - a page range, a date window - that was never
    walked at all.
    """

    NODE = "node"
    CONTAINER = "container"
    BRANCH = "branch"
    REGION = "region"


class Dimension(StrEnum):
    """What following a handle narrows or widens, for the retry contract.

    MailWeave's recovery rule (`surface/recovery.py`) is that a retry moves exactly one
    declared dimension in exactly one direction, so a chain is bounded, monotonic and
    cycle-free. Carrying the dimension on the handle is what lets a caller - or a test -
    check that a chain actually is.
    """

    DEPTH = "depth"
    BREADTH = "breadth"
    TIME_WINDOW = "time_window"
    HOPS = "hops"
    SOURCES = "sources"


class ExpansionHandle(Frozen):
    """An executable next call: the tool, the arguments, and what it moves.

    `args` must be executable **as-is** against the tool it names - contract R-07, which the
    v0.1 suite validates against the published `inputSchema` with a real JSON Schema
    validator. A handle whose arguments the named tool would reject is worse than no handle:
    it spends the caller's next call and their trust.
    """

    tool: OrivraToolName
    args: dict[str, Any] = Field(default_factory=dict)
    reduces: Dimension
    handle: str | None = Field(default=None, max_length=4096)
    """The HMAC-signed, key-epoch'd, expiring handle (`handles/mint.py`) when the call needs
    one. `None` for a call addressable by plain arguments - a thread id, a query."""

    @model_validator(mode="after")
    def _a_signed_argument_and_a_signature_go_together(self) -> Self:
        """A `map_id` argument is a signed value, and a signature is one an argument uses.

        The first draft's docstring stated both rules and the code implemented neither: the
        condition was `uses_map_id and not handle and not args["map_id"]`, which fires only
        when a `map_id` key is present *and empty*. So a handle naming a `map_id` with no
        signature passed, and a signed credential no argument consumed passed too - a
        credential travelling for no reason, which is the second rule's whole point
        (review finding R-M1-011).
        """
        named = self.args.get("map_id")
        if named is not None and not (isinstance(named, str) and named.strip()):
            raise ValueError(
                "the handle's arguments name an empty map_id; a call that cannot be "
                "verified is not an expansion, it is a refusal the caller has to discover"
            )
        if named is not None and self.handle is not None and named != self.handle:
            raise ValueError(
                "the handle's map_id argument and its signature are different values; the "
                "call would be verified against a credential it does not carry"
            )
        if self.handle is not None and named is None:
            raise ValueError(
                "this handle carries a signature no argument uses; a credential travelling "
                "for no reason is one more place it can be read from"
            )
        return self


class OmissionRecord(Frozen):
    """One thing the query reached and the response does not carry (plan §4.7).

    Four fields do the work. `what` names it at the granularity that recovers it; `count` is
    exact; `cause` is closed; `recover` is the way back, and is absent only for the two
    causes where nothing could reach it.

    **The presence-free form.** Where even the existence of the omitted thing would disclose
    something the caller is not authorised to know - the number of documents contradicting a
    visible email, in a workspace where the caller cannot see that such documents exist - the
    record degrades to connector and cause only, with `what` empty and `count` withheld.
    Internal accounting keeps the hidden identities, because the disposition ledger needs
    them to keep `H` complete and the certificate honest; the *response* does not.
    """

    what: str = Field(default="", max_length=256)
    granularity: Granularity
    count: int | None = Field(default=None, ge=0)
    cause: OmissionCause
    cap_name: str | None = Field(default=None, max_length=64)
    """Which cap, when `cause` is `CAP`. `max_hit_threads`, `disclosed_token_ceiling`,
    `max_hops` - the last of which is the graph's own and has no MailWeave equivalent."""

    why: str = Field(min_length=1, max_length=400)
    """The shared sentence, stated once per cause rather than once per record.

    `omission.bound`'s rule from v0.1: forty-five records each carrying the same explanation
    spend the ceiling the disclosure needed on a sentence the reader has already read."""

    recover: ExpansionHandle | None = None
    connector: ConnectorId
    presence_free: bool = False

    @model_validator(mode="after")
    def _a_cap_names_the_cap(self) -> Self:
        if self.cause is OmissionCause.CAP and not self.cap_name:
            raise ValueError(
                "cause is cap and no cap is named; 'a cap was hit' tells a caller nothing "
                "they can lower or raise"
            )
        if self.cause is not OmissionCause.CAP and self.cap_name:
            raise ValueError(
                f"cause is {self.cause.value!r} and a cap is named; a cap on a record that "
                "was not capped sends the caller to widen a budget that was not the reason"
            )
        return self

    @model_validator(mode="after")
    def _the_presence_free_form_is_free_of_presence(self) -> Self:
        """The degradation of plan §4.2, checked rather than trusted.

        A record that says it discloses nothing and carries an id, a count or a handle
        discloses all three. Only the connector and the cause survive, and the cause must be
        one of the two that can arise from something the caller may not see.
        """
        if not self.presence_free:
            if not self.what:
                raise ValueError(
                    "an omission record names nothing and is not marked presence-free; a "
                    "record a caller cannot act on must at least say why it cannot"
                )
            if self.count is None:
                raise ValueError(
                    "an omission record states no count and is not marked presence-free; "
                    "the count is what makes the omission measurable against the certificate"
                )
            return self
        if self.what or self.count is not None or self.recover is not None:
            raise ValueError(
                "a presence-free omission record carries an identity, a count or a handle; "
                "the form exists for the case where the existence of the thing is itself "
                "unauthorised, and only the connector and the cause survive it"
            )
        if not self.cause.may_have_no_handle:
            raise ValueError(
                f"cause {self.cause.value!r} cannot produce a presence-free record; only a "
                "thing the caller may not see, or one the source no longer has, can be "
                "withheld down to its existence"
            )
        return self

    @model_validator(mode="after")
    def _a_cause_that_can_be_reached_carries_the_way_back(self) -> Self:
        if self.cause.may_have_no_handle:
            return self
        if self.recover is None:
            raise ValueError(
                f"omission cause {self.cause.value!r} is recoverable and the record offers "
                "no handle; a handle is absent only for permission and source_gone, where "
                "there is nothing to reach and a handle would always refuse"
            )
        return self


def permission_safe_omission(
    *, connector: ConnectorId, granularity: Granularity = Granularity.NODE
) -> OmissionRecord:
    """The record that stands in for an edge a caller may not see (owner decision, R-M1-016).

    **Presence-free, and that is the whole design.** It carries a connector and a cause and
    nothing else: no node id, no count, no handle, no relation, no target. Naming the
    requirement that failed names the source; naming the reference names the document; naming
    the relation is the disclosure the edge itself would have made. A caller learns that
    something was withheld for permission reasons and learns nothing about what.

    `connector` is the one the caller can already see - the connector of the endpoint they are
    looking at - and never the connector of whatever failed. A record saying `drive` in a
    response to a caller with no Drive access would disclose that a Drive document exists,
    which is exactly the presence this form exists to withhold.

    Internal accounting keeps the hidden identities: the disposition ledger needs them to keep
    `H` complete and the certificate honest, and `Release.why_internal` carries the reason.
    The **response** gets this.
    """
    return OmissionRecord(
        granularity=granularity,
        cause=OmissionCause.PERMISSION,
        why=(
            "one or more of the sources this relationship rests on is not currently "
            "available to you, so the relationship is withheld in full"
        ),
        connector=connector,
        presence_free=True,
    )


__all__ = [
    "Dimension",
    "ExpansionHandle",
    "Granularity",
    "OmissionRecord",
    "OrivraToolName",
    "permission_safe_omission",
]
