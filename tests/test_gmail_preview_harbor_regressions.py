"""The four defects a live Harbor run exposed, each reproduced and each held closed.

The run exited 0. Every call succeeded. And the demonstration showed none of what it exists to
show: the answer's graph disclosed no node and blamed the caller's permissions, the expansion
reported an empty delta with no reason, the cache was never consulted, and the branch that was
followed was chosen by list order and ended at stubs. `benchmarks/gmail-preview-harbor.PHfUS6`
is that record, kept.

Each test below names the record's symptom, reproduces the cause offline, and asserts the
repair - through `call(service, ...)`, the shipped boundary, because three of the four defects
were in what the boundary *said* rather than in what it computed.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

import pytest

from mailweave.constants import HOST_RESULT_CHAR_CAP
from mailweave.envelope.measure import rendered_chars
from mailweave.envelope.reasons import ThreadMember
from mailweave.envelope.vocab import Depth, Role, ToolName
from mailweave.surface.recovery import NarrowingKind
from orivra.cache import BoundedCache
from orivra.contracts import (
    ConnectorId,
    ContentVersion,
    EvidenceNode,
    FreshnessState,
    FreshnessStatus,
    NodeKind,
    OmissionCause,
    PermissionContext,
    QueryGraph,
    RefKind,
    SourceReference,
)
from orivra.gmail_adapter import GmailAdapter
from orivra.graph.access import LiveProbe, disclose
from orivra.registry import ConnectorRegistry
from orivra.surface.server import call
from orivra.surface.service import OrivraService
from tests.test_mcp_surface_round24 import (
    Msg,
    SyntheticMailbox,
    epoch_ms,
    mailbox,
    make_service,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
QUESTION = "Larch pricing draft"

#: Keeps the decision thread partly out of the graph, so a recoverable handle exists and the
#: graph still holds message nodes to rest a relation on.
BUDGET = 5


def _thread_node(thread_id: str = "t-1") -> EvidenceNode:
    ref = SourceReference(
        connector=ConnectorId.GMAIL,
        account="acct",
        kind=RefKind.THREAD,
        native_id=thread_id,
        version=ContentVersion(connector=ConnectorId.GMAIL, native_id=thread_id, revision="7"),
        permission=PermissionContext(
            connector=ConnectorId.GMAIL, principal="acct", scope_set=(SCOPE,), observed_at=NOW
        ),
    )
    return EvidenceNode(
        node_id=f"gmail/thread/{thread_id}",
        ref=ref,
        kind=NodeKind.THREAD,
        role=Role.CONTEXT,
        reason=ThreadMember(thread_id=thread_id, position=0),
        depth=Depth.STUB,
        stated_total=42,
        included=0,
        freshness=FreshnessStatus(verified_at=NOW, state=FreshnessState.FRESH),
    )


def _first_handle(service: OrivraService, query_id: str) -> str:
    """The first omission that offers a way back. Order, deliberately: these tests are about
    what the tool *says*, and the walk's own relevance rule is tested separately below."""
    page = call(service, "orivra_graph", {"query_id": query_id, "select": "omissions"})
    return next(
        one["what"] for one in dict(page.structured_content or {})["items"] if one.get("recover")
    )


def _expand(service: OrivraService, query_id: str, handle: str) -> dict[str, Any]:
    result = call(service, "orivra_expand", {"query_id": query_id, "handle": handle})
    assert not result.is_error, result.content
    return dict(result.structured_content or {})


class _NeverAsked:
    """A probe that fails loudly if the source is touched. A vacuous graph must not be."""

    def permission_context(self, ref: SourceReference | None = None) -> Any:
        return ref.permission if ref is not None else None

    def version_of(self, ref: SourceReference) -> Any:  # pragma: no cover - the assertion
        raise AssertionError(f"a graph with no message node probed the source for {ref.native_id}")


# -- 1. an empty page is not an access decision -------------------------------------------------


def test_a_graph_of_derived_nodes_alone_is_not_reported_as_a_permission_refusal() -> None:
    """Record symptom: ask said `nodes: 1`, the next call returned none and one `permission`
    omission - "not released to this caller under the grant in force".

    No release was refused. There was nothing to refuse: the graph held one thread node and no
    messages, a thread node exists in virtue of the messages under it, and the source was never
    asked a question. `dropped_derived` was being folded into the permission record, so the one
    branch that fires without any access decision printed a sentence about authorization.
    """
    graph = QueryGraph(
        query_id="q",
        nodes=(_thread_node(),),
        edges=(),
        seeds=("gmail/thread/t-1",),
        hops_taken=0,
        omitted=(),
        built_at=NOW,
    )
    shown = disclose(graph, probe=LiveProbe(adapter=_NeverAsked()), observed_at=NOW)

    assert shown.nodes == (), "a derived node with no message under it was served"
    assert [one.cause for one in shown.omitted if one.cause is OmissionCause.PERMISSION] == [], (
        "an empty page was reported as a permission refusal, which no check made"
    )
    assert shown.narrowed is False, (
        "the live check was reported as having narrowed a graph it could not have served"
    )
    assert shown.source_backed == 0
    assert shown.derived_without_support == 1


