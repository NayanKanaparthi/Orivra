"""Extending a stored graph with what an expansion recovered, or refusing to.

`orivra_expand` used to fetch a thread map and hand it back. That answered "what was in the
branch" and left the graph exactly as it was, so a caller who followed a handle held two
things that did not compose: a graph missing some nodes, and a thread map that did not say
which of its rows were the missing ones.

Merging is the fix, and **not merging** is half of it. Two snapshots of the same thread taken
at different revisions describe different states of the mailbox, and stitching them into one
graph produces a structure that was never true at any instant - a reply tree whose upper half
predates a change its lower half reflects. That is worse than a gap, because a gap is visible.
So a merge whose overlap disagrees is **refused**, with the conflict named, and the caller is
told to ask again rather than handed a blend.

What a merge does:

* **Deduplicates** on `node_id` and `edge_id`. An expansion re-returns rows the graph already
  holds, by construction - a thread map returns the whole thread.
* **Checks the overlap** before adding anything. Every node present in both must agree on its
  content version; one disagreement refuses the whole merge.
* **Bounds** the result the same way the build did, and accounts for what did not fit.
* **Records the source** of what it added, so a node can be read back to the call that
  produced it rather than taken on trust.
* **Bumps the revision**, so two pages taken across a merge are distinguishable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from orivra.contracts import (
    ConnectorId,
    EvidenceEdge,
    EvidenceNode,
    Granularity,
    OmissionCause,
    OmissionRecord,
    QueryGraph,
)
from orivra.graph.build import thread_handle


class IncompatibleSnapshot(ValueError):
    """The expansion describes a different state of the source than the graph does.

    A distinct type because the caller's move is different: this is not "you asked for
    something that is not there", it is "what you are holding and what I just fetched cannot
    both be true", and the answer is a fresh question rather than a different handle.
    """


@dataclass(frozen=True)
class MergeResult:
    """The extended graph, what it gained, and what it still could not take."""

    graph: QueryGraph
    added_nodes: tuple[EvidenceNode, ...]
    added_edges: tuple[EvidenceEdge, ...]
    #: Nodes the expansion returned that the graph already held, by id. Reported rather than
    #: silently dropped: "the branch had six rows and four were already here" is the sentence
    #: that makes the count add up for a reader.
    already_held: tuple[str, ...]
    #: What the bound refused, as its own record, already folded into `graph.omitted`.
    still_capped: tuple[OmissionRecord, ...]

    @property
    def revision(self) -> int:
        return self.graph.revision


def _version_key(node: EvidenceNode) -> tuple[str | None, bool]:
    version = node.ref.version
    return (version.revision, version.deleted)


def _conflicts(
    existing: Sequence[EvidenceNode], incoming: Sequence[EvidenceNode]
) -> list[tuple[str, tuple[str | None, bool], tuple[str | None, bool]]]:
    """Where the two snapshots describe the same node differently.

    Only the overlap is checked, and only on the content version. A node's *role* in the
    response can legitimately differ between a search and a thread map - the same message is
    `matched` in one and `context` in the other - and treating that as a conflict would refuse
    every merge. The version is the thing that says whether the source changed underneath.
    """
    held = {node.node_id: node for node in existing}
    out = []
    for node in incoming:
        seen = held.get(node.node_id)
        if seen is None:
            continue
        if _version_key(seen) != _version_key(node):
            out.append((node.node_id, _version_key(seen), _version_key(node)))
    return out


def merge(
    graph: QueryGraph,
    *,
    nodes: Sequence[EvidenceNode],
    edges: Sequence[EvidenceEdge],
    recovered_from: str,
    at: datetime,
    max_nodes: int,
) -> MergeResult:
    """Fold an expansion's nodes and edges into `graph`, or refuse.

    `recovered_from` is the handle that produced these, and it goes into the record of what
    was added: a node that appeared in the graph without saying which call put it there is a
    node a reader has to take on trust.
    """
    clash = _conflicts(graph.nodes, nodes)
    if clash:
        node_id, was, now = clash[0]
        raise IncompatibleSnapshot(
            f"the expansion describes {node_id} at a different version than this graph holds "
            f"(graph {was[0]!r}, expansion {now[0]!r}"
            f"{', and the source now reports it deleted' if now[1] else ''}). The source "
            "changed after this graph was built, so the two cannot be composed into one "
            "state that was ever true. Ask again to get a graph of the current state"
        )

    held_nodes = {node.node_id for node in graph.nodes}
    held_edges = {edge.edge_id for edge in graph.edges}
    already = tuple(sorted(node.node_id for node in nodes if node.node_id in held_nodes))

    fresh = [node for node in nodes if node.node_id not in held_nodes]
    room = max(max_nodes - len(graph.nodes), 0)
    taking, refused = fresh[:room], fresh[room:]

    known = held_nodes | {node.node_id for node in taking}
    # An edge is added only when **both** endpoints are in the merged graph. `QueryGraph`
    # refuses a dangling endpoint anyway, so this is the rule that keeps the refusal from
    # becoming a construction error the caller sees as a defect.
    adding = [
        edge
        for edge in edges
        if edge.edge_id not in held_edges and edge.source in known and edge.target in known
    ]

    capped: tuple[OmissionRecord, ...] = ()
    if refused:
        capped = (
            OmissionRecord(
                what=recovered_from,
                granularity=Granularity.BRANCH,
                count=len(refused),
                cause=OmissionCause.CAP,
                cap_name="graph_max_nodes",
                why=(
                    f"the expansion recovered {len(fresh)} node(s) this graph did not hold and "
                    f"the node budget had room for {len(taking)}. The rest are reachable by "
                    "the same handle on a graph with more room"
                ),
                # The same handle, still executable. A `cap` is recoverable by definition, and
                # a record that offered none would be a dead end wearing an omission's clothes
                # - which `OmissionRecord` refuses outright rather than letting ship.
                recover=thread_handle(recovered_from.removeprefix("gmail/thread/")),
                connector=ConnectorId.GMAIL,
            ),
        )

    # The branch's own capped record is satisfied by this merge, so it is replaced rather than
    # left standing: an omission a caller has already recovered is an offer that now misleads.
    remaining = tuple(
        record
        for record in graph.omitted
        if not (record.what == recovered_from and record.cause is OmissionCause.CAP)
    )
    extended = QueryGraph(
        query_id=graph.query_id,
        nodes=(*graph.nodes, *taking),
        edges=(*graph.edges, *adding),
        seeds=graph.seeds,
        hops_taken=graph.hops_taken + 1,
        omitted=(*remaining, *capped),
        # **Carried, not recomputed.** The expansion's own nodes go through `text_edges` in the
        # caller, which produces whatever links *they* carried; this merge is about what the
        # graph already holds, and dropping the links it held would silently shrink a list the
        # answer may already have compacted out of its block on the promise that a page serves
        # it. The caller adds the expansion's links to `unresolved_links` alongside these.
        unresolved_links=graph.unresolved_links,
        entities=graph.entities,
        candidates=graph.candidates,
        built_at=graph.built_at,
        ttl=graph.ttl,
        revision=graph.revision + 1,
    )
    del at
    return MergeResult(
        graph=extended,
        added_nodes=tuple(taking),
        added_edges=tuple(adding),
        already_held=already,
        still_capped=capped,
    )


__all__ = ["IncompatibleSnapshot", "MergeResult", "merge"]
