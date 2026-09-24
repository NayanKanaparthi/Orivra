"""Two paths, and the line between them.

**`obs.said.supersedes_stated` is source-stated, not inferred.** Its namespace fixes its
origin to `observed` and its assertion to `source_stated`; the edge model refuses it a
confidence, because scoring a fact of the source reads as an inference that was promoted. I
had it on the wrong side of this line in an earlier report, and the distinction is not
bookkeeping: a source-stated edge says a human wrote this down and a reader may hold the author
to it, while an inferred edge says this server concluded it and a reader may discount it.

So this file asserts both that each path produces what it should, and - the part that matters -
that **implementing the source-stated path does not give the release inferred edges**. They
have different origins, different fields, different failure modes and different inputs.

The inferred path's input is the source-stated path's *target-ambiguity* refusals and only
those, which is `resolve_target`'s own stated design. A negated clause does not become a weak
claim; a phrase that points rather than names does not become a confident one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mailweave.envelope.reasons import GmailQueryMatch, RungId
from mailweave.envelope.vocab import Depth, Role
from orivra.contracts import (
    Assertion,
    ConnectorId,
    ContentVersion,
    EdgeOrigin,
    EvidenceNode,
    FreshnessState,
    FreshnessStatus,
    NodeKind,
    PermissionContext,
    RefKind,
    Relation,
    SourceReference,
)
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.inferred import MAX_CANDIDATES, inferred_edges
from orivra.graph.stated import ASSERTABLE_DEPTHS, stated_edges
from orivra.recognise.supersede import nominate
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import mailbox, make_service

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DRAFT = "The July 3 pricing draft is attached for review."


def _ref(native_id: str) -> SourceReference:
    return SourceReference(
        connector=ConnectorId.GMAIL,
        account="account-digest",
        kind=RefKind.MESSAGE,
        native_id=native_id,
        version=ContentVersion(connector=ConnectorId.GMAIL, native_id=native_id, revision="7"),
        permission=PermissionContext(
            connector=ConnectorId.GMAIL,
            principal="account-digest",
            scope_set=(SCOPE,),
            observed_at=NOW,
        ),
    )


def _fresh() -> FreshnessStatus:
    return FreshnessStatus(verified_at=NOW, state=FreshnessState.FRESH)


def _node(native_id: str, text: str, depth: Depth = Depth.BODY_CLEAN) -> EvidenceNode:
    return EvidenceNode(
        node_id=f"gmail/message/{native_id}",
        ref=_ref(native_id),
        kind=NodeKind.MESSAGE,
        role=Role.MATCHED,
        reason=GmailQueryMatch(query="pricing", rung=RungId.L1),
        depth=depth,
        content=text,
        freshness=_fresh(),
    )


def _both(nodes: list[EvidenceNode]):
    references = {node.node_id: node.ref for node in nodes}
    stated = stated_edges(nodes, reference_of=references, freshness=_fresh())
    inferred = inferred_edges(stated.refusals, reference_of=references, freshness=_fresh())
    return stated, inferred


# -- the relation is source-stated, and the vocabulary says so --------------------------------


def test_supersedes_stated_is_observed_and_source_stated_not_inferred() -> None:
    """The correction, asserted against the vocabulary rather than against a comment."""
    assert Relation.SUPERSEDES_STATED.origin is EdgeOrigin.OBSERVED
    assert Relation.SUPERSEDES_STATED.assertion is Assertion.SOURCE_STATED
    assert Relation.SUPERSEDES_STATED.needs_asserted_by is True
    # And the inferred counterpart is a different relation with a different origin.
    assert Relation.POTENTIALLY_SUPERSEDES.origin is EdgeOrigin.INFERRED
    assert Relation.POTENTIALLY_SUPERSEDES.assertion is Assertion.DERIVED


def test_a_stated_edge_carries_spans_and_an_asserter_and_no_confidence() -> None:
    stated, _ = _both(
        [_node("mA", "This supersedes the July 3 pricing draft."), _node("mB", DRAFT)]
    )
    (edge,) = stated.edges
    assert edge.origin is EdgeOrigin.OBSERVED
    assert edge.assertion is Assertion.SOURCE_STATED
    assert edge.confidence is None, (
        "a fact of the source scored like an inference reads as one that was promoted"
    )
    assert edge.stated is not None
    assert edge.stated.asserted_by == "gmail/message/mA"
    assert edge.stated.target.resolved_to == "gmail/message/mB"
    assert edge.stated.span in edge.spans
    assert edge.spans[0].text in "This supersedes the July 3 pricing draft."


def test_the_span_is_the_quotation_the_gates_were_run_over() -> None:
    """The reader's check: the text shown is the text at those offsets in the source."""
    text = "This supersedes the July 3 pricing draft."
    stated, _ = _both([_node("mA", text), _node("mB", DRAFT)])
    (edge,) = stated.edges
    span = edge.spans[0]
    assert text[span.start : span.end] == span.text