def test_a_real_refusal_still_produces_the_permission_record() -> None:
    """The other half: narrowing the record must not narrow it out of existence.

    A graph whose message node the source will not describe still withholds, still says so, and
    still reports the narrowing - which is what keeps the change above a correction rather than
    a loosening.
    """
    service = make_service(mailbox())
    adapter = GmailAdapter(service=service, granted_scopes=(SCOPE,))
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}),
        max_graph_nodes=BUDGET,
    )
    answer = call(orivra, "orivra_ask", {"query": QUESTION, "view": "body_clean", "graph": True})
    query_id = dict(answer.structured_content or {})["query_id"]

    class Refuses:
        def permission_context(self, ref: SourceReference | None = None) -> Any:
            return adapter.permission_context(ref)

        def version_of(self, ref: SourceReference) -> Any:
            raise RuntimeError("the source will not describe this item")

    held = orivra.graphs.get(query_id)
    shown = disclose(held, probe=LiveProbe(adapter=Refuses()), observed_at=NOW)
    assert shown.nodes == (), "a node the source would not describe was served"
    assert shown.narrowed is True, "a real withholding stopped reporting itself"
    assert any(one.cause is OmissionCause.FRESHNESS_UNVERIFIABLE for one in shown.omitted), (
        "an unverifiable node lost the record that recovers it"
    )


def test_the_answer_says_when_its_graph_holds_no_evidence() -> None:
    """Record symptom: `counts: {nodes: 1, edges: 0}` read as "there is a graph here".

    A budget that admits no message node produces exactly that shape, and the caller found out
    only when the next call came back empty. The answer now says so where the count is.
    """
    service = make_service(mailbox())
    adapter = GmailAdapter(service=service, granted_scopes=(SCOPE,))
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=1
    )
    answer = call(orivra, "orivra_ask", {"query": QUESTION, "view": "body_clean", "graph": True})
    graph = dict(answer.structured_content or {})["graph"]
    assert graph["holds_evidence"] is False
    assert "no message node" in graph["why_no_evidence"]

    fresh = GmailAdapter(service=make_service(mailbox()), granted_scopes=(SCOPE,))
    healthy = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: fresh}),
        max_graph_nodes=BUDGET,
    )
    ok = call(healthy, "orivra_ask", {"query": QUESTION, "view": "body_clean", "graph": True})
    assert dict(ok.structured_content or {})["graph"]["holds_evidence"] is True


# -- 2. a shed delta says it was shed -----------------------------------------------------------


def _wide(n: int = 16) -> tuple[Msg, ...]:
    """A thread whose recovered delta cannot fit the host cap."""
    return tuple(
        Msg(
            id=f"1a0{index:02x}beef{index:04x}",
            thread_id="t-wide",
            sender=f"p{index % 4}@team.example",
            subject="Harbor export mismatch",
            body=("The Harbor export mismatch is discussed at length here. " * 12),
            internal_date_ms=epoch_ms(2026, 3, 1 + index),
            to=("ana@team.example",),
            in_reply_to=(
                f"<1a0{index - 1:02x}beef{index - 1:04x}@mail.invalid>" if index else None
            ),
        )
        for index in range(n)
    )


@pytest.fixture
def wide_service() -> OrivraService:
    base = mailbox()
    box = SyntheticMailbox(messages=(*base.messages, *_wide()), now_ms=base.now_ms)
    service = make_service(box)
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    return OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=4
    )


def test_an_expansion_that_sheds_its_delta_says_so_and_says_how_much(
    wide_service: OrivraService,
) -> None:
    """Record symptom: `added: {nodes: [], edges: {}, already_held: []}` and nothing else.

    The delta was over the host cap, so the tool shed it and pointed at `orivra_graph` - which
    is correct. What was missing is that a reader could not tell that from the response: empty
    lists look exactly like an expansion that recovered nothing.
    """
    # **Asked at `snippet`.** The point of this fixture is a large *expansion* delta, not a
    # large answer: at `body_clean` this sixteen-message thread renders an answer within a
    # hundred characters of the host cap, so the response is refused before the expansion is
    # reached. That refusal is correct and has its own test below; here it is in the way.
    answer = call(
        wide_service,
        "orivra_ask",
        {"query": "Harbor export mismatch", "view": "snippet", "graph": True},
    )
    query_id = dict(answer.structured_content or {})["query_id"]
    handle = _first_handle(wide_service, query_id)
    expanded = _expand(wide_service, query_id, handle)

    added = expanded["added"]
    assert added["shed"] is True, "the delta was shed and the response did not say so"
    assert added["nodes"] == [] and added["edges"] == []
    assert added["counts"]["nodes"] > 0, "a shed delta reported no count of what it shed"
    assert "orivra_graph" in added["detail"]
    # And the graph really did grow, which is what makes the empty lists safe to shed.
    assert expanded["graph"]["nodes"] > 1


