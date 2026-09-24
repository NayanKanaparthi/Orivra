"""L5 executed: the gate, the pool, the shortlist, and the model loaded once per process.

Four properties this file exists to execute rather than assert in a docstring.

  * **The prohibitions are prohibitions.** SEM-04 and RANK-01 forbid a semantic rung after
    an identity resolution, after an `exact_signal_match`, and on the sender/date family.
    A prohibition that a caller can lift with `force_rungs` is not one, and the gate is
    evaluated prohibition-first so that a forbidden rung is recorded `not_applicable` rather
    than `stopped_on_evidence` - the second of which carries a call that would run it.
  * **The pool is inside `H` and outside disclosure.** Every id the pool observes is
    admitted by the ledger, and the ones the shortlist did not select come back as
    `withheld` records naming a pool cap - never as stub rows, and never as silence.
  * **`k` is a constant.** The shortlist is `top-k by cosine`, `k = max_rerank_pairs`, and
    no score threshold appears anywhere in the selection path.
  * **The server process loads its models once.** Not the registry in isolation - the
    registry is memoised and a unit test of it proves only that the memo works - but the
    shipped `MailweaveService` answering two `mailweave_search` calls, with a factory that
    counts how many times it was asked to build a backend.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest

from mailweave.envelope.reasons import ReasonKind, RungId
from mailweave.envelope.vocab import NotTriedWhy, WithheldCap
from mailweave.gmail import BackoffPolicy, CallMeter, GmailClient, StaticToken
from mailweave.handles.cache import ThreadMapCache
from mailweave.handles.keys import HandleKey
from mailweave.net.egress import build_client
from mailweave.retrieval.semantic import SemanticState, semantic_gate
from mailweave.semantic.interface import BackendRegistry, SemanticBackend, Vector
from mailweave.semantic.profile import (
    Basis,
    PoolTextMode,
    Provenance,
    SemanticProfile,
)
from mailweave.semantic.shortlist import SHORTLIST_RULE, Scored, cosine, shortlist
from mailweave.surface.arguments import parse_search
from mailweave.surface.service import MailweaveService
from tests.fixtures.mailbox import Msg, SyntheticMailbox, epoch_ms

TOKEN = "ya29.SECRET-ACCESS-TOKEN-NEVER-IN-A-SEMANTIC-FIXTURE"
ACCOUNT = "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f0"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


# --- a mailbox whose answer is not lexically findable ----------------------------------------


def paraphrase_mailbox() -> SyntheticMailbox:
    """A mailbox in which the query's words appear nowhere and the answer does.

    This is D.5's own worked example, made executable: the query asks about postponing the
    launch and the evidence says "we'll push go-live into Q4". Every lexical rung returns
    nothing, which is exactly the `hit_count == 0` state rule 4 escalates on.
    """
    threads: list[Msg] = []
    for index in range(20):
        threads.append(
            Msg(
                id=f"p-{index}",
                thread_id=f"t-{index}",
                sender="ana@team.example",
                subject=f"Planning note {index}",
                body="We'll push go-live into Q4 and tell the vendor next week.",
                internal_date_ms=epoch_ms(2026, 8, 1) + index * 86_400_000,
                to=("bo@team.example",),
            )
        )
    return SyntheticMailbox(messages=tuple(threads), now_ms=epoch_ms(2026, 9, 3))


class CountingBackend:
    """A deterministic stand-in for stage A and stage B. No weights, no network.

    The vectors are a two-dimensional bag-of-words over one word each, which is enough to
    make the cosine ordering something a test can predict and nothing like a claim about
    retrieval quality - this file measures plumbing, and H1/H2/H3 measure quality.
    """

    model_id = "test/counting"
    model_revision = "0000000000000000000000000000000000000000"

    def __init__(self) -> None:
        self.embed_calls = 0
        self.rerank_calls = 0

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        self.embed_calls += 1
        return [(float("q4" in text.lower()), float("vendor" in text.lower())) for text in texts]

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        self.rerank_calls += 1
        return [float(len(candidate)) for candidate in candidates]


def counting_registry() -> tuple[BackendRegistry, list[int]]:
    """A registry whose factory counts how many times it was asked to build."""
    built: list[int] = []
    registry = BackendRegistry()

    def factory() -> SemanticBackend:
        built.append(1)
        return CountingBackend()

    registry.register("test/counting", factory, default=True)
    return registry, built


def measured_profile(**overrides: object) -> SemanticProfile:
    base = {
        "pool_text_mode": PoolTextMode.SNIPPET,
        "pool_text_provenance": Provenance(
            basis=Basis.MEASURED, source="PF-2-metadata-headers", detail="fixture"
        ),
        "max_pool_threads": 25,
        "max_pool_messages": 300,
        "max_rerank_pairs": 25,
        "max_semantic_ms": 6_000,
        "bounds_provenance": Provenance(
            basis=Basis.MEASURED, source="PF-4-model-latency", detail="fixture"
        ),
    }
    base.update(overrides)
    return SemanticProfile(**base)  # type: ignore[arg-type]


def make_service(
    box: SyntheticMailbox,
    *,
    registry: BackendRegistry | None = None,
    profile: SemanticProfile | None = None,
    now: Callable[[], datetime] | None = None,
) -> MailweaveService:
    def open_client() -> GmailClient:
        return GmailClient(
            token=StaticToken(TOKEN),
            http=build_client(inner=box.transport()),
            meter=CallMeter(),
            policy=BackoffPolicy(),
            sleeper=lambda _seconds: None,
            jitterer=lambda: 0.5,
        )

    kit = counting_registry()[0] if registry is None else registry
    return MailweaveService(
        open_client=open_client,
        account_hash=ACCOUNT,
        handle_key=HandleKey(material=b"k" * 32, epoch=0),
        cache=ThreadMapCache(),
        now=now if now is not None else (lambda: datetime.now(UTC)),
        semantic_profile=profile if profile is not None else measured_profile(),
        registry=kit,
    )


# --- the lifecycle question the owner asked -------------------------------------------------


def test_the_server_process_reuses_one_backend_across_queries() -> None:
    """Two searches through the shipped service build the backend **once**.

    The defect this stands against is not hypothetical: the first `BackendRegistry` built a
    backend on every `acquire`, and the owner's smoke run priced that at 36,543 ms against a
    6,000 ms budget - a semantic rung that could never complete inside its own cap, on any
    machine, for any query. A unit test of the registry's memo would not have caught it
    reaching production, because the question is whether the *service* holds one registry
    across calls, and the service opens a fresh `GmailClient`, a fresh ledger and a fresh
    accountant per query. So this drives two real `mailweave_search` calls and counts
    factory invocations.
    """
    box = paraphrase_mailbox()
    registry, built = counting_registry()
    service = make_service(box, registry=registry)

    first = service.search(parse_search({"query": "postpone the launch"}))
    second = service.search(parse_search({"query": "postpone the launch again"}))

    assert built == [1], "the backend was built more than once across two queries"
    assert RungId.L5 in first.retrieval_report.rungs
    assert RungId.L5 in second.retrieval_report.rungs


def test_warming_the_backend_at_startup_is_what_keeps_a_query_off_the_cold_path() -> None:
    """`warm_semantic_backend` loads before any query, and reports failure without raising.

    PF-4 measured the cold load at 5,410 ms against a 6,000 ms `max_semantic_ms`. A first
    query that paid it inside its own budget would have 590 ms left for work measured at 250
    ms; a machine a fifth slower would have none. So `mailweave serve` pays it at startup,
    and a machine with no weights is still a machine the server runs on.
    """
    box = paraphrase_mailbox()
    registry, built = counting_registry()
    service = make_service(box, registry=registry)

    assert service.warm_semantic_backend() is True
    assert built == [1]
    service.search(parse_search({"query": "postpone the launch"}))
    assert built == [1], "a warmed process still paid the load inside a query"


def test_a_machine_with_no_weights_serves_and_declines_the_rung_in_band() -> None:
    """D.5's deterministic fallback: `not_tried`, not a failed response and not a silence."""
    box = paraphrase_mailbox()
    registry = BackendRegistry()
    service = make_service(box, registry=registry)

    assert service.warm_semantic_backend() is False
    envelope = service.search(parse_search({"query": "postpone the launch"}))
    entries = {entry.rung: entry for entry in envelope.retrieval_report.not_tried}
    assert entries[RungId.L5.value].why is NotTriedWhy.ERROR
    assert entries[RungId.L5.value].affordance is not None
    assert envelope.retrieval_report.pool is None


