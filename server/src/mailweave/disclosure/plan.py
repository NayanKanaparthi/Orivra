"""The disclosure planner: A.9's four tiers into a `Layout`, for either arm.

**Two arms, one planner, one ladder, one cost function.** RR DISC-02 requires the shipped
query-aware policy and the fixed ±2 baseline (Baseline F, EP §8.8) to be compared *at equal
token budget*, "asserted by the harness from measured tokens, not from configuration". The
only way to make that structurally true rather than carefully arranged is to give both arms
the same code path and let them differ in exactly one object: the `Selector` that decides
which non-evidence, non-floor rows are worth depth. Everything else - the E2 floor, the
A.9a ladder, the ceilings, the estimate - is shared.

So `Baseline F` is not a thing this module is arranged to beat. It is a `Selector` in this
module, runnable at any radius, under the same ceiling, and nothing in the query-aware arm
gets a token the baseline could not have. `E4_ADJACENCY_POSITIONS` is pinned to the
baseline's own radius for the same reason (see `weights.py`). **A thesis that cannot lose is
not a thesis.**

**What this module does not do.** It never fetches. It scores what the response already
holds, and where it wants text the run did not fetch it says so and mints an affordance
rather than reaching for the network - which keeps `generative_llm_calls = 0` trivially true
and keeps disclosure off the escalation path (T-CD3: reuse only, never trigger).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from mailweave.content.annotate import AnnotatedBody
from mailweave.content.reductions import Reduction
from mailweave.disclosure.floor import (
    FLOOR_BASE_DEPTH,
    FLOOR_PROMOTED_DEPTH,
    EvidenceFacts,
    FloorMember,
    MemberFacts,
    floor_of,
    floor_pairs_of,
)
from mailweave.disclosure.ladder import Ceilings, LadderStep, run_ladder
from mailweave.disclosure.layout import Band, Layout, PlannedRow, PlannedSource
from mailweave.disclosure.weights import (
    E4_ADJACENCY_POSITIONS,
    FillCandidate,
    FillScore,
    QueryFacts,
    a11_scores,
    rank,
)
from mailweave.envelope.grouping import GroupKey
from mailweave.envelope.measure import RESPONSE_STRUCTURAL_TOKENS, row_tokens
from mailweave.envelope.vocab import Depth, WithheldCap
from mailweave.envelope.wire import ThreadParticipant


@dataclass(frozen=True)
class ThreadInput:
    """One mapped thread, projected down to what disclosure reads about it.

    A projection rather than the `MappedThread` itself, for `StopInputs`' reason: a policy
    that can reach into the fetch result acquires dependencies the published policy does not
    have. Every field here is a fact of one `threads.get` and of the run that produced it.
    """

    thread_id: str
    rank: int
    hit_bearing: bool
    #: Chronological message ids (amendment A3). `positions[id]` is the index into it.
    order: tuple[str, ...]
    positions: Mapping[str, int]
    hit_ids: frozenset[str]
    parent_of: Mapping[str, str | None]
    children_of: Mapping[str, Sequence[str]]
    #: Where this thread stood in the order `max_hit_threads` cuts (2026-09-15, R-M2-095):
    #: the producer maps the first `max_hit_threads` plans in *that* order and the ranking
    #: reorders the mapped ones afterwards, so `rank` cannot say which threads a narrower
    #: width would still map. `None` for a thread outside the cut (an L4 sibling; an
    #: expansion's thread).
    mapped_at: int | None = None
    subjects: Mapping[str, str] = field(default_factory=dict)
    snippets: Mapping[str, str | None] = field(default_factory=dict)
    #: The annotated body of every message this run fetched a body for. Absent for the rest,
    #: which is a published cap (`max_body_fetches`, A.7) and not an oversight.
    bodies: Mapping[str, AnnotatedBody] = field(default_factory=dict)
    internal_dates: Mapping[str, int | None] = field(default_factory=dict)
    addresses: Mapping[str, frozenset[str]] = field(default_factory=dict)
    #: `{message id: its Authentication-Results header}`, for the messages whose observation
    #: carried one inside `MAX_AUTH_RECORD_CHARS`. The ladder charges the exact string the row
    #: will carry (INJ-05); a message absent from here will carry no record.
    auth_records: Mapping[str, str] = field(default_factory=dict)
    #: `{message id: (folded From address, display name)}` for the messages whose observation
    #: carried a `From` (2026-09-21), by `from_header_of`'s rule; the ladder charges both.
    from_headers: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    #: Which named constraints of the query each message satisfies. The input to the
    #: promotion rule's `CONSTRAINT_CARRIER` clause and to nothing else here.
    coverage: Mapping[str, frozenset[str]] = field(default_factory=dict)
    reductions: Mapping[str, tuple[Reduction, ...]] = field(default_factory=dict)
    inside_query_window: frozenset[str] = frozenset()
    #: This thread's whole address-keyed participant index, as the observation built it
    #: (round 26, R-DISC-032). The planner reads nothing out of it; it is carried onto the
    #: `PlannedSource` so the A.9a ladder can charge what the response will actually emit,
    #: which is `participants_within(this, the source's disclosed ids)`. Charging it nothing -
    #: which is what every round before this one did - left the ceiling blind to the field
    #: that was 82 % of the rendered response on a mailing-list thread.
    participants: tuple[ThreadParticipant, ...] = ()

    def observed_text(self, message_id: str) -> str | None:
        body = self.bodies.get(message_id)
        if body is not None:
            return body.view()
        return self.snippets.get(message_id)


class Selector(Protocol):
    """What decides which non-evidence, non-floor rows get depth.

    The **only** difference between the shipped arm and Baseline F, which is what makes
    DISC-02's equal-budget comparison a property of construction rather than of care.
    """

    @property
    def name(self) -> str:
        """The arm's name, as the experiment log records it."""

    def select(self, thread: ThreadInput, query: QueryFacts) -> Mapping[str, FillScore | int]:
        """Message id -> the score that admitted it. An empty mapping fills nothing."""


