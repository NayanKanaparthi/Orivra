"""A16: exhaustive accounting, separated from evidence protection, for D.5 step (c).

The owner's amendment, held at its boundaries. Every id an internal recency-pool probe
returns stays in `H`, keeps its disposition and is disclosed if its thread is mapped. What it
no longer gets, when **nothing else** reached it, is the A.9(1) evidence tier, A.9a step 3's
top-k protection and A.9(2)'s floor anchoring - and it no longer makes a thread a source on
its own, no longer counts as query evidence surviving, and no longer carries the recovery's
width.

Corpus-independent throughout: generated mailboxes and hand-built ledgers, no diagnostic case,
no expected evidence id, no corpus position.

The boundaries, each with its own test below:

  * a lexical match keeps its protection however many probes also returned it, **including
    when the probe listed it first** - the first-admission trap the owner named;
  * a shortlisted message is evidence whatever listed it;
  * D.5 step (b)'s participant probes are untouched;
  * a caller's own date query is not an internal recency probe;
  * a `threads.get` of a pool thread does not rescue a recency-only id (thread membership has
    never been a listing);
  * existing evidence keeps its parent/child obligations even when those members are also
    pool members;
  * a response carrying only unselected recency candidates does not claim evidence survived;
  * explicit reads are unchanged;
  * and every demoted id is still accounted for, which `certify` decides, not this file.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mailweave.disclosure.ladder import _carries_nothing, _top_k_hit_ids, run_ladder
from mailweave.disclosure.layout import Band
from mailweave.envelope.disposition import AdmissionRoute, DispositionLedger, ObservedEndpoint
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import Role
from mailweave.query.analysis import analyse
from mailweave.retrieval.assemble import (
    hit_threads,
    pool_listed_only,
    recency_probe_queries,
)
from mailweave.semantic.interface import BackendRegistry
from mailweave.semantic.pool import PoolStep, plan_pool
from mailweave.surface.arguments import parse_search
from tests.fixtures import envelope_kit as kit
from tests.fixtures.mailbox import Msg, SyntheticMailbox
from tests.test_semantic_rung import make_service, measured_profile

TERM = "plinth"
#: The step-(c) probe's shape. Built by `_recency_query`; the tests declare it rather than
#: matching on text, exactly as the product does.
RECENCY_Q = "after:1700000000"
PARTICIPANT_Q = "from:ana@team.example"


# --- the provenance the distinction rests on -------------------------------------------------


def _run_with(plan: Any) -> Any:
    """The one field `recency_probe_queries` reads, without building a whole `SemanticRun`."""
    return type("Run", (), {"plan": plan, "result": None})()


def _ledger_with(*observations: tuple[str, RungId, str]) -> DispositionLedger:
    """One ledger, with each `(message id, rung, query)` recorded as its own listing page,
    in the order given. The order is the point: it is what the first-admission origin fixes
    and what the routes must not be fooled by."""
    ledger = DispositionLedger()
    for message_id, rung, query in observations:
        ledger.record_list_page(
            kit.fetched((message_id,), thread_ids={message_id: "t1"}), rung=rung, query=query
        )
    return ledger


def test_a_route_is_recorded_for_every_observation_and_the_origin_still_is_not() -> None:
    """Both halves, because A16 needs the second and must not disturb the first."""
    ledger = _ledger_with(("m1", RungId.L5, RECENCY_Q), ("m1", RungId.L1B, TERM))
    assert ledger.routes["m1"] == frozenset(
        {
            AdmissionRoute(ObservedEndpoint.MESSAGES_LIST, RungId.L5, RECENCY_Q),
            AdmissionRoute(ObservedEndpoint.MESSAGES_LIST, RungId.L1B, TERM),
        }
    )
    # Unchanged: an id is admitted once and a second sighting does not move it.
    assert ledger.origins["m1"].rung is RungId.L5
    assert ledger.origins["m1"].query == RECENCY_Q


def test_a_lexical_match_the_recency_probe_listed_first_keeps_its_evidence_route() -> None:
    """**The first-admission trap.** Reading the origin would call this a recency-only id -
    the origin says L5, because the probe saw it first - and strip a lexical match of its
    protection on an accident of ordering. The rungs that run after the pool (L4's structural
    recovery, LR) make that ordering reachable, so this is held on the predicate directly."""
    ledger = _ledger_with(("m1", RungId.L5, RECENCY_Q), ("m1", RungId.L4, "rfc822msgid:<x>"))
    assert ledger.origins["m1"].rung is RungId.L5, "the fixture must exercise the trap"
    assert pool_listed_only(ledger, shortlisted=(), queries={RECENCY_Q}) == frozenset()


def test_a_recency_only_id_is_demoted_and_a_repeat_sighting_does_not_rescue_it() -> None:
    ledger = _ledger_with(
        ("m1", RungId.L5, RECENCY_Q), ("m1", RungId.L5, RECENCY_Q), ("m2", RungId.L1, TERM)
    )
    assert pool_listed_only(ledger, shortlisted=(), queries={RECENCY_Q}) == frozenset({"m1"})


def test_a_participant_probe_is_not_a_recency_probe_and_keeps_its_behaviour() -> None:
    """D.5 step (b) is outside this amendment. It stays out of A16's set, and stays in the
    set the row roles have always used, so a participant-probe row is `context` exactly as
    before and an evidence row exactly as before."""
    ledger = _ledger_with(("m1", RungId.L5, PARTICIPANT_Q), ("m2", RungId.L5, RECENCY_Q))
    assert pool_listed_only(ledger, shortlisted=(), queries={RECENCY_Q}) == frozenset({"m2"})
    # The role rule asks about pool listing in general and is unchanged by A16.
    assert pool_listed_only(ledger, shortlisted=()) == frozenset({"m1", "m2"})


def test_a_shortlisted_message_is_evidence_however_it_was_listed() -> None:
    ledger = _ledger_with(("m1", RungId.L5, RECENCY_Q), ("m2", RungId.L5, RECENCY_Q))
    ledger.record_shortlist(ids=["m1"], rule="top-k by stage-A cosine", k=3)
    assert pool_listed_only(ledger, shortlisted=ledger.shortlist_ids, queries={RECENCY_Q}) == (
        frozenset({"m2"})
    )


def test_reading_a_pool_thread_does_not_rescue_a_recency_only_id() -> None:
    """A `threads.get` is not a listing and has never made a row evidence: `hit_threads`
    reads `messages.list` alone. So an id the pool both listed and read is still pool-listed,
    and this is asserted rather than left to follow, because the pool reads most of what it
    lists and a rule that counted the read would reduce the amendment to nothing."""
    ledger = _ledger_with(("m1", RungId.L5, RECENCY_Q))
    ledger.record_thread(kit.observed_thread(("m1", "m9"), "t1"), rung=RungId.L5)
    assert "m9" in ledger.hit_ids, "the thread read must have admitted its rows"
    assert pool_listed_only(ledger, shortlisted=(), queries={RECENCY_Q}) == frozenset({"m1"})


def test_a_callers_own_date_query_is_not_an_internal_recency_probe() -> None:
    """`recency_probe_queries` reads the pool's plan, so what makes a query an internal probe
    is which probe sent it, never what the clause looks like. A caller searching `after:` is a
    lexical rung's query and keeps every protection it has."""
    now = datetime.now(UTC)
    plan = plan_pool(
        analyse(f"{TERM} after:2026/01/01", now=now),
        touched_threads=("t1",),
        profile=measured_profile(),
        now=now,
    )
    internal = recency_probe_queries(_run_with(plan))
    assert len(internal) == 1, "step (c) sends exactly one probe"
    caller = f"{TERM} after:1767225600"
    assert caller not in internal, internal
    ledger = _ledger_with(("m1", RungId.L1, caller))
    assert pool_listed_only(ledger, shortlisted=(), queries=internal) == frozenset(), (
        "a caller's own date-filtered search was read as an internal probe"
    )
    # **And the `queries` filter alone carries it, not the rung.** The row above is at a
    # lexical rung, so the `all(... is RungId.L5 ...)` half would decline the demotion even if
    # the query were never compared - which is how this assertion came to hold vacuously
    # (independent review, finding 5). The same query at L5 isolates the comparison.
    at_l5 = _ledger_with(("m1", RungId.L5, caller))
    assert pool_listed_only(at_l5, shortlisted=(), queries=internal) == frozenset(), (
        "the probe-query restriction is not being applied; every L5 listing is demoted"
    )
    assert pool_listed_only(at_l5, shortlisted=()) == frozenset({"m1"}), (
        "the fixture's row is not pool-listed at all, so the assertion above is vacuous"
    )