def test_a_delta_that_fits_is_carried_and_marked_unshed() -> None:
    """`shed` is present in both branches, so a reader never infers it from an empty list."""
    service = make_service(mailbox())
    adapter = GmailAdapter(service=service, granted_scopes=(SCOPE,))
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=BUDGET
    )
    answer = call(orivra, "orivra_ask", {"query": QUESTION, "view": "body_clean", "graph": True})
    query_id = dict(answer.structured_content or {})["query_id"]
    handle = _first_handle(orivra, query_id)
    expanded = _expand(orivra, query_id, handle)
    assert expanded["added"]["shed"] is False
    assert expanded["added"]["nodes"], "a delta that fits was not carried"


# -- 3. the cache says whether it was consulted -------------------------------------------------


def test_a_branch_absent_from_the_graph_still_reaches_the_cache() -> None:
    """Record symptom: `threads.get` every round, no `history.list` ever.

    The revision was read off the thread node in the stored graph, and the branches a caller
    follows are the ones the answer *omitted* - a source split off at the ceiling has no node -
    so the lookup returned `None` and the cache was never consulted. The adapter now remembers
    the revisions its own responses observed, and the change-feed walk still gates the serve.
    """
    from mailweave.envelope.vocab import Depth as _Depth
    from mailweave.surface.arguments import BudgetRequest, SearchRequest, parse_thread_map

    calls: Counter[str] = Counter()
    service = make_service(mailbox())
    opener = service.open_client

    def open_client() -> Any:
        client = opener()
        fetch, probe = client.get_thread, client.liveness_of_threads

        def get_thread(*args: Any, **kwargs: Any) -> Any:
            calls["threads.get"] += 1
            return fetch(*args, **kwargs)

        def liveness_of_threads(*args: Any, **kwargs: Any) -> Any:
            calls["history.list"] += 1
            return probe(*args, **kwargs)

        client.get_thread = get_thread
        client.liveness_of_threads = liveness_of_threads
        return client

    service.open_client = open_client
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    adapter.answer(
        SearchRequest(
            query=QUESTION,
            view=_Depth.BODY_CLEAN,
            scan_max_pages=None,
            budget=BudgetRequest(),
            disclosed_token_request=None,
        )
    )
    assert adapter.observed_revisions, "the answer observed no container revision to remember"

    calls.clear()
    first = adapter.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert first.cache is not None and first.cache.consulted, (
        "with no revision from the caller the cache was skipped rather than keyed on the "
        "revision this adapter had already observed"
    )
    assert first.cache.outcome == "miss"
    assert calls["threads.get"] == 1

    calls.clear()
    second = adapter.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert second.cache is not None and second.cache.outcome == "hit"
    assert calls["threads.get"] == 0, "a served entry still re-read the thread"
    assert calls["history.list"] == 1, "an entry was served without a change-feed walk"


def test_a_cache_that_cannot_be_keyed_says_so_rather_than_looking_like_a_miss() -> None:
    """ "Never consulted" and "consulted and missed" are different failures.

    The first is a wiring defect and the second is the cache working. A call count cannot tell
    them apart, which is why the Harbor record could only report `threads.get` and leave the
    reason to be guessed at.
    """
    from mailweave.surface.arguments import parse_thread_map

    service = make_service(mailbox())
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    result = adapter.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert result.cache is not None
    assert result.cache.consulted is False
    assert result.cache.outcome == "no_revision"
    assert "no historyId has been observed" in result.cache.why


def test_the_expansion_reports_the_cache_outcome_through_the_tool(
    wide_service: OrivraService,
) -> None:
    # **Asked at `snippet`.** The point of this fixture is a large *expansion* delta, not a
    # large answer: at `body_clean` this sixteen-message thread renders an answer within a
    # hundred characters of the host cap, so the response is refused before the expansion is
    # reached. That refusal is correct and has its own test below; here it is in the way.
    answer = call(
        wide_service,
        "orivra_ask",
        {"query": "Harbor export mismatch", "view": "snippet", "graph": True},
    )
    query_id = dict(answer.structured_content or {})["query_id"]
    handle = _first_handle(wide_service, query_id)
    expanded = _expand(wide_service, query_id, handle)
    assert expanded["cache"]["consulted"] is True
    assert expanded["cache"]["outcome"] in {"hit", "miss", "expired", "unverified"}
    assert expanded["disclosure"]["source_backed_nodes"] >= 0


