"""Turn one served call into one `PersonalTrace`. The only place the two shapes meet.

**Every field is read off something the response already states, or off a counter the run
recorded.** Nothing here recomputes a fact the envelope carries, for the reason
`EnvelopeBuilder.build` gives about `hit_count_per_rung`: a second derivation of one fact is
two claims that can disagree, and the one that disagrees is always the one nobody is looking
at. The trace is a *projection* of the response plus the things the response is not allowed
to carry - `pool_ids[]` and the query's own shape.

**And the projection is where redaction happens, because it is the only place it can.** The
envelope carries fenced mail text by design; the trace carries none. So every field that
would have been text becomes a count, a closed vocabulary value, or a salted digest, here,
once - rather than at each of the thirty places a field could be copied from.
"""

from __future__ import annotations

from mailweave.envelope.response import Envelope
from mailweave.freshness.recency import RecencyRun, RecencyState
from mailweave.retrieval.ranking import RankingRun
from mailweave.retrieval.semantic import SemanticRun
from mailweave.trace.redaction import Redacted, RedactionPolicy, query_features
from mailweave.trace.schema import (
    CostTrace,
    DisclosureTrace,
    Disposition,
    ErrorTrace,
    FreshnessTrace,
    PerMessageTrace,
    PersonalTrace,
    QueryFeatures,
    RetrievalOutcome,
    Routing,
    ScanScopeTrace,
    SemanticTrace,
    ShortlistTrace,
    WithheldTrace,
)


def trace_of(
    envelope: Envelope,
    *,
    trace_id: str,
    tool: str,
    query: str,
    semantic: SemanticRun | None = None,
    ranking: RankingRun | None = None,
    recency: RecencyRun | None = None,
    latency_ms: int = 0,
    policy: RedactionPolicy = RedactionPolicy.PERSONAL,
    diagnose_finding: str | None = None,
) -> PersonalTrace:
    """Project one served response into schema v2."""
    report = envelope.retrieval_report
    exact = None
    answer_type = None
    return PersonalTrace(
        trace_id=trace_id,
        redaction=policy,
        diagnose_finding=diagnose_finding,
        tool=tool,
        query_features=QueryFeatures(**query_features(query)),
        routing=Routing(
            initial_route=report.rungs[0] if report.rungs else None,
            rungs_executed=report.rungs,
            # Constraint **names**, which the parser assigns from a fixed vocabulary - not
            # the tokens the user wrote. `asked_for.parsed.dropped` carries the text; this
            # reads the name beside it.
            constraints_dropped=tuple(
                sorted({dropped.constraint for dropped in envelope.asked_for.dropped})
            ),
            fallback_triggered=bool(report.not_tried),
            escalation_offers_returned=len(envelope.affordances),
        ),
        retrieval_outcome=RetrievalOutcome(
            rounds=len(report.rungs),
            http_requests=report.counters.http_requests,
            api_calls_by_method={"total": report.counters.api_calls},
            quota_units=report.counters.quota_units,
            hit_count_per_rung={
                rung.value: count
                for rung, count in zip(report.rungs, report.hit_count_per_rung, strict=True)
            },
            scan_scope=tuple(
                ScanScopeTrace(
                    rung=entry.rung,
                    pages_fetched=entry.pages_fetched,
                    ids_returned=entry.ids_returned,
                    more_pages=entry.more_pages,
                    # The executed `q` composes the user's own words; only its digest travels.
                    query_hash=Redacted(entry.q).digest,
                )
                for entry in report.scan_scope
            ),
            term_coverage_final=envelope.asked_for.term_coverage,
            exact_signal_match=exact,
            answer_type_presence=answer_type,
            budget_caps_hit=report.budget_caps_hit,
            sufficiency_verdict=report.sufficiency.value,
            false_notfound_guard=bool(report.blocking_not_tried),
        ),
        disposition=Disposition(
            hit_ids_count=_withheld_count(envelope) + _disclosed(envelope),
            disclosed_count=_disclosed(envelope),
            withheld=tuple(
                WithheldTrace(id=record.id, cap=record.cap.value) for record in envelope.withheld
            ),
        ),
        semantic=_semantic(semantic, ranking),
        disclosure=DisclosureTrace(
            levels_traversed=len(report.rungs),
            disclosed_tokens_est=envelope.ceiling.applied if envelope.ceiling else 0,
            ceiling_applied=envelope.ceiling.applied if envelope.ceiling else None,
            per_message=tuple(
                PerMessageTrace(
                    id=row.id,
                    role=row.role.value,
                    # The reason's **kind**, never `render()`: the rendered sentence composes
                    # the executed `q`, which is the user's own words.
                    reason_kind=row.reason.kind.value if row.reason is not None else "none",
                    depth=row.depth.value,
                    tokens=0,
                )
                for source in envelope.sources
                for row in source.messages
            ),
        ),
        freshness=_freshness(recency),
        errors=tuple(ErrorTrace(code=entry.code.value) for entry in envelope.errors),
        cost=CostTrace(latency_ms_total=latency_ms),
    )


def _disclosed(envelope: Envelope) -> int:
    return sum(len(source.messages) for source in envelope.sources)


def _withheld_count(envelope: Envelope) -> int:
    """How many observed ids this response did not disclose, read off the omission summary.

    `omission` is `None` on a response with nothing to omit, which is a different fact from
    zero and is why it is not defaulted: a summary that always existed would be a block
    claiming the response computed an omission account it never had to.
    """
    return 0 if envelope.omission is None else envelope.omission.withheld_messages


def _semantic(semantic: SemanticRun | None, ranking: RankingRun | None) -> SemanticTrace | None:
    """D.10's `semantic` block, including the `pool_ids[]` the response may never carry."""
    if semantic is None and ranking is None:
        return None
    build = None if semantic is None else semantic.build
    result = None if semantic is None else semantic.result
    rerank = None if ranking is None else ranking.rerank
    return SemanticTrace(
        model_id=(semantic.model_id if semantic is not None else None)
        or (rerank.model_id if rerank is not None else None),
        model_revision=(semantic.model_revision if semantic is not None else None)
        or (rerank.model_revision if rerank is not None else None),
        embed_texts=0 if build is None else len(build.rows),
        rerank_pairs=0 if rerank is None else rerank.pairs,
        # The scope rule names the query's participant operators by value, so the trace holds
        # its digest rather than the sentence (SN §4.3: no raw query strings, and an operator
        # value is a string the user wrote).
        pool_scope_hash=(
            None
            if semantic is None or semantic.plan is None
            else Redacted(semantic.plan.scope_rule).digest
        ),
        pool_threads=0 if build is None else build.thread_count,
        pool_messages=0 if build is None else build.message_count,
        pool_ids=() if build is None else tuple(row.message_id for row in build.rows),
        shortlist=(
            None
            if result is None
            else ShortlistTrace(rule=result.rule, k=result.k, size=result.size)
        ),
        cold_load_ms=None if semantic is None else semantic.cold_load_ms,
        semantic_ms=(0 if semantic is None else semantic.semantic_ms)
        + (0 if ranking is None else ranking.ms),
    )


def _freshness(recency: RecencyRun | None) -> FreshnessTrace | None:
    if recency is None:
        return None
    started = recency.started_from
    return FreshnessTrace(
        history_id=recency.latest_history_id or (started.history_id if started else None),
        watermark_source="persisted" if started is not None else "none",
        reconciled=recency.ran,
        rebaselined=recency.state is RecencyState.REBASELINED,
    )


__all__ = ["trace_of"]
