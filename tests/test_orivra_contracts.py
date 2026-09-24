"""The Orivra contract layer refuses what the design says it must (plan §4).

One test per rule, each breaking exactly one thing about an otherwise valid object. The
rules under test are the ones the design states in prose; a test here is the sentence made
executable, and its name is the sentence.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from mailweave.envelope.vocab import Depth, Role
from mailweave.envelope.vocab import ToolName as MailweaveToolName
from orivra.contracts import (
    CandidateBasis,
    CandidateStatus,
    ChangeMarker,
    ClauseClearance,
    ConnectorId,
    ContentVersion,
    DeterministicKey,
    Dimension,
    EdgeOrigin,
    Entity,
    EntityCandidate,
    EntitySpend,
    EvidenceEdge,
    ExpansionHandle,
    FreshnessState,
    FreshnessStatus,
    Granularity,
    GraphSpend,
    NodeKind,
    OmissionCause,
    OmissionRecord,
    Origin,
    OrivraToolName,
    PermissionContext,
    PermissionRequirement,
    QueryGraph,
    RefKind,
    Relation,
    RetrievalTrace,
    SourceReference,
    SourceSpend,
    SourceState,
    Span,
    TargetResolution,
    permission_safe_omission,
    release,
    requirements_of,
)
from tests.orivra_build import (
    CUE,
    CUE_END,
    CUE_START,
    NODE_A,
    NODE_B,
    NOW,
    SCOPE,
    TEXT_A,
    TEXT_B,
    WIDER,
    confidence,
    degraded,
    drive_reference,
    edge,
    entity,
    method,
    node,
    permission,
    reference,
    slack_reference,
    span,
    stated_check,
)

# -- the relation fixes what a builder must not choose ---------------------------------


def test_a_relations_namespace_decides_its_origin_and_assertion() -> None:
    """`origin` and `assertion` are read off the relation, so no builder can disagree."""
    assert Relation.REPLY_TO.origin is EdgeOrigin.OBSERVED
    assert Relation.SUPERSEDES_STATED.origin is EdgeOrigin.OBSERVED
    assert Relation.SUPPORTS.origin is EdgeOrigin.INFERRED
    assert Relation.REPLY_TO.assertion.value == "metadata"
    assert Relation.SUPERSEDES_STATED.assertion.value == "source_stated"
    assert Relation.SUPPORTS.assertion.value == "derived"


def test_no_relation_asserts_causation_in_either_namespace() -> None:
    """§4.5: there is no `caused` relation, and no rule promotes an inference."""
    assert not any("caus" in relation.value for relation in Relation)


def test_an_edges_origin_and_recomputability_are_not_fields() -> None:
    assert "origin" not in EvidenceEdge.model_fields
    assert "assertion" not in EvidenceEdge.model_fields
    assert "recomputable" not in EvidenceEdge.model_fields
    assert edge().recomputable is False
    inferred = edge(relation=Relation.SUPPORTS, spans=(span(),), confidence=confidence())
    assert inferred.recomputable is True


# -- observed and inferred cannot look alike -------------------------------------------


def test_an_inferred_relation_with_no_spans_is_refused() -> None:
    with pytest.raises(ValidationError, match="carries no spans"):
        edge(relation=Relation.SUPPORTS, confidence=confidence())


def test_an_inferred_relation_with_no_confidence_is_refused() -> None:
    with pytest.raises(ValidationError, match="carries no confidence"):
        edge(relation=Relation.SUPPORTS, spans=(span(),))


def test_an_observed_relation_carrying_a_confidence_is_refused() -> None:
    with pytest.raises(ValidationError, match="carries a confidence"):
        edge(confidence=confidence())


def test_a_metadata_relation_carrying_spans_is_refused() -> None:
    """A header field is not quoted from content, and attaching a quotation to one invites
    a reader to check the fact against text that did not produce it."""
    with pytest.raises(ValidationError, match="carries spans"):
        edge(spans=(span(),))


# -- the four gates of a source-stated assertion (§4.5, owner correction 8) -------------


def test_a_source_stated_edge_without_its_check_is_refused() -> None:
    with pytest.raises(ValidationError, match="no StatedAssertionCheck"):
        edge(relation=Relation.SUPERSEDES_STATED, spans=(span(),))


def test_a_source_stated_edge_aimed_away_from_its_own_evidence_is_refused() -> None:
    """The verbatim-but-wrong-document fixture, at the contract layer."""
    with pytest.raises(ValidationError, match="points at"):
        edge(
            relation=Relation.SUPERSEDES_STATED,
            spans=(span(),),
            stated=stated_check(),
            target="gmail/message/mC",
            support=(reference("mA"), reference("mC")),
        )


def test_a_source_stated_edge_asserted_by_a_third_node_is_refused() -> None:
    with pytest.raises(ValidationError, match="neither endpoint"):
        edge(
            relation=Relation.SUPERSEDES_STATED,
            spans=(span(),),
            stated=stated_check(asserted_by="gmail/message/mC"),
        )


def test_an_unresolved_target_cannot_produce_a_stated_check_at_all() -> None:
    """Ambiguity is refused where the check is built, not left for the edge to notice."""
    with pytest.raises(ValidationError, match="not its target"):
        stated_check(
            target=TargetResolution(
                resolved_to=None,
                considered=(NODE_B, "gmail/message/mC"),
                referring_text="the July 3 pricing draft",
            )
        )


def test_a_resolution_pointing_outside_its_own_candidate_set_is_refused() -> None:
    with pytest.raises(ValidationError, match="not among the candidates"):
        TargetResolution(
            resolved_to=NODE_B, considered=("gmail/message/mC",), referring_text="the draft"
        )


def test_a_clearance_that_records_cues_is_not_a_clearance() -> None:
    with pytest.raises(ValidationError, match="records cues"):
        ClauseClearance(
            clause="we are not withdrawing the approval",
            language="en",
            cues_found=("negation:not",),
            span_class_signals=("no_structural_signal",),
        )


def test_a_clearance_in_a_language_the_cue_sets_do_not_cover_is_refused() -> None:
    with pytest.raises(ValidationError, match="cue sets are English"):
        ClauseClearance(
            clause="Dies ersetzt den Entwurf.",
            language="de",
            span_class_signals=("no_structural_signal",),
        )


def test_a_clearance_computed_over_other_text_clears_nothing() -> None:
    with pytest.raises(ValidationError, match="does not contain the span"):
        stated_check(
            clearance=ClauseClearance(
                clause="Something else entirely.",
                language="en",
                span_class_signals=("no_structural_signal",),
            )
        )


def test_the_referring_words_must_be_words_the_span_preserved() -> None:
    with pytest.raises(ValidationError, match="not inside the span"):
        stated_check(
            target=TargetResolution(
                resolved_to=NODE_B, considered=(NODE_B,), referring_text="a phrase not quoted"
            )
        )


def test_running_the_stated_gates_over_a_metadata_fact_is_refused() -> None:
    with pytest.raises(ValidationError, match="source-stated check"):
        edge(stated=stated_check(), spans=(span(),))


# -- permission covers the whole edge, not only its endpoints (§4.2) --------------------


def test_an_endpoint_absent_from_support_is_refused() -> None:
    with pytest.raises(ValidationError, match="not among the edge's supporting references"):
        edge(support=(reference("mA"),))


def test_an_edge_whose_conjunction_understates_its_own_support_is_refused() -> None:
    """The owner's decision on R-M1-016, at the schema.

    `requires` is re-derived from `support` and compared, so a builder cannot type a narrower
    conjunction than the edge actually rests on. Understating it is how a second source's
    requirement quietly stops being asked about, which is the third-document disclosure the
    edge-visibility rule exists to prevent.
    """
    support = (reference("mA"), reference("mB"), drive_reference("f1"))
    gmail_only = tuple(
        one for one in requirements_of(support) if one.connector is ConnectorId.GMAIL
    )
    with pytest.raises(ValidationError, match="not the one its own support produces"):
        edge(
            source=NODE_A,
            target=NODE_B,
            support=support,
            requires=gmail_only,
        )


def test_an_edge_whose_freshness_failed_is_withheld_rather_than_served() -> None:
    with pytest.raises(ValidationError, match="edge freshness"):
        edge(freshness=degraded(FreshnessState.GONE))


def test_a_span_quoting_a_third_node_belongs_in_support_not_in_the_edge() -> None:
    with pytest.raises(ValidationError, match="neither endpoint"):
        edge(
            relation=Relation.SUPPORTS,
            spans=(span(node_id="gmail/message/mC", start=0, end=4, text="This"),),
            confidence=confidence(),
        )


def test_an_edge_from_a_node_to_itself_is_refused() -> None:
    with pytest.raises(ValidationError, match="itself"):
        edge(target=NODE_A)


# -- references, versions, permission contexts -----------------------------------------


def test_a_reference_carrying_another_sources_version_is_refused() -> None:
    other = ContentVersion(connector=ConnectorId.DRIVE, native_id="mA", revision="1")
    with pytest.raises(ValidationError, match="re-verified against the wrong change feed"):
        reference("mA", version=other)


def test_a_reference_whose_version_names_another_item_is_refused() -> None:
    with pytest.raises(ValidationError, match="different items"):
        SourceReference(
            connector=ConnectorId.GMAIL,
            account="account-digest",
            kind=RefKind.MESSAGE,
            native_id="mA",
            version=ContentVersion(connector=ConnectorId.GMAIL, native_id="mZ", revision="1"),
            permission=permission(),
        )


def test_a_permission_hash_ignores_when_it_was_observed() -> None:
    """Two reads a minute apart under the same grant are one context; including the instant
    would make every cache entry unique and the dimension useless."""
    later = PermissionContext(
        connector=ConnectorId.GMAIL,
        principal="account-digest",
        scope_set=(SCOPE,),
        observed_at=NOW + timedelta(minutes=1),
    )
    assert later.hash == permission().hash


def test_a_permission_context_covers_only_a_narrower_grant_on_the_same_principal() -> None:
    narrow, wide = permission(), permission(SCOPE, WIDER)
    assert wide.covers(narrow)
    assert not narrow.covers(wide)


def test_scope_sets_are_canonical_because_they_feed_a_digest() -> None:
    with pytest.raises(ValidationError, match="sorted and de-duplicated"):
        PermissionContext(
            connector=ConnectorId.GMAIL,
            principal="p",
            scope_set=(SCOPE, WIDER),
            observed_at=NOW,
        )


def test_a_slack_change_marker_never_stores_a_cursor() -> None:
    with pytest.raises(ValidationError, match="cursors expire"):
        ChangeMarker(connector=ConnectorId.SLACK, container="C1", marker="dXNlcg==")


def test_a_gmail_change_marker_stores_no_timestamp_window() -> None:
    with pytest.raises(ValidationError, match="does not store a timestamp window"):
        ChangeMarker(connector=ConnectorId.GMAIL, marker="99", window_start="1")


def test_a_degraded_freshness_state_states_its_cause() -> None:
    with pytest.raises(ValidationError, match="carries no why"):
        FreshnessStatus(verified_at=NOW, state=FreshnessState.STALE)


def test_a_fresh_state_carries_no_explanation() -> None:
    with pytest.raises(ValidationError, match="carries a why"):
        FreshnessStatus(verified_at=NOW, state=FreshnessState.FRESH, why="all good")


def test_exactly_one_freshness_state_may_be_served() -> None:
    assert [state for state in FreshnessState if state.servable] == [FreshnessState.FRESH]


# -- nodes ------------------------------------------------------------------------------


def test_a_source_backed_node_is_addressed_by_its_reference() -> None:
    with pytest.raises(ValidationError, match="not the identity its reference produces"):
        node(node_id="mA")


def test_a_derived_node_says_what_derived_it() -> None:
    with pytest.raises(ValidationError, match="versioned method"):
        node(node_id="derived/c1", origin=Origin.DERIVED)


def test_a_source_backed_node_carrying_a_derivation_method_is_refused() -> None:
    with pytest.raises(ValidationError, match="row the source held"):
        node(method=method())


def test_a_claim_node_is_always_derived_and_always_quotes() -> None:
    with pytest.raises(ValidationError, match="always derived"):
        node(kind=NodeKind.CLAIM)
    with pytest.raises(ValidationError, match="verbatim spans"):
        node(
            node_id="derived/c1",
            kind=NodeKind.CLAIM,
            origin=Origin.DERIVED,
            method=method(),
            derived_from=(NODE_A,),
        )


def test_a_container_states_its_count_and_a_leaf_does_not() -> None:
    with pytest.raises(ValidationError, match="states no total"):
        node(
            "t1",
            None,
            node_id="gmail/thread/t1",
            ref=reference("t1", kind=RefKind.THREAD),
            kind=NodeKind.THREAD,
            depth=Depth.STUB,
            role=Role.CONTEXT,
        )
    with pytest.raises(ValidationError, match="not a container"):
        node(stated_total=3, included=1)


def test_a_container_cannot_include_more_rows_than_the_source_says_exist() -> None:
    with pytest.raises(ValidationError, match="more rows than the source says exist"):
        node(
            "t1",
            None,
            node_id="gmail/thread/t1",
            ref=reference("t1", kind=RefKind.THREAD),
            kind=NodeKind.THREAD,
            depth=Depth.STUB,
            role=Role.CONTEXT,
            stated_total=2,
            included=5,
        )


def test_a_depth_is_a_statement_about_text_that_is_present() -> None:
    with pytest.raises(ValidationError, match="stub node carries content"):
        node(depth=Depth.STUB)
    with pytest.raises(ValidationError, match="carries no content"):
        node(content=None)


def test_a_node_that_failed_verification_carries_no_content() -> None:
    with pytest.raises(ValidationError, match="never to serving"):
        node(freshness=degraded())


def test_every_node_carries_timestamps_even_when_the_source_reported_none() -> None:
    """R-DEMO-002 closes at the schema: a visible absence rather than an invisible one."""
    assert node().timestamps.any_stated is False


def test_a_span_whose_offsets_and_quotation_disagree_is_refused() -> None:
    with pytest.raises(ValidationError, match="offsets and quotation that disagree"):
        Span(node_id=NODE_A, start=0, end=5, text="abc")


# -- omission records -------------------------------------------------------------------


def _handle() -> ExpansionHandle:
    return ExpansionHandle(
        tool=OrivraToolName.THREAD_MAP, args={"thread_id": "t1"}, reduces=Dimension.BREADTH
    )


def _omission(**kwargs: object) -> OmissionRecord:
    fields: dict[str, object] = {
        "what": "gmail/thread/t1",
        "granularity": Granularity.CONTAINER,
        "count": 41,
        "cause": OmissionCause.CAP,
        "cap_name": "max_hit_threads",
        "why": "the hit-thread cap was reached",
        "recover": _handle(),
        "connector": ConnectorId.GMAIL,
    }
    fields.update(kwargs)
    return OmissionRecord(**fields)  # type: ignore[arg-type]


def test_orivra_carries_mailweaves_tool_names_verbatim() -> None:
    """A handle naming a re-spelled tool is a handle no server can execute."""
    assert {name.value for name in MailweaveToolName} <= {n.value for n in OrivraToolName}
    assert OrivraToolName.THREAD_MAP.is_mailweave
    assert not OrivraToolName.ASK.is_mailweave


def test_a_recoverable_omission_carries_the_way_back() -> None:
    with pytest.raises(ValidationError, match="offers no handle"):
        _omission(recover=None)


def test_the_two_unreachable_causes_may_omit_the_handle() -> None:
    assert [c.value for c in OmissionCause if c.may_have_no_handle] == [
        "permission",
        "source_gone",
    ]
    record = _omission(cause=OmissionCause.PERMISSION, cap_name=None, recover=None)
    assert record.count == 41


def test_a_capped_omission_names_the_cap() -> None:
    with pytest.raises(ValidationError, match="no cap is named"):
        _omission(cap_name=None)
    with pytest.raises(ValidationError, match="a cap is named"):
        _omission(cause=OmissionCause.PRUNED, cap_name="max_hops")


def test_the_presence_free_form_is_free_of_presence() -> None:
    """§4.2: where even the count would disclose something, only connector and cause survive."""
    record = OmissionRecord(
        granularity=Granularity.NODE,
        cause=OmissionCause.PERMISSION,
        why="the caller's grant does not reach it",
        connector=ConnectorId.GMAIL,
        presence_free=True,
    )
    assert record.what == "" and record.count is None and record.recover is None
    with pytest.raises(ValidationError, match="carries an identity, a count or a handle"):
        _omission(presence_free=True, cause=OmissionCause.PERMISSION, cap_name=None, recover=None)


def test_only_an_unauthorised_or_vanished_thing_can_be_withheld_down_to_its_existence() -> None:
    with pytest.raises(ValidationError, match="cannot produce a presence-free record"):
        OmissionRecord(
            granularity=Granularity.NODE,
            cause=OmissionCause.PRUNED,
            why="scored below the cut",
            connector=ConnectorId.GMAIL,
            presence_free=True,
        )


def test_an_ordinary_record_states_both_an_identity_and_a_count() -> None:
    with pytest.raises(ValidationError, match="names nothing"):
        _omission(what="")
    with pytest.raises(ValidationError, match="states no count"):
        _omission(count=None)


# -- the graph --------------------------------------------------------------------------


def _graph(**kwargs: object) -> QueryGraph:
    fields: dict[str, object] = {
        "query_id": "q1",
        "nodes": (node("mA", TEXT_A), node("mB", TEXT_B)),
        "seeds": (NODE_A, NODE_B),
        "hops_taken": 1,
        "built_at": NOW,
    }
    fields.update(kwargs)
    return QueryGraph(**fields)  # type: ignore[arg-type]


def test_a_graph_holds_one_row_per_item() -> None:
    with pytest.raises(ValidationError, match="appear more than once"):
        _graph(nodes=(node("mA"), node("mA")), seeds=(NODE_A,))


def test_an_edge_to_a_node_nobody_disclosed_is_refused() -> None:
    stated = edge(relation=Relation.SUPERSEDES_STATED, spans=(span(),), stated=stated_check())
    with pytest.raises(ValidationError, match="not a node of this graph"):
        _graph(nodes=(node("mA"),), edges=(stated,), seeds=(NODE_A,))


def test_a_seed_that_is_not_in_the_graph_was_dropped_without_a_record() -> None:
    with pytest.raises(ValidationError, match="seed"):
        _graph(seeds=(NODE_A, "gmail/message/mZ"))


def test_every_span_string_matches_the_content_it_quotes() -> None:
    """GraphRAG's covariate rule, enforced where the quoted node is in scope."""
    wrong = edge(
        relation=Relation.SUPPORTS,
        spans=(span(start=0, end=4, text="XXXX"),),
        confidence=confidence(),
    )
    with pytest.raises(ValidationError, match="not what the span preserved"):
        _graph(edges=(wrong,))