@dataclass(frozen=True)
class QueryAwareFill:
    """The shipped policy: A.9(3)'s E4 score with the published weights.

    A row is admitted when at least one published component fired. That threshold is the
    policy's own honesty: a row no component reached carries no query-specific reason, and
    DISC-01 requires every inclusion to carry one.
    """

    name: str = "query_aware_e4"

    def select(self, thread: ThreadInput, query: QueryFacts) -> Mapping[str, FillScore]:
        return {result.message_id: result for result in rank(_candidates(thread), query)}


@dataclass(frozen=True)
class FixedWindow:
    """Baseline F: the ±k window around every hit, as every prior system does it (SC §6).

    A permanent harness fixture (PROC-04), runnable here at the same ceiling and measured by
    the same estimate. It ignores `query` entirely, which is the point - it is what
    "conditioned on the query" is measured *against*, and DISC-01 says a fixed ±2 policy
    fails that criterion by construction.
    """

    radius: int = E4_ADJACENCY_POSITIONS
    name: str = "baseline_f_fixed_window"

    def select(self, thread: ThreadInput, query: QueryFacts) -> Mapping[str, int]:
        del query
        chosen: dict[str, int] = {}
        for hit in thread.hit_ids:
            anchor = thread.positions.get(hit)
            if anchor is None:
                continue
            for message_id, position in thread.positions.items():
                offset = position - anchor
                if message_id in thread.hit_ids or abs(offset) > self.radius:
                    continue
                if message_id not in chosen or abs(offset) < abs(chosen[message_id]):
                    chosen[message_id] = offset
        return chosen


