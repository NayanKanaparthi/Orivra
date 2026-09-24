"""Assemble one `QueryGraph` from one Gmail response, bounded, with what it left out.

The graph is built for a question and discarded (plan §5.1). Nothing here writes a cache,
nothing persists, and no mailbox-wide structure exists at any point: the only nodes are the
ones the response already returned rows for, plus the person nodes the participant index
earns, and the only edges are the ones the response's own metadata states.

**Bounding is the whole design, and pruning is not a failure mode.** A thread of eighty
messages is eighty nodes and a hundred and sixty edges, and a response that carries all of
them has spent its ceiling on structure instead of on evidence. So the builder takes a node
budget, keeps what the query reached, and files everything it drops as an `OmissionRecord`
with an executable handle. A pruned branch a reader cannot get back is indistinguishable from
a branch that never existed, which is the failure this package exists to avoid.

**Three relation families, kept apart.** `observed.py` draws metadata edges from the response's
own structure. `stated.py` draws `obs.said.*` edges from what a message's text says, through
four gates that refuse most nominations. `inferred.py` draws `inf.*` edges from the one refusal
that is an ambiguity rather than a denial. They are separate modules because they carry
different weight for a reader: metadata is the source's data structure, source-stated is a
human's sentence, inferred is this server's conclusion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from mailweave.envelope.response import Envelope
from orivra.contracts import (
    ConnectorId,
    Dimension,
    EvidenceEdge,
    EvidenceNode,
    ExpansionHandle,
    FreshnessStatus,
    Granularity,
    NodeKind,
    OmissionCause,
    OmissionRecord,
    OrivraToolName,
    QueryGraph,
)
from orivra.graph.observed import ObservedEdges, References, observed_edges
from orivra.graph.text import text_edges

#: How many nodes one query's graph may carry before the builder starts pruning.
#:
#: A number rather than a policy, because the honest bound is the one a reader can check
#: against the record: the graph says how many nodes it holds and the omissions say what was
#: dropped, so an undersized budget shows up as accounting rather than as absence.
DEFAULT_MAX_NODES: int = 40


@dataclass(frozen=True)
class GraphBuild:
    """The graph, the branches that did not fit, and the links nothing here can resolve."""

    graph: QueryGraph
    #: Every pruned branch, as its own record with a handle. Kept beside the graph as well as
    #: inside it so a caller that reads only the omission list sees the same set.
    pruned: tuple[OmissionRecord, ...] = ()
    #: URLs this response saw and this release cannot point at a node. Not omission records:
    #: `OmissionCause` has no member for "no connector could reach this", and the near miss
    #: (`not_tried`) is refused without a recovery handle - correctly, since offering one this
    #: server cannot execute would be an offer that refuses when taken.
    unresolved_links: tuple[dict[str, str], ...] = ()


def thread_handle(thread_id: str) -> ExpansionHandle:
    """The way back to a pruned thread: MailWeave's own thread map, named by plain argument.

    No signed handle, because none is needed - a thread id is addressable on its own, and a
    credential that travels for no reason is one more place it can be read from
    (`ExpansionHandle`'s own rule, R-M1-011).
    """
    return ExpansionHandle(
        tool=OrivraToolName.THREAD_MAP,
        args={"thread_id": thread_id},
        reduces=Dimension.BREADTH,
    )


def _capped_record(thread_id: str, dropped: int) -> OmissionRecord:
    """A branch the node budget stopped - **`CAP`, not `PRUNED`**, and the contract is right.

    `PRUNED` means a relevance scorer looked at a branch and decided against it. This builder
    has no scorer: it keeps the response's own order and drops the tail when the budget runs
    out. Filing that as `PRUNED` would tell a reader a judgement was made about this branch's
    worth, and none was - the honest statement is that a budget ended and here is the number
    it ended at, which is a cap. `OmissionRecord` refuses the combination outright, which is
    how the mislabel was caught rather than shipped.

    It stays a `BRANCH` at granularity, because the branch is what the handle recovers.
    """
    return OmissionRecord(
        what=f"gmail/thread/{thread_id}",
        granularity=Granularity.BRANCH,
        count=dropped,
        cause=OmissionCause.CAP,
        cap_name="graph_max_nodes",
        why=(
            f"the graph's node budget ended before this thread's last {dropped} message "
            "node(s) were built. No judgement was made about them - the thread itself is in "
            "the graph and its map is one call away"
        ),
        recover=thread_handle(thread_id),
        connector=ConnectorId.GMAIL,
    )


def _unlinked_record(build: ObservedEdges) -> tuple[OmissionRecord, ...]:
    """The reply parents this response could not state, as records rather than as silence.

    Two records, never one, because they have two recoveries. A row whose headers never named
    a parent is a question for the headers and a wider fetch will not answer it; a row whose
    named parent is a message this response did not return is exactly what a thread map does
    answer. Folding them together would lose which call to make.

    A row that is the first message of a *complete* thread is in neither: it has no parent and
    never did, and filing that as a gap buries the ones a reader can act on.
    """
    records: list[OmissionRecord] = []
    real_gaps = [gap for gap in build.undetermined if not gap.explained_by_being_first]
    by_thread: dict[str, list[str]] = {}
    for gap in real_gaps:
        by_thread.setdefault(gap.thread_id, []).append(gap.message_id)
    for thread_id, message_ids in sorted(by_thread.items()):
        records.append(
            OmissionRecord(
                what=f"gmail/thread/{thread_id}",
                granularity=Granularity.CONTAINER,
                count=len(message_ids),
                cause=OmissionCause.NOT_TRIED,
                why=(
                    f"{len(message_ids)} message(s) in this thread carry no RFC reply headers "
                    "this response could read, so their place in the reply tree is not known. "
                    "No edge is drawn from their order in the thread: a message printed after "
                    "another is not thereby a reply to it (contract C-02a)"
                ),
                recover=thread_handle(thread_id),
                connector=ConnectorId.GMAIL,
            )
        )
    outside: dict[str, list[str]] = {}
    for gap in build.parent_outside_graph:
        outside.setdefault(gap.thread_id, []).append(gap.message_id)
    for thread_id, message_ids in sorted(outside.items()):
        records.append(
            OmissionRecord(
                what=f"gmail/thread/{thread_id}",
                granularity=Granularity.CONTAINER,
                count=len(message_ids),
                cause=OmissionCause.CAP,
                cap_name="disclosed_rows",
                why=(
                    f"{len(message_ids)} message(s) name a reply parent this response did not "
                    "return, so the edge has no endpoint to land on. The parent exists and is "
                    "in the thread; this response simply does not carry it"
                ),
                recover=thread_handle(thread_id),
                connector=ConnectorId.GMAIL,
            )
        )
    return tuple(records)


def _prune(
    nodes: Sequence[EvidenceNode], edges: Sequence[EvidenceEdge], *, max_nodes: int
) -> tuple[tuple[EvidenceNode, ...], tuple[EvidenceEdge, ...], tuple[OmissionRecord, ...]]:
    """Keep the budget's worth of nodes, drop whole message branches, account for every drop.

    **Threads are never pruned; people are kept only while a message still joins them.** A
    thread node is the anchor a pruned branch's handle points at, so dropping it would leave a
    record naming a node the graph does not hold. A person node is different: it exists only
    in virtue of the messages that person sent or received, so once every one of them is
    pruned the node is a row about nobody this graph can still point at.

    That distinction was found by a budget tight enough to prune *every* message: the graph
    then held a thread and two people, no edges at all, and `QueryGraph` refused it - "the
    graph took no hops and holds 3 nodes for 1 seeds". The model was right and the pruner was
    wrong. `access.disclose` already applies this rule when the live gate removes a message;
    applying it here too means one rule for derived nodes rather than two that can disagree.

    A person dropped this way needs no record of its own. The thing that went is the branch,
    which is already filed with an executable handle, and recovering it brings the person back.

    Order is the response's own - the ladder already ranked these rows - so pruning takes from
    the tail rather than imposing a second ranking the caller never saw. This builder does not
    re-rank anything.
    """
    anchors = [node for node in nodes if node.kind is not NodeKind.MESSAGE]
    messages = [node for node in nodes if node.kind is NodeKind.MESSAGE]
    room = max(max_nodes - len(anchors), 0)
    if len(messages) <= room:
        return tuple(nodes), tuple(edges), ()
    kept = messages[:room]
    dropped = messages[room:]
    kept_ids = {node.node_id for node in (*anchors, *kept)}
    surviving = tuple(edge for edge in edges if edge.source in kept_ids and edge.target in kept_ids)
    joined = {edge.source for edge in surviving} | {edge.target for edge in surviving}
    anchors = [
        node for node in anchors if node.kind is not NodeKind.PERSON or node.node_id in joined
    ]
    by_thread: dict[str, int] = {}
    for node in dropped:
        thread = _thread_of(node, edges)
        by_thread[thread] = by_thread.get(thread, 0) + 1
    records = tuple(
        _capped_record(thread_id, count) for thread_id, count in sorted(by_thread.items())
    )
    return (*anchors, *kept), surviving, records


def _thread_of(node: EvidenceNode, edges: Sequence[EvidenceEdge]) -> str:
    """Which thread a message node belongs to, read off its own membership edge.

    Off the edge rather than off the id, because the thread is a fact the response stated and
    parsing it out of a node id would be this module inventing a second source for it.
    """
    for edge in edges:
        if edge.source == node.node_id and edge.target.startswith("gmail/thread/"):
            return edge.target.removeprefix("gmail/thread/")
    return "unknown"


def build_query_graph(
    envelope: Envelope,
    *,
    query_id: str,
    adapter: References,
    built_at: datetime,
    nodes: Sequence[EvidenceNode],
    omissions: Sequence[OmissionRecord] = (),
    max_nodes: int = DEFAULT_MAX_NODES,
    people: bool = True,
) -> GraphBuild:
    """One response, one graph, bounded - with every drop accounted for.

    `nodes` are the adapter's own (the container and message nodes it already builds from the
    response's rows) and `omissions` are the adapter's own accounting. Both are taken as
    inputs rather than rebuilt here: a second copy of either would be a second reader of the
    same response, free to disagree with the first.
    """
    freshness = _freshness(nodes)
    observed = observed_edges(envelope, adapter=adapter, freshness=freshness, people=people)
    all_nodes = (*nodes, *observed.nodes)
    references = {node.node_id: node.ref for node in all_nodes}

    # What the messages *say*, through the four gates - and the one refusal that is an
    # ambiguity rather than a denial, as its own inferred family. The same assembly
    # `orivra_expand` runs over the merged node set, so a recovered branch carries the same
    # relationship vocabulary as the branch the answer arrived with.
    said = text_edges(all_nodes, reference_of=references, freshness=freshness)

    kept_nodes, kept_edges, pruned = _prune(
        all_nodes, (*observed.edges, *said.edges), max_nodes=max_nodes
    )
    graph = QueryGraph(
        query_id=query_id,
        nodes=kept_nodes,
        edges=kept_edges,
        seeds=tuple(node.node_id for node in kept_nodes if node.kind is NodeKind.THREAD),
        hops_taken=1 if kept_edges else 0,
        omitted=(*omissions, *_unlinked_record(observed), *pruned),
        unresolved_links=said.unresolved_links(),
        built_at=built_at,
    )
    return GraphBuild(graph=graph, pruned=pruned, unresolved_links=said.unresolved_links())


def _freshness(nodes: Sequence[EvidenceNode]) -> FreshnessStatus:
    """The freshness the adapter already stamped on its own nodes.

    Minting a second one here would let the edges claim a verification the nodes did not have,
    and an edge is only as fresh as the rows it rests on.
    """
    if not nodes:
        raise ValueError(
            "a graph cannot be built from a response that returned no nodes; there is nothing "
            "for an edge to rest on and nothing for freshness to be a fact about"
        )
    return nodes[0].freshness


__all__ = ["DEFAULT_MAX_NODES", "GraphBuild", "build_query_graph", "thread_handle"]