# -- 4. the walk follows relevance, reaches text, and can fail -----------------------------------


def _walked(budget: int = BUDGET, rounds: int = 2) -> list[dict[str, Any]]:
    from tools.dev.gmail_walk import _counting, walk

    service = make_service(mailbox())
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=budget
    )
    calls = _counting(service)
    out: list[dict[str, Any]] = []
    for index in range(rounds):
        record, status = walk(
            orivra, QUESTION, view="body_clean", calls=calls, round_index=index + 1
        )
        assert status == 0, record.get("stopped")
        out.append(record)
    return out


def test_the_branch_is_chosen_by_the_answers_own_ranking_and_the_rule_is_recorded() -> None:
    """Record symptom: the walk took `handles[0]` - the order the omission list is written in.

    Against a real mailbox that spent the one expansion on a 42-message thread the question was
    not about. The selection now reads the answer's own disclosed ranking and records which
    rule fired, so a fallback to list order is visible as a fallback rather than silent.
    """
    for record in _walked():
        selection = record["step_3_selection"]
        assert selection["rule"] in {
            "best_ranked_not_included",
            "partially_disclosed_thread",
        }, f"the branch was chosen by list order: {selection}"
        assert selection["thread_id"], "the selected branch was not recorded"
        assert selection["handle"] == record["step_3_expand"]["handle"]


def test_the_walk_reaches_message_text_rather_than_stopping_at_structure() -> None:
    """Record symptom: 22 metadata relationships and `text_not_read` naming every row.

    A thread map recovers a branch's shape. "A replied to B" is not an answer and nothing in it
    can be checked, so the walk now reads the recovered bodies through `mailweave_get_messages`
    on the same surface and says whether it reached any.
    """
    for record in _walked():
        content = record["step_5_content"]
        assert content["reached_content"] is True, f"the walk stopped at structure: {content}"
        assert content["messages_with_text"] >= 1
        assert set(content["depths"]) <= {"body_clean", "body_full"}, (
            "content was 'reached' at a depth that carries no text"
        )


def test_the_record_still_carries_no_message_text() -> None:
    """Reaching content must not mean printing it: the record stays pasteable into a review."""
    for record in _walked():
        rendered = repr(record)
        for leaked in ("pricing draft is attached", "we are not withdrawing", "Background is at"):
            assert leaked not in rendered, f"the walk printed message text: {leaked!r}"


def test_criteria_separate_a_run_that_worked_from_a_run_that_demonstrated() -> None:
    """The Harbor run exited 0 having demonstrated nothing. Criteria are the difference."""
    records = _walked()
    first, second = records[0], records[1]

    # Reuse is reported, never graded: round 1 has nothing to reuse and a fresh fetch after a
    # change feed that saw a change is the safe path working, not a wrong answer.
    assert "cache_reuse_demonstrated" not in first["criteria"]["checks"]
    assert first["criteria"]["observations"]["cache_reuse"]["served_from_cache"] is False
    assert second["criteria"]["observations"]["cache_reuse"]["served_from_cache"] is True
    assert first["criteria"]["demonstrated"] is True, (
        "round 1 was marked undemonstrated for having nothing cached yet"
    )
    assert second["criteria"]["demonstrated"] is True, second["criteria"]["unmet"]
    for name in (
        "evidence_reachable",
        "relations_visible_through_tools",
        "branch_chosen_by_relevance",
        "expansion_delta_accounted",
        "graph_grew",
        "cache_behaved_correctly",
        "reached_message_content",
    ):
        assert second["criteria"]["checks"][name]["met"], name

    # The first response's emptiness is recorded rather than failed: the contract requires
    # reachability with an executable call, not a full first response.
    observations = second["criteria"]["observations"]
    assert "first_response_held_evidence" in observations
    assert observations["recoverable_omissions"] >= 1
    assert "C-01" in observations["why_this_is_not_a_criterion"]


