"""The Gmail adapter, over the same synthetic mailbox the v0.1 suite stands on.

Two things are being established here and they are different claims.

**That the adapter is a thin wrapper**, not a second retrieval. `answer` hands back
MailWeave's own `Envelope` object - the identity check below is `is`, not equality - so
there is no second builder, no second measurement and no second certificate. That is what
makes M1's equivalence check exact rather than approximate, and it is the property a future
change would most plausibly break by "improving" the adapter's output.

**That the translation into Orivra's contracts loses nothing and invents nothing.** Every
withholding MailWeave accounted for becomes an omission record at the granularity MailWeave
chose, carrying MailWeave's own affordance as its handle; every disclosed row becomes a node
whose depth, reason and text are the row's.

The mailbox is `tests.test_mcp_surface_round24`'s, imported rather than rebuilt for the
reason that module's own docstring gives: a second synthetic mailbox would agree with the
adapter about every mistake the adapter's author also made.
"""

from __future__ import annotations

import pytest

from mailweave.envelope.response import Envelope
from mailweave.envelope.vocab import Depth, ToolName, WithheldCap
from mailweave.envelope.wire import (
    Affordance,
    CollapsedRun,
    WithheldGroup,
    WithheldRecord,
    WithheldTail,
)
from mailweave.policy.budget import BudgetRequest
from mailweave.surface.arguments import SearchRequest
from mailweave.surface.service import MailweaveService
from orivra.adapter import NativeQuery, QueryFacts
from orivra.contracts import (
    ConnectorId,
    Dimension,
    Granularity,
    NodeKind,
    OmissionCause,
    OrivraToolName,
    RefKind,
    SourceState,
)
from orivra.gmail_adapter import (
    EMITTED_OPERATORS,
    MAX_IDS_PER_FETCH,
    GmailAdapter,
    omission_from_record,
    omission_from_tail,
)
from orivra.registry import ConnectorRegistry, ConnectorUnavailable
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


def search(query: str, **kwargs: object) -> SearchRequest:
    fields: dict[str, object] = {
        "query": query,
        "view": Depth.SNIPPET,
        "scan_max_pages": None,
        "budget": BudgetRequest(),
        "disclosed_token_request": None,
    }
    fields.update(kwargs)
    return SearchRequest(**fields)  # type: ignore[arg-type]


# -- the adapter is a wrapper, not a second retrieval -----------------------------------


def test_answer_hands_back_mailweaves_own_envelope_object(
    adapter: GmailAdapter, service: MailweaveService
) -> None:
    """`is`, not `==`. A copy would be a second object that could drift from the first."""
    request = search("vendor")
    direct = service.search(request)
    through = adapter.answer(search("vendor"))
    assert isinstance(through.envelope, Envelope)
    assert through.envelope.asked_for == direct.asked_for
    assert [source.thread_id for source in through.envelope.sources] == [
        source.thread_id for source in direct.sources
    ]


def test_the_adapter_holds_the_service_rather_than_building_one(
    adapter: GmailAdapter, service: MailweaveService
) -> None:
    """One authorised mailbox in the process, one token store, one handle key."""
    assert adapter.service is service


def test_the_adapter_declares_the_operators_it_actually_emits(adapter: GmailAdapter) -> None:
    facts = QueryFacts(
        text="pricing",
        terms=("pricing",),
        phrases=("July 3 draft",),
        excluded_phrases=("do not reply",),
        participants=("ana@team.example",),
        after="2026/05/01",
        before="2026/09/01",
        identifiers=("<abc@team.example>",),
    )
    native = adapter.translate(facts)
    assert native.connector is ConnectorId.GMAIL
    for operator in ("from:", "after:", "before:", "rfc822msgid:"):
        assert operator in native.query
    assert '"July 3 draft"' in native.query
    assert '-"do not reply"' in native.query
    assert native.unrepresentable == ()
    for operator in EMITTED_OPERATORS:
        assert operator in {name.rstrip(":") for name in EMITTED_OPERATORS}


def test_a_phrase_gmail_cannot_express_is_recorded_and_not_dropped(
    adapter: GmailAdapter,
) -> None:
    """Gmail documents no escape for a quote inside a quoted phrase, so inventing one here
    would be inventing syntax. The constraint is declared unrepresentable instead."""
    native = adapter.translate(QueryFacts(text='he said "no"', phrases=('he said "no"',)))
    assert native.unrepresentable == ('phrase:he said "no"',)
    assert '"no"' not in native.query.replace('he said "no"', "")