def _candidate(
    thread: ThreadInput,
    message_id: str,
    *,
    hit_positions: Sequence[int],
    hit_dates: Sequence[int],
) -> FillCandidate:
    """One message of this thread, projected down to the facts the five predicates read."""
    position = thread.positions[message_id]
    stamp = thread.internal_dates.get(message_id)
    seconds: int | None = None
    if stamp is not None and hit_dates:
        seconds = min(abs(stamp - other) // 1000 for other in hit_dates)
    return FillCandidate(
        message_id=message_id,
        position=position,
        addresses=thread.addresses.get(message_id, frozenset()),
        subject=thread.subjects.get(message_id, ""),
        observed_text=thread.observed_text(message_id),
        internal_date_ms=stamp,
        positions_from_nearest_hit=(
            min(abs(position - other) for other in hit_positions) if hit_positions else None
        ),
        seconds_from_nearest_hit=seconds,
        inside_query_date_window=message_id in thread.inside_query_window,
    )


def _hit_anchors(thread: ThreadInput) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The positions and the dates of this thread's hits: what the two proximity facts measure."""
    hits = thread.hit_ids
    return (
        tuple(thread.positions[mid] for mid in hits if mid in thread.positions),
        tuple(stamp for mid in hits if (stamp := thread.internal_dates.get(mid)) is not None),
    )


def _candidates(thread: ThreadInput) -> tuple[FillCandidate, ...]:
    """Every **non-hit** message of this thread, as a fill candidate.

    A hit is excluded because a hit is not filled: it is evidence already, admitted by the
    retrieval ladder rather than by the disclosure policy, and scoring it here would let the
    fill spend budget on a row the response already holds at evidence depth. Floor members
    *are* candidates - `plan_thread` bands them FLOOR whatever this returns, so their
    membership is untouched, and a floor member the query also reached carries its reason
    like any other row. This docstring used to say the floor was excluded, which was false of
    the function's own `continue` (R-MCP-014's shape, found while fixing R-DISC-026).
    """
    hit_positions, hit_dates = _hit_anchors(thread)
    return tuple(
        _candidate(thread, message_id, hit_positions=hit_positions, hit_dates=hit_dates)
        for message_id in thread.order
        if message_id not in thread.hit_ids
    )


def hit_ranks(thread: ThreadInput, query: QueryFacts) -> Mapping[str, int]:
    """**What separates one hit from another, for A.9a steps 3 and 5** (R-DISC-026).

    A.9a step 3 protects the top *k* hit bodies, and `_degrade_band` takes depth from the
    worst first; both read `PlannedRow.fill_score`. Until round 25 every evidence row carried
    `fill_score = 0`, because the only producer of a score was the *fill* and the fill never
    scores hits. A uniform zero makes the tie-break the whole selection: which hits kept a
    body was `sorted(key=position)[:k]` - **oldest-k by thread position**, in both arms, for
    every query, while `DISCLOSURE_TOP_K_HITS` said it was decided by the published score.
    EV-02's degenerate-strategy guard names a fixed newest-K or oldest-K policy by
    construction, and this was one wearing the published policy's name.

    So the hits are scored, by the same five predicates and the same published weights as
    everything else, ranked **among themselves**: amendment A11's rule is computed over the
    hit pool, so a fact identical on every hit of the thread - the shared subject, a
    participant on every message, and both proximity facts, which are zero for a hit by
    definition - cannot decide which hit keeps its body. Where nothing separates the hits
    every value is 0 and thread position decides, exactly as before but now for a stated
    reason rather than by omission.

    **Both of A11's guards, not one** (round 26, R-DISC-034). Round 25 applied the
    discriminating-facts narrowing here and left out `rank`'s all-or-none sweep, so a
    component that survived the narrowing and then fired on *every* hit produced a uniform
    **nonzero** value - which looks like a score and is not one, because a tie on every hit
    makes `_top_k_hit_ids`' `(-fill_score, position)` tie-break the whole selection. That is
    oldest-K again, wearing the published policy's name, and it is what Gmail's `Re:` shape
    produced. `weights.a11_scores` is now the one place either guard lives, and `rank` reads
    the same function, so a third pool added later inherits both halves.

    **This is not the fill, and it is not selector-dependent.** It is computed here, from the
    query, for both arms. DISC-02 compares the arms at equal budget and they must differ in
    which rows the *fill* buys, not in which evidence bodies the ladder sacrifices; a baseline
    whose evidence degraded in a different order would be running a different ladder.
    """
    hit_positions, hit_dates = _hit_anchors(thread)
    pool = tuple(
        _candidate(thread, message_id, hit_positions=hit_positions, hit_dates=hit_dates)
        for message_id in thread.order
        if message_id in thread.hit_ids
    )
    return {result.message_id: result.anchored_value for _, result in a11_scores(pool, query)}


def floor_obligations(thread: ThreadInput) -> tuple[tuple[str, str], ...]:
    """Every `(evidence message, floor member)` pair A.9(2) creates for this thread.

    Derived from the reply tree the observation produced, not from `floor_of`'s output, so
    the ladder's gate is checked against A.9(2) rather than against the planner's own
    account of A.9(2) - which is the self-comparison R-DISC-021 found in round 23's floor
    tests and which is why the hole in `floor_of` was invisible to sixteen plants.
    """
    return floor_pairs_of(
        evidence_ids=thread.hit_ids,
        parent_of=thread.parent_of,
        children_of=thread.children_of,
        known_ids=thread.order,
    )


def floor_members(thread: ThreadInput) -> tuple[FloorMember, ...]:
    """This thread's E2 floor, with each member's dependence decided by the promotion rule."""
    return floor_of(
        evidence_ids=thread.hit_ids,
        order=thread.order,
        parent_of=thread.parent_of,
        children_of=thread.children_of,
        evidence={
            message_id: EvidenceFacts(
                message_id=message_id,
                body=thread.bodies.get(message_id),
                constraint_coverage=thread.coverage.get(message_id, frozenset()),
            )
            for message_id in thread.hit_ids
        },
        members={
            message_id: MemberFacts(
                message_id=message_id,
                observed_text=thread.observed_text(message_id),
                constraint_coverage=thread.coverage.get(message_id, frozenset()),
            )
            for message_id in thread.order
        },
    )


@dataclass(frozen=True)
class PlannedThread:
    """One thread's plan, before the ladder: the source plus the decisions behind it."""

    source: PlannedSource
    floor: tuple[FloorMember, ...]
    fill: Mapping[str, FillScore | int]


def depth_for(text: str | None, body: AnnotatedBody | None, wanted: Depth) -> Depth:
    """The deepest depth `wanted` that the text this response holds can actually support.

    A depth is a statement about text that exists (`PlannedRow.__post_init__`), so wanting
    `body_clean` for a message whose body was never fetched yields `snippet`, and wanting
    `snippet` where the observation carried none yields `stub`. Declared by falling back
    rather than by asserting, because the fallback is the honest answer and the row's own
    `unabridged` affordance is the path to the rest.

    `body_full` falls back the same way and for the same reason. A.9's tiers never plan one
    - `mailweave_get_messages(view="body_full")` is the only thing that asks - so the branch
    is inert for the planner and is here rather than in WS-15 because there must be exactly
    one answer in this system to "what depth can this text support" (round 24).
    """
    if wanted in _BODY_DEPTHS and body is not None:
        return wanted
    if wanted is not Depth.STUB and text is not None:
        return Depth.SNIPPET
    return Depth.STUB


#: The depths that need a fetched body behind them.
_BODY_DEPTHS: Final[frozenset[Depth]] = frozenset({Depth.BODY_CLEAN, Depth.BODY_FULL})


def plan_thread(
    thread: ThreadInput,
    *,
    query: QueryFacts,
    selector: Selector,
    evidence_view: Depth = Depth.BODY_CLEAN,
) -> PlannedThread:
    """A.9's four tiers for one thread, before any degradation.

    `evidence_view` is the depth an evidence row is *wanted* at, and it exists because AD
    D.1 gives `mailweave_search` a `view` argument (round 24). It defaults to A.9(1)'s own
    `body_clean` so nothing about the shipped policy changes, and it can only ever ask for
    a depth the text supports - `depth_for` still decides what is actually reachable, and a
    caller asking for less than A.9 would give gets less, which is the direction that
    cannot over-claim. It is deliberately **not** a way to ask for more: `body_full` is not
    a search view (D.1), so `mailweave_get_messages` remains the only route to it.
    """
    members = {member.message_id: member for member in floor_members(thread)}
    fill = selector.select(thread, query)
    # **The hits are scored too** (R-DISC-026). Not by the selector - see `hit_ranks` - so
    # that both arms sacrifice evidence depth in the same order and DISC-02's equal-budget
    # comparison stays a comparison of fills.
    hits = hit_ranks(thread, query)
    rows: list[PlannedRow] = []
    for message_id in thread.order:
        position = thread.positions[message_id]
        body = thread.bodies.get(message_id)
        snippet = thread.snippets.get(message_id)
        reductions = thread.reductions.get(message_id, ())
        text = thread.observed_text(message_id)
        if message_id in thread.hit_ids:
            band, wanted, ranked = Band.EVIDENCE, evidence_view, hits.get(message_id, 0)
        elif message_id in members:
            member = members[message_id]
            band = Band.FLOOR
            wanted = FLOOR_PROMOTED_DEPTH if member.promoted else FLOOR_BASE_DEPTH
            ranked = _score_of(fill, message_id)
        elif message_id in fill:
            band, wanted, ranked = Band.FILL, Depth.SNIPPET, _score_of(fill, message_id)
        else:
            band, wanted, ranked = Band.MAP, Depth.STUB, 0
        rows.append(
            PlannedRow(
                id=message_id,
                position=position,
                band=band,
                depth=depth_for(text, body, wanted),
                body=body.view() if body is not None else None,
                snippet=snippet,
                base_reductions=reductions,
                fill_score=ranked,
                auth_record=thread.auth_records.get(message_id, ""),
                from_address=thread.from_headers.get(message_id, ("", ""))[0],
                from_display=thread.from_headers.get(message_id, ("", ""))[1],
            )
        )
    return PlannedThread(
        source=PlannedSource(
            thread_id=thread.thread_id,
            rank=thread.rank,
            hit_bearing=thread.hit_bearing,
            rows=tuple(rows),
            participants=thread.participants,
            mapped_at=thread.mapped_at,
        ),
        floor=tuple(members.values()),
        fill=fill,
    )


def _score_of(fill: Mapping[str, FillScore | int], message_id: str) -> int:
    """The comparable score of one row, whichever arm produced it.

    Baseline F's selector returns a signed offset, which is not a score; its magnitude is
    inverted so that "nearer the hit" sorts the same way "scored higher" does. Without this
    the ladder would degrade the baseline's rows in the opposite order from the shipped
    arm's, and the two arms would no longer be running the same ladder.
    """
    value = fill.get(message_id)
    if value is None:
        return 0
    if isinstance(value, FillScore):
        # **The anchored score, not the published sum** (amendment A11). `fill_score` is what
        # the A.9a ladder degrades by and what step 3 protects by, so it is a *rank*, and a
        # rank may not be decided by query-independent components alone. Using `value.value`
        # here would put `POSITION_ADJACENCY` back in charge of which filled rows lose their
        # depth first, which is the same defect one layer down from `rank`.
        return value.anchored_value
    return max(0, E4_ADJACENCY_POSITIONS + 1 - abs(value))


@dataclass(frozen=True)
class Disclosure:
    """One planned, degraded response: what to emit and the account of how it got there."""

    layout: Layout
    steps: tuple[LadderStep, ...]
    threads: tuple[PlannedThread, ...]
    selector_name: str

    @property
    def tokens(self) -> int:
        return self.layout.cost()

    @property
    def self_truncated(self) -> bool:
        return bool(self.steps)


def disclose(
    threads: Sequence[ThreadInput],
    *,
    query: QueryFacts,
    selector: Selector,
    accounted_ids: frozenset[str],
    ceilings: Ceilings | None = None,
    evidence_view: Depth = Depth.BODY_CLEAN,
    not_included_before: int = 0,
    accounted_thread_id_chars: int = 0,
    grouped_ids: frozenset[str] = frozenset(),
    groups: frozenset[GroupKey] = frozenset(),
    foldable_caps: frozenset[WithheldCap] = frozenset(),
    request_echo_chars: int = 0,
    ranks: Mapping[str, int] | None = None,
    query_chars: int = 0,
    query_bearing_ids: frozenset[str] = frozenset(),
) -> Disclosure:
    """Plan every thread, then run A.9a's precedence over the whole response.

    The ladder runs over the *response*, not per thread, because the ceiling is per response:
    a per-thread ladder would let two threads each fit and the response not.

    `not_included_before` is how many `not_included_sources[]` entries the response already
    carries - threads that never became a layout source at all. The ladder charges that block,
    and it can only charge the number the envelope will emit if it is told the part it cannot
    see (round 26, R-DISC-032).
    """
    planned = tuple(
        plan_thread(thread, query=query, selector=selector, evidence_view=evidence_view)
        for thread in threads
    )
    floor_ids = frozenset(member.message_id for entry in planned for member in entry.floor)
    hit_ids = frozenset(mid for thread in threads for mid in thread.hit_ids)
    layout = Layout(
        sources=tuple(entry.source for entry in planned),
        accounted_ids=accounted_ids,
        floor_ids=floor_ids,
        hit_ids=hit_ids,
        floor_pairs=tuple(pair for thread in threads for pair in floor_obligations(thread)),
        not_included_before=not_included_before,
        accounted_thread_id_chars=accounted_thread_id_chars,
        # Round 29, R-MCP-033: the threads that will be accounted for a thread at a time,
        # known before the ladder runs. `_split_off` adds its own as it goes.
        grouped_ids=grouped_ids,
        groups=groups,
        foldable_caps=foldable_caps,
        request_echo_chars=request_echo_chars,
        ranks=() if ranks is None else tuple(sorted(ranks.items())),
        query_chars=query_chars,
        query_bearing_ids=query_bearing_ids,
        recommends_expansion=True,
    )
    degraded, steps = run_ladder(layout, ceilings=ceilings)
    return Disclosure(layout=degraded, steps=steps, threads=planned, selector_name=selector.name)


# -- DISC-04: context efficiency against a full dump ---------------------------------------


@dataclass(frozen=True)
class Efficiency:
    """DISC-04's two numbers, in the estimate's units, computed over the same payload.

    Both are **estimates**: DISC-04's pinned tokenizer is registered at G0, and this is the
    same whitespace count the ceiling is enforced with. Reported as a ratio and a fraction
    rather than as a verdict - the bar is `[INHERITED - EP §13.4 CG-PD]` and this module does
    not carry it, because a module that carried the bar would be a module that could be
    tuned to it.
    """

    disclosed_tokens: int
    full_dump_tokens: int
    relevant_tokens: int

    @property
    def fraction_of_full_dump(self) -> float:
        return self.disclosed_tokens / self.full_dump_tokens if self.full_dump_tokens else 0.0

    @property
    def relevant_token_fraction(self) -> float:
        return self.relevant_tokens / self.disclosed_tokens if self.disclosed_tokens else 0.0


def full_dump_tokens(threads: Sequence[ThreadInput]) -> int:
    """Baseline B: every message of every mapped thread at whatever depth this run holds.

    A message whose body was fetched counts its whole body; one that was not counts its
    snippet; one with neither counts a stub row. That is the honest dump for *this* run - it
    cannot count text nothing fetched - and it is the same treatment the disclosed side gets,
    so the ratio compares two selections of one corpus rather than two corpora.

    **Charged through `row_tokens`**, the same function the disclosed side is charged
    through (round 25). Before A11's structural rule the dump counted bare text while the
    response counted text plus structure, so DISC-04's ratio compared two different units
    and flattered the disclosed side by exactly the structure it was not charged for. A dump
    is a response too: every message in it would be a row.
    """
    total = RESPONSE_STRUCTURAL_TOKENS
    for thread in threads:
        for message_id in thread.order:
            total += row_tokens(thread.observed_text(message_id) or None)
    return total


def efficiency(disclosure: Disclosure, threads: Sequence[ThreadInput]) -> Efficiency:
    """What the response spent, against the dump, with the relevant share named."""
    relevant = 0
    for source in disclosure.layout.sources:
        for row in source.rows:
            if row.band in (Band.EVIDENCE, Band.FLOOR):
                relevant += row.cost()
    return Efficiency(
        disclosed_tokens=disclosure.tokens,
        full_dump_tokens=full_dump_tokens(threads),
        relevant_tokens=relevant,
    )