def test_an_unmet_criterion_is_reported_rather_than_passed_over() -> None:
    """A criterion that cannot fail is not evidence, so each one is shown failing.

    Driven through `_criteria` on a record with one thing missing at a time, because forcing
    retrieval to produce each failure would be contorting the retrieval to test the report.
    """
    from tools.dev.gmail_walk import _criteria

    full: dict[str, Any] = {
        "step_1_ask": {
            "holds_evidence": False,
            "answer": {"every_not_included_source_carries_a_call": True, "disclosed_messages": 0},
        },
        "step_2_inspect": {
            "edges": {"relations": [{"source": "a", "relation": "r", "target": "b"}]},
            "omissions": [{"what": "gmail/thread/t", "recover": {"tool": "mailweave_thread_map"}}],
        },
        "step_3_selection": {"rule": "best_ranked_not_included"},
        "step_3_expand": {
            "added": {"nodes": ["gmail/message/m"], "shed": False},
            "cache": {"consulted": True, "outcome": "hit", "reason": "unchanged"},
        },
        "step_4_inspect_again": {"gained": ["a -r-> b"], "edges": {"relations": []}},
        "step_5_content": {"reached_content": True, "query_term_overlap": {"terms_missing": []}},
    }
    assert _criteria(full, round_index=2)["demonstrated"] is True, "the baseline record fails"

    for name, broken in (
        ("evidence_reachable", {"step_2_inspect": {**full["step_2_inspect"], "omissions": []}}),
        (
            "relations_visible_through_tools",
            {
                "step_2_inspect": {**full["step_2_inspect"], "edges": {"relations": []}},
                "step_4_inspect_again": {
                    **full["step_4_inspect_again"],
                    "edges": {"relations": []},
                },
            },
        ),
        (
            "branch_chosen_by_relevance",
            {"step_3_selection": {"rule": "first_recoverable_fallback"}},
        ),
        ("graph_grew", {"step_4_inspect_again": {**full["step_4_inspect_again"], "gained": []}}),
        (
            "cache_behaved_correctly",
            {"step_3_expand": {**full["step_3_expand"], "cache": {"consulted": False}}},
        ),
        (
            # A hit that did not come from a conclusive unchanged walk is the one cache
            # outcome that is a defect: it served an entry nothing established.
            "cache_behaved_correctly",
            {
                "step_3_expand": {
                    **full["step_3_expand"],
                    "cache": {"consulted": True, "outcome": "hit", "reason": "inconclusive"},
                }
            },
        ),
        (
            "reached_message_content",
            {"step_5_content": {"reached_content": False, "query_term_overlap": {}}},
        ),
    ):
        criteria = _criteria({**full, **broken}, round_index=2)
        assert criteria["demonstrated"] is False, name
        assert name in criteria["unmet"], f"{name} failed silently: {criteria['unmet']}"


def test_an_empty_first_response_is_recorded_and_not_failed() -> None:
    """The contract question, answered the contract's way.

    A budget admitting no message node gives an answer whose graph holds nothing. Every call
    succeeds and every omission carries an executable call, so the walk records the emptiness
    as an observation and does not fail it - C-01 forbids an id that no record names, not a
    first response that is not full, and R-07 is satisfied by the handles.
    """
    from tools.dev.gmail_walk import walk

    service = make_service(mailbox())
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    orivra = OrivraService(
        registry=ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter}), max_graph_nodes=1
    )
    record, status = walk(orivra, QUESTION, view="body_clean", round_index=1)
    assert status == 0
    observations = record["criteria"]["observations"]
    assert observations["first_response_held_evidence"] is False
    assert "graph_holds_evidence" not in record["criteria"]["checks"], (
        "a first-response requirement the contract does not make was still a criterion"
    )
    assert record["criteria"]["checks"]["evidence_reachable"]["met"] is True, (
        "the omissions carried working handles and the expansion recovered nodes, which is "
        "what the contract asks for"
    )


# -- 5. the revalidation says what it actually found ---------------------------------------------


def _probing(reply: Any) -> tuple[GmailAdapter, Counter[str]]:
    """An adapter whose change feed answers however the test needs it to."""
    calls: Counter[str] = Counter()
    service = make_service(mailbox())
    opener = service.open_client

    def open_client() -> Any:
        client = opener()
        fetch = client.get_thread

        def get_thread(*args: Any, **kwargs: Any) -> Any:
            calls["threads.get"] += 1
            return fetch(*args, **kwargs)

        def liveness_of_threads(*args: Any, **kwargs: Any) -> Any:
            calls["history.list"] += 1
            return reply()

        client.get_thread = get_thread
        client.liveness_of_threads = liveness_of_threads
        return client

    service.open_client = open_client
    adapter = GmailAdapter(
        service=service, granted_scopes=(SCOPE,), cache=BoundedCache(now=service.now)
    )
    return adapter, calls


def _probe(**fields: Any) -> Any:
    from mailweave.gmail.client import LivenessProbe

    base = {
        "touched": {},
        "expired": False,
        "pages_fetched": 1,
        "pages_exhausted": False,
        "latest_history_id": "99",
    }
    return LivenessProbe(**{**base, **fields})


