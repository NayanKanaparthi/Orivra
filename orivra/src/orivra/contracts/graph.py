"""`QueryGraph`: the query-time context graph, and the checks that hold it together.

**Query-time, not persistent** (plan §2, §5.1). The graph is built for one question and
discarded; what survives is the bounded cache of things that are expensive and stable -
vectors, normalised metadata, source-native structure, observed edges - and not the graph
itself. A `QueryGraph` is kept for its `ttl` only so `orivra_expand` and the query resources
can address it, which is a statelessness accommodation and not a store.

This module is where the checks that need **the nodes and the edges together** live. The
edge model can refuse an edge that contradicts itself; only the graph can refuse an edge
that points at a node nobody put in it, or a claim whose quotation does not appear in the
content it claims to quote. Both are refused here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Self

from pydantic import Field, model_validator

from orivra.contracts.edges import EvidenceEdge
from orivra.contracts.entities import Entity, EntityCandidate
from orivra.contracts.nodes import EvidenceNode, Span
from orivra.contracts.omission import OmissionRecord
from orivra.contracts.refs import Frozen
from orivra.contracts.vocab import NodeKind

#: How long a built graph stays addressable. Ten minutes, per plan §5.1.
#:
#: Long enough that an agent reading a response can follow an expansion handle without the
#: graph having gone; short enough that "ephemeral" is true rather than aspirational.
DEFAULT_TTL: timedelta = timedelta(minutes=10)


class QueryGraph(Frozen):
    """The nodes and edges one query assembled, plus what it left out.

    `query_id` is server-minted and passed back by the client, because MCP revision
    2026-07-28 is stateless: there is no session to hang a graph on, so the identifier is
    the whole of the continuity and the server holds the graph under it for `ttl`.
    """

    query_id: str = Field(min_length=1, max_length=128)
    nodes: tuple[EvidenceNode, ...] = ()
    edges: tuple[EvidenceEdge, ...] = ()
    seeds: tuple[str, ...] = ()
    hops_taken: int = Field(default=0, ge=0)
    omitted: tuple[OmissionRecord, ...] = ()
    #: Links the bodies carried that no node in this graph represents, each with the node it
    #: came from and why it resolved to nothing.
    #:
    #: **On the graph rather than only on the build** (2026-09-19). They used to live on
    #: `GraphBuild` and reach the caller only inline, in the `orivra_ask` block. That made them
    #: the one part of the block that could not be compacted when the answer and its graph
    #: would not both fit the host cap: dropping them would have been a silent loss, because
    #: nothing else held them. Held here, they are servable by `orivra_graph select=links` like
    #: any other part of the graph, under the same live-access gate - a link is only served
    #: when the node it came from survives disclosure, because the URL is a thing that node's
    #: body said.
    unresolved_links: tuple[dict[str, str], ...] = ()
    entities: tuple[Entity, ...] = ()
    candidates: tuple[EntityCandidate, ...] = ()
    built_at: datetime
    ttl: timedelta = DEFAULT_TTL
    #: How many times this graph has been extended by an expansion. `0` is the graph the
    #: answer built. It is here rather than in a wrapper because a caller holding a page of
    #: nodes needs to know which version of the graph it came from - two pages from different
    #: revisions are not a consistent view, and nothing else in the payload would say so.
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _identities_are_unique(self) -> Self:
        seen_nodes = [node.node_id for node in self.nodes]
        if len(set(seen_nodes)) != len(seen_nodes):
            duplicated = sorted({n for n in seen_nodes if seen_nodes.count(n) > 1})
            raise ValueError(
                f"node ids {duplicated} appear more than once; two rows for one item are two "
                "answers to one question, and an edge then points at whichever one its "
                "builder held"
            )
        seen_edges = [edge.edge_id for edge in self.edges]
        if len(set(seen_edges)) != len(seen_edges):
            raise ValueError("edge ids are not unique within one graph")
        return self

    @model_validator(mode="after")
    def _every_endpoint_and_seed_is_in_the_graph(self) -> Self:
        present = {node.node_id for node in self.nodes}
        for edge in self.edges:
            for role, node_id in (("source", edge.source), ("target", edge.target)):
                if node_id not in present:
                    raise ValueError(
                        f"edge {edge.edge_id!r} names {role} {node_id!r}, which is not a node "
                        "of this graph; an edge to a node nobody disclosed asserts a "
                        "relationship to something the reader cannot see or check"
                    )
        for seed in self.seeds:
            if seed not in present:
                raise ValueError(
                    f"seed {seed!r} is not a node of this graph; the seed set is what "
                    "retrieval put in before expansion, and one that is not there was "
                    "dropped without an omission record"
                )
        return self

    @model_validator(mode="after")
    def _every_span_string_matches_the_content_it_quotes(self) -> Self:
        """GraphRAG's covariate rule, enforced where the source content is in scope.

        `nodes.py` can check that a claim carries spans; only here is the quoted node
        available to check that the quotation is *in* it. A node that carries no content was
        never read at this depth, so a span quoting it is refused rather than skipped -
        skipping is how an unverifiable quotation becomes an unchecked one.
        """
        by_id = {node.node_id: node for node in self.nodes}
        quoting: list[tuple[str, Span]] = [
            (f"node {node.node_id!r}", span) for node in self.nodes for span in node.spans
        ]
        quoting += [(f"edge {edge.edge_id!r}", span) for edge in self.edges for span in edge.spans]
        for owner, span in quoting:
            quoted_node = by_id.get(span.node_id)
            if quoted_node is None:
                raise ValueError(
                    f"{owner} quotes {span.node_id!r}, which is not a node of this graph"
                )
            content = quoted_node.content
            if content is None:
                raise ValueError(
                    f"{owner} quotes {quoted_node.node_id!r}, which carries no content at "
                    f"depth {quoted_node.depth.value!r}; a quotation from text that was "
                    "never read cannot be checked, and an unverifiable quotation published "
                    "as evidence is the failure the span rule exists to prevent"
                )
            if content[span.start : span.end] != span.text:
                raise ValueError(
                    f"{owner} quotes {quoted_node.node_id!r} at [{span.start}, {span.end}) "
                    "and the text there is not what the span preserved; a span that does "
                    "not string-match its source is an extraction nobody can check"
                )
        return self

    @model_validator(mode="after")
    def _a_claim_is_derived_from_nodes_this_graph_holds(self) -> Self:
        present = {node.node_id for node in self.nodes}
        for node in self.nodes:
            if node.kind is not NodeKind.CLAIM:
                continue
            missing = [origin for origin in node.derived_from if origin not in present]
            if missing:
                raise ValueError(
                    f"claim {node.node_id!r} is derived from {missing}, which this graph does "
                    "not hold; a claim whose sources are absent is an assertion with its "
                    "evidence removed"
                )
        return self

    @model_validator(mode="after")
    def _a_candidate_relates_entities_this_graph_holds(self) -> Self:
        known = {entity.entity_id for entity in self.entities}
        for candidate in self.candidates:
            for side in (candidate.left, candidate.right):
                if side not in known:
                    raise ValueError(
                        f"entity candidate names {side!r}, which is not an entity of this "
                        "graph; a likeness between one known identity and an unknown one "
                        "cannot be judged by the reader it is disclosed to"
                    )
        return self

    @model_validator(mode="after")
    def _hops_and_seeds_agree(self) -> Self:
        if self.hops_taken == 0 and len(self.nodes) > len(self.seeds):
            raise ValueError(
                f"the graph took no hops and holds {len(self.nodes)} nodes for "
                f"{len(self.seeds)} seeds; nodes beyond the seed set arrived by an expansion "
                "the hop count does not account for"
            )
        return self

    @property
    def expires_at(self) -> datetime:
        """When this graph stops being addressable. **A property, like the accessor below.**

        It was a plain method, and that shape is a live footgun on a value whose whole use is
        a comparison: `graph.expires_at <= now` raises, but `if graph.expires_at:` is a bound
        method and therefore always true, so an expiry check written that way silently never
        expires anything. Two derived accessors on one model should not differ in how they are
        called; this one moves to match `edge_count_by_origin` rather than the other way, so
        the safe spelling is the only spelling.
        """
        return self.built_at + self.ttl

    @property
    def edge_count_by_origin(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in self.edges:
            counts[edge.origin.value] = counts.get(edge.origin.value, 0) + 1
        return counts


__all__ = ["DEFAULT_TTL", "QueryGraph"]