# -- the gates refuse, and refusing is the normal case ----------------------------------------


def test_a_negated_clause_produces_no_edge_on_either_path() -> None:
    """ "We are **not** withdrawing the approval" states the opposite. Inferring a weakened
    version of a claim the writer denied is worse than drawing nothing."""
    stated, inferred = _both(
        [_node("mA", "We are not withdrawing the July 3 pricing draft."), _node("mB", DRAFT)]
    )
    assert stated.edges == ()
    assert [one.gate for one in stated.refusals] == ["clause"]
    assert inferred.edges == ()
    assert inferred.declined and "not an ambiguity" in inferred.declined[0][1]


def test_a_hypothetical_clause_is_not_nominated_at_all() -> None:
    assert nominate("If certification fails we would replace the vendor contract.") == ()


def test_a_past_tense_report_is_not_a_performance() -> None:
    """ "We superseded the draft last year" reports an event that happened somewhere this
    response cannot see. Reading a report as a performance is how a graph acquires an edge
    for a decision it never observed."""
    assert nominate("We superseded the draft last year.") == ()


def test_a_phrase_that_points_rather_than_names_produces_nothing() -> None:
    """**The over-claim this had, and lost.** "This supersedes the earlier version" matched no
    candidate. With one message in scope an inference from it would have carried confidence
    1.0 for a phrase that identifies nothing - the scope manufacturing a referent, which is
    exactly what the target gate refuses."""
    stated, inferred = _both(
        [_node("mA", "This supersedes the earlier version."), _node("mB", DRAFT)]
    )
    assert stated.edges == ()
    (refusal,) = stated.refusals
    assert refusal.gate == "target"
    assert refusal.matched == (), "a non-referring phrase must match nothing"
    assert inferred.edges == ()
    assert "points rather than names" in inferred.declined[0][1]


def test_a_snippet_row_is_never_read_for_a_stated_assertion() -> None:
    """A snippet is Gmail's excerpt and may carry quoted text, so the single-ORIGINAL-span
    annotation would be a claim about provenance nothing established."""
    assert Depth.SNIPPET not in ASSERTABLE_DEPTHS
    stated, _ = _both(
        [
            _node("mA", "This supersedes the July 3 pricing draft.", depth=Depth.SNIPPET),
            _node("mB", DRAFT),
        ]
    )
    assert stated.edges == ()
    assert stated.refusals == ()


def test_a_message_cannot_supersede_itself() -> None:
    stated, _ = _both([_node("mA", "This supersedes the July 3 pricing draft.")])
    assert stated.edges == ()


# -- the inferred path, which is a different thing ---------------------------------------------


def test_an_ambiguous_reference_becomes_inferred_edges_over_the_candidates() -> None:
    """`resolve_target`'s own stated design: several matches come back with the full candidate
    set, "exactly what an `inf.potentially_supersedes` edge needs to record the ambiguity"."""
    stated, inferred = _both(
        [
            _node("mA", "This replaces the pricing draft."),
            _node("mB", "The pricing draft revision one is attached."),
            _node("mC", "The pricing draft revision two is attached."),
        ]
    )
    assert stated.edges == (), "an ambiguous reference must not produce an observed edge"
    assert len(inferred.edges) == 2
    for edge in inferred.edges:
        assert edge.origin is EdgeOrigin.INFERRED
        assert edge.assertion is Assertion.DERIVED
        assert edge.relation is Relation.POTENTIALLY_SUPERSEDES
        assert edge.confidence is not None
        assert edge.confidence.value == pytest.approx(0.5)
        assert edge.spans, "an inference with nothing quoted is an assertion"
        assert edge.stated is None, "an inference is not a source-stated check"
    targets = {edge.target for edge in inferred.edges}
    assert targets == {"gmail/message/mB", "gmail/message/mC"}