def test_a_span_quoting_a_node_that_was_never_read_is_refused() -> None:
    stub = node("mA", None, depth=Depth.STUB)
    quoting = edge(
        relation=Relation.SUPPORTS,
        spans=(span(start=0, end=4, text="This"),),
        confidence=confidence(),
    )
    with pytest.raises(ValidationError, match="carries no content at depth"):
        _graph(nodes=(stub, node("mB", TEXT_B)), edges=(quoting,))


def test_a_claim_whose_sources_are_absent_is_an_assertion_with_its_evidence_removed() -> None:
    claim = node(
        "mB",
        TEXT_B,
        node_id="derived/c1",
        kind=NodeKind.CLAIM,
        origin=Origin.DERIVED,
        method=method(),
        derived_from=("gmail/message/mZ",),
        spans=(span(node_id=NODE_B, start=0, end=3, text="The"),),
    )
    with pytest.raises(ValidationError, match="which this graph does not hold"):
        _graph(nodes=(node("mB", TEXT_B), claim), seeds=(NODE_B,))


def test_nodes_beyond_the_seed_set_need_a_hop_that_accounts_for_them() -> None:
    with pytest.raises(ValidationError, match="took no hops"):
        _graph(hops_taken=0, seeds=(NODE_A,))


def test_a_graph_is_addressable_for_its_ttl_and_no_longer() -> None:
    graph = _graph()
    assert graph.expires_at == NOW + timedelta(minutes=10)


