"""M3, first increment: the observed edges a real Gmail response produces.

Driven through `MailweaveService.search` and the `GmailAdapter`, not over hand-built rows.
The point of these edges is that they are facts *of a response*, so a test that assembled its
own rows would be testing a fixture's reply headers rather than the product's.

Two things are being held here and the second is the one that matters:

1. Every reply the response **stated** becomes an edge, with both endpoints in its support
   and its permission conjunction derived from that support rather than typed.
2. Every reply the response **did not** state becomes no edge at all, and is reported as a
   gap instead. `Linkage.NO_REPLY_HEADERS` is spelled "date-adjacent (no RFC reply headers)"
   and contract C-02a forbids reading it as a link; a graph that drew one would be inventing
   the thread structure it exists to disclose.
"""

from __future__ import annotations

import pytest

from mailweave.envelope.vocab import Depth, Linkage
from mailweave.policy.budget import BudgetRequest
from mailweave.surface.arguments import SearchRequest
from mailweave.surface.service import MailweaveService
from orivra.contracts import (
    Assertion,
    ConnectorId,
    EdgeOrigin,
    FreshnessState,
    FreshnessStatus,
    Relation,
    requirements_of,
)
from orivra.gmail_adapter import GmailAdapter
from orivra.graph import observed_edges
from orivra.graph.observed import LINKED
from tests.fixtures.mailbox import SyntheticMailbox
from tests.test_mcp_surface_round24 import mailbox, make_service

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@pytest.fixture
def box() -> SyntheticMailbox:
    return mailbox()


@pytest.fixture
def service(box: SyntheticMailbox) -> MailweaveService:
    return make_service(box)


@pytest.fixture
def adapter(service: MailweaveService) -> GmailAdapter:
    return GmailAdapter(service=service, granted_scopes=(SCOPE,))


def _search(query: str) -> SearchRequest:
    return SearchRequest(
        query=query,
        view=Depth.SNIPPET,
        scan_max_pages=None,
        budget=BudgetRequest(),
        disclosed_token_request=None,
    )


def _fresh(adapter: GmailAdapter) -> FreshnessStatus:
    status = adapter.permission_context()
    return FreshnessStatus(verified_at=status.observed_at, state=FreshnessState.FRESH)


@pytest.fixture
def built(adapter: GmailAdapter, service: MailweaveService):
    envelope = service.search(_search("vendor"))
    return envelope, observed_edges(envelope, adapter=adapter, freshness=_fresh(adapter))


# -- the response has to be worth reading before anything below means anything ---------------


def test_the_response_this_file_reads_actually_returned_rows(built) -> None:
    envelope, _ = built
    rows = [row for source in envelope.sources for row in source.messages]
    assert rows, "no rows came back; every assertion below would pass vacuously"


def test_every_row_the_response_returned_is_a_member_of_its_thread(built) -> None:
    """Membership is the one relation a `threads.get` states about every row it returns."""
    envelope, result = built
    membership = {
        edge.source: edge.target for edge in result.edges if edge.relation is Relation.THREAD_MEMBER
    }
    for source in envelope.sources:
        for row in source.messages:
            assert membership[f"gmail/message/{row.id}"] == f"gmail/thread/{source.thread_id}"


# -- stated links become edges; unstated ones become gaps ------------------------------------


def test_a_reply_edge_exists_exactly_where_the_row_named_a_parent_this_response_holds(
    built,
) -> None:
    envelope, result = built
    held = {row.id for source in envelope.sources for row in source.messages}
    expected = {
        (row.id, row.reply_parent_id)
        for source in envelope.sources
        for row in source.messages
        if row.linkage in LINKED and row.reply_parent_id in held
    }
    drawn = {
        (edge.source.removeprefix("gmail/message/"), edge.target.removeprefix("gmail/message/"))
        for edge in result.edges
        if edge.relation is Relation.REPLY_TO
    }
    assert drawn == expected


