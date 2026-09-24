"""The two corrections: tools reach the whole graph, and expansion extends it.

**Tools-first.** MCP resources are optional for clients; tools are not. The first wiring put
the full projection behind `orivra://queries/{id}/graph` because it did not fit inside the
host cap, which left a client with no resource support holding counts. "11 edges" does not
tell anyone which message replied to which, so every test below that inspects the graph does
it through `call(service, "orivra_graph", ...)` - the shipped tool boundary - and never reads
a resource.

**Expansion.** Following a handle used to fetch a thread map and leave the graph untouched, so
a caller held a graph missing nodes and a map that did not say which rows were the missing
ones. It now merges, deduplicates, bounds, bumps a revision, and refuses rather than blending
two snapshots that disagree.

**Live authorization on every disclosure.** A stored `PermissionRequirement` records what an
edge rested on when it was built. Whether this caller may see it now is a different question
and it is asked on every page, every expansion and every resource read.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mailweave.surface.arguments import ArgumentInvalid
from orivra.contracts import ConnectorId, ContentVersion, FreshnessState
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.access import LiveProbe, disclose
from orivra.graph.merge import IncompatibleSnapshot, merge
from orivra.graph.page import Selection, paginate
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call, read_graph_resource
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "vendor contract renewal terms"
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


def tool(service: OrivraService, name: str, args: dict) -> dict:
    """Through the published surface, not the service method. A tool a client can call is the
    thing under test; calling the method directly would skip the dispatch table, the argument
    partition and the response model that a real client goes through."""
    result = call(service, name, args)
    assert not result.is_error, result.content
    return dict(result.structured_content or {})


def all_items(service: OrivraService, query_id: str, select: str) -> list[dict[str, Any]]:
    """Every item of one selection, following the cursor with the view it came with.

    **Pages hold fewer items since the budget started charging for both projections**, which
    is the point of the change: a page is charged for what the host is handed, and the host is
    handed the structured items *and* the text that renders them. Anything the page cannot
    afford stays reachable through the continuation, so a reader who wants the whole selection
    follows it - exactly as a client does.
    """
    out: list[dict[str, Any]] = []
    cursor: int | None = 0
    view: str | None = None
    while cursor is not None:
        args: dict[str, Any] = {"query_id": query_id, "select": select}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = tool(service, "orivra_graph", args)
        out.extend(dict(one) for one in page["items"])
        cursor, view = page["next_cursor"], page["view"]
    return out


@pytest.fixture
def asked(orivra: OrivraService):
    return orivra, tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})


# -- 1. a client with no resource support -----------------------------------------------------


def test_a_client_with_no_resource_support_can_read_every_edge(asked) -> None:
    """The guarantee the summary broke. Not counts: the actual relations, each naming its two
    endpoints and the references it rests on."""
    service, answer = asked
    page = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert page["total"] == answer["graph"]["counts"]["edges"]
    assert page["items"], "the page carried no relations at all"
    for edge in page["items"]:
        assert edge["source"] and edge["target"] and edge["relation"]
        assert len(edge["support"]) >= 2, "an edge arrived without the references it rests on"
        assert edge["requires"], "an edge arrived without its permission conjunction"
    relations = {(one["source"], one["relation"], one["target"]) for one in page["items"]}
    assert len(relations) == len(page["items"]), "the page repeated a relation"


def test_the_pages_cover_every_node_and_every_omission_too(asked) -> None:
    service, answer = asked
    for select, count_key in (("nodes", "nodes"), ("omissions", "omitted")):
        page = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": select})
        assert page["total"] == answer["graph"]["counts"][count_key] or select == "omissions"
        assert page["items"]
    nodes = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "nodes"})
    for node in nodes["items"]:
        assert node["source"]["native_id"], "a node arrived with no source reference"
        assert node["freshness"]["state"]


def test_the_paged_tool_and_the_resource_return_the_same_projection(asked) -> None:
    """One projection, two doors. A caller who paged and a caller who read the resource have
    to be able to compare notes, which they cannot do if the two shapes differ."""
    service, answer = asked
    paged = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    served = json.loads(read_graph_resource(service, answer["resource_link"]).contents[0].text)
    assert paged["items"] == served["edges"][: len(paged["items"])]


def test_a_page_is_bounded_by_characters_rather_than_by_count() -> None:
    """A fixed page size either wastes the budget on small items or blows it on large ones.

    This test used to also assert that a page "always returns at least one item". That was the
    wrong rule: it shipped an item over the response cap, and the host cuts an oversized
    response where nothing can declare the cut. The oversized case now lives in
    `tests/test_orivra_graph_paging.py` as its own contract - named, stepped over, recoverable.
    """
    fat = [{"id": index, "pad": "x" * 9_000} for index in range(4)]
    page = paginate(
        fat,
        select=Selection.NODES,
        render=lambda one: one,
        identity=lambda one: str(one["id"]),
        cursor=0,
        revision=0,
    )
    assert 0 < len(page.items) < len(fat)
    assert page.next_cursor == len(page.items)
    assert page.view


def test_paging_reaches_the_end_and_reports_it(asked) -> None:
    service, answer = asked
    seen: list[dict[str, Any]] = []
    cursor, guard = 0, 0
    page: dict[str, Any] = {}
    while True:
        guard += 1
        assert guard < 50, "paging did not terminate"
        args = {"query_id": answer["query_id"], "select": "edges"}
        if cursor:
            args |= {"cursor": cursor, "view": page["view"]}
        page = tool(service, "orivra_graph", args)
        seen.extend(page["items"])
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert len(seen) == page["total"]


def test_branch_level_disclosure_returns_only_the_edges_touching_one_node(asked) -> None:
    """For a caller following a thread rather than reading a whole graph."""
    service, answer = asked
    scoped = tool(
        service,
        "orivra_graph",
        {"query_id": answer["query_id"], "select": "edges", "node": "gmail/message/v-1"},
    )
    assert scoped["items"]
    for edge in scoped["items"]:
        assert "gmail/message/v-1" in (edge["source"], edge["target"])
    whole = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert scoped["total"] < whole["total"]


def test_a_bad_cursor_or_selection_is_refused_rather_than_clamped(asked) -> None:
    service, answer = asked
    for bad in (
        {"select": "everything"},
        {"cursor": -1, "view": "whatever"},
        {"cursor": 10_000, "view": "whatever"},
        {"node": "gmail/message/not-in-this-graph"},
        {"unknown": 1},
    ):
        with pytest.raises(ArgumentInvalid):
            service.graph({"query_id": answer["query_id"], **bad})


# -- 2. expansion extends the graph ------------------------------------------------------------


def test_expansion_adds_the_recovered_nodes_to_the_graph_and_bumps_the_revision(
    asked,
) -> None:
    service, answer = asked
    before = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    before_all = all_items(service, answer["query_id"], "edges")
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")

    expanded = tool(service, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})
    assert expanded["revision"] == before["revision"] + 1
    assert expanded["added"]["nodes"], "the expansion added no nodes"
    assert expanded["added"]["edges"], "the expansion added no relations"
    assert expanded["graph"]["hops_taken"] > 0

    after = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert after["revision"] == expanded["revision"]
    assert after["total"] > before["total"], "the graph did not grow"
    # Over the whole selection, not one page of it: since the budget charges for both the
    # structured items and the text that renders them, a page holds fewer of them and the rest
    # arrive through the continuation.
    was = {(one["source"], one["relation"], one["target"]) for one in before_all}
    now = {
        (one["source"], one["relation"], one["target"])
        for one in all_items(service, answer["query_id"], "edges")
    }
    assert was < now, "the earlier relations did not survive the merge"
    added = {(one["source"], one["relation"], one["target"]) for one in expanded["added"]["edges"]}
    assert added == now - was, "what expand reported adding is not what the graph gained"


def test_the_newly_available_nodes_are_readable_with_their_own_sources(asked) -> None:
    """Counts are not sufficient: the recovered rows have to be inspectable afterwards."""
    service, answer = asked
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    expanded = tool(service, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})
    recovered = {one["node_id"] for one in expanded["added"]["nodes"]}

    nodes = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "nodes"})
    held = {one["node_id"]: one for one in nodes["items"]}
    assert recovered <= set(held)
    for node_id in recovered:
        assert held[node_id]["source"]["native_id"]
        assert held[node_id]["freshness"]["state"]
        # And it is reachable as a branch, which is the point of having added it.
        scoped = tool(
            service,
            "orivra_graph",
            {"query_id": answer["query_id"], "select": "edges", "node": node_id},
        )
        assert scoped["items"]


def test_expansion_deduplicates_rather_than_doubling_the_thread(asked) -> None:
    """A thread map returns the whole thread, so most of what it recovers is already held."""
    service, answer = asked
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    expanded = tool(service, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})
    assert expanded["added"]["already_held"], "nothing was reported as already held"
    assert not (
        {one["node_id"] for one in expanded["added"]["nodes"]}
        & set(expanded["added"]["already_held"])
    )
    nodes = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "nodes"})
    ids = [one["node_id"] for one in nodes["items"]]
    assert len(ids) == len(set(ids)), "the merge duplicated a node"


def test_the_recovered_branchs_own_omission_is_retired_by_the_merge(asked) -> None:
    """An offer the caller has already accepted is an offer that now misleads."""
    service, answer = asked
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    tool(service, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})
    after = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"})
    assert not [one for one in after["items"] if one["what"] == handle and one["cause"] == "cap"]


def test_two_snapshots_at_different_versions_are_refused_rather_than_blended(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """**The rule that matters most.** Stitching two snapshots taken at different revisions
    produces a reply tree whose upper half predates a change its lower half reflects - a
    structure that was never true at any instant. A gap is better, because a gap is visible."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])
    held = next(node for node in graph.nodes if node.kind.value == "message")
    moved = held.model_copy(
        update={
            "ref": held.ref.model_copy(
                update={
                    "version": ContentVersion(
                        connector=ConnectorId.GMAIL,
                        native_id=held.ref.native_id,
                        revision="a-later-revision",
                    )
                }
            )
        }
    )
    with pytest.raises(IncompatibleSnapshot) as clash:
        merge(
            graph,
            nodes=(moved,),
            edges=(),
            recovered_from="gmail/thread/t-vendor",
            at=orivra.now(),
            max_nodes=99,
        )
    assert held.node_id in str(clash.value)
    assert "Ask again" in str(clash.value)