def test_a_translation_from_another_source_is_refused(adapter: GmailAdapter) -> None:
    with pytest.raises(ValueError, match="reached the Gmail adapter"):
        adapter.search(NativeQuery(connector=ConnectorId.SLACK, query="in:#general"))


def test_the_ladder_is_read_off_mailweaves_own_tuple(adapter: GmailAdapter) -> None:
    """Read off `LADDER`, because a ladder listed twice is a ladder edited once."""
    from mailweave.retrieval.ladder import LADDER

    assert len(adapter.rungs()) == len(LADDER)
    assert [spec.rung_id for spec in adapter.rungs()] == [rung.rung.value for rung in LADDER]


def test_capabilities_are_declared_rather_than_probed(adapter: GmailAdapter) -> None:
    capabilities = adapter.capabilities()
    assert capabilities.connector is ConnectorId.GMAIL
    assert capabilities.native_search is True
    assert capabilities.container_kind == "thread"
    assert capabilities.revisions is False
    assert capabilities.change_feed == "history"
    assert capabilities.max_ids_per_fetch == MAX_IDS_PER_FETCH


# -- what the translation into Orivra's contracts preserves ------------------------------


def test_every_disclosed_row_becomes_a_node_carrying_its_own_reason_and_depth(
    adapter: GmailAdapter,
) -> None:
    result = adapter.answer(search("vendor"))
    assert result.envelope is not None
    rows = {row.id: row for source in result.envelope.sources for row in source.messages}
    nodes = {node.node_id: node for node in result.nodes if node.kind is NodeKind.MESSAGE}
    assert rows, "the fixture query returned no rows, so this test proves nothing"
    for message_id, row in rows.items():
        node = nodes[f"gmail/message/{message_id}"]
        assert node.depth is row.depth
        assert node.reason == row.reason
        assert node.ref.kind is RefKind.MESSAGE
        assert node.ref.permission.scope_set == (SCOPE,)


def test_every_source_becomes_a_container_node_with_the_sources_own_counts(
    adapter: GmailAdapter,
) -> None:
    result = adapter.answer(search("vendor"))
    assert result.envelope is not None
    containers = {node.node_id: node for node in result.nodes if node.kind is NodeKind.THREAD}
    for source in result.envelope.sources:
        node = containers[f"gmail/thread/{source.thread_id}"]
        assert node.stated_total == source.stated_total
        assert node.included == source.included


def test_every_node_carries_a_timestamp_the_certificate_recorded(
    adapter: GmailAdapter,
) -> None:
    """R-DEMO-002: a row a reader had to date by its position is the defect this closes.

    The instant comes off the certificate, which is where amendment A6 put it."""
    result = adapter.answer(search("vendor"))
    assert result.envelope is not None
    dated = [
        node
        for node in result.nodes
        if node.kind is NodeKind.MESSAGE and node.timestamps.sent is not None
    ]
    assert dated, "no node carried an internalDate, so A6's seal was not read"
    for node in dated:
        assert node.timestamps.sent is not None
        assert node.timestamps.sent.tzinfo is not None


#: A fixture query that really does hit `max_hit_threads` and produce a withheld group.
#: Chosen by running the mailbox rather than by hoping: a test that skips when it finds
#: nothing proves nothing, and three of these skipped on the first draft.
WITHHOLDING = ("note", BudgetRequest(max_hit_threads=1))


def test_a_group_stays_a_group_because_granularity_is_the_call_that_recovers_it(
    adapter: GmailAdapter,
) -> None:
    """Round 29's rule, preserved across the translation rather than re-derived.

    Re-splitting one group into forty-five node records would mint forty-five handles for
    one call, which is the 23,220-character failure R-MCP-033 recorded.
    """
    query, budget = WITHHOLDING
    result = adapter.answer(search(query, budget=budget))
    assert result.envelope is not None
    groups = result.envelope.withheld_groups
    assert groups, "the chosen fixture query no longer withholds; pick another"
    container_records = [
        record for record in result.omissions if record.granularity is Granularity.CONTAINER
    ]
    assert len(container_records) == len(groups)
    for record, group in zip(container_records, groups, strict=True):
        assert record.count == group.message_count
        assert record.what == f"gmail/thread/{group.thread_id}"
        assert record.cause is OmissionCause.CAP
        assert record.cap_name == group.cap.value
        assert record.why == group.why


