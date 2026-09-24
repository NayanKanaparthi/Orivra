"""The live gate every stored-graph disclosure runs, and what it does when the answer is no.

**A stored `PermissionRequirement` is not an authorization check.** It records what an edge
rested on when it was built, which is a fact about the past; whether this caller may see it
now is a fact about now, and the two diverge exactly where it matters - a scope narrowed after
consent was re-granted, a message deleted, a thread whose labels moved. A graph that is
addressable for ten minutes is a graph that can be read after any of those.

So every path that discloses a stored graph - the paging tool, `orivra_expand`, and the
resource - goes through `disclose`, which:

* asks `permission.release` per edge, with a **live probe**, against the edge's own
  requirements and every reference it rests on;
* re-verifies each node's content version against the source, so a node whose revision moved
  since the graph was built is served as `STALE` rather than as `FRESH`, and one that is gone
  is not served at all;
* replaces whatever it withholds with a presence-free `OmissionRecord` - connector and cause
  and nothing else, because naming the requirement names the source and naming the reference
  names the document.

The probe caches within one disclosure and not across them. Caching across would be the same
mistake one layer down: a cheaper answer to a question whose whole point is that it is asked
now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from orivra.contracts import (
    ConnectorId,
    ContentVersion,
    EvidenceEdge,
    EvidenceNode,
    FreshnessState,
    FreshnessStatus,
    Granularity,
    NodeKind,
    OmissionCause,
    OmissionRecord,
    PermissionContext,
    PermissionRequirement,
    QueryGraph,
    RefKind,
    SourceReference,
    release,
)
from orivra.graph.build import thread_handle


class VersionProbe(Protocol):
    """What `disclose` needs from an adapter: the grant now, and each item's version now.

    A `Protocol` rather than an import of `GmailAdapter`: this gate is about what an adapter
    can be asked, not about which adapter is asking, and taking the concrete class here would
    make the one security-relevant path in the package Gmail-shaped for no gain.
    """

    def permission_context(
        self, ref: SourceReference | None = None
    ) -> PermissionContext: ...  # pragma: no cover

    def version_of(self, ref: SourceReference) -> ContentVersion: ...  # pragma: no cover


@dataclass
class LiveProbe:
    """`AccessProbe` over a source adapter, asked at disclosure time.

    `authorizes` compares a requirement's `scope_set` against the grant the adapter reports
    **now**. Read back rather than remembered: consent can be narrowed between the build and
    the read, and a requirement that was satisfied at build time is exactly the one that would
    slip through a check against a stored copy.

    `can_access` asks the source for the item's current version. A deleted item is not
    accessible; an item the source refuses to describe is not accessible either, and the
    refusal is treated as a no rather than as an error to be worked around - failing closed is
    the only safe direction for a question about someone else's data.
    """

    adapter: VersionProbe
    #: Within one disclosure only. Two nodes resting on the same message ask once.
    _versions: dict[str, ContentVersion | None] = field(default_factory=dict, repr=False)
    _grant: PermissionContext | None = field(default=None, repr=False)

    def _context(self) -> PermissionContext:
        if self._grant is None:
            self._grant = self.adapter.permission_context()
        return self._grant

    def authorizes(self, requirement: PermissionRequirement) -> bool:
        context = self._context()
        if requirement.connector is not ConnectorId.GMAIL:
            # This release ships one connector. A requirement naming another is not something
            # this probe can answer, and an unanswerable question is a no.
            return False
        if context.principal != requirement.principal:
            return False
        return set(requirement.scope_set) <= set(context.scope_set)

    def version(self, reference: SourceReference) -> ContentVersion | None:
        key = f"{reference.kind.value}/{reference.native_id}"
        if key not in self._versions:
            try:
                self._versions[key] = self.adapter.version_of(reference)
            except Exception:
                # Fail closed. A source that will not say whether an item exists has not said
                # that it does, and an item this caller may not reach raises here too.
                self._versions[key] = None
        return self._versions[key]

    def can_access(self, reference: SourceReference) -> bool:
        """Whether this caller can reach this item now - **asked of the right kind.**

        Only a message is a thing Gmail can be asked about on its own. A thread reference and
        a person reference have no independent existence to probe: a thread's identity is
        carried by the messages in it, and a person is derived from a thread's participant
        index and has no revision at all. Probing them means a message fetch on a thread id or
        on an email address, which fails - and the first wiring read that failure as "not
        accessible", refused every edge resting on a thread or a person, and served two of
        eleven relations on a mailbox where nothing was wrong.

        So this returns `True` for derived kinds, and **that is not the check being skipped**:
        `disclose` keeps a derived node only when a message it is joined to survived its own
        probe, so a person whose every message went away goes away too. The reachability of a
        derived reference is established there, over the graph, where the evidence for it is.
        """
        if reference.kind is not RefKind.MESSAGE:
            return True
        current = self.version(reference)
        return current is not None and not getattr(current, "deleted", False)


def _freshness_now(node: EvidenceNode, probe: LiveProbe, observed_at: datetime) -> FreshnessStatus:
    """This node's freshness **as of this disclosure**, not as of the build.

    Three answers and they are not two. The revision matches, so the node is `FRESH` and says
    so with a new `verified_at`. The revision moved, so the content behind this node changed
    after it was built and the node is `STALE` - still servable, because the caller asked for
    the graph they were handed and a changed row is a fact worth seeing, but never labelled
    fresh. The source will not describe it at all, so it is `UNVERIFIABLE` and is withheld by
    the caller of this function.
    """
    current = probe.version(node.ref)
    if current is None:
        return FreshnessStatus(
            verified_at=observed_at,
            state=FreshnessState.UNVERIFIABLE,
            why="the source did not describe this item when the graph was disclosed",
        )
    if getattr(current, "deleted", False):
        return FreshnessStatus(
            verified_at=observed_at, state=FreshnessState.GONE, why="the source reports it gone"
        )
    stored = node.ref.version.revision
    now = getattr(current, "revision", None)
    if stored is None and now is not None:
        # Nothing to compare against. Reporting `FRESH` here would be claiming a verification
        # that did not happen, which is the defect that made this whole check ornamental until
        # the build started stamping revisions from the response's certificate.
        return FreshnessStatus(
            verified_at=observed_at,
            state=FreshnessState.UNVERIFIABLE,
            why=(
                "this node carries no recorded revision, so the source's current one cannot "
                "be compared against what the graph was built from"
            ),
        )
    if stored is not None and now is not None and stored != now:
        return FreshnessStatus(
            verified_at=observed_at,
            state=FreshnessState.STALE,
            why=(
                "the source's revision for this item moved after the graph was built, so what "
                "it holds is a view of an earlier state"
            ),
        )
    return FreshnessStatus(verified_at=observed_at, state=FreshnessState.FRESH)


def _presence_free(cause: OmissionCause, why: str) -> OmissionRecord:
    """A withholding that names nothing it withheld - **including how much**.

        The first version carried a count, and `OmissionRecord` refused it outright. The contract
        is right and the reasoning is worth keeping: presence-free exists for the case where the
        *existence* of the thing is what the caller is not authorised to know, and a count is an
        existence claim. "Three relations were withheld from you" tells a caller there are three,
        which is the fact the refusal was protecting.

    **Not every withholding takes this form**, and `OmissionRecord` is the thing that said so:
        only a cause that is about what the caller may see, or about the source no longer having
        it, can be withheld down to its existence. A `FRESHNESS_UNVERIFIABLE` item is neither. The
        caller already holds this graph and was already shown that node; that this server could
        not re-verify it on this read is a fact about the read, not a secret about the caller's
        access, and hiding the count there would withhold something useful for no gain.

        So permission refusals and gone items are presence-free, unverifiable ones are counted,
        and the boundary is the contract's rather than this module's.
    """
    return OmissionRecord(
        granularity=Granularity.NODE,
        cause=cause,
        why=why,
        connector=ConnectorId.GMAIL,
        presence_free=True,
    )


@dataclass(frozen=True)
class Disclosed:
    """One graph, as this caller may see it **now**."""

    nodes: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...]
    omitted: tuple[OmissionRecord, ...]
    #: True when the live pass **withheld something that was otherwise servable**. Not "the
    #: output is smaller than the graph": a graph holding no source-backed node has nothing for
    #: this pass to withhold, and reporting that as a narrowing told a live run its access had
    #: been restricted when the source was never even asked.
    narrowed: bool = False
    #: How many source-backed nodes this pass had to consider. **Zero is the interesting
    #: value**: it means the graph carried only derived nodes - threads and people - and a
    #: derived node exists in virtue of messages, so with none of them the graph was vacuous
    #: before any check ran. A caller seeing an empty page needs to tell that apart from an
    #: access decision, and this is the field that tells it.
    source_backed: int = 0
    #: Derived nodes dropped because no message they join survived. A consequence of whatever
    #: removed those messages, which has its own record; carried as a number rather than folded
    #: into a permission omission, because it is not a permission decision.
    derived_without_support: int = 0

    @property
    def stale(self) -> tuple[EvidenceNode, ...]:
        return tuple(
            node for node in self.nodes if node.freshness.state is not FreshnessState.FRESH
        )


def disclose(graph: QueryGraph, *, probe: LiveProbe, observed_at: datetime) -> Disclosed:
    """Re-check the whole graph against this caller, now, and return what survives.

    **Only source-backed items are probed.** A message is a thing Gmail can be asked about and
    has a version of its own. A thread node and a person node are not: the thread's identity
    is carried by the messages in it, and a person is derived from the thread's participant
    index and has no revision at all. Asking the source for a "version of
    ana@team.example" is a message fetch on an address, which fails - and the first wiring
    read that failure as "unverifiable", withheld every person and thread node, orphaned every
    edge that touched one, and served two edges out of eleven. The check has to ask each kind
    the question that kind has an answer to.

    So derived nodes are kept exactly when a message they rest on is kept. That is stricter
    than dropping the check - a person whose every message went away goes away too - and it
    makes the reachability of a derived node a consequence of the source rather than an
    assumption about it.

    Order matters: nodes first, then edges. An edge whose endpoint is withheld has nowhere to
    land, and releasing it would disclose that the endpoint exists - which is what withholding
    the node was for.
    """
    thread_of = {
        edge.source: edge.target.removeprefix("gmail/thread/")
        for edge in graph.edges
        if edge.target.startswith("gmail/thread/")
    }
    messages = [node for node in graph.nodes if node.kind is NodeKind.MESSAGE]
    derived = [node for node in graph.nodes if node.kind is not NodeKind.MESSAGE]

    kept_nodes: list[EvidenceNode] = []
    gone = 0
    unverified_threads: dict[str, int] = {}
    for node in messages:
        freshness = _freshness_now(node, probe, observed_at)
        if freshness.state is FreshnessState.GONE:
            gone += 1
            continue
        if freshness.state is FreshnessState.UNVERIFIABLE:
            where = thread_of.get(node.node_id, "unknown")
            unverified_threads[where] = unverified_threads.get(where, 0) + 1
            continue
        # **A stale node is served, and labelled stale.** The caller asked for the graph they
        # were handed; a row whose revision moved is a fact worth seeing, and dropping it
        # would turn a change into an absence. What it never gets is the word `fresh`.
        kept_nodes.append(node.model_copy(update={"freshness": freshness}))

    surviving = {node.node_id for node in kept_nodes}
    # A derived node is kept when an edge joins it to a message that survived. Read off the
    # graph's own edges rather than from the id, because which messages a person authored is
    # a fact the response stated and parsing it out of a node id would invent a second source.
    supported = {
        end
        for edge in graph.edges
        for end in (edge.source, edge.target)
        if {edge.source, edge.target} & surviving
    }
    dropped_derived = 0
    for node in derived:
        if node.node_id in supported:
            kept_nodes.append(node)
        else:
            dropped_derived += 1

    held = {node.node_id for node in kept_nodes}
    kept_edges: list[EvidenceEdge] = []
    refused = 0
    orphaned = 0
    for edge in graph.edges:
        if edge.source not in held or edge.target not in held:
            orphaned += 1
            continue
        decision = release(edge.requires, edge.support, probe)
        if not decision.granted:
            refused += 1
            continue
        kept_edges.append(edge)

    extra: list[OmissionRecord] = []
    for thread_id, count in sorted(unverified_threads.items()):
        if thread_id == "unknown":  # pragma: no cover - a message always carries membership
            continue
        extra.append(
            OmissionRecord(
                # **Per thread, because the record has to be recoverable.** The contract
                # refuses a `freshness_unverifiable` record with no handle - the cause is
                # recoverable, so a record that offered nothing would be a dead end dressed
                # as an omission. The call that recovers a message is its thread's map.
                what=f"gmail/thread/{thread_id}",
                granularity=Granularity.CONTAINER,
                count=count,
                cause=OmissionCause.FRESHNESS_UNVERIFIABLE,
                why=(
                    f"{count} item(s) of this thread could not be verified against the source "
                    "when the graph was read, so they are not served from a stored view. The "
                    "thread's map reads them from the source as it is now"
                ),
                recover=thread_handle(thread_id),
                connector=ConnectorId.GMAIL,
            )
        )
    if gone:
        extra.append(
            _presence_free(
                OmissionCause.SOURCE_GONE,
                "the source no longer holds items this graph was built over",
            )
        )
    # **Only a refusal is a permission record.** This used to fire on `refused or orphaned or
    # dropped_derived`, and the two it should not have covered are the two that fire without
    # any access decision at all: an orphaned edge lost an endpoint that some *other* record
    # already explains, and a dropped derived node is a thread or a person with no surviving
    # message under it. A live Gmail run whose graph held one thread node and no messages was
    # told "not released to this caller under the grant in force" - a sentence about
    # authorization, printed for a graph the source was never asked about.
    #
    # An orphaned edge still travels with the refusal when there was one, because an endpoint
    # withheld for permission is exactly the case the presence-free form exists for: naming the
    # edge would name the endpoint the refusal hid.
    if refused:
        extra.append(
            _presence_free(
                OmissionCause.PERMISSION,
                "relations this graph holds were not released to this caller under the grant "
                "in force when it was read, or rest on items that were not",
            )
        )
    return Disclosed(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        omitted=(*graph.omitted, *extra),
        # A graph with no source-backed node is not a narrowed graph. Nothing was withheld,
        # because there was nothing this pass could have served in the first place.
        narrowed=bool(messages) and bool(gone or unverified_threads or refused or orphaned),
        source_backed=len(messages),
        derived_without_support=dropped_derived,
    )


__all__ = ["Disclosed", "LiveProbe", "VersionProbe", "disclose"]