def test_an_incompatible_expansion_reaches_the_caller_as_a_refusal(asked) -> None:
    """And the refusal is an argument error, not a server defect: the caller's move is a fresh
    question, which is something they can do."""
    service, answer = asked
    graph = service.graphs.get(answer["query_id"])
    stale = graph.model_copy(
        update={
            "nodes": tuple(
                node.model_copy(
                    update={
                        "ref": node.ref.model_copy(
                            update={
                                "version": ContentVersion(
                                    connector=ConnectorId.GMAIL,
                                    native_id=node.ref.native_id,
                                    revision="from-another-era",
                                )
                            }
                        )
                    }
                )
                if node.kind.value == "message"
                else node
                for node in graph.nodes
            )
        }
    )
    service.graphs.put(stale)
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    with pytest.raises(ArgumentInvalid) as refused:
        service.expand({"query_id": answer["query_id"], "handle": handle})
    assert "cannot be composed" in str(refused.value)


def test_a_merge_is_bounded_and_accounts_for_what_still_did_not_fit(
    orivra: OrivraService,
) -> None:
    # Built with no headroom, rather than mutated: `OrivraService` is frozen, and a test that
    # reached past that would be testing a service the server cannot construct.
    tight = OrivraService(registry=orivra.registry, max_graph_nodes=TIGHT, expansion_headroom=0)
    answer = tool(tight, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = tight.graphs.get(answer["query_id"])
    omissions = tool(tight, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"})
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    expanded = tool(tight, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})
    assert len(tight.graphs.get(answer["query_id"]).nodes) == len(graph.nodes), (
        "a merge with no headroom added nodes past the bound"
    )
    if expanded["omitted"]:
        assert expanded["omitted"][0]["cause"] == "cap"
        assert expanded["omitted"][0]["recover"]["tool"] == "mailweave_thread_map"


# -- 3. live authorization on every stored-graph path -------------------------------------------


class _NarrowedGrant(GmailAdapter):
    """The adapter, with the grant narrowed after the graph was built.

    A subclass rather than a stand-in, because `ConnectorRegistry.gmail()` type-checks what it
    hands out - and a test whose double the registry would refuse would be testing a
    configuration the server cannot be in.
    """

    def permission_context(self, ref=None):
        context = super().permission_context(ref)
        return context.model_copy(update={"scope_set": ("https://example.invalid/narrower",)})


def _narrowed(adapter: GmailAdapter) -> _NarrowedGrant:
    return _NarrowedGrant(service=adapter.service, granted_scopes=adapter.granted_scopes)


def test_a_narrowed_grant_withholds_edges_from_a_stored_graph(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """**A stored requirement is not a check.** The graph was built under a grant that
    satisfied every edge; the caller's grant is narrower now, and the stored copy must not be
    what decides."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])
    assert graph.edges, "the fixture built no edges to withhold"

    shown = disclose(graph, probe=LiveProbe(adapter=_narrowed(adapter)), observed_at=orivra.now())
    assert shown.edges == (), "edges survived a grant that does not authorise them"
    assert shown.narrowed is True
    withheld = [one for one in shown.omitted if one.cause.value == "permission"]
    assert withheld, "nothing recorded the withholding"
    assert withheld[0].presence_free is True
    assert withheld[0].what == ""
    assert withheld[0].count is None, (
        "a count of what was withheld is an existence claim about what the caller may not see"
    )


def test_a_deleted_message_is_not_served_from_the_stored_graph(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])

    class _Gone:
        def permission_context(self, ref=None):
            return adapter.permission_context(ref)

        def version_of(self, ref):
            return ContentVersion(
                connector=ConnectorId.GMAIL, native_id=ref.native_id, deleted=True
            )

    shown = disclose(graph, probe=LiveProbe(adapter=_Gone()), observed_at=orivra.now())
    assert not [node for node in shown.nodes if node.kind.value == "message"]
    gone = [one for one in shown.omitted if one.cause.value == "source_gone"]
    assert gone and gone[0].presence_free is True


def test_a_message_whose_revision_moved_is_served_stale_and_never_fresh(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """Served, because the caller asked for the graph they were handed and a changed row is a
    fact worth seeing. Never labelled fresh, because it is not."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])

    class _Moved:
        def permission_context(self, ref=None):
            return adapter.permission_context(ref)

        def version_of(self, ref):
            return ContentVersion(
                connector=ConnectorId.GMAIL, native_id=ref.native_id, revision="moved-on"
            )

    shown = disclose(graph, probe=LiveProbe(adapter=_Moved()), observed_at=orivra.now())
    messages = [node for node in shown.nodes if node.kind.value == "message"]
    assert messages, "every message was dropped; a stale row is served, not withheld"
    assert all(node.freshness.state is FreshnessState.STALE for node in messages)
    assert shown.stale


def test_a_derived_node_is_kept_only_while_a_message_it_rests_on_survives(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """Person and thread nodes are not probed - they have no version of their own - so their
    reachability is established over the graph instead. That is stricter than skipping the
    check, not looser: when the messages go, they go."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])
    assert [node for node in graph.nodes if node.kind.value == "person"]

    class _AllGone:
        def permission_context(self, ref=None):
            return adapter.permission_context(ref)

        def version_of(self, ref):
            return ContentVersion(
                connector=ConnectorId.GMAIL, native_id=ref.native_id, deleted=True
            )

    shown = disclose(graph, probe=LiveProbe(adapter=_AllGone()), observed_at=orivra.now())
    assert shown.nodes == (), "a person node outlived every message it was derived from"


def test_the_resource_runs_the_same_live_gate_as_the_tool(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """The resource is not a side door. If it skipped the gate it would be the one path where
    a narrowed grant did not apply."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    orivra.registry.adapters[ConnectorId.GMAIL] = _narrowed(adapter)
    served = json.loads(read_graph_resource(orivra, answer["resource_link"]).contents[0].text)
    assert served["edges"] == []
    assert served["narrowed_by_live_check"] is True


def test_the_live_check_runs_on_every_page_not_once_per_graph(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """A grant can be narrowed between two pages of the same read."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    first = tool(orivra, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert first["items"] and first["narrowed_by_live_check"] is False
    orivra.registry.adapters[ConnectorId.GMAIL] = _narrowed(adapter)
    second = tool(orivra, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert second["items"] == []
    assert second["narrowed_by_live_check"] is True


def test_the_probe_asks_the_source_once_per_item_within_one_disclosure(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """Cached within a disclosure and not across one. Across would be the same mistake a layer
    down: a cheaper answer to a question whose whole point is that it is asked now."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    graph = orivra.graphs.get(answer["query_id"])
    asked_for: list[str] = []

    class _Counting:
        def permission_context(self, ref=None):
            return adapter.permission_context(ref)

        def version_of(self, ref):
            asked_for.append(ref.native_id)
            return adapter.version_of(ref)

    probe = LiveProbe(adapter=_Counting())
    disclose(graph, probe=probe, observed_at=orivra.now())
    assert len(asked_for) == len(set(asked_for)), "the same item was probed twice in one pass"
    messages = {node.ref.native_id for node in graph.nodes if node.kind.value == "message"}
    assert set(asked_for) == messages, "a non-message reference was probed for a version"

    disclose(graph, probe=LiveProbe(adapter=_Counting()), observed_at=orivra.now())
    assert len(asked_for) == 2 * len(messages), "a second disclosure reused the first's answers"


# -- 4. the surface agrees with itself ----------------------------------------------------------


def test_orivra_graph_is_published_and_dispatchable() -> None:
    from orivra.surface.server import orivra_handlers, tool_list
    from orivra.surface.tools import PLANNED, OrivraToolName

    published = {one.name for one in tool_list().tools}
    assert "orivra_graph" in published
    assert OrivraToolName.GRAPH not in PLANNED
    assert "orivra_graph" in orivra_handlers(OrivraService(registry=ConnectorRegistry(adapters={})))
    assert {"mailweave_search", "mailweave_thread_map"} <= published