def _prime(adapter: GmailAdapter) -> str:
    """One uncached read, so there is an entry for the next revalidation to decide about.

    Returns the revision the entry was actually keyed on - the one the *fetch* observed, never
    a value the test made up, because an entry keyed on a guess is one no lookup can ever hit.
    """
    from mailweave.surface.arguments import parse_thread_map

    adapter.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert adapter.cache is not None
    (key,) = [one.key for one in adapter.cache._entries.values()]
    return key.content_version


@pytest.mark.parametrize(
    ("reply", "reason", "rebaselined"),
    [
        (lambda: _probe(), "unchanged", False),
        (
            lambda: _probe(
                touched={
                    "t-decision": __import__(
                        "mailweave.gmail.client", fromlist=["ThreadChange"]
                    ).ThreadChange(labels_added=1)
                }
            ),
            "changed",
            False,
        ),
        (lambda: _probe(expired=True, pages_fetched=0), "watermark_expired", True),
        (lambda: _probe(pages_exhausted=True), "inconclusive", False),
    ],
    ids=["unchanged", "changed", "watermark_expired", "pages_exhausted"],
)
def test_each_probe_shape_reports_its_own_reason(
    reply: Any, reason: str, rebaselined: bool
) -> None:
    """Record symptom: round 2 said "written under an access state that no longer holds".

    The change feed had not said anything about access. `BoundedCache.get` took a bool, so a
    change, an exhausted walk, an expired watermark and a genuine access loss all arrived as
    `False` and all got the one sentence written for the last of them. A live run reading that
    record would conclude its permissions had moved.
    """
    from mailweave.surface.arguments import parse_thread_map

    adapter, calls = _probing(reply)
    revision = _prime(adapter)
    calls.clear()
    result = adapter.answer_thread_map(
        parse_thread_map({"thread_id": "t-decision"}), known_revision=revision
    )
    assert result.cache is not None
    assert result.cache.reason == reason
    assert result.cache.rebaselined is rebaselined
    if reason != "unchanged":
        assert "access state" not in result.cache.why, (
            "an unsuccessful revalidation that was not about access said it was"
        )


def test_every_unsuccessful_revalidation_still_falls_back_to_a_fresh_read() -> None:
    """Naming the reason must not change what happens next: the source is read, every time."""
    from mailweave.gmail.client import ThreadChange
    from mailweave.surface.arguments import parse_thread_map

    for reply in (
        lambda: _probe(touched={"t-decision": ThreadChange(messages_added=1)}),
        lambda: _probe(expired=True, pages_fetched=0),
        lambda: _probe(pages_exhausted=True),
    ):
        adapter, calls = _probing(reply)
        revision = _prime(adapter)
        calls.clear()
        result = adapter.answer_thread_map(
            parse_thread_map({"thread_id": "t-decision"}), known_revision=revision
        )
        assert calls["threads.get"] == 1, "an unserved entry did not fall back to the source"
        assert result.nodes, "the fallback read returned nothing"
        assert result.cache is not None and result.cache.outcome == "unverified"


def test_an_expired_watermark_is_discarded_rather_than_walked_again() -> None:
    """The one reason where retrying is certainly useless, so the watermark goes.

    Gmail no longer retains history from that `startHistoryId`; the walk will 404 every time.
    Keeping it would make every future expansion of this thread pay for a doomed walk before
    falling back. The fresh read re-learns a current watermark.
    """
    from mailweave.surface.arguments import parse_thread_map

    adapter, calls = _probing(lambda: _probe(expired=True, pages_fetched=0))
    revision = _prime(adapter)
    adapter.observed_revisions["t-decision"] = revision

    calls.clear()
    first = adapter.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert first.cache is not None and first.cache.rebaselined is True
    assert calls["history.list"] == 1, "the doomed walk was not attempted once"
    assert calls["threads.get"] == 1, "the fresh-fetch fallback did not run"
    # **Observed at the moment it matters, not by comparing before and after.** The fixture is
    # static, so the fresh read re-learns the same historyId and an inequality assertion here
    # would pass for the wrong reason. What the discard actually guarantees is that the index
    # is re-populated *by the fresh read* rather than left holding a watermark Gmail has
    # forgotten - so the next call keys on something the feed can be walked from.
    assert adapter.observed_revisions.get("t-decision"), (
        "the watermark was discarded and never re-baselined, so the next expansion has no key"
    )

    # And the pop is asserted where it is visible: with the fresh read suppressed, the index
    # is empty afterwards, which it would not be if the expired watermark had been kept.
    bare, _ = _probing(lambda: _probe(expired=True, pages_fetched=0))
    held = _prime(bare)
    bare.observed_revisions["t-decision"] = held
    bare.service.thread_map = _raises  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        bare.answer_thread_map(parse_thread_map({"thread_id": "t-decision"}))
    assert "t-decision" not in bare.observed_revisions, (
        "the expired watermark was kept, so the next expansion pays for the same 404"
    )