def test_the_probe_set_is_the_plans_step_c_probes_and_nothing_else() -> None:
    now = datetime.now(UTC)
    plan = plan_pool(
        analyse(f"{TERM} from:ana@team.example", now=now),
        touched_threads=("t1",),
        profile=measured_profile(),
        now=now,
    )
    steps = {probe.step for probe in plan.probes}
    assert PoolStep.PARTICIPANT in steps and PoolStep.RECENCY in steps, plan.probes
    internal = recency_probe_queries(_run_with(plan))
    assert internal == {probe.query for probe in plan.probes if probe.step is PoolStep.RECENCY}
    assert all(not q.startswith("from:") for q in internal)


def test_hit_threads_subtracts_the_demoted_and_adds_only_the_shortlist() -> None:
    """The tier is what the **query** selected: the listings minus the demoted, plus the
    shortlist. Both halves are asserted here because the first version of A16 shipped the
    subtraction alone and called that "narrows and widens nothing" - which was true of the
    function and false of the response (independent review, finding 1)."""
    ledger = _ledger_with(("m1", RungId.L1, TERM), ("m2", RungId.L5, RECENCY_Q))
    wide = {plan.thread_id: plan.hit_ids for plan in hit_threads(ledger)}
    narrow = {plan.thread_id: plan.hit_ids for plan in hit_threads(ledger, not_evidence={"m2"})}
    assert wide == {"t1": frozenset({"m1", "m2"})}
    assert narrow == {"t1": frozenset({"m1"})}
    for thread, ids in narrow.items():
        assert ids <= wide[thread]
    assert set(narrow) == set(wide), "a thread left the plan list and its ids lost their cap"