# -- entities ---------------------------------------------------------------------------


def test_identity_is_a_key_and_never_a_display_name() -> None:
    one = entity()
    assert "display_names" in Entity.model_fields
    assert one.display_names == ()
    assert all(key.kind != "display_name" for key in one.keys)


def test_an_address_key_is_stored_folded() -> None:
    with pytest.raises(ValidationError, match="stored folded"):
        DeterministicKey(connector=ConnectorId.GMAIL, kind="address", value="Alex@Company.com")


def test_an_entity_id_is_derived_from_its_keys_and_not_from_who_built_it() -> None:
    with pytest.raises(ValidationError, match="not the digest of its keys"):
        Entity(
            entity_id="entity/chosen-by-the-builder",
            keys=(
                DeterministicKey(
                    connector=ConnectorId.GMAIL, kind="address", value="alex@company.com"
                ),
            ),
        )


def test_no_confidence_promotes_a_likeness_into_an_identity() -> None:
    left, right = (
        entity(),
        entity(DeterministicKey(connector=ConnectorId.SLACK, kind="user_id", value="U123")),
    )
    with pytest.raises(ValidationError, match="only a source stating the link"):
        EntityCandidate(
            left=left.entity_id,
            right=right.entity_id,
            basis=CandidateBasis.DISPLAY_NAME_MATCH,
            evidence=(reference("mA"),),
            confidence=confidence(0.99),
            status=CandidateStatus.CONFIRMED_BY_SOURCE,
        )