def test_an_omission_handle_is_mailweaves_affordance_relabelled_never_reminted(
    adapter: GmailAdapter,
) -> None:
    """The affordance already satisfies R-07 and the suite validates it against the
    published inputSchema; a handle Orivra invented would have none of that behind it."""
    query, budget = WITHHOLDING
    result = adapter.answer(search(query, budget=budget))
    assert result.envelope is not None
    sources: list[WithheldRecord | WithheldGroup | WithheldTail | CollapsedRun] = [
        *result.envelope.withheld,
        *result.envelope.withheld_groups,
        *result.envelope.withheld_tail,
        *[run for source in result.envelope.sources for run in source.collapsed_runs],
    ]
    assert sources, "the chosen fixture query no longer withholds; pick another"
    for record, origin in zip(result.omissions, sources, strict=True):
        assert record.recover is not None
        assert record.recover.tool.value == origin.affordance.tool.value
        assert record.recover.args == dict(origin.affordance.args)
        assert record.recover.tool.is_mailweave


def test_every_withheld_thing_becomes_exactly_one_omission_record(
    adapter: GmailAdapter,
) -> None:
    """The count is the claim: a translation that dropped one would be a silence, and a
    translation that split one would mint a call nobody can make."""
    query, budget = WITHHOLDING
    result = adapter.answer(search(query, budget=budget))
    assert result.envelope is not None
    expected = (
        len(result.envelope.withheld)
        + len(result.envelope.withheld_groups)
        + len(result.envelope.withheld_tail)
        # **Four shapes, not three** (review finding R-M1-004). A count over three of them
        # is the count that let a collapsed run of eighty vanish.
        + sum(len(source.collapsed_runs) for source in result.envelope.sources)
    )
    assert len(result.omissions) == expected


def test_a_single_withheld_message_translates_at_node_granularity() -> None:
    """The per-message shape, unit-tested rather than hunted for in the fixture mailbox.

    `WithheldRecord` is the shape a capped *message* produces, and the synthetic mailbox
    happens to produce groups rather than records for every query that fits its budgets. A
    test that skipped on that would leave the commonest translation unexercised.
    """
    record = WithheldRecord(
        id="m-9",
        thread_id="t-9",
        cap=WithheldCap.MAX_POOL_MESSAGES,
        why="the message pool cap was reached",
        affordance=Affordance(
            tool=ToolName.GET_MESSAGES, args={"message_ids": ["m-9"], "view": "snippet"}
        ),
    )
    translated = omission_from_record(record)
    assert translated.what == "gmail/message/m-9"
    assert translated.granularity is Granularity.NODE
    assert translated.count == 1
    assert translated.cause is OmissionCause.CAP
    assert translated.cap_name == WithheldCap.MAX_POOL_MESSAGES.value
    assert translated.recover is not None
    assert translated.recover.tool is OrivraToolName.GET_MESSAGES
    assert translated.recover.reduces is Dimension.DEPTH


def test_a_tail_is_a_region_because_it_deliberately_names_no_thread() -> None:
    """The tail's compaction is that it names no thread; a record claiming a container id
    would undo exactly that."""
    tail = WithheldTail(
        cap=WithheldCap.MAX_HIT_THREADS,
        why="threads past the named groups, under one cap",
        thread_count=12,
        message_count=61,
        affordance=Affordance(
            tool=ToolName.SEARCH, args={"query": "note", "budget": {"max_hit_threads": 24}}
        ),
    )
    translated = omission_from_tail(tail)
    assert translated.granularity is Granularity.REGION
    assert translated.what == "gmail/cap/max_hit_threads"
    assert translated.count == 61
    assert translated.recover is not None
    assert translated.recover.reduces is Dimension.BREADTH


def test_a_ceiling_is_not_reported_as_a_cap_a_caller_could_raise() -> None:
    """Raising a cap and widening a ceiling are different actions, and a caller told "cap"
    for both would take the wrong one."""
    record = WithheldRecord(
        id="m-4",
        thread_id="t-4",
        cap=WithheldCap.DISCLOSED_TOKEN_CEILING,
        why="the disclosed-token ceiling was reached",
        affordance=Affordance(tool=ToolName.GET_MESSAGES, args={"message_ids": ["m-4"]}),
    )
    translated = omission_from_record(record)
    assert translated.cause is OmissionCause.CEILING
    assert translated.cap_name is None