def test_hit_threads_gives_the_shortlist_the_tier_even_when_no_listing_reached_it() -> None:
    """A message the pool **read** rather than listed, and then selected.

    `m9` arrives by `threads.get` alone, so it has no `messages.list` origin and was never a
    hit; `m1` is the thread's only listing and is recency-only. Subtraction alone leaves the
    thread planned with an empty tier while the shortlist's own choice sits in it, which is
    what finding 1 demonstrated end to end. The union is asserted at the function because
    that is where it is decided; the served shape is asserted below.
    """
    ledger = _ledger_with(("m1", RungId.L5, RECENCY_Q))
    ledger.record_thread(kit.observed_thread(("m1", "m9"), "t1"), rung=RungId.L5)
    assert "m9" in ledger.hit_ids and "m9" not in {
        mid
        for mid, origin in ledger.origins.items()
        if origin.endpoint is ObservedEndpoint.MESSAGES_LIST
    }, "the fixture must reach m9 by a thread read alone"
    plans = {plan.thread_id: plan for plan in hit_threads(ledger, not_evidence={"m1"})}
    assert plans["t1"].hit_ids == frozenset(), "the fixture no longer empties the tier"
    with_shortlist = {
        plan.thread_id: plan for plan in hit_threads(ledger, not_evidence={"m1"}, selected={"m9"})
    }
    assert with_shortlist["t1"].hit_ids == frozenset({"m9"})
    # The listing set is what the source was *asked* about and does not move: a message the
    # pool only read is not one `messages.list` returned, so issue #296 still asks the same
    # question of the thread.
    assert with_shortlist["t1"].listed == frozenset({"m1"})


# --- the same boundaries through the shipped surface -------------------------------------------
#
# **The shortlist is made deterministic, and that is not a convenience.** The first version of
# this fixture let a bag-of-words backend choose, and it chose every message the assertions
# were about: sixteen of nineteen tests then passed with the amendment removed, because the
# ids they called "recency-only" were shortlisted and so were evidence either way. A marker
# word decides selection here, so a test that says "this id was not selected" is stating a
# fact about the fixture rather than hoping.


class _MarkedBackend:
    """Stage A as a switch: a row whose text carries `PICK` is selected, and nothing else is.

    The query embeds to `(1, 0)` and a marked row to `(1, 0)`, so its cosine is 1 and every
    other row's is 0. No weights, no network, and no claim about retrieval - this file
    measures a disclosure boundary.

    A high cosine is not by itself enough to decide selection. The shortlist is `top-k by
    cosine` with **no threshold** (`SHORTLIST_RULE`), so a `k` larger than the number of
    marked rows fills its remaining slots with zero-cosine rows - which is how the first
    fixture came to shortlist the very ids it called recency-only. `k` is therefore pinned
    to the marked count by `SHORTLIST_K` below, and `test_the_fixture_selects_what_it_says
    _it_selects` asserts the outcome rather than trusting the arithmetic.
    """

    model_id = "test/marked"
    model_revision = "0" * 40

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [
            (1.0, 0.0) if ("PICK" in text or text.strip() == TERM) else (0.0, 1.0) for text in texts
        ]

    def rerank(self, query: str, candidates: Sequence[str]) -> list[float]:
        return [float(len(candidate)) for candidate in candidates]


