"""`RetrievalTrace`: AD D.10's report, plus the dimensions v1 adds.

**Wrapped, not extended.** `mailweave.envelope.wire.RetrievalReport` is a `SealedModel`, and
`SealedModel.__init_subclass__` refuses a subclass of a model that declares fields - because
a substituted class reaching the wire is how three routes published `partial: false` for a
response missing a message (R-ARCH-033). So Orivra's trace *holds* a `RetrievalReport`
rather than inheriting from one. Every D.10 field is present, reachable at `report.…`, and
still validated by the class that owns it.

What v1 adds is three dimensions D.10 had no reason to have: **per source**, because a query
that touched Gmail and Drive spent two budgets; **graph**, because a hop and a pruned branch
are things that happened and are otherwise invisible; and **entities**, because a candidate
that was disclosed and a candidate that was confirmed are different events.

`redaction_policy` names which policy produced the trace, so a stored trace can be read
against the rules that made it rather than the rules in force when someone opens it.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from mailweave.envelope.wire import RetrievalReport
from orivra.contracts.refs import Frozen
from orivra.contracts.vocab import ConnectorId, SourceState

#: The redaction policy this build applies to traces. Bump it when the rules change.
#:
#: v1's policy: identities are digests, never addresses; no message, document or Slack text
#: of any length appears; counts appear except where §4.2's presence-free rule applies.
REDACTION_POLICY: str = "orivra/trace-redaction@1"


class SourceSpend(Frozen):
    """What one connector cost and returned during one query.

    `caps_hit` are names rather than a closed enum because the caps differ per source and a
    union enum over three sources would have to be edited for every connector; the names are
    checked against each adapter's published cap table by the adapter's own tests.
    """

    connector: ConnectorId
    state: SourceState
    rungs_executed: tuple[str, ...] = ()
    hits: int = Field(default=0, ge=0)
    api_calls_by_method: dict[str, int] = Field(default_factory=dict)
    quota_units: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    caps_hit: tuple[str, ...] = ()
    change_marker_used: str | None = Field(default=None, max_length=64)
    """The **digest** of the marker the query walked from, never the marker.

    A Gmail `historyId` is not a secret, but a Drive `startPageToken` is a bearer value for
    a change feed and a Slack window names a channel. One rule for all three is the rule
    that does not have to be remembered per connector."""

    @model_validator(mode="after")
    def _a_source_that_did_nothing_reports_no_spend(self) -> Self:
        if self.state is SourceState.READY:
            return self
        if self.hits or self.quota_units or self.api_calls_by_method:
            raise ValueError(
                f"connector {self.connector.value} is {self.state.value!r} and reports hits "
                "or spend; a source that was not ready cannot have returned evidence, and a "
                "trace saying it did will be read as a source that failed silently"
            )
        return self


class GraphSpend(Frozen):
    """What the graph builder did, in figures a reader can check against the disclosure."""

    seed_count: int = Field(default=0, ge=0)
    node_count: int = Field(default=0, ge=0)
    edge_count_by_origin: dict[str, int] = Field(default_factory=dict)
    hops: int = Field(default=0, ge=0)
    pruned_count: int = Field(default=0, ge=0)
    inferred_methods_used: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _an_inferred_edge_count_names_the_methods_that_made_them(self) -> Self:
        if self.edge_count_by_origin.get("inferred", 0) and not self.inferred_methods_used:
            raise ValueError(
                "the trace reports inferred edges and names no method; an inference whose "
                "method is unrecorded cannot be invalidated when the method changes"
            )
        return self


class EntitySpend(Frozen):
    confirmed: int = Field(default=0, ge=0)
    candidates: int = Field(default=0, ge=0)


class RetrievalTrace(Frozen):
    """One query's whole account of itself."""

    query_id: str = Field(min_length=1, max_length=128)
    report: RetrievalReport | None = None
    """MailWeave's own D.10 report, when a Gmail path produced one. `None` for a query that
    reached no source that publishes one - which is not the same as a query that reached no
    source, and `per_source` distinguishes them."""

    per_source: tuple[SourceSpend, ...] = ()
    graph: GraphSpend = GraphSpend()
    entities: EntitySpend = EntitySpend()
    redaction_policy: str = REDACTION_POLICY

    @model_validator(mode="after")
    def _one_entry_per_connector(self) -> Self:
        seen = [spend.connector for spend in self.per_source]
        if len(set(seen)) != len(seen):
            raise ValueError(
                "a connector appears twice in per_source; two spends for one source are two "
                "accounts of one budget, and the one that disagrees is the one nobody reads"
            )
        return self

    @model_validator(mode="after")
    def _a_trace_names_the_policy_that_redacted_it(self) -> Self:
        if not self.redaction_policy.strip():
            raise ValueError(
                "a trace with no redaction policy cannot be read against the rules that "
                "produced it, only against whichever rules are in force when it is opened"
            )
        return self


__all__ = [
    "REDACTION_POLICY",
    "EntitySpend",
    "GraphSpend",
    "RetrievalTrace",
    "SourceSpend",
]