def test_the_confidence_falls_as_the_ambiguity_widens() -> None:
    nodes = [_node("mA", "This replaces the pricing draft.")]
    for index in range(3):
        nodes.append(_node(f"m{index}", f"The pricing draft revision {index} is attached."))
    _, inferred = _both(nodes)
    assert len(inferred.edges) == 3
    assert inferred.edges[0].confidence is not None
    assert inferred.edges[0].confidence.value == pytest.approx(1 / 3, abs=1e-3)
    assert "1/n" in inferred.edges[0].confidence.basis


def test_the_confidence_says_on_the_wire_that_it_is_an_allocation_not_a_probability() -> None:
    """The distinction has to survive into the response, not stay in a docstring.

    `1/n` spreads one unit of belief over candidates nothing distinguishes. It is not an
    estimate that this edge is true: it assumes the true target is among the candidates at
    all, it assumes they are equiprobable because nothing separates them rather than because
    anything established that they are, and no labelled set has been scored against the
    method. A caller who reads 0.5 as a 50% hit rate and thresholds on it is doing something
    this number does not support, so the number says so where the caller will read it.
    """
    nodes = [_node("mA", "This replaces the pricing draft.")]
    for index in range(2):
        nodes.append(_node(f"m{index}", f"The pricing draft revision {index} is attached."))
    _, inferred = _both(nodes)
    assert inferred.edges
    total = 0.0
    for edge in inferred.edges:
        assert edge.confidence is not None
        basis = edge.confidence.basis
        assert "heuristic allocation" in basis
        assert "not a calibrated probability" in basis
        assert "No labelled set has been scored" in basis
        assert "not comparable with another method's" in basis
        total += edge.confidence.value
    # An allocation's shares sum to one. That is the property it actually has, and it is a
    # different property from "each of these is 50% likely to be the right edge".
    assert total == pytest.approx(1.0, abs=1e-3)


def test_an_inference_spread_too_wide_is_declined_rather_than_drawn() -> None:
    """Past the cap the edge set is a statement about how much was in scope rather than about
    the sentence - the failure the target gate refuses one candidate at a time."""
    nodes = [_node("mA", "This replaces the pricing draft.")]
    for index in range(MAX_CANDIDATES + 1):
        nodes.append(_node(f"m{index}", f"The pricing draft revision {index} is attached."))
    _, inferred = _both(nodes)
    assert inferred.edges == ()
    assert inferred.declined
    assert "statement about how much was in scope" in inferred.declined[0][1]


def test_the_two_paths_never_produce_the_same_edge() -> None:
    """The whole point of the correction. One input produces one kind or the other, and the
    kinds are distinguishable by origin without reading anything else."""
    for nodes in (
        [_node("mA", "This supersedes the July 3 pricing draft."), _node("mB", DRAFT)],
        [
            _node("mA", "This replaces the pricing draft."),
            _node("mB", "The pricing draft revision one."),
            _node("mC", "The pricing draft revision two."),
        ],
    ):
        stated, inferred = _both(nodes)
        assert not (stated.edges and inferred.edges)
        origins = {edge.origin for edge in (*stated.edges, *inferred.edges)}
        assert len(origins) <= 1


def test_implementing_the_stated_path_did_not_produce_any_inferred_edge() -> None:
    """Named plainly, because the claim it refutes is one I made: a release with
    `supersedes_stated` working still has an untested inferred path unless the inferred path
    is built and tested on its own, which is what the file above this line does."""
    stated, inferred = _both(
        [_node("mA", "This supersedes the July 3 pricing draft."), _node("mB", DRAFT)]
    )
    assert stated.edges
    assert inferred.edges == ()
    assert all(edge.origin is EdgeOrigin.OBSERVED for edge in stated.edges)