def _registry() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register("test/marked", _MarkedBackend, default=True)
    return registry


def _mixed_mailbox(*, participant_probe: bool = False) -> SyntheticMailbox:
    """One mapped thread carrying both kinds of message, and one thread carrying only the
    second kind. Every message is recent, so the step-(c) probe's ninety-day window returns
    all of them; only some carry the query's term, and only `PICK` rows are shortlisted.

    `t-evi`: m0 matches the query; m1 does not and is **not** marked, so it is recency-only;
    m2 matches **and replies to m1**, which makes m1 a floor member of an evidence message
    while being, by route, a recency-only candidate - the owner's "parent/child obligations
    remain intact even when those messages also belong to the pool". m3 is marked, so it is
    shortlisted and stays evidence however it was listed.

    `t-rec`: three recent unmarked messages, none matching. Nothing but the internal probe
    reaches them.
    """
    now = datetime.now(UTC)
    rows: list[Msg] = []

    def message(thread: str, index: int, body: str, *, parent: str | None = None) -> Msg:
        stamp = now - timedelta(days=2, minutes=60 - index)
        return Msg(
            id=f"{thread}-m{index}",
            thread_id=thread,
            sender="ana@team.example" if participant_probe else "bo@team.example",
            subject="cadence review" if index == 0 else "Re: cadence review",
            body=body,
            internal_date_ms=int(stamp.timestamp() * 1000),
            to=("cy@team.example",),
            in_reply_to=None if parent is None else f"<{parent}@mail.invalid>",
        )

    rows.append(message("t-evi", 0, f"{TERM} the agreed figure is 41"))
    rows.append(message("t-evi", 1, "a note about the depot roster", parent="t-evi-m0"))
    rows.append(message("t-evi", 2, f"{TERM} confirmed again", parent="t-evi-m1"))
    rows.append(message("t-evi", 3, "PICK the shortlist takes this one", parent="t-evi-m2"))
    for index in range(4, 6):
        rows.append(message("t-evi", index, f"more roster chatter {index}", parent="t-evi-m2"))
    for index in range(3):
        rows.append(message("t-rec", index, f"unrelated calendar note {index}"))
    return SyntheticMailbox(messages=tuple(rows), now_ms=int(now.timestamp() * 1000))


#: The ids `_mixed_mailbox` makes recency-only: listed by the step-(c) probe, matching no
#: term, carrying no marker, and so selected by nothing.
RECENCY_ONLY = frozenset({"t-evi-m1", "t-evi-m4", "t-evi-m5"})
#: The ids the query matches. A16 may not touch these.
LEXICAL = frozenset({"t-evi-m0", "t-evi-m2"})
#: Marked, and so shortlisted: evidence from the retriever whatever listed it.
SHORTLISTED = frozenset({"t-evi-m3"})
#: `k` for the shortlist, tied to the marked count so the two cannot drift apart. The
#: selection rule has no score floor, so any larger `k` would shortlist unmarked rows.
SHORTLIST_K = len(SHORTLISTED)


def _profile() -> Any:
    return measured_profile(max_rerank_pairs=SHORTLIST_K)


def _served(box: SyntheticMailbox, **request: Any) -> Any:
    service = make_service(box, registry=_registry(), profile=_profile())
    return service.search(parse_search({"query": TERM, "force_rungs": ["L5"], **request}))


def _rows_by_id(envelope: Any) -> dict[str, Any]:
    return {row.id: row for source in envelope.sources for row in source.messages}


class _Shortlist:
    """What the shortlist selected, captured from the rung rather than guessed at.

    The wire does not carry the selected ids - `pool_ids[]` is trace-only, by A.7a - and the
    tests need them to say "this id was not selected". Spying on the runner is how the
    diagnostic trace reads them too; it changes nothing and returns what it wrapped.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.retrieval.semantic as semantic_module

        self.ids: frozenset[str] = frozenset()
        original = semantic_module.SemanticRunner.run

        def spy(inner: Any, *args: Any, **kwargs: Any) -> Any:
            run = original(inner, *args, **kwargs)
            if run.result is not None:
                self.ids = frozenset(run.result.selected_ids)
            return run

        monkeypatch.setattr(semantic_module.SemanticRunner, "run", spy)


def test_the_fixture_selects_what_it_says_it_selects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every assertion below rests on this, so it is asserted rather than assumed: the pool
    runs, the marked row is shortlisted, and the ids called recency-only are selected by
    nothing. Without it the file repeats the vacuity its first version shipped with."""
    picked = _Shortlist(monkeypatch)
    envelope = _served(_mixed_mailbox())
    report = envelope.retrieval_report
    assert report.pool is not None and report.pool.message_count > 0
    assert picked.ids == SHORTLISTED, sorted(picked.ids)
    assert not (RECENCY_ONLY & picked.ids)
    assert not (LEXICAL & picked.ids)


