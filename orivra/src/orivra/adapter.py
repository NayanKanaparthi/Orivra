"""`SourceAdapter`: the seam a connector implements (plan §2.1).

**Fitted over the existing Gmail code, not carved into it.** Every method below is, for
Gmail, a thin call into something v0.1 already ships: `translate` is `query/operators.py`,
`rungs` is `plan_ladder`, `search` is the ladder's `messages.list` path, `container` is the
thread map, `items` is the content pipeline, `changes_since` is `history_additions` plus the
documented 404 re-baseline, `version_of` is `(message id, historyId)`.

**The `mailweave_*` tools do not go through this seam at all.** They keep calling
`MailweaveService` directly, unchanged, with the defaults v0.1 froze. Orivra's own tools
reach Gmail only through an adapter. That separation is what makes M1's demonstration
meaningful rather than circular: the same workflow runs once down each path and the two are
compared, which is only informative while the paths are actually distinct.

A `Protocol` rather than an abstract base: an adapter is a *shape*, and a connector written
against this file should not have to import a base class from it to be one. `runtime_
checkable` is deliberately not used - it checks method names and not signatures, so it
would report a half-written adapter as conforming, which is worse than no check. The real
check is `mypy --strict` plus the conformance tests each adapter's milestone adds.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from mailweave.envelope.response import Envelope
from orivra.contracts import (
    ChangeMarker,
    ConnectorId,
    ContentVersion,
    EvidenceNode,
    OmissionRecord,
    PermissionContext,
    SourceReference,
    SourceSpend,
)


@dataclass(frozen=True)
class AdapterCapabilities:
    """What this source can actually do, so the planner asks nothing it cannot answer.

    Declared rather than probed: a planner that discovers a capability by trying it has
    already spent a call, and on a rate-limited surface that call is the scarce thing.
    """

    connector: ConnectorId
    native_search: bool
    """Whether the source has a server-side query language at all. Gmail and Drive do;
    Slack's depends on the token and the plan tier, which is why M5 has a preflight."""

    search_operators: tuple[str, ...]
    """The operators this adapter will actually emit. Not the operators the source
    documents - the ones this code translates to - so a trace can be read against it."""

    container_kind: str
    """What "the thing this item belongs to" is here: `thread`, `file`, `conversation`."""

    revisions: bool
    """Whether an item has independently addressable earlier versions (Drive: yes)."""

    change_feed: str
    """`history` (Gmail), `page_token` (Drive), `window` (Slack), or `none`."""

    max_ids_per_fetch: int
    """The largest id batch `items` will accept. Gmail has no batch get, so this is the
    largest number of sequential fetches one call will make before it must be split."""


@dataclass(frozen=True)
class QueryFacts:
    """The source-independent facts of one question, before any source sees it.

    Deliberately not a parsed Gmail query: `translate` is where a source's own operator
    language is produced, and passing one source's syntax to another adapter is how a Gmail
    `after:` ends up in a Slack request.
    """

    text: str
    terms: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()
    excluded_phrases: tuple[str, ...] = ()
    participants: tuple[str, ...] = ()
    """Senders. A participant whose role the question did not fix belongs here, because
    `from:` is the constraint a sender-shaped question means."""

    recipients: tuple[str, ...] = ()
    """Recipients, kept apart from senders because they are a different constraint and a
    source that folded them together would answer a different question (R-M1-019)."""

    after: str | None = None
    before: str | None = None
    identifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeQuery:
    """One source's own query, plus the facts it could not carry.

    `unrepresentable` is the field that keeps a translation honest. A source that cannot
    express "before this date" does not get a query that silently drops the constraint; it
    gets one that names what was dropped, and the response declares the narrowing.
    """

    connector: ConnectorId
    query: str
    unrepresentable: tuple[str, ...] = ()


@dataclass(frozen=True)
class RungSpec:
    """One rung of this source's lexical ladder, as the trace will name it."""

    rung_id: str
    why: str
    widens: bool
    """Whether this rung can return ids a narrower rung did not. A ladder whose every rung
    narrows cannot recover from an over-specific query, which is what A.7's ladder exists
    for."""


@dataclass(frozen=True)
class Hits:
    """Ids only. **Every returned id enters `H`.**

    Ids and not rows, because I-1's evidence-preservation invariant is stated over the ids a
    retrieval *observed*, and a method that returned rows would let a caller drop one before
    the ledger saw it. The rows come later, from `items`, under a budget.
    """

    ids: tuple[str, ...]
    container_ids: tuple[str, ...] = ()
    truncated: bool = False
    rungs_executed: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContainerMap:
    """A thread, conversation or revision set, with the source's own count.

    `stated_total` is the source's figure and never a length: a container that states forty
    and yields four is a container with thirty-six omissions, and computing the total from
    what arrived is how those thirty-six become invisible.
    """

    ref: SourceReference
    member_ids: tuple[str, ...]
    stated_total: int
    positions: dict[str, int]