def test_a_candidate_naming_an_entity_the_graph_does_not_hold_is_refused() -> None:
    left = entity()
    stray = EntityCandidate(
        left=left.entity_id,
        right="entity/unknown",
        basis=CandidateBasis.DOMAIN_MATCH,
        evidence=(reference("mA"),),
        confidence=confidence(0.3),
    )
    with pytest.raises(ValidationError, match="not an entity of this graph"):
        _graph(entities=(left,), candidates=(stray,))


# -- the trace --------------------------------------------------------------------------


def test_orivras_trace_wraps_mailweaves_report_rather_than_extending_it() -> None:
    """`RetrievalReport` is a `SealedModel`; a subclass of one is refused at class creation,
    which is R-ARCH-033's rule and the reason this is composition."""
    trace = RetrievalTrace(query_id="q1")
    assert trace.report is None
    assert "report" in RetrievalTrace.model_fields


def test_a_source_that_was_not_ready_reports_no_spend() -> None:
    with pytest.raises(ValidationError, match="cannot have returned evidence"):
        SourceSpend(connector=ConnectorId.DRIVE, state=SourceState.AUTH_REQUIRED, hits=3)


def test_inferred_edges_in_a_trace_name_the_methods_that_made_them() -> None:
    with pytest.raises(ValidationError, match="names no method"):
        GraphSpend(edge_count_by_origin={"inferred": 2})


