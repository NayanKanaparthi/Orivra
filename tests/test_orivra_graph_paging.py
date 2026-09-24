"""The paging contract: oversized items, and continuations that cannot silently drift.

Three failures this file exists to make impossible, each of them silent without a check:

**An item no page can carry.** The first pager always returned at least one item, reasoning
that a page returning nothing is a cursor that never advances. True, and the wrong fix: it
shipped an item over the response cap, and the host cuts an oversized response where nothing
can declare the cut. The contract now names the item, steps the cursor past it, and says the
result is recoverable.

**A continuation across an expansion.** Positions are indices. An expansion adds nodes and
edges, so index 5 of the old list and index 5 of the new one are different rows - a caller
resuming with a bare cursor skips or repeats evidence and has no way to notice.

**A continuation across a permission or freshness change.** The live access gate asks the
source on *every* page. A message deleted or a grant narrowed between two calls changes which
rows the list holds with no expansion and no revision bump, so binding a cursor to the
revision alone is not enough. The view token is over the disclosed identities in order.
"""

from __future__ import annotations

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.surface.arguments import ArgumentInvalid
from orivra.contracts import ConnectorId, ContentVersion
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.page import (
    PAGE_CHAR_BUDGET,
    PageState,
    Selection,
    StaleCursor,
    paginate,
    view_token,
)
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "vendor contract renewal terms"


@pytest.fixture
def adapter() -> GmailAdapter:
    return GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))


@pytest.fixture
def orivra(adapter: GmailAdapter) -> OrivraService:
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=7
    )


def tool(service: OrivraService, name: str, args: dict) -> dict:
    result = call(service, name, args)
    assert not result.is_error, result.content
    return dict(result.structured_content or {})


@pytest.fixture
def asked(orivra: OrivraService):
    return orivra, tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})


def _ident(one: dict) -> str:
    return str(one["id"])


# -- oversized items ---------------------------------------------------------------------------


def test_an_item_larger_than_a_page_is_named_and_stepped_over() -> None:
    """Not shipped, because the host cuts an oversized response where nothing can declare the
    cut. Not dropped, because a hole is something the caller cannot see. Named."""
    items = [
        {"id": "small-a", "pad": "x"},
        {"id": "enormous", "pad": "y" * (PAGE_CHAR_BUDGET * 2)},
        {"id": "small-b", "pad": "z"},
    ]
    first = paginate(
        items,
        select=Selection.NODES,
        render=lambda one: one,
        identity=_ident,
        cursor=0,
        revision=0,
    )
    assert first.state is PageState.OK
    assert [one["id"] for one in first.items] == ["small-a"]
    assert first.next_cursor == 1

    blocked = paginate(
        items,
        select=Selection.NODES,
        render=lambda one: one,
        identity=_ident,
        cursor=1,
        revision=0,
        expect_view=first.view,
    )
    assert blocked.state is PageState.OVERSIZED
    assert blocked.items == ()
    assert blocked.oversized is not None
    assert blocked.oversized["identity"] == "enormous"
    assert blocked.oversized["position"] == 1
    assert blocked.oversized["chars"] > blocked.oversized["budget"]
    assert blocked.next_cursor == 2, "the cursor did not step past the item nothing can carry"

    rest = paginate(
        items,
        select=Selection.NODES,
        render=lambda one: one,
        identity=_ident,
        cursor=blocked.next_cursor,
        revision=0,
        expect_view=blocked.view,
    )
    assert [one["id"] for one in rest.items] == ["small-b"]
    assert rest.complete


def test_an_oversized_item_at_the_end_reports_no_continuation() -> None:
    """Recoverable about the page, terminal about the item: there is nothing after it, so the
    cursor is `None` and the caller is not invited to ask again for the same nothing."""
    items = [{"id": "a", "pad": "x"}, {"id": "huge", "pad": "y" * (PAGE_CHAR_BUDGET * 2)}]
    first = paginate(
        items, select=Selection.NODES, render=lambda one: one, identity=_ident,
        cursor=0, revision=0,
    )
    blocked = paginate(
        items, select=Selection.NODES, render=lambda one: one, identity=_ident,
        cursor=1, revision=0, expect_view=first.view,
    )
    assert blocked.state is PageState.OVERSIZED
    assert blocked.next_cursor is None
    assert blocked.complete


def test_no_page_ever_exceeds_the_budget_it_was_given() -> None:
    """The property the oversized branch exists to preserve, asserted over every page of a
    selection that contains one."""
    import json

    items = [{"id": f"n{index}", "pad": "x" * 6_000} for index in range(6)]
    items.insert(3, {"id": "huge", "pad": "y" * (PAGE_CHAR_BUDGET * 3)})
    cursor, view, guard = 0, None, 0
    while True:
        guard += 1
        assert guard < 30
        page = paginate(
            items, select=Selection.NODES, render=lambda one: one, identity=_ident,
            cursor=cursor, revision=0, expect_view=view,
        )
        assert len(json.dumps(list(page.items))) <= PAGE_CHAR_BUDGET or not page.items
        if page.next_cursor is None:
            break
        cursor, view = page.next_cursor, page.view