class _Ledger:
    """The disposition ledger the run built, captured from the producer.

    Read rather than rebuilt: a test that re-derived "what did the probe list" from the
    mailbox would be asserting against its own model of the probe instead of against the run.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.retrieval.assemble as assemble

        self.ledger: Any = None
        original = assemble.hit_threads

        def spy(ledger: Any, **kwargs: Any) -> Any:
            self.ledger = ledger
            return original(ledger, **kwargs)

        monkeypatch.setattr(assemble, "hit_threads", spy)


class _CapturedLayout:
    """The layout A.9a finished with, which is where the evidence tier actually lives.

    The row `role` cannot stand in for it: the role rule (`pooled_only`) declines to call a
    pool row `matched` whether or not the id is in the evidence tier, so a test that asserts
    on roles passes either way - which is how this file's first version came to prove almost
    nothing. `layout.hit_ids` is the set every one of A16's surfaces reads: the bands, the
    floor's anchors, step 3's top-k, source eligibility, `_carries_nothing` and the width the
    recovery narrows.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mailweave.disclosure.plan as plan_module

        self.layout: Any = None
        # Read from where it is defined and patched where it is *called*: `plan` binds the
        # name at import, so patching `ladder` alone would leave the caller on the original.
        original = run_ladder

        def spy(layout: Any, **kwargs: Any) -> Any:
            finished, steps = original(layout, **kwargs)
            self.layout = finished
            return finished, steps

        monkeypatch.setattr(plan_module, "run_ladder", spy)


def _surfaces(layout: Any) -> dict[str, Any]:
    """The five places the owner named, read off one finished layout.

    Each is a real product field or a real product function called on the real layout -
    nothing here recomputes a rule. Reading them together is what lets the control below
    show, quantity by quantity, that each one moves when the separation is removed. A test
    that holds one of these steady is then holding something that could have moved.

      * `tier` - A.9(1)'s evidence set, which is also what planning, recovery width and
        `_carries_nothing` read;
      * `evidence_band` - where the row actually landed, which is what the bands degrade by;
      * `top_k` - A.9a step 3's protected head, by the product's own selection;
      * `anchors` - the evidence messages A.9(2) owes a floor to.

    **Source eligibility is deliberately not here.** A.9(5) is decided by
    `_split_off_unselected_pool_threads` on the admitting *rung* and the shortlist, not on the
    tier, and A16 does not change it; including it would have made the control below claim a
    surface moves when it does not (independent review, finding 2).
    """
    return {
        "tier": layout.hit_ids,
        "evidence_band": frozenset(
            row.id for source in layout.sources for row in source.rows if row.band is Band.EVIDENCE
        ),
        "top_k": _top_k_hit_ids(layout),
        "anchors": frozenset(anchor for anchor, _ in layout.floor_pairs),
    }


def _would_claim_evidence_survived(layout: Any, present: Collection[str]) -> bool:
    """Whether the ladder would ship a response whose surviving rows are exactly `present`,
    on the strength of that response still carrying evidence.

    `_carries_nothing` is the ladder's own gate and it is called here rather than restated:
    it reads `hit_ids & present_ids`, so what the response is *allowed to claim* is decided
    by which ids are in the tier. The layout is narrowed with `dataclasses.replace` and the
    product's own source rows; no field is invented and no rule is re-implemented.
    """
    kept = tuple(
        replace(source, rows=tuple(row for row in source.rows if row.id in present), runs=())
        for source in layout.sources
    )
    return not _carries_nothing(replace(layout, sources=kept))


def test_the_evidence_tier_excludes_the_probes_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """The amendment, on the set it is about."""
    captured = _CapturedLayout(monkeypatch)
    envelope = _served(_mixed_mailbox())
    assert captured.layout is not None
    hits = captured.layout.hit_ids
    assert hits >= LEXICAL, "a lexical match lost its place in the evidence tier"
    assert hits >= SHORTLISTED, "a shortlisted message lost its place in the evidence tier"
    assert not (RECENCY_ONLY & hits), sorted(RECENCY_ONLY & hits)
    # And they are still disclosed, which is the half the amendment must not touch.
    disclosed = {row.id for source in envelope.sources for row in source.messages}
    assert disclosed >= RECENCY_ONLY