def test_a_date_adjacent_row_produces_no_edge_and_is_reported_as_a_gap(built) -> None:
    """C-02a, which is the whole reason this builder reads `linkage` and not position.

    A thread whose rows carry no RFC reply headers is a thread whose structure this response
    does not know. Drawing the obvious chain would manufacture exactly the claim the wire
    model refuses to make, and a reader has no way to tell a manufactured chain from a real
    one once it is an edge.
    """
    envelope, result = built
    unstated = {
        row.id
        for source in envelope.sources
        for row in source.messages
        if row.linkage not in LINKED
    }
    if not unstated:
        pytest.skip("this mailbox stated a parent for every row; the gap path is unexercised")
    reported = {gap.message_id for gap in result.undetermined}
    assert unstated == reported
    replying = {
        edge.source.removeprefix("gmail/message/")
        for edge in result.edges
        if edge.relation is Relation.REPLY_TO
    }
    assert not (unstated & replying), "a row with no stated parent was given one"


def test_the_thread_start_is_not_reported_as_a_broken_chain(built) -> None:
    """The first message of a thread has no parent and never did. Filing that beside a
    genuinely broken reply chain as the same fact buries the one a reader can act on.

    The distinction is only available when the response holds the whole thread, and that
    condition is asserted here rather than assumed: in a truncated thread the earliest row
    returned may have a parent that was simply not fetched, and calling that a thread start
    would be the response explaining away a gap with a fact it does not have.
    """
    envelope, result = built
    by_thread = {source.thread_id: source for source in envelope.sources}
    for gap in result.undetermined:
        if not gap.explained_by_being_first:
            continue
        source = by_thread[gap.thread_id]
        assert gap.position == 0
        assert source.included == source.stated_total, (
            "a truncated thread's earliest row was called a thread start"
        )


def test_a_gap_in_a_truncated_thread_is_never_explained_away_as_a_start(built) -> None:
    envelope, result = built
    partial = {
        source.thread_id for source in envelope.sources if source.included != source.stated_total
    }
    for gap in result.undetermined:
        if gap.thread_id in partial:
            assert not gap.explained_by_being_first


def test_the_gap_carries_the_linkage_that_explains_it(built) -> None:
    """A gap with no cause is a gap a reader cannot act on: "no Message-ID" and "reply headers
    carried no readable Message-ID" are different problems with different recoveries."""
    _, result = built
    for gap in result.undetermined:
        assert isinstance(gap.linkage, Linkage)
        assert gap.linkage not in LINKED
        assert gap.thread_id


# -- what every edge owes, whatever relation it is -------------------------------------------


def test_every_edge_is_observed_metadata_and_therefore_quotes_nothing(built) -> None:
    """The observed/inferred distinction, read off the relation rather than set by the builder.

    A metadata edge carrying spans invites a reader to check a header field against text that
    did not produce it; a metadata edge carrying a confidence reads as an inference that was
    promoted. The edge model refuses both, and this asserts the builder never tries.
    """
    _, result = built
    for edge in result.edges:
        assert edge.origin is EdgeOrigin.OBSERVED
        assert edge.assertion is Assertion.METADATA
        assert edge.spans == ()
        assert edge.confidence is None
        assert edge.stated is None


def test_every_edge_carries_both_endpoints_in_support_and_derives_its_own_conjunction(
    built,
) -> None:
    """`requires` is re-derived and compared by the model. This asserts the builder hands it
    the derivation rather than a hand-typed conjunction that happens to match today."""
    _, result = built
    for edge in result.edges:
        by_node = {reference.node_id for reference in edge.support}
        assert {edge.source, edge.target} <= by_node
        assert sorted(one.hash for one in edge.requires) == sorted(
            one.hash for one in requirements_of(edge.support)
        )
        for requirement in edge.requires:
            assert requirement.connector is ConnectorId.GMAIL


def test_no_edge_names_a_message_this_response_did_not_return(built) -> None:
    """The disclosure rule, one layer out. An edge to a withheld message would disclose that
    the message exists - and `QueryGraph` refuses a dangling endpoint anyway, so a builder
    that emitted one would produce a graph that cannot be constructed."""
    envelope, result = built
    held = {f"gmail/message/{row.id}" for source in envelope.sources for row in source.messages}
    held |= {f"gmail/thread/{source.thread_id}" for source in envelope.sources}
    # Person nodes are the graph's own, minted here rather than by the adapter, so they are
    # held too - but only the ones this builder actually minted, which is the scoping the
    # participant half depends on.
    held |= {node.node_id for node in result.nodes}
    for edge in result.edges:
        assert edge.source in held
        assert edge.target in held