# --- the gate ---------------------------------------------------------------------------------


def test_an_identity_resolution_forbids_the_semantic_rung_and_force_rungs_cannot_lift_it() -> None:
    """D.3 rule 1 halts the ladder; SEM-04 and RANK-01 forbid what comes after it."""
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="x-1",
                thread_id="t-x",
                sender="ana@team.example",
                subject="Contract",
                body="signed",
                internal_date_ms=epoch_ms(2026, 8, 1),
                rfc822_message_id="<only-one@mail.invalid>",
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    registry, built = counting_registry()
    service = make_service(box, registry=registry)
    envelope = service.search(
        parse_search({"query": "rfc822msgid:<only-one@mail.invalid>", "force_rungs": ["semantic"]})
    )
    entries = {entry.rung: entry for entry in envelope.retrieval_report.not_tried}
    assert entries[RungId.L5.value].why is NotTriedWhy.NOT_APPLICABLE
    assert entries[RungId.L5.value].affordance is None, (
        "a forbidden rung carried the call that would run it"
    )
    assert built == [], "a forbidden rung loaded a model"


def test_the_sender_and_date_family_never_reaches_the_semantic_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEM-04: Gmail answers `from:`/`after:` exactly, and a cosine over it ranks nothing."""
    from mailweave.query.analysis import analyse
    from mailweave.retrieval.ladder import LadderRun
    from mailweave.retrieval.signals import AnswerTypePresence, ExactSignal

    parsed = analyse("from:ana@team.example after:2026/01/01", now=NOW)
    run = LadderRun(
        parsed=parsed,
        executions=(),
        exact_signal=ExactSignal(
            fired=False, branch=None, phrase_tokens=0, hit_count=0, verified_locally=False
        ),
        answer_type=AnswerTypePresence(answer_type=None, present=None, examined=0),
        stop_rule=None,
        stopped_after=None,
    )
    gate = semantic_gate(run)
    assert gate.fires is False
    assert gate.state is SemanticState.NOT_APPLICABLE
    assert "SEM-04" in gate.why


def test_evidence_found_declines_the_rung_with_the_call_that_would_run_it() -> None:
    """`stopped_on_evidence` is not `not_applicable`: it has a remedy and says so."""
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="f-1",
                thread_id="t-f",
                sender="ana@team.example",
                subject="Cutover",
                body="The cutover is on Tuesday.",
                internal_date_ms=epoch_ms(2026, 8, 1),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    registry, built = counting_registry()
    service = make_service(box, registry=registry)
    envelope = service.search(parse_search({"query": "cutover"}))
    entries = {entry.rung: entry for entry in envelope.retrieval_report.not_tried}
    entry = entries[RungId.L5.value]
    assert entry.why is NotTriedWhy.STOPPED_ON_EVIDENCE
    assert entry.affordance is not None
    assert entry.affordance.args["force_rungs"] == ["L5"]
    assert built == [], "a declined rung loaded a model"


# --- the pool and the shortlist -----------------------------------------------------------


def test_the_pool_declares_its_scope_and_size_and_creates_no_rows() -> None:
    """A.7a: pool membership is disclosed by rule and count, never as sources.

    **The claim is about *which* threads became sources, not how many rows came out.** The
    first version of this test compared the disclosed row count against the pool size, and
    the replant that removes the split (R196) walked straight through it: with twenty pool
    threads, `max_hit_threads = 12` and one message per thread, "every pool thread became a
    source" still produces twelve rows against a pool of twenty, and `12 < 20` is true. What
    a width cap happens to leave over is not evidence about what the pool may disclose.

    So the shortlist is made narrower than the pool - `k = 3` against twenty candidates - and
    the two halves of D.5's rule are asserted directly: at most `k` threads become sources,
    and the pool candidates the shortlist passed over come back as withheld records naming
    the shortlist's own cap. Under R196 the first fails at twelve sources against three.
    """
    box = paraphrase_mailbox()
    service = make_service(box, profile=measured_profile(max_rerank_pairs=3))
    envelope = service.search(parse_search({"query": "postpone the launch"}))
    pool = envelope.retrieval_report.pool
    block = envelope.retrieval_report.shortlist
    assert pool is not None and block is not None
    assert pool.thread_count > block.k, "the pool is not wider than the shortlist here"
    assert "max_pool_threads=25" in pool.scope_rule
    assert "subject+participants+snippet" in pool.scope_rule
    assert pool.note == "pool membership creates no source and no stub rows (A.7a)"

    assert envelope.sources, "the semantic rung disclosed nothing, so this proves nothing"
    assert len(envelope.sources) <= block.k, (
        "more threads became sources than the shortlist selected: the pool created sources"
    )
    caps = {record.cap for record in envelope.withheld} | {
        group.cap for group in envelope.withheld_groups
    }
    assert WithheldCap.MAX_RERANK_PAIRS in caps, (
        "the pool candidates the shortlist passed over were dropped rather than withheld"
    )


def test_the_shortlist_is_k_by_rule_and_k_is_max_rerank_pairs() -> None:
    """§H-5 / ADV-109: `k` is pre-registered, not a threshold an implementer picks."""
    box = paraphrase_mailbox()
    service = make_service(box, profile=measured_profile(max_rerank_pairs=3))
    envelope = service.search(parse_search({"query": "postpone the launch"}))
    block = envelope.retrieval_report.shortlist
    pool = envelope.retrieval_report.pool
    assert block is not None and pool is not None
    assert block.k == 3
    assert block.rule == SHORTLIST_RULE
    # **`size == min(k, pool)` is the property; `size <= k` is not.** A score threshold
    # satisfies `size <= k` for every k, which is how R199 - the replant that swaps top-k for
    # `cosine >= 0.4` - passed the first version of this test: this fixture's query embeds to
    # the origin, every cosine is 0.0, and a threshold selected nothing while `0 <= 3` held.
    # Top-k selects k whatever the scores are, which is exactly what makes it not a dial.
    assert block.size == min(block.k, pool.message_count)


def test_a_pool_thread_the_cap_excluded_is_withheld_under_the_pool_cap() -> None:
    """A.7a's row: a thread the pool cap kept out is a `withheld` record, not a drop."""
    box = paraphrase_mailbox()
    service = make_service(box, profile=measured_profile(max_pool_threads=1))
    envelope = service.search(parse_search({"query": "postpone the launch"}))
    caps = {record.cap for record in envelope.withheld} | {
        group.cap for group in envelope.withheld_groups
    }
    assert WithheldCap.MAX_POOL_THREADS in caps