def test_the_protected_top_k_is_chosen_from_evidence_and_not_from_the_probes_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A.9a step 3's protected head, by the product's own selection.

    Protection is scarce - `DISCLOSURE_TOP_K_HITS` rows keep their bodies while the rest
    head-truncate - and step 3 chooses it out of the evidence band by `(-fill_score,
    position)`. A pool row scores zero and tends to sit early, so before the separation the
    window did not merely join the tier: it **took protection from a shortlisted message**,
    which is the concrete harm behind the owner's "protected top-k status".
    """
    captured = _CapturedLayout(monkeypatch)
    _served(_mixed_mailbox())
    assert captured.layout is not None
    protected = _top_k_hit_ids(captured.layout)
    assert not (RECENCY_ONLY & protected), sorted(RECENCY_ONLY & protected)
    assert protected >= SHORTLISTED, (
        f"a shortlisted message lost protected top-k space: {sorted(protected)}"
    )


def test_a_recency_only_id_anchors_no_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """A.9(2)'s obligations are owed **by** evidence, and the amendment is about which
    messages are evidence. Asserted on `floor_pairs` rather than `floor_ids` because the
    pairs are what name the anchor; the flattened set cannot say whose floor a member is,
    and it is the anchoring the owner's "E2 anchor obligations" is about."""
    captured = _CapturedLayout(monkeypatch)
    _served(_mixed_mailbox())
    assert captured.layout is not None
    anchors = frozenset(anchor for anchor, _ in captured.layout.floor_pairs)
    assert not (RECENCY_ONLY & anchors), sorted(RECENCY_ONLY & anchors)
    assert anchors <= captured.layout.hit_ids, "a floor is owed by something that is not evidence"


def test_a_response_of_only_recency_candidates_does_not_claim_evidence_survived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner's sentence, on the ladder's own gate.

    `_carries_nothing` decides whether a response that lost rows still has an answer, by
    asking whether any evidence is still present. Before the separation an unselected
    recency candidate answered yes - so a response whose survivors were all pool rows shipped
    as though the query had found something. With it, the same response reaches the gate with
    no surviving evidence and the ladder declines instead of overclaiming.
    """
    captured = _CapturedLayout(monkeypatch)
    _served(_mixed_mailbox())
    assert captured.layout is not None
    assert not _would_claim_evidence_survived(captured.layout, RECENCY_ONLY)
    # ... and the same gate still ships a response that kept real evidence, so the check
    # above is not simply "this layout always declines".
    assert _would_claim_evidence_survived(captured.layout, LEXICAL | RECENCY_ONLY)


def _outside_the_window_mailbox() -> SyntheticMailbox:
    """A thread whose decisive message the step-(c) probe cannot have listed.

    `t-sel-m0` carries the marker and is **400 days old**, so the probe's default ninety-day
    window excludes it; `t-sel-m1` is recent and unmarked. The probe lists `m1` alone, the
    thread enters the pool, `threads.get` reads it whole and the pool embeds every row - so
    `m0` is shortlisted while having no `messages.list` observation at all.

    This shape was unreachable in this repository until the double learned to evaluate
    `after:<epoch>` (`tests/fixtures/mailbox.py`): the server writes its probe in epoch
    seconds, the double returned `None` for that form, and `None` means *match everything*.
    Every integration statement about the recency window was therefore made against a probe
    that selected the whole mailbox, which is why the first version of A16 could not find
    finding 1.
    """
    now = datetime.now(UTC)

    def message(index: int, body: str, *, days: int, parent: str | None) -> Msg:
        stamp = now - timedelta(days=days)
        return Msg(
            id=f"t-sel-m{index}",
            thread_id="t-sel",
            sender="bo@team.example",
            subject="cadence review" if index == 0 else "Re: cadence review",
            body=body,
            internal_date_ms=int(stamp.timestamp() * 1000),
            to=("cy@team.example",),
            in_reply_to=None if parent is None else f"<{parent}@mail.invalid>",
        )

    return SyntheticMailbox(
        messages=(
            message(0, "PICK the decisive one", days=400, parent=None),
            message(1, "a calendar note", days=2, parent="t-sel-m0"),
        ),
        now_ms=int(now.timestamp() * 1000),
    )


def test_the_probes_window_really_excludes_a_message_outside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The instrument, asserted before the test that depends on it.

    If the probe listed `t-sel-m0` after all, the test below would be about nothing. The
    listing is read off the ledger's routes rather than inferred.
    """
    captured = _Ledger(monkeypatch)
    _served(_outside_the_window_mailbox())
    assert captured.ledger is not None
    listed = {
        message_id
        for message_id, routes in captured.ledger.routes.items()
        if any(route.endpoint is ObservedEndpoint.MESSAGES_LIST for route in routes)
    }
    assert listed == {"t-sel-m1"}, sorted(listed)
    assert "t-sel-m0" in captured.ledger.hit_ids, "the pool never read the thread"