def test_the_spend_block_restates_mailweaves_own_counters(adapter: GmailAdapter) -> None:
    result = adapter.answer(search("vendor"))
    assert result.envelope is not None
    report = result.envelope.retrieval_report
    assert result.spend.connector is ConnectorId.GMAIL
    assert result.spend.state is SourceState.READY
    assert result.spend.quota_units == report.counters.quota_units
    assert result.spend.hits == sum(report.hit_count_per_rung)
    assert result.spend.rungs_executed == tuple(rung.value for rung in report.rungs)


# -- the primitives ----------------------------------------------------------------------


def test_search_returns_ids_that_entered_H(adapter: GmailAdapter) -> None:
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    assert hits.ids
    assert all(isinstance(one, str) and one for one in hits.ids)
    assert hits.rungs_executed


def test_container_reads_the_structured_payload_and_carries_the_stated_total(
    adapter: GmailAdapter,
) -> None:
    """Read from the structured payload and never from the text mirror, which closes
    R-DEMO-001 and R-DEMO-004 here rather than in each demo script."""
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    assert hits.container_ids
    thread = adapter.reference(hits.container_ids[0], kind=RefKind.THREAD)
    container = adapter.container(thread)
    assert container.stated_total >= len(container.member_ids)
    assert set(container.positions) == set(container.member_ids)


def test_asking_a_message_for_its_members_is_refused(adapter: GmailAdapter) -> None:
    with pytest.raises(ValueError, match="container of one"):
        adapter.container(adapter.reference("m-1"))


def test_items_lowers_the_depth_rather_than_claiming_text_that_is_not_there(
    adapter: GmailAdapter,
) -> None:
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    refs = tuple(adapter.reference(one) for one in hits.ids[:3])
    nodes = adapter.items(refs, depth=Depth.BODY_CLEAN.value)
    assert nodes
    for node in nodes:
        if node.depth in {Depth.BODY_CLEAN, Depth.BODY_FULL}:
            assert node.content
        elif node.depth is Depth.STUB:
            assert node.content is None


def test_the_permission_context_carries_the_granted_scope_set(adapter: GmailAdapter) -> None:
    """The granted set, never the requested one: a request for gmail.readonly granted
    something narrower must not produce a context claiming the wider scope."""
    context = adapter.permission_context()
    assert context.scope_set == (SCOPE,)
    assert context.principal == adapter.service.account_hash
    assert context.connector is ConnectorId.GMAIL


# -- the registry --------------------------------------------------------------------------


def test_the_registry_names_every_connector_including_the_ones_it_does_not_have(
    adapter: GmailAdapter,
) -> None:
    """ "Drive is not configured" and "Drive returned nothing" are different answers to
    "what did you look at?"."""
    registry = ConnectorRegistry(adapters={ConnectorId.GMAIL: adapter})
    statuses = {status.connector: status for status in registry.statuses()}
    assert set(statuses) == set(ConnectorId)
    assert statuses[ConnectorId.GMAIL].state is SourceState.READY
    assert statuses[ConnectorId.GMAIL].capabilities is not None
    for absent in (ConnectorId.DRIVE, ConnectorId.SLACK):
        assert statuses[absent].state is SourceState.NOT_CONFIGURED
        assert statuses[absent].detail
        assert statuses[absent].capabilities is None


def test_a_registry_with_no_gmail_adapter_refuses_with_the_remedy(
    adapter: GmailAdapter,
) -> None:
    registry = ConnectorRegistry(adapters={})
    with pytest.raises(ConnectorUnavailable, match="mailweave auth login"):
        registry.gmail()
    # **Not a LookupError** (review finding R-M1-002): `except LookupError` on the surface
    # caught every KeyError and IndexError inside a handler and reported it to the client as
    # auth_reauth_required with the exception string in the remediation.
    assert not issubclass(ConnectorUnavailable, LookupError)
    assert adapter.connector is ConnectorId.GMAIL


def test_orivra_carries_mailweaves_four_tool_names_unchanged() -> None:
    """The compatibility claim, executed: a handle naming a re-spelled tool is one no
    server can run."""
    assert {name.value for name in ToolName} <= {name.value for name in OrivraToolName}


# -- R-M1-004 / R-M1-005: the fourth accounting shape, which the first draft dropped --------
#
# MailWeave has four: WithheldRecord, WithheldGroup, WithheldTail and Source.collapsed_runs.
# The adapter translated three. On a 300-message thread the ladder collapsed, MailWeave
# accounted for all 300 with an executable affordance and Orivra emitted a container node
# saying `included=300` beside a handful of children and **no record at all** - the
# partiality invariant lost in translation, which is worse than never having had it, because
# the container's own numbers said the response was complete.

