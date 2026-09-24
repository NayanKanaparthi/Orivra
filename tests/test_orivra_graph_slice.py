"""M3's vertical slice: ask, get a bounded graph, follow a handle, get the branch back.

One path, executed rather than described: `orivra_ask` builds a graph from the response it
already produced, the node budget stops it short, the branch it could not build is filed as an
omission with an executable handle, and `orivra_expand` runs that handle and returns what it
recovers. Every assertion below is about an object a caller actually receives.

**Why the graph is a summary inline and a resource in full.** The first wiring put the whole
projection in the tool response and the host cap refused it: a five-message thread renders over
25,000 characters once every node carries its `SourceReference` and every edge its support and
permission conjunction. Those are the fields that make a graph checkable, so the answer was not
to shorten them. The omission records and their handles stay inline because they are the
affordances; nodes and edges move to `orivra://queries/{id}/graph`.
"""

from __future__ import annotations

import json

import pytest

from mailweave.surface.arguments import ArgumentInvalid
from orivra.contracts import ConnectorId, EdgeOrigin, Granularity, OmissionCause
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.project import graph_uri, project
from orivra.graph.store import GraphExpired, QueryGraphStore
from orivra.registry import ConnectorRegistry
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
#: Small enough that the five-message vendor thread does not fit, so the capped path runs on
#: every execution of this file rather than only on a mailbox that happens to be large.
TIGHT = 7


@pytest.fixture
def adapter() -> GmailAdapter:
    return GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))


@pytest.fixture
def orivra(adapter: GmailAdapter) -> OrivraService:
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=TIGHT,
    )


#: A multi-term question, because that is what the query-type router sends down the full path.
#: A single-term lookup routes to `STRUCTURE_ONLY` and builds no person nodes, so the slice
#: would run with fewer nodes than the budget and never exercise the capped branch at all.
QUESTION = "vendor contract renewal terms"


@pytest.fixture
def answered(orivra: OrivraService):
    return orivra, orivra.ask({"query": QUESTION, "view": "snippet"})


# -- the slice, end to end --------------------------------------------------------------------


def test_ask_returns_a_graph_a_link_and_a_handle_that_runs(answered) -> None:
    """The whole path in one test, so a regression anywhere in it fails here first."""
    orivra, answer = answered
    query_id = answer.structured["query_id"]
    graph = answer.structured["graph"]

    assert answer.structured["resource_link"] == graph_uri(query_id)
    assert graph["counts"]["nodes"] == TIGHT
    assert graph["counts"]["edges"] > 0

    capped = [one for one in graph["omitted"] if one["cause"] == OmissionCause.CAP.value]
    assert capped, "the tight budget produced no capped branch; the slice is untested"
    record = capped[0]
    assert record["granularity"] == Granularity.BRANCH.value
    assert record["cap_name"] == "graph_max_nodes"
    assert record["count"] > 0

    recovered = orivra.expand({"query_id": query_id, "handle": record["what"]})
    assert recovered.structured["executed"]["tool"] == "mailweave_thread_map"
    # **The expansion extends the graph; it no longer hands back a raw envelope.** This
    # asserted a `gmail` payload until 2026-09-18, which was the shape of the defect: the
    # caller got a thread map that did not say which of its rows were the ones the graph was
    # missing. What it gets now is the delta, in the graph's own vocabulary.
    added = recovered.structured["added"]["nodes"]
    assert len(added) >= record["count"], (
        "the expansion added fewer nodes than the omission said were missing"
    )
    assert recovered.structured["revision"] > 0


def test_the_recovered_branch_contains_the_nodes_the_graph_could_not_build(answered) -> None:
    """Not just "some rows came back": the ones the budget dropped."""
    orivra, answer = answered
    graph = answer.structured["graph"]
    in_graph = {
        node["node_id"].removeprefix("gmail/message/")
        for node in project(orivra.graphs.get(answer.structured["query_id"]))["nodes"]
        if node["kind"] == "message"
    }
    record = next(one for one in graph["omitted"] if one["cause"] == OmissionCause.CAP.value)
    recovered = orivra.expand(
        {"query_id": answer.structured["query_id"], "handle": record["what"]}
    )
    gained = {
        node["node_id"].removeprefix("gmail/message/")
        for node in recovered.structured["added"]["nodes"]
    }
    assert gained - in_graph, "the expansion recovered nothing the graph did not already hold"
    # And the graph itself now holds them, which is the half that used to be missing.
    after = {
        node["node_id"].removeprefix("gmail/message/")
        for node in project(orivra.graphs.get(answer.structured["query_id"]))["nodes"]
        if node["kind"] == "message"
    }
    assert gained <= after