def test_a_named_parent_outside_the_response_is_a_separate_fact_from_an_unnamed_one(
    built,
) -> None:
    """Two different absences with two different recoveries: "this response never established
    a parent" is a question for the headers, and "the parent is a message you were not shown"
    is a question for a wider fetch. Folding them together loses which one to ask."""
    _, result = built
    assert not (
        {gap.message_id for gap in result.undetermined}
        & {gap.message_id for gap in result.parent_outside_graph}
    )
    for gap in result.parent_outside_graph:
        assert gap.linkage in LINKED, "a row with no stated parent is not a parent-outside case"


def test_edge_ids_are_unique_so_a_graph_can_hold_them(built) -> None:
    """`QueryGraph` refuses duplicate identities. Membership and reply edges share endpoints,
    so the id has to carry the relation as well as the pair."""
    _, result = built
    ids = [edge.edge_id for edge in result.edges]
    assert len(set(ids)) == len(ids)


# -- the participant half ---------------------------------------------------------------------


def test_a_person_node_is_minted_only_for_an_address_that_touched_a_returned_row(
    built,
) -> None:
    """The participant index names every message an address touched in the thread, including
    ones the disclosure ladder withheld. A node whose roles were earned entirely by withheld
    messages would carry a claim about rows the caller was never shown, and its edges would
    have nowhere to land."""
    envelope, result = built
    held = {row.id for source in envelope.sources for row in source.messages}
    by_address = {
        participant.address: participant
        for source in envelope.sources
        for participant in source.participants
    }
    minted = {node.node_id.removeprefix("gmail/person/") for node in result.nodes}
    for address, participant in by_address.items():
        touched = (frozenset(participant.authored) | frozenset(participant.addressed)) & held
        assert (address in minted) == bool(touched), address


def test_a_person_nodes_reason_names_only_roles_it_actually_holds(built) -> None:
    envelope, result = built
    held = {row.id for source in envelope.sources for row in source.messages}
    by_address = {
        participant.address: participant
        for source in envelope.sources
        for participant in source.participants
    }
    for node in result.nodes:
        address = node.node_id.removeprefix("gmail/person/")
        participant = by_address[address]
        for role in node.reason.roles:
            assert frozenset(getattr(participant, role)) & held, (address, role)


def test_a_reply_to_header_is_not_treated_as_taking_part(built) -> None:
    """`Reply-To` is a routing instruction, and `mentioned` is something a *body* says - which
    makes it content the stated-assertion gates own rather than metadata this module may read.
    Neither becomes a participant edge."""
    _, result = built
    for node in result.nodes:
        assert set(node.reason.roles) <= {"authored", "addressed"}


def test_turning_people_off_removes_the_nodes_and_their_edges_and_nothing_else(
    adapter, service
) -> None:
    """The selector's knob. Person nodes join threads that share no reply chain, which is the
    point on a decision question and pure width on an exact lookup - so it has to be possible
    to build the graph without them, and to do so without disturbing the reply tree."""
    envelope = service.search(_search("vendor"))
    fresh = _fresh(adapter)
    with_people = observed_edges(envelope, adapter=adapter, freshness=fresh)
    without = observed_edges(envelope, adapter=adapter, freshness=fresh, people=False)
    assert without.nodes == ()
    person_relations = {Relation.AUTHORED_BY, Relation.SENT_TO}
    assert not [edge for edge in without.edges if edge.relation in person_relations]
    # Compared on identity rather than on whole objects: `adapter.reference` stamps each
    # `PermissionContext` with the instant it was observed, so two builds of the same graph
    # differ in a timestamp that is a fact of the build and not of the edge.
    def identity(edges):
        return [(e.edge_id, e.source, e.target, e.relation) for e in edges]

    kept = tuple(edge for edge in with_people.edges if edge.relation not in person_relations)
    assert identity(without.edges) == identity(kept)
    assert without.undetermined == with_people.undetermined