def test_a_shortlisted_message_the_probe_could_not_list_is_still_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Independent review, finding 1**, end to end.

    The shortlist's own choice is the thread's only evidence and it reached the response by a
    thread read. Subtracting the recency-only listing without adding the selection left the
    source in the response with an empty tier - `hit_bearing` false, `_carries_nothing` on its
    "there was never any evidence" branch, and step 7 free to drop the source carrying the
    answer.
    """
    captured = _CapturedLayout(monkeypatch)
    envelope = _served(_outside_the_window_mailbox())
    assert captured.layout is not None
    assert captured.layout.hit_ids == frozenset({"t-sel-m0"}), sorted(captured.layout.hit_ids)
    assert [source.hit_bearing for source in captured.layout.sources] == [True]
    assert _would_claim_evidence_survived(captured.layout, {"t-sel-m0"})
    assert not _would_claim_evidence_survived(captured.layout, {"t-sel-m1"})
    # Accounting, unchanged: both ids are in the response.
    assert {"t-sel-m0", "t-sel-m1"} <= set(_rows_by_id(envelope))


def test_without_the_union_the_shortlists_own_choice_leaves_the_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the test above, at the same place: drop `selected` and the tier empties."""
    import mailweave.retrieval.assemble as assemble

    captured = _CapturedLayout(monkeypatch)
    real = assemble.hit_threads
    monkeypatch.setattr(
        assemble,
        "hit_threads",
        lambda ledger, **kwargs: real(ledger, **{**kwargs, "selected": ()}),
    )
    _served(_outside_the_window_mailbox())
    assert captured.layout is not None
    assert captured.layout.hit_ids == frozenset(), sorted(captured.layout.hit_ids)
    assert [source.hit_bearing for source in captured.layout.sources] == [False], (
        "the fixture no longer empties the tier without the union, so the test above asserts "
        "nothing"
    )


