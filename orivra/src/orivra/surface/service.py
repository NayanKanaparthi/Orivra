"""`OrivraService`: what the Orivra tools do, over the sources this installation has.

**It owns no retrieval policy.** Everything about how Gmail is searched, what may be spent,
how deep to disclose and whether a response may be emitted at all belongs to
`MailweaveService`, and this class calls it. What is decided here is which adapters to ask
and how to present what they return - which is one level up from anything v0.1 owns, and is
deliberately the only thing at this level.

**The Gmail container is MailWeave's payload, not a rendering of it.** `orivra_ask` runs the
question through the Gmail adapter, which delegates to `MailweaveService.search`, and puts
the resulting envelope's rendered structured form under `gmail` verbatim. Under an injected
clock, nonce source and handle key, `orivra_ask(...)["gmail"]` and `mailweave_search(...)`
are the same bytes - which is M1's level-1 equivalence check, and it is a property of this
composition rather than a test that has to be maintained alongside it.

**The Orivra block is measured against the host's cap too.** Adding `query_id`, `per_source`
and `budget` spends the same 25,000 characters the Gmail container was fitted into. A
response that fits before the block and not after is refused rather than handed to a host
that would cut it - the same rule, and the same reason, as R-DISC-033.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.envelope.vocab import Role, ToolName
from mailweave.envelope.wire import Affordance
from mailweave.errors import MailweaveError
from mailweave.query.analysis import analyse
from mailweave.surface.arguments import ArgumentInvalid, parse_search, parse_thread_map
from mailweave.surface.partition import HostCapExceeded
from mailweave.surface.recovery import Narrowing, NarrowingKind, Recovery, narrower_call
from mailweave.surface.rendering import Rendered, render
from orivra.budget import OrivraBudget, Stage, m1_budget
from orivra.contracts import ConnectorId, NodeKind, OrivraToolName, SourceSpend, SourceState
from orivra.graph.access import LiveProbe, disclose
from orivra.graph.build import DEFAULT_MAX_NODES, build_query_graph
from orivra.graph.merge import IncompatibleSnapshot, merge
from orivra.graph.observed import observed_edges
from orivra.graph.page import PageState, Selection, StaleCursor, paginate
from orivra.graph.project import (
    compact,
    edge_payload,
    graph_uri,
    node_payload,
    omission_payload,
    summarise,
)
from orivra.graph.route import route_for
from orivra.graph.stated import ASSERTABLE_DEPTHS
from orivra.graph.store import GraphExpired, QueryGraphStore
from orivra.graph.text import text_edges
from orivra.registry import ConnectorRegistry
from orivra.surface.allocation import allocate
from orivra.surface.projection import OrivraResponse, composed_cost

#: The connectors `orivra_ask` can actually answer from in this release.
ANSWERABLE: frozenset[ConnectorId] = frozenset({ConnectorId.GMAIL})


def _now() -> datetime:
    return datetime.now(UTC)


def _mint_query_id() -> str:
    """A server-minted identifier for one query.

    Opaque and random rather than derived from the question: a query id derived from the
    query text would be the same id for two different callers asking the same thing, which
    turns a continuity token into a cross-caller handle.
    """
    return f"q-{uuid.uuid4().hex}"


@dataclass(frozen=True)
class OrivraService:
    """The Orivra tools, over one connector registry."""

    registry: ConnectorRegistry
    budget: OrivraBudget = field(default_factory=m1_budget)
    now: Callable[[], datetime] = _now
    mint_query_id: Callable[[], str] = _mint_query_id
    #: Built graphs, for their ten minutes. A statelessness accommodation, not a store - see
    #: `orivra.graph.store`. Mutable state on a frozen dataclass is deliberate: the *service*
    #: is a fixed configuration and the graphs are the in-flight working set.
    graphs: QueryGraphStore = field(default_factory=QueryGraphStore)
    max_graph_nodes: int = DEFAULT_MAX_NODES
    #: Extra nodes a merge may add beyond the build budget. An expansion the caller explicitly
    #: asked for should not be refused by the bound that caused the omission they are
    #: following - that would be an offer this server cannot honour.
    expansion_headroom: int = 40

    # -- orivra_ask ---------------------------------------------------------------------

    def ask(self, raw: Mapping[str, Any]) -> Rendered:
        """One question, answered from the sources this installation has.

        The Gmail arguments are parsed by **MailWeave's own** `parse_search`, not by a
        second reader written here. That is what makes the two paths comparable at all: a
        second parser would apply its own defaults, and two responses that differ because
        their defaults differ would fail an equivalence test for a reason that has nothing
        to do with retrieval.
        """
        asked = dict(raw)
        wanted = _requested_sources(asked.pop("sources", None))
        # The caller's explicit preference, or `None` for "you decide". `route_for` reads the
        # parse below and is the one place that decision is made.
        wants_graph = asked.pop("graph", None)
        if wants_graph is not None and not isinstance(wants_graph, bool):
            raise ArgumentInvalid("graph is true or false")
        # `sources` is already gone; a second filter for it was a condition that is always
        # true (review finding R-M1-028).
        request = parse_search(asked)
        # Analysed once, here, with MailWeave's own analyser. The retrieval path parses the
        # same string for itself; routing off a second reader's opinion of the query would be
        # a decision made about a query the retrieval never saw.
        routing = route_for(analyse(request.query, now=self.now()), requested=wants_graph)

        # **The query id is minted before the container is built, not after.** It is an input
        # to the allocation below - the reserve has to render the block that will carry it, and
        # `resource_link` is derived from it - and nothing about it depends on what the
        # retrieval finds.
        query_id = self.mint_query_id()
        budget_payload = _budget_payload(self.budget)
        # **The allocation, made before the retrieval rather than discovered after it.** This
        # is the whole of the repair: MailWeave's ladder fits its container to the room it is
        # given, and inside an `orivra_ask` the room is the host cap minus what Orivra's own
        # block will spend. Before this, the ladder was told it had the whole cap, Orivra's
        # block then spent characters the ladder had already promised away, and the composed
        # response was refused - which is how two live Desktop runs reached a cited answer
        # through `mailweave_search` and never saw a graph at all.
        allocation = allocate(
            query_id=query_id,
            # **The digest, because the digest is what is guaranteed.** The reserve is the
            # size of this block in the form `ask` can always fall back to; the full stage
            # payload is what it serves when the container left room for it. Reserving the
            # full form would hold back a thousand characters the response is willing to give
            # up first, and `mailweave`'s ladder is quantised finely enough that a thousand
            # characters is sometimes a whole layout.
            budget=_budget_digest(budget_payload),
            connectors=tuple(status.connector for status in self.registry.statuses()),
            resource_link=graph_uri(query_id),
            with_graph=routing.build,
        )

        spends: list[SourceSpend] = []
        gmail_payload: dict[str, Any] | None = None
        result = None
        mirror = ""
        if ConnectorId.GMAIL in wanted:
            result = self.registry.gmail().answer(request, host_chars=allocation.container)
            if result.envelope is None:  # pragma: no cover - `answer` builds one or raises
                # **Not an `assert`** (review finding R-M1-028). Under `-O` an assert is
                # removed, and the next line would have raised `AttributeError` on `None`;
                # with assertions on it raised `AssertionError`, which the partition does not
                # catch either. A defect in this server says so, in the taxonomy's own terms.
                raise MailweaveError(
                    "the Gmail adapter returned no envelope for a query it accepted; this is "
                    "a defect in this server, not in the call"
                )
            rendered = render(result.envelope)
            gmail_payload = rendered.structured
            mirror = rendered.text
            spends.append(result.spend)

        structured: dict[str, Any] = {
            "query_id": query_id,
            "per_source": self._per_source(spends, wanted),
            "budget": budget_payload,
            # **Declared on every answer, not only a narrowed one.** See
            # `Allocation.declaration`: a caller comparing this response against
            # `mailweave_search` needs to know the two were fitted to different rooms whether
            # or not the difference changed the evidence this time.
            "allocation": allocation.declaration(),
        }
        collapsed = _collapsed_under_allocation(gmail_payload, arguments=raw)
        if collapsed is not None:
            structured["allocation"]["disclosed_nothing"] = collapsed
        if gmail_payload is not None:
            structured["gmail"] = gmail_payload
        # **The graph is built from the same response, never from a second retrieval.** It is
        # the response's own rows and the response's own metadata, reorganised; a builder that
        # went back to the source would be answering a slightly different question under the
        # same query_id.
        if routing.build and result is not None and result.envelope is not None and result.nodes:
            build = build_query_graph(
                result.envelope,
                query_id=query_id,
                adapter=self.registry.gmail(),
                built_at=self.now(),
                nodes=result.nodes,
                omissions=result.omissions,
                max_nodes=self.max_graph_nodes,
                people=routing.people,
            )
            self.graphs.put(build.graph)
            graph_payload: dict[str, Any] = {**summarise(build.graph), "routing": routing.why}
            # **A graph of derived nodes is not a graph.** A thread node exists in virtue of
            # the messages in it and a person node in virtue of the messages they sent; with no
            # message node the graph carries no evidence, and `counts.nodes: 1` reads as "there
            # is a graph here" when there is not. A live run against a mailbox where every
            # source was split off at the ceiling reported exactly that, and the caller only
            # found out when the next call returned an empty page.
            bearing = sum(1 for node in build.graph.nodes if node.kind is NodeKind.MESSAGE)
            graph_payload["holds_evidence"] = bearing > 0
            if not bearing:
                graph_payload["why_no_evidence"] = (
                    "this graph holds no message node, so there is nothing for a relation to "
                    "rest on and nothing for a later call to disclose. Every source this "
                    "answer reached was omitted - the omission list says by which cap or "
                    "ceiling, and each record carries the call that recovers it"
                )
            if build.unresolved_links:
                # **Reported, not silently dropped.** These are URLs the bodies carried that no
                # connector in this release can point at a node. They are not edges and not
                # omission records - they are links whose target is outside this release's
                # reach, and saying so is the difference between a scoped `links_to` and a
                # `links_to` that quietly loses evidence.
                graph_payload["unresolved_links"] = [dict(one) for one in build.unresolved_links]
            structured["graph"] = graph_payload
            structured["resource_link"] = graph_uri(query_id)
        else:
            # **Absent and explained, never absent and silent.** A graph that is sometimes
            # missing and never says why is indistinguishable from one that failed to build,
            # and a caller cannot tell a routing decision from a defect by looking.
            structured["graph"] = {"built": False, "routing": routing.why}

        # **The whole response, both projections, measured before it leaves.** The allocation
        # above is an estimate of what this block would cost; this is the measurement of what
        # it did cost, and the two differ whenever the graph's own variable-length lists - its
        # omission records and its unresolved links - ran longer than the entry they were
        # reserved against.
        #
        # **When they do, Orivra's block gives way and the evidence does not.** The block is
        # this server's own account of a graph it is still holding under this `query_id`; every
        # record it sets down here is servable, paginated, by `orivra_graph`, so compacting it
        # costs the caller one call and loses nothing. The container is MailWeave's answer to
        # the question, already fitted to the room it was given, and re-fitting it would mean
        # either a second retrieval or discarding evidence that was disclosed. So the order is
        # fixed: compact the block, never the container.
        answer = OrivraResponse(tool=OrivraToolName.ASK, body=structured, mirror=mirror)
        size = rendered_chars(answer.structured(), answer.text())
        if size > HOST_RESULT_CHAR_CAP and isinstance(structured.get("graph"), dict):
            graph_block = structured["graph"]
            moved = [key for key in ("omitted", "unresolved_links") if graph_block.get(key)]
            if moved:
                structured["graph"] = compact(graph_block, paginated=moved)
                answer = OrivraResponse(tool=OrivraToolName.ASK, body=structured, mirror=mirror)
                size = rendered_chars(answer.structured(), answer.text())
        if size > HOST_RESULT_CHAR_CAP:
            # **Second and last, because it is the one that costs a round trip.** The graph's
            # lists were reachable by a call that also does work; this one is reachable by
            # `orivra_sources`, which does none. Order is by what the caller loses, not by
            # what saves the most characters.
            structured["budget"] = _budget_digest(budget_payload)
            answer = OrivraResponse(tool=OrivraToolName.ASK, body=structured, mirror=mirror)
            size = rendered_chars(answer.structured(), answer.text())
        if size > HOST_RESULT_CHAR_CAP:
            # Reached only when the container alone, at the room it was given, still will not
            # leave space for the accounting that cannot be compacted. The cap is not raised
            # and nothing is dropped quietly: the call declines, in band, with a retry.
            raise _too_large(size, gmail_payload, arguments=raw, mirror=mirror)
        return Rendered(structured=answer.structured(), text=answer.text())

    # -- orivra_expand ------------------------------------------------------------------

    def expand(self, raw: Mapping[str, Any]) -> Rendered:
        """Follow one handle out of a graph this server built, under the same `query_id`.

        **Only handles the graph itself carries are executable.** The caller names an omission
        by its `what`; this method looks that record up *in the stored graph* and executes the
        `ExpansionHandle` the record already carries. The arguments are never taken from the
        request, so `orivra_expand` cannot be turned into an arbitrary call to any tool: the
        caller chooses which of this server's own offers to accept, not what the offer is.

        That is the same rule MailWeave's affordances follow, and it is the reason the handle
        is looked up rather than parsed.
        """
        asked = dict(raw)
        query_id = asked.pop("query_id", None)
        wanted = asked.pop("handle", None)
        if asked:
            raise ArgumentInvalid(
                f"orivra_expand takes query_id and handle; it was given {sorted(asked)}"
            )
        if not isinstance(query_id, str) or not query_id.strip():
            raise ArgumentInvalid("orivra_expand needs the query_id the answer carried")
        if not isinstance(wanted, str) or not wanted.strip():
            raise ArgumentInvalid(
                "orivra_expand needs a handle: the `what` of an omission record, exactly as "
                "the answer's omission list spelled it"
            )
        try:
            graph = self.graphs.get(query_id)
        except GraphExpired as gone:
            raise ArgumentInvalid(str(gone)) from gone

        record = next(
            (held for held in graph.omitted if held.what == wanted and held.recover is not None),
            None,
        )
        if record is None or record.recover is None:
            # Same answer for "no such handle" and "that omission has no recovery": the two
            # are a distinction about this server's accounting, and spelling them apart would
            # let a caller enumerate which ids exist in a graph they hold.
            raise ArgumentInvalid(
                f"this query's graph carries no recoverable handle named {wanted!r}. The "
                "handles it does carry are the `what` values of its omission records"
            )

        handle = record.recover
        executed = {
            "tool": handle.tool.value,
            "args": dict(handle.args),
            "reduces": handle.reduces.value,
        }
        if handle.tool is not OrivraToolName.THREAD_MAP:
            # Declared rather than guessed. A handle naming a tool this method cannot execute
            # is this server's own accounting error, and saying so beats half-answering.
            raise MailweaveError(
                f"this server minted a handle naming {handle.tool.value}, which orivra_expand "
                "does not execute in this release. That is a defect here, not in the call"
            )

        adapter = self.registry.gmail()
        # **The revision this graph already observed, handed to the adapter.** It is the
        # thread's `historyId` as the answer's own response recorded it, and it is what lets
        # the structure cache be keyed on a version rather than on a thread id alone. Without
        # it the adapter has no way to ask "is this still the thread I read" that does not
        # cost the read it is trying to avoid, so it simply reads.
        known = next(
            (
                node.ref.version.revision
                for node in graph.nodes
                if node.kind is NodeKind.THREAD
                and node.ref.native_id == str(handle.args.get("thread_id", ""))
            ),
            None,
        )
        recovered = adapter.answer_thread_map(
            parse_thread_map(dict(handle.args)), known_revision=known
        )
        if recovered.envelope is None or not recovered.nodes:  # pragma: no cover - builds one
            raise MailweaveError(
                "the Gmail adapter returned no envelope for a thread map this server's own "
                "handle named; this is a defect in this server, not in the call"
            )
        # **The expansion extends the graph; it does not merely fetch.** Following a handle
        # used to return a thread map and leave the graph untouched, so a caller held a graph
        # missing nodes and a map that did not say which rows were the missing ones.
        freshness = recovered.nodes[0].freshness
        observed = observed_edges(
            recovered.envelope,
            adapter=adapter,
            freshness=freshness,
            people=any(node.kind is NodeKind.PERSON for node in graph.nodes),
        )
        # **The recovered branch gets the same relationship vocabulary the answer did.**
        # Running only `observed_edges` here left an expanded thread with metadata edges and
        # nothing a message *said*, so whether a supersession was visible depended on which
        # call had happened to return the message - which is a property of this server's
        # paging, not of the mailbox.
        #
        # Over the union of held and recovered nodes, deliberately. An assertion refused at
        # build time because its target was outside the response becomes resolvable once the
        # expansion brings that target in, and `merge` deduplicates whatever was already held.
        arriving = (*recovered.nodes, *observed.nodes)
        union = (*graph.nodes, *arriving)
        said = text_edges(
            union,
            reference_of={node.node_id: node.ref for node in union},
            freshness=freshness,
        )
        try:
            merged = merge(
                graph,
                nodes=arriving,
                edges=(*observed.edges, *said.edges),
                recovered_from=wanted,
                at=self.now(),
                max_nodes=self.max_graph_nodes + self.expansion_headroom,
            )
        except IncompatibleSnapshot as clash:
            # **Not merged, and said so.** Two snapshots at different revisions describe
            # different states of the mailbox; composing them makes a structure that was never
            # true at any instant, and a gap is better than a blend because a gap is visible.
            raise ArgumentInvalid(str(clash)) from clash
        # **The stored graph carries the union's links, so a later `select=links` page serves
        # what this expansion added as well as what the answer found.** `text_edges` above ran
        # over the union of held and recovered nodes, so `said.unresolved_links()` is already
        # the whole set rather than a delta; `merge` carried the graph's own set forward and
        # this replaces it with the union, de-duplicated on the pair that identifies a link.
        seen: set[tuple[str, str]] = set()
        links: list[dict[str, str]] = []
        for link in (*merged.graph.unresolved_links, *said.unresolved_links()):
            key = (link.get("from", ""), link.get("url", ""))
            if key not in seen:
                seen.add(key)
                links.append(dict(link))
        self.graphs.put(merged.graph.model_copy(update={"unresolved_links": tuple(links)}))

        probe = LiveProbe(adapter=adapter)
        shown = disclose(merged.graph, probe=probe, observed_at=self.now())
        added = {node.node_id for node in merged.added_nodes}
        structured: dict[str, Any] = {
            "query_id": query_id,
            "handle": wanted,
            "executed": executed,
            "revision": merged.revision,
            "added": {
                # Always present, in both branches, so a reader never has to infer it from an
                # empty list. `False` here and `True` in the overflow branch below.
                "shed": False,
                "nodes": [node_payload(node) for node in shown.nodes if node.node_id in added],
                "edges": [
                    edge_payload(edge)
                    for edge in shown.edges
                    if edge.edge_id in {one.edge_id for one in merged.added_edges}
                ],
                "already_held": list(merged.already_held),
            },
            "graph": {
                "nodes": len(shown.nodes),
                "edges": len(shown.edges),
                "omitted": len(shown.omitted),
                "hops_taken": merged.graph.hops_taken,
            },
            "omitted": [omission_payload(one) for one in merged.still_capped],
            "narrowed_by_live_check": shown.narrowed,
            "disclosure": {
                "source_backed_nodes": shown.source_backed,
                "derived_without_support": shown.derived_without_support,
            },
            # **What the cache did, in its own words.** A call-count cannot distinguish "the
            # cache was never consulted because nothing supplied a revision" from "it was
            # consulted and missed", and the first is a wiring defect while the second is the
            # cache working. The Harbor run could only report `threads.get` and had to leave
            # the reason to be guessed at.
            "cache": (recovered.cache.payload() if recovered.cache is not None else None),
            "budget": _budget_payload(self.budget),
        }
        if said.unresolved_links():
            # The merged graph's whole set, not the delta: `text_edges` ran over the union, and
            # a caller holding the graph needs what it currently cannot resolve rather than
            # what this one call happened to add to that list.
            structured["unresolved_links"] = [dict(one) for one in said.unresolved_links()]
        # Only rows whose text this graph does not already hold. A thread map re-returns the
        # whole thread, so a message the answer already disclosed at body depth arrives again
        # as a stub; naming it here would report a gap the graph does not have.
        read_already = {
            node.node_id
            for node in merged.graph.nodes
            if node.kind is NodeKind.MESSAGE and node.depth in ASSERTABLE_DEPTHS
        }
        # Over the *merged graph's* nodes, not over everything the expansion returned. A row
        # the node budget refused is not a row whose text went unread - it is a row this graph
        # does not hold, and `merged.still_capped` is where that is accounted for. Reading it
        # off the graph also keeps this list bounded by the node budget, which is what the
        # response cap below is sized against.
        unread = tuple(
            node.node_id
            for node in merged.graph.nodes
            if node.kind is NodeKind.MESSAGE
            and node.depth not in ASSERTABLE_DEPTHS
            and node.node_id not in read_already
        )
        if unread:
            # **Absent and explained, never absent and silent.** A thread map recovers the shape
            # of a branch, not its bodies, so these rows arrive at `stub` depth and the four
            # recognition gates have no text to run over. Without this the caller would read an
            # expansion carrying only `obs.meta.*` edges and have no way to tell "nobody in this
            # branch stated anything" from "nothing in this branch was read".
            #
            # No recovery handle, deliberately. `orivra_expand` executes thread-map handles and
            # nothing else, so minting one that named a body fetch would be an offer that
            # refuses when taken - the reason `links.py` carries unresolved links as themselves
            # rather than as `not_tried` omission records.
            structured["text_not_read"] = {
                "nodes": list(unread),
                "why": (
                    "these rows were recovered from a thread map, which returns each message's "
                    "place in the thread and not its body. No obs.said.* or inf.* relation is "
                    "drawn for them: there is no disclosed text for the recognition gates to "
                    "read, which is not the same as a message that said nothing. Ask again at "
                    "a body view to have them read"
                ),
            }
        expanded = OrivraResponse(tool=OrivraToolName.EXPAND, body=structured)
        mirror = expanded.text()
        size = rendered_chars(structured, mirror)
        if size > HOST_RESULT_CHAR_CAP:
            # The delta itself does not fit. Say where the rest is rather than truncating:
            # `orivra_graph` pages the merged graph and the revision above names the version.
            # **Shed, and it says so in a field a projection cannot lose by accident.** The
            # empty lists alone were read by a live run as "the expansion recovered nothing",
            # because the demonstration's own projection copied `nodes` and `edges` and dropped
            # `detail`. A boolean named `shed` cannot be dropped silently: a reader either
            # carries it or is visibly not carrying it.
            structured["added"] = {
                "shed": True,
                "nodes": [],
                "edges": [],
                "already_held": list(merged.already_held),
                "counts": {
                    "nodes": len(merged.added_nodes),
                    "edges": len(merged.added_edges),
                },
                "detail": (
                    f"the expansion added {len(merged.added_nodes)} node(s) and "
                    f"{len(merged.added_edges)} relation(s) and the delta did not fit in this "
                    f"response, so it is not repeated here. Read them with orivra_graph at "
                    f"revision {merged.revision}"
                ),
            }
            # Re-rendered, because the text projection is derived from the body and the body
            # just changed. Rendering once and reusing it would ship a text block describing a
            # delta this response no longer carries.
            mirror = OrivraResponse(tool=OrivraToolName.EXPAND, body=structured).text()
            size = rendered_chars(structured, mirror)
            if size > HOST_RESULT_CHAR_CAP:  # pragma: no cover - the envelope alone is small
                raise _too_large(size, None)
        return Rendered(structured=structured, text=mirror)

    # -- orivra_graph -------------------------------------------------------------------

    def graph(self, raw: Mapping[str, Any]) -> Rendered:
        """A page of the stored graph, through a tool, with the live gate on every page.

        **The tools-first guarantee.** MCP resources are optional for clients and tools are
        not, so a client that reads no resources must still be able to see an actual
        relationship - which message replied to which, resting on which references. Counts are
        not evidence. This returns `project`'s own node and edge forms, so a caller who paged
        and a caller who read the resource hold the same thing.
        """
        asked = dict(raw)
        query_id = asked.pop("query_id", None)
        select = asked.pop("select", Selection.EDGES.value)
        cursor = asked.pop("cursor", 0)
        scope = asked.pop("node", None)
        expect_view = asked.pop("view", None)
        if asked:
            raise ArgumentInvalid(
                f"orivra_graph takes query_id, select, cursor, node and view; it was given "
                f"{sorted(asked)}"
            )
        if expect_view is not None and not isinstance(expect_view, str):
            raise ArgumentInvalid("view is the token a previous page returned")
        if cursor and expect_view is None:
            # **A continuation without its view is refused.** Honouring it would index into a
            # list that may have moved - an expansion between the calls, or the live access
            # gate disclosing a different set - and the caller would silently skip or repeat
            # evidence with no way to detect it.
            raise ArgumentInvalid(
                "a cursor must be presented with the view token the page that produced it "
                "returned. Without it this call cannot tell whether the positions still mean "
                "what they meant"
            )
        if not isinstance(query_id, str) or not query_id.strip():
            raise ArgumentInvalid("orivra_graph needs the query_id the answer carried")
        try:
            selection = Selection(select)
        except ValueError as unknown:
            raise ArgumentInvalid(
                f"select is one of {[one.value for one in Selection]}; it was {select!r}"
            ) from unknown
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            raise ArgumentInvalid("cursor is a non-negative integer from a previous page")
        try:
            held = self.graphs.get(query_id)
        except GraphExpired as gone:
            raise ArgumentInvalid(str(gone)) from gone

        # **Live, on every page.** Not once per graph and not at build time: a grant can be
        # narrowed and a message deleted between two pages of the same read.
        adapter = self.registry.gmail()
        shown = disclose(held, probe=LiveProbe(adapter=adapter), observed_at=self.now())

        nodes, edges = shown.nodes, shown.edges
        if scope is not None:
            if not isinstance(scope, str) or not scope.strip():
                raise ArgumentInvalid("node is a node_id from this graph")
            touching = [edge for edge in edges if edge.source == scope or edge.target == scope]
            reachable = (
                {scope} | {edge.source for edge in touching} | {edge.target for edge in touching}
            )
            nodes = tuple(node for node in nodes if node.node_id in reachable)
            edges = tuple(touching)
            if not nodes:
                raise ArgumentInvalid(
                    f"this graph holds no disclosable node {scope!r}. Read select=nodes to "
                    "see the ones it does hold"
                )

        items: Sequence[Any]
        render: Callable[[Any], dict[str, Any]]
        identity: Callable[[Any], str]
        if selection is Selection.NODES:
            items, render = nodes, node_payload
            identity = lambda one: one.node_id  # noqa: E731
        elif selection is Selection.EDGES:
            items, render = edges, edge_payload
            identity = lambda one: one.edge_id  # noqa: E731
        elif selection is Selection.LINKS:
            # **Gated by the node the link came from, not served beside it.** A link payload is
            # a URL this server read out of a message body, so it is mail-derived content and
            # the live-access check applies to it exactly as it applies to the node. `disclose`
            # has already decided which nodes may be served now; a link whose `from` node was
            # withheld is withheld with it, and stays accounted for by that node's own omission
            # record rather than appearing here without the thing it came from.
            servable = {node.node_id for node in shown.nodes}
            items = [link for link in held.unresolved_links if link.get("from") in servable]
            render = dict
            identity = lambda one: f"{one.get('from')}/{one.get('url')}"  # noqa: E731
        else:
            items, render = shown.omitted, omission_payload
            # An omission has no id of its own, so the identity is the tuple that makes it the
            # record it is. Enough for the view digest, which asks "is this the same list".
            identity = lambda one: f"{one.cause.value}/{one.what}/{one.count}"  # noqa: E731
        try:
            page = paginate(
                items,
                select=selection,
                render=render,
                identity=identity,
                cursor=cursor,
                revision=held.revision,
                expect_view=expect_view,
                # Charged for what the host is handed: the structured item **and** the line
                # the text projection renders it as. One budget over both projections.
                cost=lambda rendered: composed_cost(rendered, selection.value),
            )
        except StaleCursor as moved:
            raise ArgumentInvalid(str(moved)) from moved
        except ValueError as bad:
            raise ArgumentInvalid(str(bad)) from bad

        structured: dict[str, Any] = {
            "query_id": query_id,
            "revision": page.revision,
            "select": page.select.value,
            "state": page.state.value,
            "items": list(page.items),
            "total": page.total,
            "returned_from": page.returned_from,
            "next_cursor": page.next_cursor,
            # Passed back with the next cursor. It is the whole of what makes a continuation
            # safe, so it travels with every page rather than only with a continuable one.
            "view": page.view,
            "narrowed_by_live_check": shown.narrowed,
            # **An empty page has more than one cause and they are not interchangeable.**
            # `narrowed_by_live_check` answers "did the gate withhold something servable".
            # `source_backed` answers "was there anything for it to withhold" - zero means the
            # graph carried only derived nodes, which is a fact about the graph rather than
            # about this caller's access.
            "disclosure": {
                "source_backed_nodes": shown.source_backed,
                "derived_without_support": shown.derived_without_support,
            },
            "budget": _budget_payload(self.budget),
        }
        if page.state is PageState.OVERSIZED and page.oversized is not None:
            structured["oversized"] = page.oversized
        if scope is not None:
            structured["node"] = scope
        page_text = OrivraResponse(tool=OrivraToolName.GRAPH, body=structured).text()
        size = rendered_chars(structured, page_text)
        if size > HOST_RESULT_CHAR_CAP:  # pragma: no cover - the pager is budgeted below it
            raise _too_large(size, None)
        return Rendered(structured=structured, text=page_text)

    # -- orivra_sources -----------------------------------------------------------------

    def sources(self, raw: Mapping[str, Any] | None = None) -> Rendered:
        """Every source Orivra knows about, and the state each is in.

        Reads no mail, opens no document and makes no request to any source: the states come
        from the registry, which was built at startup, and the capabilities are declared
        rather than probed.
        """
        if raw:
            raise ArgumentInvalid(
                "orivra_sources takes no arguments; it reports what this installation has, "
                f"and {sorted(raw)} would be a filter over a list of at most three rows"
            )
        rows = [
            {
                "connector": status.connector.value,
                "state": status.state.value,
                "detail": status.detail,
                "capabilities": (
                    None
                    if status.capabilities is None
                    else {
                        "native_search": status.capabilities.native_search,
                        "search_operators": list(status.capabilities.search_operators),
                        "container_kind": status.capabilities.container_kind,
                        "revisions": status.capabilities.revisions,
                        "change_feed": status.capabilities.change_feed,
                        "max_ids_per_fetch": status.capabilities.max_ids_per_fetch,
                    }
                ),
            }
            for status in self.registry.statuses()
        ]
        structured: dict[str, Any] = {
            "sources": rows,
            "budget": _budget_payload(self.budget),
        }
        return Rendered(
            structured=structured,
            text=OrivraResponse(tool=OrivraToolName.SOURCES, body=structured).text(),
        )

    # -- shared -------------------------------------------------------------------------

    def _per_source(
        self, spends: list[SourceSpend], wanted: frozenset[ConnectorId]
    ) -> list[dict[str, Any]]:
        """One row per connector Orivra knows about, whatever this query did with it.

        Every connector, not every connector that ran: a list holding only what ran cannot
        answer "did you look at Drive?", and a caller who cannot tell "not configured" from
        "found nothing" will read the second as the first.
        """
        by_connector = {spend.connector: spend for spend in spends}
        rows: list[dict[str, Any]] = []
        for status in self.registry.statuses():
            spend = by_connector.get(status.connector)
            if spend is not None:
                rows.append(
                    {
                        "connector": spend.connector.value,
                        "state": spend.state.value,
                        "asked": True,
                        "hits": spend.hits,
                        "quota_units": spend.quota_units,
                        "rungs_executed": list(spend.rungs_executed),
                        "caps_hit": list(spend.caps_hit),
                    }
                )
                continue
            not_asked = status.connector not in wanted and status.state is SourceState.READY
            rows.append(
                {
                    "connector": status.connector.value,
                    "state": (SourceState.READY.value if not_asked else status.state.value),
                    # **A field, not a sentence** (review finding R-M1-018). A connected
                    # source this call did not ask for was reported `ready` with `hits: 0`,
                    # distinguished from "searched and found nothing" only by free prose -
                    # which is the confusion this block exists to prevent.
                    "asked": False,
                    "detail": (
                        "this source is connected and was not among the sources the call asked for"
                        if not_asked
                        else status.detail
                    ),
                    "hits": 0,
                }
            )
        return rows


def _requested_sources(value: Any) -> frozenset[ConnectorId]:
    """Which sources the caller asked for, defaulting to every answerable one.

    A source this release cannot answer from is **not** an error: it comes back in
    `per_source` with its state, because a caller who names Drive is entitled to learn that
    Drive is not configured rather than to have their whole question refused.
    """
    if value is None:
        return frozenset(ANSWERABLE)
    if not isinstance(value, list) or not value:
        raise ArgumentInvalid(
            "sources must be a non-empty array of connector names; omit it to search every "
            "source this installation can answer from"
        )
    chosen: set[ConnectorId] = set()
    for item in value:
        if not isinstance(item, str):
            raise ArgumentInvalid(f"sources contains {item!r}, which is not a connector name")
        try:
            chosen.add(ConnectorId(item))
        except ValueError as unknown:
            known = ", ".join(connector.value for connector in ConnectorId)
            raise ArgumentInvalid(
                f"unknown source {item!r}; this server knows about {known}"
            ) from unknown
    return frozenset(chosen)


def _budget_payload(budget: OrivraBudget) -> dict[str, Any]:
    return {"stages": [_stage_payload(stage) for stage in budget.stages]}


def _budget_digest(payload: dict[str, Any]) -> dict[str, Any]:
    """The stage budget reduced to its shape, with the call that serves it whole.

    **The last thing `ask` gives up, and it gives up the least by doing so.** The full stage
    payload is ~1,330 characters of *invariant* accounting: it says the same thing on every
    response this installation ever returns, because it is a property of the build rather than
    of the query. `orivra_sources` already returns it - the same function, the same bytes - and
    that call takes no arguments, reads no mail and makes no request to any source, so the
    round trip it costs is a local one.

    Weighed against what the characters buy: `mailweave`'s A.9a ladder is quantised, and on a
    thread whose bodies nearly fill the cap the step below "five messages at body_clean" is
    *no messages at all*. Reserving the full payload put the container the wrong side of that
    step and answered a question with zero rows. Every stage is still named here, and whether
    it is measured, so a reader can see that nothing has silently appeared or vanished; what
    they fetch is the per-stage reason prose.
    """
    stages = payload.get("stages") or []
    return {
        "measured": [one["stage"] for one in stages if "measured_on" in one],
        "unmeasured": [one["stage"] for one in stages if "measured_on" not in one],
        "compacted": {
            "why": "figures and reasons: orivra_sources, same bytes, no arguments, reads nothing",
            "recover": {"tool": OrivraToolName.SOURCES.value, "args": {}},
        },
    }


def _stage_payload(stage: Stage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": stage.name.value,
        "connector": None if stage.connector is None else stage.connector.value,
        "limit_ms": stage.limit_ms,
    }
    if stage.measurement is None:
        payload["unmeasured_because"] = stage.unmeasured_because
    else:
        payload["measured_on"] = stage.measurement.measured_on.isoformat()
        payload["provenance"] = stage.measurement.provenance.value
        payload["adoptable"] = stage.measurement.adoptable
    return payload


def _too_large(
    size: int,
    gmail: dict[str, Any] | None,
    *,
    arguments: Mapping[str, Any] | None = None,
    mirror: str = "",
) -> HostCapExceeded:
    """The refusal for a composed response the host would cut, **with a retry that works**.

    Carries the same recovery facts MailWeave's own refusal carries, so
    `surface/recovery.narrower_call` can mint the next hop from it rather than from a second
    vocabulary invented here.

    **And for `orivra_ask`, one this server works out itself.** `narrower_call` branches on
    the tool name, and its search branch does not cover `orivra_ask`, so an oversized ask was
    declared terminal: a refusal with nothing the caller could do about it. The retry is not
    guesswork, because this function can measure the thing that decides it. An `orivra_ask`
    response is MailWeave's container plus Orivra's own block; if the container alone fits,
    the strictly narrower call is the same search through `mailweave_search`, which returns
    the same evidence without Orivra's block. If the container alone does not fit either,
    then the search itself is what has to narrow, and `narrower_call`'s own arithmetic is
    what narrows it - reached by asking it about the search rather than about the ask.

    `Affordance.tool` names one of the four constant tools by design, so a retry naming
    `orivra_ask` is not expressible and is not wanted: dropping Orivra's block *is* the
    narrowing, and naming the legacy tool is how a caller performs it.
    """
    oversized = HostCapExceeded(
        f"this response renders {size} characters against the host's "
        f"{HOST_RESULT_CHAR_CAP}-character result cap. The Gmail container was fitted to that "
        "cap by MailWeave's disclosure ladder and Orivra's own block spends the same "
        "characters, so the composed result is refused rather than handed to a host that "
        "would cut it where nothing can declare the cut"
    )
    bearing = _matched_threads(gmail)
    oversized.top_thread = bearing[0] if bearing else None
    oversized.hit_threads = len(bearing)
    if arguments is not None:
        oversized.recovery = _ask_recovery(arguments, gmail, mirror, bearing)
    return oversized


def _ask_recovery(
    arguments: Mapping[str, Any],
    gmail: dict[str, Any] | None,
    mirror: str,
    bearing: list[str],
) -> Recovery | None:
    """The one narrower call an oversized `orivra_ask` can offer, chosen by measurement."""
    plain = {key: value for key, value in arguments.items() if key not in {"graph", "sources"}}
    if gmail is not None and rendered_chars(gmail, mirror) <= HOST_RESULT_CHAR_CAP:
        return Recovery(
            affordance=Affordance(tool=ToolName.SEARCH, args=dict(plain)),
            narrowing=Narrowing(
                "tool",
                OrivraToolName.ASK.value,
                ToolName.SEARCH.value,
                kind=NarrowingKind.SCOPE_CHANGE,
            ),
            why=(
                "The same retrieval, without Orivra's block. This response is MailWeave's "
                "container plus an account of the graph built over it, and the container "
                "alone fits the cap - so the narrowing is to drop the block rather than to "
                "reduce the evidence. The graph for this query is not built on that call."
            ),
        )
    # The container alone does not fit either, so the search is what must narrow. Asked about
    # the search rather than about the ask, because that is the call whose width is limiting.
    return narrower_call(
        ToolName.SEARCH.value,
        plain,
        top_thread=bearing[0] if bearing else None,
        hit_threads=len(bearing),
    )


def _collapsed_under_allocation(
    gmail: dict[str, Any] | None, *, arguments: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Set when the retrieval found threads and the allocation disclosed none of them.

    **A distinct outcome from "nothing matched", and the two are not interchangeable.** A
    caller reading a response with no rows has to be able to tell "your mailbox has nothing
    like this" from "it does, and this call had no room for it" - the first ends the search
    and the second is one call away from an answer.

    It happens because `mailweave`'s A.9a ladder is quantised, and coarsely so on a single
    thread of long bodies: measured on 2026-09-19, the ladder asks for about 1,550 characters
    more room than the layout it picks actually renders, and on such a thread the step below
    "five messages at body_clean" is *no messages at all*. So between the room `orivra_ask` can
    give the container and the room `mailweave_search` gives it lies a band - exactly as wide
    as Orivra's reserve - where the same query answers on one path and discloses nothing on the
    other. That is a property of the ladder rather than of this allocation, and the honest
    response is to say which band this call fell into and name the call that does not.

    The named call is **not** a graph result and this does not pretend otherwise: it is the
    evidence without the graph, which is the thing the caller came for and could not be given
    here. R-07's rule is that a statement of partiality sits next to an executable call; this
    is that call.
    """
    if gmail is None:
        return None
    sources = gmail.get("sources")
    if not isinstance(sources, list) or not sources:
        # No source at all is "the retrieval reached nothing", which is a different answer and
        # already has one: the report's own `empty_diagnosis`.
        return None
    disclosed = sum(
        len(source["messages"])
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("messages"), list)
    )
    if disclosed:
        return None
    retry = {
        key: value for key, value in dict(arguments).items() if key not in {"graph", "sources"}
    }
    return {
        "sources_reached": len(sources),
        "why": (
            "the retrieval reached these sources and the container's allocation had no "
            "room for a layout that discloses any message of them. The A.9a ladder's next "
            "step down on a thread of long bodies is no messages at all, so what is missing "
            "here is the whole disclosure rather than part of it"
        ),
        "recover": {
            "tool": ToolName.SEARCH.value,
            "args": retry,
            "gets": (
                "the same retrieval at the whole host cap, which is the room this container "
                "did not have. It builds no graph: this is the evidence without it"
            ),
        },
    }


def _matched_threads(gmail: dict[str, Any] | None) -> list[str]:
    if gmail is None:
        return []
    sources = gmail.get("sources")
    if not isinstance(sources, list):
        return []
    found: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        rows = source.get("messages")
        thread_id = source.get("thread_id")
        if not isinstance(rows, list) or not isinstance(thread_id, str):
            continue
        if any(isinstance(row, dict) and row.get("role") == Role.MATCHED.value for row in rows):
            found.append(thread_id)
    return found


__all__ = ["ANSWERABLE", "OrivraService"]