# -- through the real response, not over constructed nodes ---------------------------------------


def test_the_families_are_drawn_from_a_real_gmail_response() -> None:
    """End to end, because a family wired into the build and never run through a response is a
    family that works in a unit test and is broken in the product.

    The fixture thread states one supersession that resolves, links to a message the graph
    holds, links to a document outside the mailbox, and denies a supersession in its last
    message. All four outcomes come from the same three-message thread.
    """
    from collections import Counter

    from mailweave.policy.budget import BudgetRequest
    from mailweave.surface.arguments import SearchRequest
    from orivra.graph.build import build_query_graph

    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))
    answered = adapter.answer(
        SearchRequest(
            query="Larch pricing draft",
            view=Depth.BODY_CLEAN,
            scan_max_pages=None,
            budget=BudgetRequest(),
            disclosed_token_request=None,
        )
    )
    built = build_query_graph(
        answered.envelope,
        query_id="q-e2e",
        adapter=adapter,
        built_at=adapter.permission_context().observed_at,
        nodes=answered.nodes,
        omissions=answered.omissions,
        max_nodes=60,
    )
    relations = Counter(edge.relation.value for edge in built.graph.edges)
    assert relations[Relation.SUPERSEDES_STATED.value] == 1, (
        "the stated supersession did not survive the real response path"
    )
    assert relations[Relation.LINKS_TO.value] == 1, "the resolvable permalink drew no edge"

    stated = [edge for edge in built.graph.edges if edge.relation is Relation.SUPERSEDES_STATED]
    assert stated[0].confidence is None
    assert stated[0].stated is not None
    assert stated[0].spans

    # The denial in the third message produced nothing on either path.
    assert Relation.POTENTIALLY_SUPERSEDES.value not in relations

    # The document outside the mailbox is carried as an unresolved link, not as a node.
    urls = [one["url"] for one in built.unresolved_links]
    assert any("drive.google.com" in one for one in urls)
    assert not [node for node in built.graph.nodes if "drive.google.com" in node.node_id], (
        "a URL became a graph node"
    )


# -- 5. the expansion path carries the same families -------------------------------------------


def _decision_answer(max_nodes: int) -> tuple[OrivraService, dict]:
    """Ask the decision thread's question through the shipped surface, at a tight budget."""
    adapter = GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))
    service = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=max_nodes,
    )
    result = call(
        service,
        "orivra_ask",
        {"query": "Larch pricing draft", "view": "body_clean", "graph": True},
    )
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return service, dict(result.structured_content)


def _edges(service: OrivraService, query_id: str) -> list[dict]:
    """Every edge of the stored graph, read through the tool a client actually has."""
    out: list[dict] = []
    cursor: int | None = 0
    view: str | None = None
    while cursor is not None:
        args: dict = {"query_id": query_id, "select": "edges"}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = call(service, "orivra_graph", args)
        assert not page.is_error, page.content
        assert page.structured_content is not None
        body = dict(page.structured_content)
        out.extend(dict(one) for one in body["items"])
        cursor, view = body["next_cursor"], body["view"]
    return out


def _nodes_of(service: OrivraService, query_id: str) -> list[dict]:
    out: list[dict] = []
    cursor: int | None = 0
    view: str | None = None
    while cursor is not None:
        args: dict = {"query_id": query_id, "select": "nodes"}
        if cursor:
            args |= {"cursor": cursor, "view": view}
        page = call(service, "orivra_graph", args)
        assert page.structured_content is not None
        body = dict(page.structured_content)
        out.extend(dict(one) for one in body["items"])
        cursor, view = body["next_cursor"], body["view"]
    return out


def _expand_decision(max_nodes: int = 4) -> tuple[OrivraService, str, dict]:
    """Ask at a budget that prunes the decision branch, then follow the handle it filed."""
    service, answer = _decision_answer(max_nodes=max_nodes)
    query_id = answer["query_id"]
    omissions = call(service, "orivra_graph", {"query_id": query_id, "select": "omissions"})
    assert omissions.structured_content is not None
    handle = next(
        one["what"]
        for one in dict(omissions.structured_content)["items"]
        if one["what"] == "gmail/thread/t-decision" and one["recover"]
    )
    expanded = call(service, "orivra_expand", {"query_id": query_id, "handle": handle})
    assert not expanded.is_error, expanded.content
    assert expanded.structured_content is not None
    return service, query_id, dict(expanded.structured_content)