def _raises(*_: Any, **__: Any) -> Any:
    """Stands in for the fresh read, so the discard can be observed without it re-learning."""
    raise RuntimeError("the fresh read is suppressed for this assertion")


# -- 6. what the walk is scoped to, and what it refuses to judge ---------------------------------

#: The four things the scripted walk exists to exercise. Anything a criterion asserts has to be
#: one of these; answer quality is Path B's question and is put to a client that can read.
IN_SCOPE = {
    "evidence_reachable",  # tool operation: the contract's reachability rule
    "relations_visible_through_tools",  # tool operation
    "branch_chosen_by_relevance",  # graph expansion: which branch, and on whose ranking
    "expansion_delta_accounted",  # graph expansion
    "graph_grew",  # graph expansion
    "cache_behaved_correctly",  # cache behaviour
    "reached_message_content",  # content access
}


def test_the_walk_grades_nothing_outside_its_four_areas() -> None:
    """Tool operation, graph expansion, content access, cache behaviour. Not answers.

    A term-overlap check was briefly a criterion, which made a correct walk fail because a mail
    said "fixed" where the question said "resolved". A scripted walk cannot judge an answer and
    should not be built into a harness that pretends to; this pins the boundary so the next
    useful-looking measurement does not drift across it.
    """
    for record in _walked():
        assert set(record["criteria"]["checks"]) == IN_SCOPE, (
            "a criterion appeared outside tool operation, graph expansion, content access and "
            f"cache behaviour: {sorted(set(record['criteria']['checks']) - IN_SCOPE)}"
        )


def test_word_overlap_is_measured_and_never_graded() -> None:
    """The numbers survive; the verdict does not.

    Every discriminating word missing is worth a reader's attention - it can mean the rows read
    were the wrong ones - and it is worth nothing as a pass or fail, because a synonym is not a
    defect and word presence is not an answer.
    """
    for record in _walked():
        overlap = record["step_5_content"]["query_term_overlap"]
        assert overlap["informational"] is True
        assert "terms" in overlap and "messages_per_term" in overlap
        assert "terms_missing" in overlap and "best_single_message_terms" in overlap
        assert "covers_question" not in overlap, "the verdict came back"
        assert "neither relevance nor correctness" in overlap["caveat"]
        # Carried into the record where a reader will see it, and out of the graded set.
        assert record["criteria"]["observations"]["query_term_overlap"] == overlap
        assert not any(
            "overlap" in name or "covers" in name for name in record["criteria"]["checks"]
        )


def test_a_missing_question_word_does_not_fail_the_demonstration() -> None:
    """ "exact" and "resolved" are the question's words, not the mailbox's.

    Driven through `_criteria` with the overlap reporting every term missing, because the point
    is that the verdict does not move.
    """
    from tools.dev.gmail_walk import _criteria

    record = _walked()[1]
    assert record["criteria"]["demonstrated"] is True

    starved = {
        **record,
        "step_5_content": {
            **record["step_5_content"],
            "query_term_overlap": {
                "informational": True,
                "terms": ["exact", "resolved", "harbor"],
                "terms_found": [],
                "terms_missing": ["exact", "harbor", "resolved"],
                "messages_per_term": {},
                "best_single_message_terms": 0,
                "caveat": "neither relevance nor correctness",
            },
        },
    }
    after = _criteria(starved, round_index=2)
    assert after["demonstrated"] is True, (
        f"missing question words failed the walk: {after['unmet']}"
    )
    assert after["observations"]["query_term_overlap"]["terms_missing"] == [
        "exact",
        "harbor",
        "resolved",
    ], "the measurement was dropped along with the verdict"


def test_a_safe_fresh_fetch_is_not_reported_as_a_failure() -> None:
    """Cache correctness and cache reuse are two questions with two homes.

    A change feed that saw a change, ran out of pages or found an expired watermark sends the
    call to the source. That is the design working. Only one cache outcome is a defect: an
    entry served on a walk that established nothing.
    """
    from tools.dev.gmail_walk import _criteria

    base = _walked()[1]
    for reason in ("changed", "inconclusive", "watermark_expired", "access_changed"):
        record = {
            **base,
            "step_3_expand": {
                **base["step_3_expand"],
                "cache": {
                    "consulted": True,
                    "outcome": "unverified",
                    "reason": reason,
                    "rebaselined": reason == "watermark_expired",
                },
            },
        }
        criteria = _criteria(record, round_index=2)
        assert criteria["checks"]["cache_behaved_correctly"]["met"], (
            f"a safe fresh fetch after {reason} was reported as a failure"
        )
        assert criteria["observations"]["cache_reuse"]["served_from_cache"] is False
        assert criteria["observations"]["cache_reuse"]["reason"] == reason