def test_the_caller_can_narrow_the_pool_and_cannot_widen_it() -> None:
    """Lowering only, and a narrowed bound stops citing the measurement it left behind."""
    profile = measured_profile()
    assert profile.narrowed(max_threads=5, max_messages=None).max_pool_threads == 5
    assert profile.narrowed(max_threads=999, max_messages=None).max_pool_threads == 25
    narrowed = profile.narrowed(max_threads=5, max_messages=None)
    assert narrowed.bounds_provenance.basis is Basis.ASSUMED
    assert "max_pool_threads 25->5" in narrowed.bounds_provenance.detail
    assert profile.narrowed(max_threads=None, max_messages=None) is profile


def test_the_shortlist_orders_the_threads_the_mapper_gets_first() -> None:
    """Without this the pool's whole output is cut alphabetically by `max_hit_threads`."""
    from mailweave.retrieval.assemble import _semantic_order
    from mailweave.retrieval.semantic import SemanticRun

    result = shortlist(
        (1.0, 0.0),
        [
            ("m-z", "t-z", (1.0, 0.0), "b"),
            ("m-a", "t-a", (0.0, 1.0), "b"),
            ("m-z2", "t-z", (0.9, 0.1), "b"),
        ],
        k=3,
    )
    run = SemanticRun(state=SemanticState.RAN, why="fixture", result=result)
    assert _semantic_order(run) == ("t-z", "t-a"), "a thread took the rank of its worst row"