def test_the_budget_that_prunes_every_message_leaves_no_person_behind() -> None:
    """Found by the expansion fixture, and it was a real defect rather than a test artefact.

    `_prune` kept every non-message node unconditionally, so a budget tight enough to drop all
    three messages produced a graph of one thread and two people with no edges at all -
    "the graph took no hops and holds 3 nodes for 1 seeds", which `QueryGraph` refused
    outright. The model was right: a person node exists in virtue of the messages that person
    sent, and none of them survived.
    """
    service, answer = _decision_answer(max_nodes=3)
    counts = answer["graph"]["counts"]
    assert counts["nodes"] == 1 and counts["edges"] == 0, (
        "the stored graph kept a derived node that every message earning it was pruned from"
    )
    assert counts["omitted"], "the messages went without a record"
    # And nothing is disclosed: `access.disclose` drops a thread no surviving message joins,
    # which is the same rule `_prune` now applies to people. An empty page rather than a
    # refusal is the correct end state for a budget this tight.
    assert _nodes_of(service, answer["query_id"]) == []


def test_an_expansion_extends_the_graph_and_says_what_it_could_not_read() -> None:
    """The families are assembled once and both paths run that assembly - and where an
    expansion has no text, it says so rather than returning a quiet metadata-only graph.

    A thread map recovers a branch's *shape*: every row arrives at `stub` depth. So the four
    recognition gates have nothing to read, no `obs.said.*` edge can be drawn for these rows,
    and the honest report is that their text was not read - not silence that a caller would
    reasonably take for "nobody in this branch stated anything".
    """
    service, query_id, delta = _expand_decision()

    gained = {one["relation"] for one in delta["added"]["edges"]}
    assert gained, "the expansion added no relations at all"
    assert gained <= {
        Relation.THREAD_MEMBER.value,
        Relation.AUTHORED_BY.value,
        Relation.SENT_TO.value,
        Relation.REPLY_TO.value,
    }, "an obs.said.* or inf.* edge was drawn over rows that carry no disclosed text"

    unread = delta["text_not_read"]
    held = {one["node_id"] for one in _nodes_of(service, query_id)}
    assert set(unread["nodes"]) <= held, (
        "a row the graph does not hold was reported as text this graph did not read; a row "
        "the node budget refused is accounted for as a cap, not as an unread body"
    )
    assert set(unread["nodes"]) >= {"gmail/message/d-2", "gmail/message/d-3"}, (
        "the rows whose bodies were never fetched are not named, so a caller cannot tell an "
        "unread message from a message that stated nothing"
    )
    assert "thread map" in unread["why"] and "body view" in unread["why"]


def test_the_same_question_at_a_body_view_does_draw_what_the_expansion_could_not() -> None:
    """The counterpart, and the reason the absence above is a depth fact rather than a defect.

    Same mailbox, same thread, same code path - a budget that keeps the messages instead of
    pruning them, so the bodies are disclosed and the gates have text. The stated supersession
    and the resolvable permalink both appear, which is what makes `text_not_read` a statement
    about what this call fetched rather than about what the mailbox contains.
    """
    service, answer = _decision_answer(max_nodes=8)
    relations = {one["relation"] for one in _edges(service, answer["query_id"])}
    assert Relation.SUPERSEDES_STATED.value in relations
    assert Relation.LINKS_TO.value in relations


def test_an_expansion_carries_the_links_it_still_cannot_resolve() -> None:
    """Unresolved is a fact about this release's reach, and it has to survive a merge."""
    service, answer = _decision_answer(max_nodes=8)
    urls = [one["url"] for one in answer["graph"]["unresolved_links"]]
    assert any("drive.google.com" in one for one in urls), (
        "the Drive link the answer carried was neither an edge nor reported"
    )
    nodes = _nodes_of(service, answer["query_id"])
    assert not [one for one in nodes if "drive.google.com" in one["node_id"]], (
        "an unresolvable URL became a graph node"
    )