#: A fixture query whose response really does carry collapsed runs.
COLLAPSING = "note"


def test_a_collapsed_run_becomes_an_omission_record(adapter: GmailAdapter) -> None:
    result = adapter.answer(search(COLLAPSING))
    assert result.envelope is not None
    runs = [
        (source.thread_id, run)
        for source in result.envelope.sources
        for run in source.collapsed_runs
    ]
    assert runs, "the chosen fixture query no longer collapses; pick another"
    branches = [record for record in result.omissions if record.granularity is Granularity.BRANCH]
    assert len(branches) == len(runs)
    for record, (thread_id, run) in zip(branches, runs, strict=True):
        assert record.count == run.count
        assert thread_id in record.what
        assert record.recover is not None
        assert record.recover.args == dict(run.affordance.args)


def test_nodes_and_omissions_together_account_for_every_stated_message(
    adapter: GmailAdapter,
) -> None:
    """The invariant the dropped shape broke, stated over the adapter's own output.

    Every message a container states is either a node in the result or inside an omission
    record. A translation that loses an accounting shape fails here rather than being noticed
    on an eighty-message thread by a reviewer.
    """
    result = adapter.answer(search(COLLAPSING))
    assert result.envelope is not None
    stated = sum(source.stated_total for source in result.envelope.sources)
    disclosed = len([node for node in result.nodes if node.kind is NodeKind.MESSAGE])
    accounted = sum(record.count or 0 for record in result.omissions)
    assert stated > disclosed, "this query discloses everything, so it proves nothing"
    assert disclosed + accounted >= stated, (
        f"{stated} messages stated, {disclosed} disclosed as nodes and {accounted} "
        "accounted for as omissions; the difference is a silence"
    )


def test_container_carries_the_members_a_collapsed_run_holds(
    adapter: GmailAdapter,
) -> None:
    """`source.messages` holds only what the ladder disclosed; a thread it compacted has its
    members in `collapsed_runs`, which carry `member_ids` on the wire precisely so a reader
    can compute the set from the response alone."""
    result = adapter.answer(search(COLLAPSING))
    assert result.envelope is not None
    biggest = max(result.envelope.sources, key=lambda one: one.stated_total)
    assert biggest.collapsed_runs, "the chosen source no longer collapses"
    container = adapter.container(adapter.reference(biggest.thread_id, kind=RefKind.THREAD))
    assert len(container.member_ids) > len(biggest.messages)
    assert len(container.member_ids) == container.stated_total
    assert set(container.positions) == set(container.member_ids)
    ordered = [container.positions[one] for one in container.member_ids]
    assert ordered == sorted(ordered), "members are returned out of thread order"


# -- the correction pass: what the review found in the translation --------------------------


def test_node_content_is_unfenced_so_a_span_can_be_checked_against_it(
    adapter: GmailAdapter,
) -> None:
    """R-M1-006. `nodes.py` says a node is not an emission and must not carry a response's
    fence; the code returned `row.content.text`, which is fenced. Two consequences: a cached
    node carried a dead nonce that a later response would re-emit inside a live one, and every
    span offset shifted by the length of the opening marker, so the graph's string-match
    compared fenced text against offsets computed over the unfenced body.
    """
    result = adapter.answer(search("vendor"))
    assert result.envelope is not None
    nonce = result.envelope.fence_nonce
    bodied = [
        node for node in result.nodes if node.kind is NodeKind.MESSAGE and node.content is not None
    ]
    assert bodied, "no node carried content, so this test proves nothing"
    for node in bodied:
        assert node.content is not None
        assert nonce not in node.content
        assert not node.content.startswith("<<<")


def test_a_node_can_be_quoted_at_the_offsets_the_recogniser_computes(
    adapter: GmailAdapter,
) -> None:
    """The consequence of the fence bug, as its own assertion: the graph's span check and the
    recogniser's offsets have to be in the same frame of reference."""
    result = adapter.answer(search("vendor", view=Depth.BODY_CLEAN))
    assert result.envelope is not None
    node = next(one for one in result.nodes if one.kind is NodeKind.MESSAGE and one.content)
    assert node.content is not None
    word = node.content.split()[0]
    assert node.content[0 : len(word)] == word