def test_one_spend_entry_per_connector() -> None:
    ready = SourceSpend(connector=ConnectorId.GMAIL, state=SourceState.READY)
    with pytest.raises(ValidationError, match="appears twice"):
        RetrievalTrace(query_id="q1", per_source=(ready, ready))


def test_a_trace_names_the_policy_that_redacted_it() -> None:
    trace = RetrievalTrace(
        query_id="q1",
        per_source=(SourceSpend(connector=ConnectorId.GMAIL, state=SourceState.READY, hits=4),),
        entities=EntitySpend(confirmed=1),
    )
    assert trace.redaction_policy.startswith("orivra/trace-redaction@")


def test_a_change_marker_is_recorded_as_a_digest_and_never_as_the_marker() -> None:
    """A Drive `startPageToken` is a bearer value for a change feed; one rule for all three
    sources is the rule that does not have to be remembered per connector."""
    digest = hashlib.sha256(b"start-page-token").hexdigest()[:12]
    spend = SourceSpend(
        connector=ConnectorId.DRIVE, state=SourceState.READY, change_marker_used=digest
    )
    assert spend.change_marker_used is not None
    assert len(spend.change_marker_used) <= 64


def test_the_worked_example_builds_end_to_end() -> None:
    """One graph carrying the plan's own worked example, so the negative tests above are
    known to be breaking something that otherwise holds."""
    stated = edge(relation=Relation.SUPERSEDES_STATED, spans=(span(),), stated=stated_check())
    graph = _graph(edges=(stated,))
    assert graph.edge_count_by_origin == {"observed": 1}
    assert stated.asserted_by == NODE_A
    assert stated.assertion.value == "source_stated"
    assert graph.nodes[0].content is not None
    assert graph.nodes[0].content[CUE_START:CUE_END] == CUE
    assert datetime.now(UTC) > NOW - timedelta(days=1)


