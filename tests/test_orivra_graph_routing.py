"""Which questions get a graph, and the response saying which branch ran.

Plan §8.2a ships the query-type selector with M3 so the graph is off for simple lookups from
the start. The cost argument is the smaller half: a graph over an exact lookup answers a
question nobody asked, and the host cap is fixed, so width spent on a neighbourhood is depth
not spent on the message the caller named.

Every case here goes through `OrivraService.ask`, because the routing is only worth testing
where it actually runs - the same reason the H2 wiring tests go through the command.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mailweave.query.analysis import analyse
from mailweave.surface.arguments import ArgumentInvalid
from orivra.contracts import ConnectorId
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.route import GraphRoute, route_for
from orivra.registry import ConnectorRegistry
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def orivra() -> OrivraService:
    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=7
    )


def _route(query: str, **kwargs: object) -> GraphRoute:
    return route_for(analyse(query, now=NOW), **kwargs).route  # type: ignore[arg-type]


# -- the decision itself -----------------------------------------------------------------------


def test_a_query_that_names_one_message_by_identifier_gets_no_graph() -> None:
    """Read off the parse, not off the string. A raw-substring check would fire on a quoted
    phrase that merely mentions the operator and miss a spelling the parser normalises - the
    reasoning `ranking.gate._is_an_identifier_route` already settled, applied here."""
    assert _route("rfc822msgid:<a@b.invalid>") is GraphRoute.OFF
    assert _route("rfc822msgid:<a@b.invalid> cutover") is GraphRoute.OFF
    # The same words as a phrase are not an identity route: nothing is being named.
    assert _route('"rfc822msgid is how you name one" cutover') is not GraphRoute.OFF


def test_a_single_term_lookup_gets_structure_without_people() -> None:
    """A thread's shape is part of reading it; joining threads through participants is a
    different question, and one term did not ask it."""
    decision = route_for(analyse("invoice", now=NOW))
    assert decision.route is GraphRoute.STRUCTURE_ONLY
    assert decision.build is True
    assert decision.people is False


def test_a_multi_term_question_gets_the_full_graph() -> None:
    decision = route_for(analyse("why did we reverse the larch decision", now=NOW))
    assert decision.route is GraphRoute.FULL
    assert decision.people is True


def test_an_explicit_request_wins_in_both_directions() -> None:
    """The routing is a default, not a policy a caller has to work around."""
    assert _route("rfc822msgid:<a@b.invalid>", requested=True) is GraphRoute.FULL
    assert _route("why did we reverse the larch decision", requested=False) is GraphRoute.OFF


def test_every_route_carries_a_sentence_that_names_its_own_reason() -> None:
    for query in ("rfc822msgid:<a@b.invalid>", "invoice", "why did we reverse the decision"):
        decision = route_for(analyse(query, now=NOW))
        assert len(decision.why) > 40
        assert decision.why.splitlines() == [decision.why]


# -- what the caller actually receives ---------------------------------------------------------


def test_an_identifier_lookup_answers_without_a_graph_and_says_so(
    orivra: OrivraService,
) -> None:
    """**Absent and explained, never absent and silent.** A graph that is sometimes missing
    and never says why is indistinguishable from one that failed to build, and a caller cannot
    tell a routing decision from a defect by looking at the response."""
    answer = orivra.ask({"query": "rfc822msgid:<x@y.invalid>", "view": "snippet"})
    graph = answer.structured["graph"]
    assert graph["built"] is False
    assert "rfc822msgid" in graph["routing"]
    assert "resource_link" not in answer.structured


def test_a_question_gets_a_graph_with_people_in_it(orivra: OrivraService) -> None:
    answer = orivra.ask({"query": "vendor contract renewal terms", "view": "snippet"})
    graph = answer.structured["graph"]
    assert graph["counts"]["nodes"] > 0
    assert graph["counts"]["by_relation"].get("obs.meta.authored_by", 0) > 0
    assert answer.structured["resource_link"]


def test_a_single_term_lookup_gets_a_graph_with_no_person_edges(
    orivra: OrivraService,
) -> None:
    answer = orivra.ask({"query": "vendor", "view": "snippet"})
    by_relation = answer.structured["graph"]["counts"]["by_relation"]
    assert by_relation.get("obs.meta.thread_member", 0) > 0
    assert "obs.meta.authored_by" not in by_relation
    assert "obs.meta.sent_to" not in by_relation


def test_turning_the_graph_off_still_answers_the_question(orivra: OrivraService) -> None:
    """The graph is an addition, not a precondition. A caller who wants none gets the same
    Gmail answer they got before M3."""
    with_graph = orivra.ask({"query": "vendor", "view": "snippet"})
    without = orivra.ask({"query": "vendor", "view": "snippet", "graph": False})
    assert without.structured["graph"]["built"] is False

    # Compared on the rows, not on the whole block: each search stamps its own `fetched_at`
    # and mints its own `map_id`, which are facts of the call rather than of the answer.
    def rows(answer):
        return [
            (source["thread_id"], row["id"], row["role"], row["depth"])
            for source in answer.structured["gmail"]["sources"]
            for row in source["messages"]
        ]

    assert rows(without) == rows(with_graph)
    assert rows(without), "the comparison is vacuous if the query returned nothing"


def test_the_graph_argument_is_a_boolean_and_says_so(orivra: OrivraService) -> None:
    with pytest.raises(ArgumentInvalid):
        orivra.ask({"query": "vendor", "view": "snippet", "graph": "yes"})


def test_no_graph_is_stored_for_a_query_that_was_routed_off(orivra: OrivraService) -> None:
    """Routed off means nothing was built, not that something was built and hidden - so there
    is no handle to expand and no graph holding a ten-minute reference to the response."""
    before = len(orivra.graphs)
    answer = orivra.ask({"query": "rfc822msgid:<x@y.invalid>", "view": "snippet"})
    assert len(orivra.graphs) == before
    with pytest.raises(ArgumentInvalid):
        orivra.expand(
            {"query_id": answer.structured["query_id"], "handle": "gmail/thread/t-vendor"}
        )