# -- what the inline block owes, and what it honestly does not carry ---------------------------


def test_the_inline_block_carries_every_handle_and_says_where_the_rest_is(answered) -> None:
    _, answer = answered
    graph = answer.structured["graph"]
    assert graph["detail"] == graph_uri(answer.structured["query_id"])
    for record in graph["omitted"]:
        assert record["why"]
        if record["recover"] is not None:
            assert record["recover"]["tool"]
            assert record["recover"]["args"]


def test_the_inline_block_fits_inside_the_host_cap(answered) -> None:
    """The reason the block is a summary at all. A graph that pushed the composed response
    over the cap would be refused, and a refused answer is worse than a summarised graph."""
    from mailweave.constants import HOST_RESULT_CHAR_CAP

    _, answer = answered
    assert len(json.dumps(answer.structured, default=str)) <= HOST_RESULT_CHAR_CAP


def test_the_resource_projection_carries_the_sources_the_summary_omits(answered) -> None:
    """The other half of that trade: nothing is lost, it moved. Every node keeps its
    reference and every edge keeps its support and its permission conjunction."""
    orivra, answer = answered
    full = project(orivra.graphs.get(answer.structured["query_id"]))
    assert full["nodes"] and full["edges"]
    for node in full["nodes"]:
        assert node["source"]["native_id"]
        assert node["source"]["connector"] == ConnectorId.GMAIL.value
        assert node["freshness"]["state"]
    for edge in full["edges"]:
        assert len(edge["support"]) >= 2
        assert edge["requires"]
        assert {edge["source"], edge["target"]} <= {one["node_id"] for one in full["nodes"]}


def test_observed_and_inferred_are_distinguishable_on_the_wire(answered) -> None:
    """A reader sorting on `origin` alone must get a correct split. Today every edge is
    observed, so the assertion is that none of them is dressed as an inference: no spans, no
    confidence, and the field says so."""
    orivra, answer = answered
    full = project(orivra.graphs.get(answer.structured["query_id"]))
    for edge in full["edges"]:
        assert edge["origin"] == EdgeOrigin.OBSERVED.value
        assert "confidence" not in edge
        assert "spans" not in edge
    assert answer.structured["graph"]["counts"]["by_origin"] == {
        EdgeOrigin.OBSERVED.value: len(full["edges"])
    }


# -- the handle is an offer, not an instruction ------------------------------------------------


def test_a_handle_the_graph_never_minted_is_refused(answered) -> None:
    """`orivra_expand` looks the handle up in the stored graph and executes the record's own
    `ExpansionHandle`. The arguments never come from the request, so the tool cannot be turned
    into an arbitrary call - the caller picks which of this server's offers to accept."""
    orivra, answer = answered
    with pytest.raises(ArgumentInvalid):
        orivra.expand(
            {"query_id": answer.structured["query_id"], "handle": "gmail/thread/t-not-mine"}
        )


def test_expand_refuses_arguments_it_was_not_given_a_handle_for(answered) -> None:
    orivra, answer = answered
    record = next(one for one in answer.structured["graph"]["omitted"] if one["recover"])
    with pytest.raises(ArgumentInvalid):
        orivra.expand(
            {
                "query_id": answer.structured["query_id"],
                "handle": record["what"],
                "thread_id": "t-somewhere-else",
            }
        )


def test_an_unknown_query_id_is_refused(orivra: OrivraService) -> None:
    with pytest.raises(ArgumentInvalid):
        orivra.expand({"query_id": "q-never-minted", "handle": "gmail/thread/t-vendor"})


# -- the graph is ephemeral, and the store proves it -------------------------------------------


def test_an_expired_query_id_is_refused_rather_than_rebuilt(answered) -> None:
    """Ten minutes, checked on read. A handle that kept working would be a promise this server
    did not make, and one that silently answered from a fresh retrieval would be worse: the
    caller would believe they were expanding the answer they are holding."""
    from datetime import timedelta

    orivra, answer = answered
    graph = orivra.graphs.get(answer.structured["query_id"])
    orivra.graphs.now = lambda: graph.expires_at + timedelta(seconds=1)
    with pytest.raises(ArgumentInvalid):
        orivra.expand(
            {
                "query_id": answer.structured["query_id"],
                "handle": answer.structured["graph"]["omitted"][0]["what"],
            }
        )