def test_the_whole_response_stays_under_the_host_cap_on_every_page(asked) -> None:
    """Through the tool, where the cap actually applies - the page budget leaves room for the
    envelope, and this is what says the sum of the two still fits."""
    import json

    service, answer = asked
    cursor, view = 0, None
    for _ in range(20):
        args = {"query_id": answer["query_id"], "select": "edges"}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = tool(service, "orivra_graph", args)
        assert len(json.dumps(page, default=str)) <= HOST_RESULT_CHAR_CAP
        if page["next_cursor"] is None:
            break
        cursor, view = page["next_cursor"], page["view"]


# -- continuations bound to the view they came from ---------------------------------------------


def test_a_page_carries_the_view_its_cursor_belongs_to(asked) -> None:
    service, answer = asked
    page = tool(service, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    assert page["view"]
    assert page["state"] == PageState.OK.value


def test_a_cursor_without_its_view_is_refused(asked) -> None:
    """A bare index is exactly what silently drifts, so it is not accepted at all."""
    service, answer = asked
    with pytest.raises(ArgumentInvalid) as refused:
        service.graph({"query_id": answer["query_id"], "select": "edges", "cursor": 1})
    assert "view token" in str(refused.value)


def test_a_cursor_is_refused_after_an_expansion_moved_the_view(asked) -> None:
    """**The skip-or-repeat case.** An expansion inserts rows; resuming at the old index reads
    a different row than the one the caller was promised, and nothing about the response would
    have said so."""
    service, answer = asked
    first = tool(
        service,
        "orivra_graph",
        {"query_id": answer["query_id"], "select": "nodes"},
    )
    omissions = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "omissions"}
    )
    handle = next(one["what"] for one in omissions["items"] if one["cause"] == "cap")
    tool(service, "orivra_expand", {"query_id": answer["query_id"], "handle": handle})

    with pytest.raises(ArgumentInvalid) as refused:
        service.graph(
            {
                "query_id": answer["query_id"],
                "select": "nodes",
                "cursor": 1,
                "view": first["view"],
            }
        )
    assert "positions have moved" in str(refused.value)
    # And restarting works, which is what makes the refusal cheap rather than a dead end.
    restarted = tool(
        service, "orivra_graph", {"query_id": answer["query_id"], "select": "nodes"}
    )
    assert restarted["view"] != first["view"]
    assert restarted["total"] > first["total"]


def test_a_cursor_is_refused_after_the_live_check_changed_what_is_disclosed(
    orivra: OrivraService, adapter: GmailAdapter
) -> None:
    """**The case a revision counter alone would miss.** No expansion happens here and the
    revision does not move; the access gate simply discloses less on the second call, and the
    positions change underneath a cursor that looks valid."""
    answer = tool(orivra, "orivra_ask", {"query": QUESTION, "view": "snippet"})
    first = tool(orivra, "orivra_graph", {"query_id": answer["query_id"], "select": "edges"})
    before = orivra.graphs.get(answer["query_id"]).revision

    class _OneGone(GmailAdapter):
        def version_of(self, ref):
            if ref.native_id == "v-2":
                return ContentVersion(
                    connector=ConnectorId.GMAIL, native_id=ref.native_id, deleted=True
                )
            return super().version_of(ref)

    orivra.registry.adapters[ConnectorId.GMAIL] = _OneGone(
        service=adapter.service, granted_scopes=adapter.granted_scopes
    )
    assert orivra.graphs.get(answer["query_id"]).revision == before, (
        "the fixture must not move the revision, or it tests the wrong thing"
    )
    with pytest.raises(ArgumentInvalid) as refused:
        orivra.graph(
            {
                "query_id": answer["query_id"],
                "select": "edges",
                "cursor": 1,
                "view": first["view"],
            }
        )
    assert "positions have moved" in str(refused.value)


def test_the_view_token_moves_when_the_content_moves_and_not_otherwise() -> None:
    """The digest is over the identities in order, so a reorder counts and a re-read does
    not."""
    assert view_token(0, ["a", "b"]) == view_token(0, ["a", "b"])
    assert view_token(0, ["a", "b"]) != view_token(0, ["b", "a"])
    assert view_token(0, ["a", "b"]) != view_token(0, ["a"])
    assert view_token(0, ["a", "b"]) != view_token(1, ["a", "b"])


def test_a_stale_cursor_raises_rather_than_returning_a_wrong_page() -> None:
    items = [{"id": "a"}, {"id": "b"}]
    page = paginate(
        items, select=Selection.NODES, render=lambda one: one, identity=_ident,
        cursor=0, revision=0,
    )
    with pytest.raises(StaleCursor):
        paginate(
            [{"id": "a"}],
            select=Selection.NODES,
            render=lambda one: one,
            identity=_ident,
            cursor=1,
            revision=0,
            expect_view=page.view,
        )


def test_paging_to_the_end_with_view_tokens_returns_each_item_exactly_once(asked) -> None:
    """The property the whole mechanism protects: no skips, no repeats."""
    service, answer = asked
    seen: list[str] = []
    cursor, view, guard = 0, None, 0
    while True:
        guard += 1
        assert guard < 50
        args = {"query_id": answer["query_id"], "select": "edges"}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = tool(service, "orivra_graph", args)
        seen.extend(one["edge_id"] for one in page["items"])
        if page["next_cursor"] is None:
            break
        cursor, view = page["next_cursor"], page["view"]
    assert len(seen) == len(set(seen)), "an edge was returned twice"
    assert len(seen) == page["total"], "an edge was skipped"