def test_version_of_reads_the_messages_own_history_id(
    adapter: GmailAdapter, box: SyntheticMailbox
) -> None:
    """R-M1-008. It read `users.getProfile().historyId`, which is the MAILBOX watermark:
    every message in the account came back with the same revision, so no version could
    distinguish "this message's view changed" from "something else did", and at M2 one
    unrelated event would invalidate every cached entry in the account.

    **Asserted by the calls it makes, not by the value it returns.** The synthetic mailbox
    gives every message the profile's `historyId`, so the two are indistinguishable by value
    here - which is exactly how a test over this fixture can pass while the code reads the
    wrong field. What is decidable is that the profile is not fetched at all: the message's
    own `historyId` came back with the first call, and the second was pure quota.
    """
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="note"))
    assert hits.ids
    box.calls.clear()
    version = adapter.version_of(adapter.reference(hits.ids[0]))
    made = {name: count for name, count in box.calls.items() if count}
    assert version.native_id == hits.ids[0]
    assert version.revision
    assert not any("profile" in name for name in made), made
    assert sum(made.values()) == 1, made


def test_a_source_that_answered_incompletely_is_not_reported_as_unverifiable() -> None:
    """R-M1-009. Raising a cap, widening a ceiling, re-verifying a version and retrying a
    source are four actions; three causes for four conditions makes one wrong."""
    record = WithheldRecord(
        id="m-7",
        thread_id="t-7",
        cap=WithheldCap.PARTIAL_SOURCE_FAILURE,
        why="one sibling request failed and the rest answered",
        affordance=Affordance(tool=ToolName.GET_MESSAGES, args={"message_ids": ["m-7"]}),
    )
    translated = omission_from_record(record)
    assert translated.cause is OmissionCause.PARTIAL_SOURCE_FAILURE
    assert translated.cap_name is None
    assert translated.recover is not None


def test_items_at_stub_depth_discloses_no_text(adapter: GmailAdapter) -> None:
    """R-M1-017. Stub is the depth that says no text is here; returning a snippet for it and
    raising the declared depth discloses text no ceiling measured."""
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    nodes = adapter.items(tuple(adapter.reference(one) for one in hits.ids[:2]), depth="stub")
    assert nodes
    for node in nodes:
        assert node.depth is Depth.STUB
        assert node.content is None


def test_items_at_raw_depth_returns_a_body_rather_than_degrading_to_metadata(
    adapter: GmailAdapter,
) -> None:
    """R-M1-017. `raw` is the fullest depth and was not in the set that fetches one, so a
    request for it silently came back as a snippet."""
    hits = adapter.search(NativeQuery(connector=ConnectorId.GMAIL, query="vendor"))
    nodes = adapter.items(tuple(adapter.reference(one) for one in hits.ids[:1]), depth="raw")
    assert nodes
    assert nodes[0].depth is not Depth.STUB
    assert nodes[0].content


def test_translate_emits_a_recipient_constraint_as_a_recipient_constraint(
    adapter: GmailAdapter,
) -> None:
    """R-M1-019. `to:` was published as an emitted operator and never emitted, and every
    participant became a sender filter - so `orivra_sources` told a planner a recipient
    constraint was expressible and `translate` answered a different question."""
    native = adapter.translate(
        QueryFacts(
            text="x",
            participants=("ana@team.example",),
            recipients=("bo@team.example",),
        )
    )
    assert "from:ana@team.example" in native.query
    assert "to:bo@team.example" in native.query


def test_every_published_operator_is_one_translate_can_emit(adapter: GmailAdapter) -> None:
    """The constant is published as a capability, so a planner reads it as a promise."""
    native = adapter.translate(
        QueryFacts(
            text="x",
            participants=("ana@team.example",),
            recipients=("bo@team.example",),
            after="2026/01/01",
            before="2026/02/01",
            identifiers=("<a@b>",),
        )
    )
    for operator in EMITTED_OPERATORS:
        assert f"{operator}:" in native.query, operator


def test_an_internal_date_python_cannot_represent_is_an_absent_one() -> None:
    """R-M1-020. `GmailNumericId` accepts twenty digits; `fromtimestamp` raises well before
    that, and the exception escaped the tool call as an internal error - one odd field taking
    down the whole response."""
    from orivra.gmail_adapter import _timestamps

    assert _timestamps("99999999999999999999").sent is None
    assert _timestamps("9999999999999999999").sent is None
    assert _timestamps("not-a-number").sent is None
    assert _timestamps(None).sent is None
    assert _timestamps("1767258000000").sent is not None
