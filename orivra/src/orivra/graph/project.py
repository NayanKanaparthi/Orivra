"""Projecting a `QueryGraph` onto the wire, and onto `orivra://queries/{id}/graph`.

One projection, used by the tool response and by the resource, because a resource that showed
a different graph from the one the tool returned would be a second reader of the same object -
and the two would drift the first time either changed.

**Every node and edge carries its sources out.** A node's `ref` and an edge's `support` are
what let a reader go and check the claim, and a projection that dropped them to save bytes
would turn evidence into assertion. The permission requirements travel too: an edge says what
a caller must hold to see it, and the answer is not "whatever you held when you asked".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from orivra.contracts import (
    EvidenceEdge,
    EvidenceNode,
    OmissionRecord,
    OrivraToolName,
    QueryGraph,
)


def _reference(reference: Any) -> dict[str, Any]:
    return {
        "connector": reference.connector.value,
        "kind": reference.kind.value,
        "native_id": reference.native_id,
        "version": {
            "revision": reference.version.revision,
            "deleted": reference.version.deleted,
        },
    }


def node_payload(node: EvidenceNode) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "kind": node.kind.value,
        "role": node.role.value,
        "reason": node.reason.render(),
        "reason_kind": node.reason.kind.value,
        "depth": node.depth.value,
        "origin": node.origin.value,
        "source": _reference(node.ref),
        "freshness": {
            "state": node.freshness.state.value,
            "verified_at": node.freshness.verified_at.isoformat(),
        },
    }


def edge_payload(edge: EvidenceEdge) -> dict[str, Any]:
    """One edge, with the observed/inferred distinction on its face.

    `origin` and `assertion` are read off the relation by the model, so they cannot disagree
    with what the edge is; `spans` and `confidence` are present only on an inference, which is
    the contract's rule and not this projection's. A reader can sort by `origin` alone and get
    a correct split between what a source stated and what this server concluded.
    """
    payload: dict[str, Any] = {
        "edge_id": edge.edge_id,
        "source": edge.source,
        "target": edge.target,
        "relation": edge.relation.value,
        "origin": edge.origin.value,
        "assertion": edge.assertion.value,
        "method": {"name": edge.method.name, "version": edge.method.version},
        "support": [_reference(reference) for reference in edge.support],
        "requires": [
            {
                "connector": requirement.connector.value,
                "scope_set": list(requirement.scope_set),
                "applies_to": list(requirement.applies_to),
            }
            for requirement in edge.requires
        ],
        "freshness": {
            "state": edge.freshness.state.value,
            "verified_at": edge.freshness.verified_at.isoformat(),
        },
    }
    if edge.spans:
        payload["spans"] = [
            {"node_id": span.node_id, "start": span.start, "end": span.end, "text": span.text}
            for span in edge.spans
        ]
    if edge.confidence is not None:
        payload["confidence"] = edge.confidence.value
    if edge.stated is not None:
        payload["stated"] = {
            "asserted_by": edge.stated.asserted_by,
            "resolved_to": edge.stated.target.resolved_to,
            "considered": list(edge.stated.target.considered),
            "referring_text": edge.stated.target.referring_text,
        }
    return payload


def omission_payload(record: OmissionRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "what": record.what,
        "granularity": record.granularity.value,
        "count": record.count,
        "cause": record.cause.value,
        "why": record.why,
        "connector": record.connector.value,
    }
    if record.cap_name is not None:
        payload["cap_name"] = record.cap_name
    if record.recover is not None:
        payload["recover"] = {
            "tool": record.recover.tool.value,
            "args": dict(record.recover.args),
            "reduces": record.recover.reduces.value,
        }
    return payload


def project(graph: QueryGraph) -> dict[str, Any]:
    """The graph as the tool returns it and as the resource serves it - one shape, one place."""
    return {
        "query_id": graph.query_id,
        "built_at": graph.built_at.isoformat(),
        "expires_at": graph.expires_at.isoformat(),
        "seeds": list(graph.seeds),
        "hops_taken": graph.hops_taken,
        "counts": {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "omitted": len(graph.omitted),
            "by_origin": dict(graph.edge_count_by_origin),
        },
        "nodes": [node_payload(node) for node in graph.nodes],
        "edges": [edge_payload(edge) for edge in graph.edges],
        "omitted": [omission_payload(record) for record in graph.omitted],
    }


def summarise(graph: QueryGraph) -> dict[str, Any]:
    """The bounded block that travels **inside** the tool response.

    `project` is the whole graph and it does not fit. A five-message thread already renders
    ~25,000 characters once every node carries its `SourceReference` and every edge its
    support and its permission conjunction - and those are the fields that make the graph
    checkable, so shortening them is not available. The composed response was refused by the
    host cap, which is the rule working: MailWeave fitted the Gmail container to that cap and
    Orivra's block spends the same characters.

    So the tool returns this, and the resource serves `project`. What stays inline is chosen
    by what a caller cannot act without:

    * the **omission records with their handles**, in full. These are the affordances - a
      pruned branch whose handle lived only at a resource would be an offer the caller has to
      make a second call to discover.
    * the shape: counts by relation and by origin, and the seeds. Enough to see that the
      observed/inferred split is what it claims to be before fetching anything.
    * the link to the full graph.

    Nodes and edges themselves are **not** inline. That is a real limitation and it is named
    in the block rather than left to be discovered: `detail` says where the rest is.
    """
    by_relation: dict[str, int] = {}
    for edge in graph.edges:
        by_relation[edge.relation.value] = by_relation.get(edge.relation.value, 0) + 1
    return {
        "query_id": graph.query_id,
        "built_at": graph.built_at.isoformat(),
        "expires_at": graph.expires_at.isoformat(),
        "seeds": list(graph.seeds),
        "hops_taken": graph.hops_taken,
        "counts": {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "omitted": len(graph.omitted),
            "by_origin": dict(graph.edge_count_by_origin),
            "by_relation": by_relation,
        },
        "omitted": [omission_payload(record) for record in graph.omitted],
        "detail": graph_uri(graph.query_id),
    }


#: The keys `compact` keeps. Everything a caller needs to decide whether to page into the graph
#: at all: that it was built, whether it rests on any message, how big it is, and where it
#: started. The two variable-length lists - the omission records and the unresolved links - are
#: what it gives up, and `compact` replaces each with a count and the call that serves it.
_ENTRY_KEYS: Final[tuple[str, ...]] = (
    "query_id",
    "built_at",
    "expires_at",
    "seeds",
    "hops_taken",
    "counts",
    "detail",
)


def compact(summary: Mapping[str, Any], *, paginated: Sequence[str]) -> dict[str, Any]:
    """`summarise` reduced to an entry point, with the rest reachable and said to be.

    **What this is for.** `summarise` inlines the omission records in full, deliberately: they
    are the affordances, and a handle that lived only at a resource would be an offer the
    caller has to make a second call to discover. That reasoning holds right up to the point
    where inlining them costs the answer they are attached to. `orivra_ask` composes this block
    with MailWeave's container under one host cap; when the two will not both fit, the choice
    is between an entry point the caller can page from and no response at all.

    So the lists come out and **nothing is dropped**: each one leaves behind its own count and
    the executable `orivra_graph` call that serves it, paginated, from the graph this server is
    already holding under this `query_id`. `counts` was already carrying `omitted`, so the
    accounting was never in the list itself. The caller makes one more call and gets every
    record, with its handle, in pages that are themselves budgeted.

    `paginated` names which lists moved, so the record says what happened to *this* response
    rather than describing a policy.
    """
    entry = {key: summary[key] for key in _ENTRY_KEYS if key in summary}
    for key in ("routing", "holds_evidence", "why_no_evidence"):
        if key in summary:
            entry[key] = summary[key]
    query_id = summary.get("query_id")
    moved = []
    for key in paginated:
        moved.append(
            {
                "field": key,
                "count": len(summary.get(key) or ()),
                "recover": {
                    "tool": OrivraToolName.GRAPH.value,
                    "args": {"query_id": query_id, "select": _SELECTION_FOR[key]},
                },
            }
        )
    entry["compacted"] = {
        "why": (
            "the answer and its graph did not both fit the cap. Nothing was discarded: each "
            "list below gives its count and the call that serves it, in pages"
        ),
        "moved": moved,
    }
    return entry


#: Which `orivra_graph` selection serves each list `compact` moves out.
_SELECTION_FOR: Final[dict[str, str]] = {
    "omitted": "omissions",
    "unresolved_links": "links",
}


def graph_uri(query_id: str) -> str:
    return f"orivra://queries/{query_id}/graph"


__all__ = [
    "compact",
    "edge_payload",
    "graph_uri",
    "node_payload",
    "omission_payload",
    "project",
    "summarise",
]