# -- 7. an ask that cannot fit serves the answer and the graph anyway ---------------------------


def test_an_ask_that_used_to_refuse_now_serves_the_answer_and_its_graph(
    wide_service: OrivraService,
) -> None:
    """The case two live Claude Desktop runs died on, at the boundary that killed them.

    **What this used to assert, and why that was the wrong contract.** Until 2026-09-19 this
    fixture's `body_clean` answer composed past the 25,000-character cap and `orivra_ask`
    declined, offering `mailweave_search` - the same evidence without the graph. The refusal
    was correct given the composition and useless given the product: the second Desktop run
    took the offer, answered Harbor out of message reads, and never saw a graph. A recovery
    that abandons the graph is not a graph recovery.

    What is asserted now is the repair. The container is fitted to the room left after
    Orivra's block rather than to the whole cap, so both are served: the answer is here, the
    graph is here, the composed result is inside the cap, and whatever the block set aside to
    make that true names the call that serves it - and that call is executed here, not merely
    read, because an offer that refuses when taken is worse than no offer.
    """
    answer = call(
        wide_service,
        "orivra_ask",
        {"query": "Harbor export mismatch", "view": "body_clean", "graph": True},
    )
    assert not answer.is_error, answer.content
    payload = dict(answer.structured_content or {})
    assert "code" not in payload, f"the ask declined: {payload.get('message')}"
    assert payload["query_id"], "no query_id, so nothing downstream can be addressed"

    text = "\n".join(
        block.text for block in answer.content if getattr(block, "type", None) == "text"
    )
    assert rendered_chars(payload, text) <= HOST_RESULT_CHAR_CAP, (
        "the served result is over the cap"
    )

    allocation = payload["allocation"]
    assert allocation["host_cap_chars"] == HOST_RESULT_CHAR_CAP, "the cap was moved"
    assert allocation["container_chars"] < HOST_RESULT_CHAR_CAP, (
        "the container was still handed the whole cap, which is the defect itself"
    )
    assert (
        allocation["container_chars"] + allocation["orivra_reserve_chars"] == HOST_RESULT_CHAR_CAP
    ), "the split does not add up to the cap, so one of the two is unaccounted"

    graph = payload["graph"]
    assert graph.get("built") is not False, "the graph was dropped to make the answer fit"
    assert graph["counts"]["nodes"] >= 1

    for record in (graph.get("compacted") or {}).get("moved") or ():
        assert record["count"] >= 1, "a list was compacted out with nothing in it"
        recovered = call(wide_service, record["recover"]["tool"], record["recover"]["args"])
        assert not recovered.is_error, recovered.content
        assert dict(recovered.structured_content or {})["total"] == record["count"], (
            "the page serves a different number of records than the entry point promised"
        )


def test_the_last_resort_refusal_still_carries_a_recovery_that_runs(
    wide_service: OrivraService,
) -> None:
    """`_too_large` is a backstop now, and a backstop is still tested.

    `ask` cannot reach it by construction: the container is capped at `cap - reserve` and the
    block compacts into `reserve`, so the composition fits. It stays because "by construction"
    is a claim about arithmetic that no fixture can check from outside, and a result the host
    would cut silently is worse than a decline. What is checked is that *if* it is reached the
    decline is not terminal and the call it names returns evidence - the defect fixed on
    2026-09-18, which nothing can now reproduce through the front door.
    """
    from mailweave.surface.rendering import text_of
    from orivra.surface.service import _too_large

    arguments = {"query": "Harbor export mismatch", "view": "body_clean", "graph": True}
    container = dict(
        call(
            wide_service, ToolName.SEARCH.value, {"query": "Harbor export mismatch"}
        ).structured_content
        or {}
    )
    oversized = _too_large(
        HOST_RESULT_CHAR_CAP + 1,
        container,
        arguments=arguments,
        mirror=text_of(container),
    )
    step = oversized.recovery
    assert step is not None, "a recoverable refusal was declared final"
    assert step.affordance.tool is ToolName.SEARCH
    assert "graph" not in step.affordance.args
    assert step.narrowing.kind is NarrowingKind.SCOPE_CHANGE

    followed = call(wide_service, step.affordance.tool.value, dict(step.affordance.args))
    assert not followed.is_error, followed.content
    assert dict(followed.structured_content or {})["sources"], "the retry recovered no evidence"