@dataclass(frozen=True)
class ChangeSet:
    """What moved since a marker, and where the feed now stands."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    marker: ChangeMarker


@dataclass(frozen=True)
class Resync:
    """The feed could not be walked from that marker; everything must be re-read.

    Gmail's documented 404 on an expired `startHistoryId` produces this, and so does a Slack
    `channel_history_changed`. It is a **declared** outcome and not an exception, because a
    resync is a normal thing for a change feed to demand and a caller that treats it as a
    failure will serve stale data rather than pay for it.
    """

    why: str
    connector: ConnectorId


@dataclass(frozen=True)
class CacheOutcome:
    """Why this call did or did not serve from the bounded cache.

    `consulted` is the field that matters most and the one a call-count cannot supply: a
    lookup that never happened, because nothing supplied the revision to key on, is a
    different failure from a lookup that happened and missed.
    """

    consulted: bool
    outcome: str
    why: str
    #: **What the revalidation established, as its own field.** `outcome` says what the store
    #: did (hit, miss, expired, unverified); `reason` says why the live check answered as it
    #: did - unchanged, changed, inconclusive, watermark_expired, access_changed, probe_failed.
    #: They are two questions, and collapsing them is what made an inconclusive change feed
    #: read as a caller who had lost access.
    reason: str = "not_applicable"
    #: True when what went stale is the *watermark* rather than the entry, so the caller
    #: discarded it rather than retrying a walk that cannot succeed.
    rebaselined: bool = False

    def payload(self) -> dict[str, str | bool]:
        return {
            "consulted": self.consulted,
            "outcome": self.outcome,
            "reason": self.reason,
            "rebaselined": self.rebaselined,
            "why": self.why,
        }


@dataclass(frozen=True)
class AdapterResult:
    """What one adapter contributes to one query.

    `envelope` is the crucial field and the reason M1 is achievable at all. A Gmail adapter
    that re-drove the ladder in parallel with `MailweaveService` would produce a second
    answer to the same question, and the two would diverge - which is the failure the
    equivalence test is meant to *detect*, not one it should have to tolerate. So the Gmail
    adapter delegates and hands back MailWeave's own envelope, unmodified. Orivra's response
    carries it as this source's container.
    """

    connector: ConnectorId
    envelope: Envelope | None
    nodes: tuple[EvidenceNode, ...]
    omissions: tuple[OmissionRecord, ...]
    spend: SourceSpend
    #: What the bounded cache did on this call, in its own words. `None` for a path with no
    #: cache seat. Carried out of the adapter rather than inferred from call counts, because a
    #: live run that never consulted the cache and a live run that consulted it and missed look
    #: identical from outside - and the first is a wiring defect while the second is the cache
    #: working. A demonstration that cannot tell them apart cannot report either.
    cache: CacheOutcome | None = None


class SourceAdapter(Protocol):
    """The methods a connector provides. See the module docstring for what Gmail maps to.

    **`answer` is deliberately not here.** `GmailAdapter` has one - a whole-query route that
    delegates to `MailweaveService` and hands back MailWeave's own envelope - and it is not
    on the protocol, because designing a general interface from one example is how an
    interface acquires a parameter list only its first implementer wants. Gmail's `answer`
    takes MailWeave's own `SearchRequest` precisely so the caller's view, budget and rung
    forcing reach the engine unchanged, which is what makes M1's equivalence check exact. A
    general `answer` would have to take `QueryFacts` and rebuild that request, losing those
    arguments. It becomes a protocol method when a second source needs one - M4 - and its
    shape is decided then, by two examples rather than one.
    """

    @property
    def connector(self) -> ConnectorId:
        """Which source this adapter speaks for.

        A read-only property rather than a mutable attribute: an adapter's connector is
        fixed at construction, and a protocol declaring a settable attribute would refuse
        every frozen implementation - which is all of them, and rightly so.
        """
        ...

    def capabilities(self) -> AdapterCapabilities: ...

    def translate(self, facts: QueryFacts) -> NativeQuery: ...

    def rungs(self) -> tuple[RungSpec, ...]: ...

    def search(self, native: NativeQuery, *, max_ids: int) -> Hits: ...

    def container(self, ref: SourceReference) -> ContainerMap: ...

    def items(self, refs: Sequence[SourceReference], *, depth: str) -> tuple[EvidenceNode, ...]: ...

    def changes_since(self, marker: ChangeMarker) -> ChangeSet | Resync: ...

    def permission_context(self, ref: SourceReference) -> PermissionContext: ...

    def version_of(self, ref: SourceReference) -> ContentVersion: ...


__all__ = [
    "AdapterCapabilities",
    "AdapterResult",
    "CacheOutcome",
    "ChangeSet",
    "ContainerMap",
    "Hits",
    "NativeQuery",
    "QueryFacts",
    "Resync",
    "RungSpec",
    "SourceAdapter",
]