# -- the correction pass: two validators that did not do what they said ---------------------


def test_a_handle_naming_a_map_id_with_no_signature_is_refused() -> None:
    """R-M1-011. The docstring stated two rules and the condition implemented neither: it
    fired only when a `map_id` key was present *and empty*, so an unsigned call passed."""
    with pytest.raises(ValidationError, match="signature no argument uses"):
        ExpansionHandle(
            tool=OrivraToolName.THREAD_MAP,
            args={"thread_id": "t1"},
            reduces=Dimension.BREADTH,
            handle="SIGNED-CREDENTIAL",
        )


def test_a_signature_no_argument_uses_is_refused() -> None:
    """The second rule, which had no code at all: a credential travelling for no reason is
    one more place it can be read from."""
    with pytest.raises(ValidationError, match="signature no argument uses"):
        ExpansionHandle(
            tool=OrivraToolName.GET_MESSAGES,
            args={"message_ids": ["m1"]},
            reduces=Dimension.DEPTH,
            handle="SIGNED-CREDENTIAL",
        )


def test_a_map_id_and_its_signature_must_be_the_same_value() -> None:
    with pytest.raises(ValidationError, match="different values"):
        ExpansionHandle(
            tool=OrivraToolName.THREAD_MAP,
            args={"map_id": "one"},
            reduces=Dimension.BREADTH,
            handle="another",
        )