def test_ties_in_the_cosine_are_broken_by_message_id_so_h_is_reproducible() -> None:
    """A non-total order would make `H` itself depend on dictionary iteration order."""
    rows = [("m-b", "t", (1.0, 0.0), "x"), ("m-a", "t", (1.0, 0.0), "x")]
    assert [row.message_id for row in shortlist((1.0, 0.0), rows, k=2).selected] == ["m-a", "m-b"]


def test_a_zero_magnitude_vector_scores_zero_rather_than_raising() -> None:
    """A row that embedded to the origin has no angle to anything; that is not an error."""
    assert cosine((0.0, 0.0), (1.0, 0.0)) == 0.0
    with pytest.raises(ValueError, match="different width"):
        cosine((1.0,), (1.0, 0.0))


def test_a_shortlist_of_k_zero_is_refused_rather_than_selecting_nothing() -> None:
    with pytest.raises(ValueError, match="max_rerank_pairs"):
        shortlist((1.0,), [("m", "t", (1.0,), "x")], k=0)


# --- L6, through the shipped service ---------------------------------------------------------


def test_a_row_gmail_q_selected_carries_no_numeric_score() -> None:
    """D.7: a `q` match is an exact statement, and a similarity number beside it invites a
    reader to compare the two on one scale - the fabricated comparability RANK-03 refuses.

    **The fixture has to reach a row that both was `q`-selected and *does* have a rerank
    score**, or the test passes for the wrong reason. R203 - the replant that removes the
    guard - walked through the first version of this test because that mailbox never ran
    L5 at all: with no shortlist there is no score to suppress, and `None` came back from
    the absence rather than from the rule. So both rungs are forced here: the query matches
    lexically, the pool's step (a) picks up the threads L0-L3 touched, the shortlist selects
    their rows, and the cross-encoder scores them. Every one of those rows is `q`-selected
    and carries a live rerank score, and every one of them must still report `score: null`.
    """
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="q-1",
                thread_id="t-q",
                sender="ana@team.example",
                subject="Cutover",
                body="The cutover is on Tuesday.",
                internal_date_ms=epoch_ms(2026, 8, 1),
            ),
            Msg(
                id="q-2",
                thread_id="t-q2",
                sender="bo@team.example",
                subject="Cutover again",
                body="The cutover moved.",
                internal_date_ms=epoch_ms(2026, 8, 2),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    registry, _built = counting_registry()
    service = make_service(box, registry=registry)
    envelope = service.search(
        parse_search({"query": "cutover", "force_rungs": ["semantic", "rerank"]})
    )
    matched = [
        row
        for source in envelope.sources
        for row in source.messages
        if row.reason is not None and row.reason.kind is ReasonKind.GMAIL_QUERY_MATCH
    ]
    assert matched, "no q-selected row in this response, so this proves nothing"
    assert envelope.retrieval_report.shortlist is not None, "L5 did not run: nothing to suppress"
    shortlisted = {row.message_id for row in _shortlisted_of(service, box)}
    assert {row.id for row in matched} & shortlisted, (
        "no q-selected row was also shortlisted, so a suppressed score would be indistinguishable "
        "from an absent one"
    )
    assert all(row.score is None for row in matched)


def _shortlisted_of(service: MailweaveService, box: SyntheticMailbox) -> tuple[Scored, ...]:
    """Re-run L5 alone against the same mailbox to see which rows the shortlist selected.

    A second run rather than a hook into the first: the point is that the *response* refuses
    the score, and reaching inside the run that produced it to prove the score existed would
    be asserting against the thing under test.
    """
    from mailweave.envelope.disposition import DispositionLedger
    from mailweave.retrieval.ladder import LadderRunner
    from mailweave.retrieval.semantic import SemanticRunner

    client = service.open_client()
    ledger = DispositionLedger()
    run = LadderRunner(client, ledger).run("cutover", now=service.now())
    semantic = SemanticRunner(
        client, ledger, profile=service.semantic_profile, registry=service.registry
    ).run(run, now=service.now(), forced=True)
    assert semantic.result is not None
    return semantic.result.selected


def test_l6_reports_itself_as_run_when_only_its_mechanical_tier_ran() -> None:
    """D.7's first tier *is* L6. A response that ranked and said it did not rank is wrong.

    **The absence of a `not_tried` entry is not the claim.** The first version of this test
    asserted only that, and a build with no L6 at all produces the same absence - so it could
    not distinguish "the mechanical tier ran" from "this rung does not exist", which is
    exactly what the response was doing: `rungs` did not name L6 either, and the rung was
    claimed neither run nor not-tried. The positive half is what this asserts now.
    """
    box = paraphrase_mailbox()
    service = make_service(box)
    envelope = service.search(parse_search({"query": "postpone the launch"}))
    named = {entry.rung for entry in envelope.retrieval_report.not_tried}
    assert RungId.L6.value not in named, (
        "the mechanical tier ran and the response recorded L6 as not tried"
    )
    assert RungId.L6 in envelope.retrieval_report.rungs, (
        "the response's ordering is mailweave/mechanical-v1 and it does not name the rung "
        "that produced it"
    )


def test_the_ranking_orders_the_sources_it_is_given() -> None:
    """The ordering is visible on the wire, not computed and discarded.

    A thread the query's own participant operator names outranks one it does not, all else
    equal - which is `PARTICIPANT_MATCH` firing, and is the cheapest end-to-end evidence
    that `mechanical_rank`'s output reaches the layout.
    """
    box = SyntheticMailbox(
        messages=(
            Msg(
                id="r-1",
                thread_id="t-other",
                sender="zoe@team.example",
                subject="Rollout",
                body="rollout notes",
                internal_date_ms=epoch_ms(2026, 8, 1),
            ),
            Msg(
                id="r-2",
                thread_id="t-ana",
                sender="ana@team.example",
                subject="Rollout",
                body="rollout notes",
                internal_date_ms=epoch_ms(2026, 8, 2),
            ),
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    service = make_service(box)
    envelope = service.search(parse_search({"query": "rollout from:ana@team.example"}))
    assert [source.thread_id for source in envelope.sources][:1] == ["t-ana"]

    # **A ranking that returned nothing must change the answer, or this test is asserting
    # `hit_threads`' own order.** The first version caught an *inverted* ranking and not a
    # discarded one: `hit_threads` already put `t-ana` first and `mappable.sort` is stable, so
    # a `mechanical_rank` that returned an empty tuple left the order untouched and the test
    # green. This forces the two orders apart before checking which one the wire carries.
    import mailweave.retrieval.ranking as ranking_module

    original = ranking_module.mechanical_rank
    try:
        ranking_module.mechanical_rank = lambda candidates: tuple(reversed(original(candidates)))
        reversed_env = make_service(box).search(
            parse_search({"query": "rollout from:ana@team.example"})
        )
    finally:
        ranking_module.mechanical_rank = original
    assert [source.thread_id for source in reversed_env.sources][:1] == ["t-other"], (
        "reversing the ranking did not change the response, so the ordering the wire carries "
        "is not the ranking's"
    )


def test_a_messages_own_addresses_are_addresses_and_not_display_names() -> None:
    """`addresses_in_header` returns `(display name, address)`, and three call sites read it.

    **A regression test for a defect that shipped.** `_addresses_of` unpacked the pair
    backwards, so the E4 fill's `participant_match` - the highest-weighted component of the
    query-aware fill, ranked first in A.9(3) precisely because it is the most query-driven
    signal available - compared the query's addresses against display names, and against the
    empty string for every bare `bo@team.example`. It could fire only by coincidence. Found
    while writing LR's local re-check, which needs the same fact; the pool's row text and
    the re-check had copied the same mistake before this test existed.
    """
    from mailweave.freshness.recheck import _addresses as recheck_addresses
    from mailweave.gmail.models import Message
    from mailweave.retrieval.assemble import _addresses_of
    from mailweave.semantic.pool import pool_row_text

    message = Message.model_validate(
        {
            "id": "m-1",
            "threadId": "t-1",
            "snippet": "the cutover slipped",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Cutover"},
                    {"name": "From", "value": "Ana Lee <ana@team.example>"},
                    {"name": "To", "value": "bo@team.example"},
                ],
            },
        }
    )
    expected = {"ana@team.example", "bo@team.example"}
    assert _addresses_of(message) == expected
    assert recheck_addresses(message, ("From", "To", "Cc")) == expected
    text = pool_row_text(message, mode=PoolTextMode.SNIPPET)
    assert "ana@team.example" in text and "bo@team.example" in text
    assert "Ana Lee" not in text, "a display name reached the text stage A embeds"


def test_the_participant_component_can_now_decide_which_hit_keeps_its_body() -> None:
    """N-1's substantive half, reachable only now that `_addresses_of` returns addresses.

    A.9(3) ranks `participant_match` first because it is the most query-driven signal
    available: the message's own `From`/`To`/`Cc` against an address the *query named*. With
    the pair unpacked backwards it compared the query's address against display names and
    the empty string, so on an all-hit thread every hit tied at zero and thread position
    decided which body survived - which is the oldest-K policy EV-02's degenerate-strategy
    guard names, wearing the published policy's name. This asserts the component separates
    two hits that differ only in who they are from.
    """
    from mailweave.disclosure.plan import ThreadInput, hit_ranks
    from mailweave.disclosure.weights import QueryFacts

    order = ("m-1", "m-2")
    thread = ThreadInput(
        thread_id="t-1",
        rank=0,
        hit_bearing=True,
        order=order,
        positions={"m-1": 0, "m-2": 1},
        hit_ids=frozenset(order),
        parent_of=dict.fromkeys(order, None),
        children_of=dict.fromkeys(order, ()),
        subjects=dict.fromkeys(order, "Cutover"),
        internal_dates=dict.fromkeys(order, 1_767_700_800_000),
        addresses={
            "m-1": frozenset({"zoe@other.example"}),
            "m-2": frozenset({"ana@team.example"}),
        },
        coverage=dict.fromkeys(order, frozenset()),
    )
    ranks = hit_ranks(
        thread,
        QueryFacts(
            participants=frozenset({"ana@team.example"}), terms=frozenset(), has_date_window=False
        ),
    )
    assert ranks["m-2"] > ranks["m-1"], (
        "the two hits differ only in who they are from and the participant component did "
        "not separate them: the ladder is back to oldest-K"
    )


def test_two_responses_that_differ_only_in_which_tier_ordered_them_are_distinguishable() -> None:
    """AD D.5's cost disclosure, which is what makes D.7's score rule survivable.

    D.7 says a row Gmail's `q` selected carries no numeric score. On a mailbox where every
    disclosed row is a `q` match, that left two responses - one the cross-encoder had
    reordered and one it had not - byte-identical in their rows, opposite in their source
    order, and with nothing anywhere saying a model had been involved. A reader could not
    tell which tier decided the order, or that a second tier existed.

    `retrieval_report.semantic_cost` is that missing statement: `rerank_pairs` says a model
    looked at the candidates, `ordering_method` says whether it was allowed to order them,
    and `model` says which model, with no score on any row.
    """
    box = SyntheticMailbox(
        messages=tuple(
            Msg(
                id=f"c-{index}",
                thread_id=f"t-{index}",
                sender="ana@team.example",
                subject="Cutover",
                body="the cutover moved",
                internal_date_ms=epoch_ms(2026, 8, 1) + index * 86_400_000,
            )
            for index in range(3)
        ),
        now_ms=epoch_ms(2026, 9, 3),
    )
    arguments = {"query": "cutover", "force_rungs": ["semantic", "rerank"]}

    partial = make_service(
        box, registry=counting_registry()[0], profile=measured_profile(max_rerank_pairs=2)
    ).search(parse_search(arguments))
    whole = make_service(
        box, registry=counting_registry()[0], profile=measured_profile(max_rerank_pairs=3)
    ).search(parse_search(arguments))

    assert all(
        row.score is None for env in (partial, whole) for s in env.sources for row in s.messages
    ), "this fixture is meant to be all q-matched rows; with scores on them it proves nothing"
    partial_cost = partial.retrieval_report.semantic_cost
    whole_cost = whole.retrieval_report.semantic_cost
    assert partial_cost is not None and whole_cost is not None
    assert partial_cost.escalated is whole_cost.escalated is True
    assert partial_cost.rerank_pairs == 2 and whole_cost.rerank_pairs == 3
    assert partial_cost.ordering_method == "mailweave/mechanical-v1"
    assert whole_cost.ordering_method == "mailweave/mechanical-v1+cross-encoder"
    assert whole_cost.model is not None and "@" in whole_cost.model


def test_a_shortlist_without_a_cost_block_is_refused_by_the_wire() -> None:
    """Half a disclosure is what this validator exists to stop shipping."""
    from mailweave.envelope.vocab import Outcome, Sufficiency
    from mailweave.envelope.wire import Counters, PoolBlock, RetrievalReport, Shortlist

    with pytest.raises(ValueError, match="semantic_cost"):
        RetrievalReport(
            outcome=Outcome.INCONCLUSIVE,
            rungs=(RungId.L5,),
            hit_count_per_rung=(1,),
            pool=PoolBlock(scope_rule="r", thread_count=1, message_count=1, why="w"),
            shortlist=Shortlist(rule="top-k", k=25, size=1),
            sufficiency=Sufficiency.AMBIGUOUS,
            counters=Counters(http_requests=1, api_calls=1, quota_units=5),
        )