def _without_the_separation(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the same request with A16 neutralised at the product, and return the layout.

    Neutralised at the call site's argument rather than by reverting a file, so the control
    and the tests above run the same code on the same fixture and differ in one value.
    """
    import mailweave.retrieval.assemble as assemble

    captured = _CapturedLayout(monkeypatch)
    real = assemble.hit_threads
    monkeypatch.setattr(
        assemble,
        "hit_threads",
        lambda ledger, **kwargs: real(ledger, **{**kwargs, "not_evidence": ()}),
    )
    _served(_mixed_mailbox())
    assert captured.layout is not None
    return captured.layout


def test_without_the_separation_every_surface_this_file_asserts_on_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The non-vacuity control, stated per surface rather than once.**

    The first version of this file asserted a boundary the fixture satisfied either way, and
    sixteen of its nineteen tests passed with the amendment removed. So the control does not
    say "something changed": it names each quantity the tests above hold, and fails if that
    quantity is the same with the separation and without it. A surface that stops moving here
    is a surface whose test above has quietly become an assertion about nothing.
    """
    without = _surfaces(_without_the_separation(monkeypatch))
    assert without["tier"] >= RECENCY_ONLY, (
        "the fixture does not put the probe's window in the evidence tier even without the "
        "separation, so every tier assertion in this file holds vacuously"
    )
    assert without["evidence_band"] >= RECENCY_ONLY, sorted(without["evidence_band"])
    assert without["top_k"] & RECENCY_ONLY, (
        f"a recency-only row does not take protected top-k space even without the "
        f"separation: {sorted(without['top_k'])}"
    )
    assert without["anchors"] & RECENCY_ONLY, sorted(without["anchors"])
    assert _would_claim_evidence_survived(_without_the_separation(monkeypatch), RECENCY_ONLY), (
        "a response of only recency candidates does not claim surviving evidence even "
        "without the separation"
    )


def test_a_recency_only_row_is_disclosed_and_is_not_matched() -> None:
    """The accounting half: **a guard, and it passes in the control on purpose.**

    Exhaustive accounting is what the amendment must *not* change, so this asserts an
    invariant that held before it and has to hold after. It is not evidence that A16 works -
    the control above names the surfaces that are - and it is kept because the likeliest way
    to implement the separation wrongly is to drop these ids out of the response instead of
    out of the tier, which is the failure the first attempt actually made.
    """
    rows = _rows_by_id(_served(_mixed_mailbox()))
    for message_id in sorted(RECENCY_ONLY):
        assert message_id in rows, f"{message_id} left the payload instead of being context"
        assert rows[message_id].role is not Role.MATCHED, message_id


def test_a_lexical_match_the_probe_also_returned_keeps_everything() -> None:
    """`t-evi-m0` and `t-evi-m2` match the query, are listed by the step-(c) probe as well,
    and are selected by no shortlist - so only the lexical route protects them."""
    rows = _rows_by_id(_served(_mixed_mailbox()))
    for message_id in sorted(LEXICAL):
        assert rows[message_id].role is Role.MATCHED, message_id


def test_the_floor_member_of_an_evidence_message_survives_being_a_pool_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`t-evi-m1` is the reply parent of `t-evi-m2`, which is evidence, and is itself
    recency-only. A16 takes away its power to *anchor* a floor; it does not take it out of
    the floor it belongs to."""
    captured = _CapturedLayout(monkeypatch)
    envelope = _served(_mixed_mailbox())
    assert captured.layout is not None
    assert "t-evi-m1" not in captured.layout.hit_ids, "the fixture no longer demotes the parent"
    assert ("t-evi-m2", "t-evi-m1") in captured.layout.floor_pairs, (
        "A.9(2) no longer owes the parent to its evidence child"
    )
    assert "t-evi-m1" in _rows_by_id(envelope), "a floor member left the response"


def test_a_thread_of_only_recency_candidates_is_not_a_source_and_its_ids_are_grouped() -> None:
    """A.9(5), and the disposition that must follow it: **a guard, and it passes in the
    control on purpose.**

    Source eligibility is decided by `_split_off_unselected_pool_threads` on the admitting
    rung and the shortlist - not on the evidence tier - so A16 neither changes it nor is
    tested by it. It is kept because a separation implemented by dropping threads out of
    `plans` would break exactly this, and the first attempt at A16 did (independent review,
    finding 2, which caught this test claiming more than it holds).

    The group is named and its count checked: a global "something was grouped" would pass
    against a response that dropped these ids entirely."""
    envelope = _served(_mixed_mailbox())
    assert "t-rec" not in {source.thread_id for source in envelope.sources}
    covered = {group.thread_id: group.message_count for group in envelope.withheld_groups}
    named = {record.id for record in envelope.withheld}
    assert covered.get("t-rec") == 3 or {f"t-rec-m{i}" for i in range(3)} <= named, (
        f"the three recency-only ids of an unmapped thread have no disposition: "
        f"groups={covered} named={sorted(named)}"
    )


def test_a_participant_probe_run_is_byte_identical_with_and_without_the_amendment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D.5 step (b) is outside this amendment, held end to end rather than only on the
    predicate. The query names a participant, so the pool sends a participant probe as well
    as the recency one, and the response must not move."""
    import mailweave.retrieval.assemble as assemble

    box = _mixed_mailbox(participant_probe=True)
    request = {"query": f"{TERM} from:ana@team.example", "force_rungs": ["L5"]}

    def run() -> Any:
        service = make_service(box, registry=_registry(), profile=_profile())
        return service.search(parse_search(request))

    def shape(envelope: Any) -> Any:
        return [
            (
                source.thread_id,
                [(row.id, row.role.value, row.depth.value) for row in source.messages],
            )
            for source in envelope.sources
        ]

    # **The row shape is not enough on its own** (independent review, finding 5): the role
    # rule declines to call a pool row `matched` whether or not it is in the tier, so this
    # comparison passed even against an implementation that demoted every participant-probe
    # id. The finished layout is compared as well, which is where the tier lives.
    captured = _CapturedLayout(monkeypatch)
    with_a16 = shape(run())
    surfaces_with = _surfaces(captured.layout)
    real = assemble.hit_threads
    monkeypatch.setattr(
        assemble,
        "hit_threads",
        lambda ledger, **kwargs: real(ledger, **{**kwargs, "not_evidence": ()}),
    )
    without = shape(run())
    assert with_a16 == without, "A16 moved a response whose pool sent a participant probe"
    assert surfaces_with == _surfaces(captured.layout), (
        "A16 moved the evidence tier, the protected top-k or the floor anchors of a response "
        "whose pool sent a participant probe"
    )