def test_an_empty_map_id_argument_is_refused() -> None:
    with pytest.raises(ValidationError, match="empty map_id"):
        ExpansionHandle(
            tool=OrivraToolName.THREAD_MAP, args={"map_id": ""}, reduces=Dimension.BREADTH
        )


def test_a_signed_handle_its_argument_uses_is_accepted() -> None:
    """The rule must not refuse the shape it exists to describe."""
    handle = ExpansionHandle(
        tool=OrivraToolName.THREAD_MAP,
        args={"map_id": "SIGNED"},
        reduces=Dimension.BREADTH,
        handle="SIGNED",
    )
    assert handle.handle == handle.args["map_id"]


def test_a_stated_assertion_refusal_does_not_quote_the_message_body() -> None:
    """R-M1-021. `referring_text` is a verbatim run of message body, up to 400 characters,
    and the refusal echoed it into a validation report (R-SEC-043's rule: the field, never
    the value)."""
    quoted = "the confidential Q3 pricing draft ada@acme.example"
    with pytest.raises(ValidationError) as refusal:
        stated_check(
            target=TargetResolution(resolved_to=NODE_B, considered=(NODE_B,), referring_text=quoted)
        )
    assert quoted not in str(refusal.value)
    assert "not echoed here" in str(refusal.value)


def test_a_source_that_answered_incompletely_has_its_own_cause() -> None:
    """R-M1-009. Reporting it as `freshness_unverifiable` sends a caller to re-verify
    something that was never fetched."""
    assert OmissionCause.PARTIAL_SOURCE_FAILURE.value == "partial_source_failure"
    assert not OmissionCause.PARTIAL_SOURCE_FAILURE.may_have_no_handle


# -- R-M1-016: a conjunction of per-source requirements, and a live gate --------------------
#
# An edge used to carry one `PermissionContext`. `PermissionContext.covers` is false whenever
# the connectors differ, so a Gmail-to-Drive edge was **unconstructible** - the schema could
# not express the thing v1 exists to do. The owner settled it: one `PermissionRequirement` per
# (connector, principal), all of which must hold; never one synthetic context, never a union;
# and a permission hash may take part in cache identity and may never authorise serving.


class _Probe:
    """A live check that answers from two explicit sets, so a test says what it means."""

    def __init__(
        self,
        *,
        authorised: frozenset[str] = frozenset(),
        reachable: frozenset[str] = frozenset(),
        all_authorised: bool = False,
        all_reachable: bool = False,
    ) -> None:
        self.authorised = authorised
        self.reachable = reachable
        self.all_authorised = all_authorised
        self.all_reachable = all_reachable
        self.asked: list[str] = []

    def authorizes(self, requirement: PermissionRequirement) -> bool:
        self.asked.append(f"auth:{requirement.connector.value}")
        return self.all_authorised or requirement.connector.value in self.authorised

    def can_access(self, reference: SourceReference) -> bool:
        self.asked.append(f"reach:{reference.node_id}")
        return self.all_reachable or reference.node_id in self.reachable


def _cross_source_edge(other: SourceReference) -> EvidenceEdge:
    """A metadata edge from a Gmail message to something in another source."""
    support = (reference("mA"), other)
    return edge(
        edge_id="x1",
        source=NODE_A,
        target=other.node_id,
        relation=Relation.ATTACHMENT_OF,
        support=support,
        requires=requirements_of(support),
        method=method("metadata/attachment_of"),
    )


def test_a_gmail_to_drive_edge_is_constructible() -> None:
    """The case the first design could not represent at all."""
    drive = drive_reference("f1")
    built = _cross_source_edge(drive)
    assert built.connectors == (ConnectorId.DRIVE, ConnectorId.GMAIL)
    assert len(built.requires) == 2
    by_connector = {one.connector: one for one in built.requires}
    assert by_connector[ConnectorId.GMAIL].applies_to == (NODE_A,)
    assert by_connector[ConnectorId.DRIVE].applies_to == (drive.node_id,)