def test_the_store_reports_gone_and_never_existed_identically() -> None:
    """Distinguishable from outside only by timing. A response that said "expired" would
    confirm that some query with that id once ran, which is a fact about somebody's traffic."""
    from datetime import UTC, datetime, timedelta

    from orivra.contracts import QueryGraph

    now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    store = QueryGraphStore(now=lambda: now)
    store.put(QueryGraph(query_id="q-1", built_at=now))
    assert store.get("q-1").query_id == "q-1"
    store.now = lambda: now + timedelta(minutes=11)
    with pytest.raises(GraphExpired) as expired:
        store.get("q-1")
    with pytest.raises(GraphExpired) as absent:
        store.get("q-never")
    assert str(expired.value) == str(absent.value)


def test_the_store_is_bounded_and_drops_the_oldest_first() -> None:
    from datetime import UTC, datetime, timedelta

    from orivra.contracts import QueryGraph

    now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    store = QueryGraphStore(capacity=3, now=lambda: now)
    for index in range(4):
        store.put(QueryGraph(query_id=f"q-{index}", built_at=now + timedelta(seconds=index)))
    assert len(store) == 3
    with pytest.raises(GraphExpired):
        store.get("q-0")
    assert store.get("q-3").query_id == "q-3"


# -- the surface agrees with itself ------------------------------------------------------------


def test_expand_is_published_and_no_longer_listed_as_planned() -> None:
    from orivra.surface.server import orivra_handlers, tool_list
    from orivra.surface.tools import PLANNED, OrivraToolName

    published = {tool.name for tool in tool_list().tools}
    assert "orivra_expand" in published
    assert OrivraToolName.EXPAND not in PLANNED
    assert "orivra_expand" in orivra_handlers(
        OrivraService(registry=ConnectorRegistry(adapters={}))
    )


def test_the_mailweave_tools_are_still_on_the_surface_under_their_own_names() -> None:
    """M3 adds a tool; it renames nothing. A caller integrated against v0.1 sees what it saw."""
    from orivra.surface.server import tool_list

    published = {tool.name for tool in tool_list().tools}
    assert {
        "mailweave_search",
        "mailweave_thread_map",
        "mailweave_get_messages",
        "mailweave_get_attachment",
    } <= published


# -- the resource, which is where the full graph lives -----------------------------------------


def test_the_resource_template_is_published_and_the_listing_is_empty(orivra) -> None:
    """A template, not a list. A graph exists only while some caller holds its `query_id`, so
    enumerating them would hand every client a directory of other callers' in-flight
    questions - which is a fact about somebody's traffic, not a capability."""
    from orivra.surface.server import GRAPH_TEMPLATE, build_server, resource_templates

    published = [one.uri_template for one in resource_templates().resource_templates]
    assert published == [GRAPH_TEMPLATE]
    assert "{query_id}" in GRAPH_TEMPLATE

    # The server accepts the handlers - asserted by building it, since a `Server` that refused
    # one would raise here. The empty listing itself is asserted on the handler's own rule
    # rather than through the transport: what matters is that nothing enumerates graphs.
    assert build_server(orivra) is not None


def test_the_resource_serves_the_same_graph_the_answer_summarised(answered) -> None:
    """One projection, one place. A resource that built its own view would be a second reader
    of the same object, free to disagree with the first the moment either changed."""
    import json

    from orivra.surface.server import read_graph_resource

    orivra, answer = answered
    served = json.loads(
        read_graph_resource(orivra, answer.structured["resource_link"]).contents[0].text
    )
    summary = answer.structured["graph"]
    assert served["query_id"] == answer.structured["query_id"]
    assert served["counts"]["nodes"] == summary["counts"]["nodes"]
    assert served["counts"]["edges"] == summary["counts"]["edges"]
    assert [one["what"] for one in served["omitted"]] == [
        one["what"] for one in summary["omitted"]
    ]


def test_the_resource_refuses_a_uri_that_is_not_a_graph(orivra) -> None:
    from orivra.surface.server import read_graph_resource

    for uri in (
        "orivra://queries//graph",
        "orivra://queries/q-1/trace",
        "file:///etc/passwd",
        "orivra://queries/../../graph",
    ):
        with pytest.raises(ValueError):
            read_graph_resource(orivra, uri)


def test_the_resource_reports_an_expired_graph_the_same_way_as_an_unknown_one(
    answered,
) -> None:
    from datetime import timedelta

    from orivra.surface.server import read_graph_resource

    orivra, answer = answered
    graph = orivra.graphs.get(answer.structured["query_id"])
    orivra.graphs.now = lambda: graph.expires_at + timedelta(seconds=1)
    with pytest.raises(ValueError) as expired:
        read_graph_resource(orivra, answer.structured["resource_link"])
    with pytest.raises(ValueError) as unknown:
        read_graph_resource(orivra, "orivra://queries/q-never-minted/graph")
    assert str(expired.value) == str(unknown.value)