def test_a_gmail_to_slack_edge_is_constructible_and_carries_slacks_capability() -> None:
    slack = slack_reference("C1:1700000000.0001")
    built = _cross_source_edge(slack)
    assert built.connectors == (ConnectorId.GMAIL, ConnectorId.SLACK)
    slack_requirement = next(one for one in built.requires if one.connector is ConnectorId.SLACK)
    assert slack_requirement.scope_set == ("search:read", "users:read.email")
    assert slack_requirement.capability == ("tier=enterprise", "token=user")


def test_the_conjunction_is_not_a_union_and_not_one_synthetic_context() -> None:
    """A union asks "does the caller hold any of these?", which lets Drive access stand in
    for Slack access. The conjunction asks "every one", which is the only safe question."""
    built = _cross_source_edge(drive_reference("f1"))
    scopes = {scope for one in built.requires for scope in one.scope_set}
    assert len(built.requires) == 2, "the two sources were collapsed into one requirement"
    for requirement in built.requires:
        assert set(requirement.scope_set) < scopes, (
            "a requirement carries every source's scopes; that is a synthetic context"
        )


def test_an_edge_is_released_only_when_every_requirement_and_every_reference_passes() -> None:
    built = _cross_source_edge(drive_reference("f1"))
    granted = release(
        built.requires, built.support, _Probe(all_authorised=True, all_reachable=True)
    )
    assert granted.granted is True


def test_losing_access_to_one_endpoint_refuses_the_whole_edge() -> None:
    """A grant can be unchanged while a file is unshared, so the gate asks both questions."""
    drive = drive_reference("f1")
    built = _cross_source_edge(drive)
    probe = _Probe(all_authorised=True, reachable=frozenset({NODE_A}))
    refused = release(built.requires, built.support, probe)
    assert refused.granted is False
    assert refused.refused_reference is not None
    assert refused.refused_reference.node_id == drive.node_id


def test_losing_one_sources_authorisation_refuses_the_whole_edge() -> None:
    built = _cross_source_edge(slack_reference("C1:1700000000.0001"))
    refused = release(
        built.requires, built.support, _Probe(authorised=frozenset({"gmail"}), all_reachable=True)
    )
    assert refused.granted is False
    assert refused.refused_by is not None
    assert refused.refused_by.connector is ConnectorId.SLACK


def test_a_conjunction_over_an_empty_set_is_refused_rather_than_vacuously_true() -> None:
    """The one arithmetic this gate must not inherit."""
    with pytest.raises(ValueError, match="released to everyone"):
        release((), (reference("mA"),), _Probe(all_authorised=True, all_reachable=True))


def test_a_refused_edge_produces_a_record_that_reveals_nothing_about_it() -> None:
    """Naming the requirement names the source; naming the reference names the document;
    naming the relation is the disclosure the edge itself would have made."""
    drive = drive_reference("f1")
    built = _cross_source_edge(drive)
    record = permission_safe_omission(connector=ConnectorId.GMAIL)
    rendered = record.model_dump_json()
    assert record.presence_free is True
    assert record.what == "" and record.count is None and record.recover is None
    for leak in (
        drive.node_id,
        drive.native_id,
        NODE_A,
        built.edge_id,
        built.relation.value,
        "drive",
        "supersedes",
    ):
        assert leak not in rendered, leak
    assert record.cause is OmissionCause.PERMISSION


def test_the_omission_names_a_connector_the_caller_can_already_see() -> None:
    """A record saying `drive` to a caller with no Drive access discloses that a Drive
    document exists, which is exactly the presence this form withholds."""
    record = permission_safe_omission(connector=ConnectorId.GMAIL)
    assert record.connector is ConnectorId.GMAIL


def test_a_permission_hash_is_cache_identity_and_never_authority() -> None:
    """Two edges over the same grants share a cache identity; neither is thereby servable."""
    first = _cross_source_edge(drive_reference("f1"))
    second = _cross_source_edge(drive_reference("f1"))
    assert first.cache_identity == second.cache_identity
    refused = release(
        first.requires, first.support, _Probe(all_authorised=False, all_reachable=True)
    )
    assert refused.granted is False, "a matching cache identity authorised a refused caller"


def test_a_requirement_is_satisfied_only_by_a_grant_on_the_same_principal() -> None:
    drive = drive_reference("f1")
    requirement = next(
        one for one in requirements_of((drive,)) if one.connector is ConnectorId.DRIVE
    )
    assert requirement.satisfied_by(drive.permission)
    other = drive_reference("f1", principal="someone-else").permission
    assert not requirement.satisfied_by(other)
    assert not requirement.satisfied_by(permission())
